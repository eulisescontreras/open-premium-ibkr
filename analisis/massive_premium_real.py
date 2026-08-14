# -*- coding: utf-8 -*-
"""DESCARGA EL PRECIO REAL de los contratos que el sistema OPERA, desde Massive.

Es la via para cerrar el gate: hoy el backtest de 511 sesiones usa premium SINTETICO
calibrado con 3 dias. Esto trae el precio REAL (agregados de 1 min, OPRA) de cada contrato
que el backtest compro, para poder recalcular el resultado sin inventar precios.

POR QUE SOLO LOS CONTRATOS OPERADOS: los flat files completos son ~12 GB y estan
BLOQUEADOS con el plan Options Basic ($0) -get_object devuelve 403-. La API si funciona,
pero a ~5 peticiones/minuto. Bajar solo lo que se opera son ~1.400 peticiones (~5 h) en vez
de millones.

LIMITES DEL PLAN, VERIFICADOS ejecutando la API el 2026-08-14:
  - ventana movil de 24 MESES: 2024-09-13 OK, 2024-08-09 -> HTTP 403.
    El backtest empieza el 2024-07-31, asi que las ~10 primeras sesiones NO son accesibles.
  - rate limit ~5 peticiones/minuto (HTTP 429 si se pasa).
  - los minute_aggs son OHLC de OPERACIONES EJECUTADAS, no bid/ask. El bid/ask real esta en
    quotes_v1, que pesa ~140 GB/dia y tambien esta bloqueado. O sea: esto quita el sesgo del
    PRECIO del contrato, pero el SPREAD sigue habiendo que modelarlo.

ES RESUMIBLE: guarda cada contrato en massive_premium.db y salta los ya descargados, asi que
se puede parar y continuar cuando se quiera.

Uso:
    set MASSIVE_KEY=...          (nunca se escribe en disco)
    python analisis/massive_premium_real.py plan        # solo calcula que hay que bajar
    python analisis/massive_premium_real.py bajar [minutos]
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "analisis"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "https://api.massive.com"
DB = os.path.join(RAIZ, "massive_premium.db")
PLAN = os.path.join(RAIZ, "massive_plan_contratos.json")
PAUSA = 12.5                      # ~4,8 peticiones/minuto, por debajo del limite
LIMITE_ANTIGUEDAD = "2024-08-15"  # ventana movil de 24 meses (verificado)


def esquema(c):
    c.execute("""CREATE TABLE IF NOT EXISTS aggs(
        ticker TEXT, fecha TEXT, ts INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL, vwap REAL,
        PRIMARY KEY(ticker, ts))""")
    c.execute("""CREATE TABLE IF NOT EXISTS hechos(
        ticker TEXT PRIMARY KEY, fecha TEXT, barras INTEGER, estado TEXT, cuando TEXT)""")
    c.commit()


def ticker_opra(fecha, strike, right):
    """O:SPY{YYMMDD}{C|P}{strike*1000, 8 digitos}. 0DTE: vencimiento = el mismo dia."""
    yy = fecha[2:4]; mm = fecha[5:7]; dd = fecha[8:10]
    return "O:SPY%s%s%s%s%08d" % (yy, mm, dd, right, int(round(float(strike) * 1000)))


def construir_plan():
    """Corre el backtest REAL y anota que contrato compro en cada sesion."""
    import backtest_st3_orb as B
    from synth_premium import calibra
    from simulador_st import simular
    print("calculando las operaciones del backtest (esto tarda unos minutos)...", flush=True)
    modelo = calibra(B.DIAS_CALIBRACION)
    plan = []
    for fk, bars, rth in B.sesiones():
        if fk < LIMITE_ANTIGUEDAD:
            continue                      # fuera de la ventana de 24 meses del plan
        dk = fk.replace("-", "")
        B.build_tmp(modelo, fk, dk, rth)
        sen = sorted(B.orb_senal(bars) + B.sen_principal(bars))
        if not sen:
            continue
        ops, _ = simular(fk, senales=sen, trail=99.0, db_velas=B.TMP, db_tape=None,
                         expiry=dk, mid=False, mag_umbral=None, size_cap=B.SIZE_CAP,
                         salir_en_flip=True, max_trades=B.MAX_TRADES)
        for o in ops:
            plan.append({"fecha": fk, "strike": o["strike"], "right": o["right"],
                         "ticker": ticker_opra(fk, o["strike"], o["right"]),
                         "entrada": o.get("entrada"), "salida": o.get("salida")})
    if os.path.exists(B.TMP):
        os.remove(B.TMP)
    # un contrato puede repetirse dentro del dia: se baja UNA vez
    unicos = {}
    for p in plan:
        unicos[p["ticker"]] = p
    plan = sorted(unicos.values(), key=lambda x: (x["fecha"], x["ticker"]))
    with open(PLAN, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1)
    return plan


def cargar_plan():
    if os.path.exists(PLAN):
        with open(PLAN, encoding="utf-8") as f:
            return json.load(f)
    return construir_plan()


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < 2:
                time.sleep(35)
                continue
            return None, "HTTP %d" % e.code
        except Exception as e:
            return None, str(e)[:50]
    return None, "429 persistente"


def bajar(minutos):
    K = os.environ.get("MASSIVE_KEY", "").strip()
    if len(K) < 20:
        print("falta MASSIVE_KEY"); return 1
    plan = cargar_plan()
    c = sqlite3.connect(DB)
    esquema(c)
    hechos = {r[0] for r in c.execute("select ticker from hechos")}
    pend = [p for p in plan if p["ticker"] not in hechos]
    # ORDEN: lo MAS RECIENTE primero. El año 2 (2025-08-01 .. 2026-08-13) es la RESERVA OOS
    # (+11.786$), que es el numero que de verdad vale, y ademas es el regimen mas parecido al
    # de ahora. Si la descarga se corta a medias, mejor tener entero el año que importa que la
    # mitad del año de entrenamiento. (Lo señalo el agente de investigacion; antes iba en orden
    # cronologico ascendente y gastaba las primeras horas en el año menos util.)
    pend.sort(key=lambda p: p["fecha"], reverse=True)
    print("=" * 74)
    print("contratos en el plan : %d" % len(plan))
    print("ya descargados       : %d" % len(hechos))
    print("PENDIENTES           : %d" % len(pend))
    print("ritmo                : 1 cada %.1f s  (~%.1f/min)" % (PAUSA, 60.0 / PAUSA))
    print("tiempo para el resto : %.1f h" % (len(pend) * PAUSA / 3600.0))
    if minutos:
        print("LIMITE DE ESTA TANDA : %d min  ->  ~%d contratos"
              % (minutos, int(minutos * 60 / PAUSA)))
    print("=" * 74, flush=True)
    t0 = time.time()
    ok = vacio = err = 0
    for i, p in enumerate(pend, 1):
        if minutos and (time.time() - t0) > minutos * 60:
            print("\n-- limite de tiempo alcanzado, parando (es resumible) --", flush=True)
            break
        t = p["ticker"]; f = p["fecha"]
        r, e = get("%s/v2/aggs/ticker/%s/range/1/minute/%s/%s?adjusted=true&sort=asc"
                   "&limit=50000&apiKey=%s" % (BASE, t, f, f, K))
        if e:
            c.execute("insert or replace into hechos values(?,?,?,?,datetime('now'))",
                      (t, f, 0, e))
            err += 1
        else:
            res = r.get("results") or []
            c.executemany("insert or replace into aggs values(?,?,?,?,?,?,?,?,?)",
                          [(t, f, b.get("t"), b.get("o"), b.get("h"), b.get("l"),
                            b.get("c"), b.get("v"), b.get("vw")) for b in res])
            c.execute("insert or replace into hechos values(?,?,?,?,datetime('now'))",
                      (t, f, len(res), "OK" if res else "VACIO"))
            if res:
                ok += 1
            else:
                vacio += 1
        c.commit()
        if i % 10 == 0 or i == 1:
            tr = time.time() - t0
            print("  [%4d/%4d] %s %s | ok=%d vacio=%d err=%d | %.1f min"
                  % (i, len(pend), f, t, ok, vacio, err, tr / 60.0), flush=True)
        time.sleep(PAUSA)
    n = c.execute("select count(*) from aggs").fetchone()[0]
    d = c.execute("select count(distinct ticker) from aggs").fetchone()[0]
    c.close()
    print("\n" + "=" * 74)
    print("TANDA TERMINADA: ok=%d vacio=%d err=%d  |  %.1f min" % (ok, vacio, err,
                                                                   (time.time() - t0) / 60.0))
    print("BD %s: %d barras de %d contratos" % (os.path.basename(DB), n, d))
    print("Reanudar con:  python analisis/massive_premium_real.py bajar [minutos]")
    return 0


def estado():
    """Que hay descargado y que falta. NO descarga nada ni toca la API.
    OJO: `bajar 0` NO sirve para esto: con minutos=0 la guarda `if minutos` es falsa y el
    script baja el plan ENTERO (4,4 h). Por eso existe este modo aparte."""
    plan = cargar_plan()
    if not os.path.exists(DB):
        print("todavia no hay massive_premium.db: 0 de %d contratos" % len(plan))
        return 0
    c = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    hechos = {r[0] for r in c.execute("select ticker from hechos")}
    pend = [p for p in plan if p["ticker"] not in hechos]
    print("=" * 70)
    print("ESTADO DE LA DESCARGA")
    print("=" * 70)
    print("  contratos en el plan : %d" % len(plan))
    print("  ya descargados       : %d  (%.0f%%)" % (len(hechos), 100.0 * len(hechos) / len(plan)))
    print("  PENDIENTES           : %d  -> %.1f h a %.1f/min"
          % (len(pend), len(pend) * PAUSA / 3600.0, 60.0 / PAUSA))
    for e, k in c.execute("select estado,count(*) from hechos group by estado order by 2 desc"):
        print("    %-8s %d" % (e, k))
    n = c.execute("select count(*) from aggs").fetchone()[0]
    print("  barras de 1 min      : %d" % n)
    r = c.execute("select min(fecha),max(fecha) from hechos").fetchone()
    print("  periodo cubierto     : %s .. %s" % r)
    nr = c.execute("select count(distinct fecha) from hechos where fecha>='2025-08-01'"
                   ).fetchone()[0]
    print("  sesiones del AÑO DE RESERVA (2025-08-01+): %d" % nr)
    if pend:
        pend.sort(key=lambda p: p["fecha"], reverse=True)
        print("\n  lo siguiente que bajaria: %s %s" % (pend[0]["fecha"], pend[0]["ticker"]))
        print("  lo mas antiguo pendiente: %s %s" % (pend[-1]["fecha"], pend[-1]["ticker"]))
        print("\n  continuar con:  python analisis/massive_premium_real.py bajar [minutos]")
        print("  (retoma donde quedo; nunca repite un contrato ya descargado)")
    else:
        print("\n  COMPLETO: no queda nada pendiente")
    c.close()
    return 0


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if modo == "estado":
        return estado()
    if modo == "plan":
        plan = construir_plan()
        print("contratos a descargar: %d" % len(plan))
        if plan:
            print("  primero: %s  %s" % (plan[0]["fecha"], plan[0]["ticker"]))
            print("  ultimo : %s  %s" % (plan[-1]["fecha"], plan[-1]["ticker"]))
            print("  tiempo estimado: %.1f h a %.1f/min" % (len(plan) * PAUSA / 3600.0,
                                                            60.0 / PAUSA))
        return 0
    if modo == "bajar":
        mins = float(sys.argv[2]) if len(sys.argv) > 2 else 0
        return bajar(mins)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
