# -*- coding: utf-8 -*-
"""EL GATE, con premium REAL de Massive: ¿cuanto valen los +25.769$ con precios que existieron?

Construye una BD `premium_minute` a partir de los agregados REALES de 1 min de Massive y se la
pasa a `simular()` como db_velas, igual que hace el backtest con la sintetica. Asi se reutiliza
el motor real (R3/R9) y lo UNICO que cambia entre las dos corridas es la fuente de precios.

EL PROBLEMA DE LOS HUECOS Y COMO SE TRATA (decidido con el agente de investigacion):
los minute_aggs solo traen minutos con operaciones. Medido: el 5,7% de las ENTRADAS y el 14,3%
de las SALIDAS caen en un minuto sin barra, y NO es aleatorio: las salidas que faltan se
concentran en 15:59 (el aplanado de cierre) y en el valle de mediodia. Como la eleccion de que
hacer con ellas puede mover el resultado, se publican TRES variantes y ademas el subconjunto
limpio:

  A) intrinseco desde las 15:55 + barra previa hasta 3 min + descartar y CONTAR el resto
  B) descartar TODA operacion con hueco en cualquiera de los dos extremos
  C) barra previa hasta 5 min, sin intrinseco
  LIMPIO) solo las operaciones con barra REAL en los dos extremos -> no depende de ninguna
          regla de imputacion. Si aqui el real se parece al sintetico, la respuesta esta dada
          sin discutir de huecos.

POR QUE EL INTRINSECO NO ES UN APAÑO: a las 15:59 un 0DTE esta a un minuto de expirar, su
extrinseco es ~0 y el sistema sale ITM (profundidad mediana 4,11 en ganadoras, 1,59 en
perdedoras), donde el intrinseco domina. Ademas SUBESTIMA el precio de venta, o sea perjudica
al sistema: es el sesgo que uno quiere cuando valida algo propio.

El bid/ask se reconstruye como close*0.99 / close*1.01, el mismo 2% que aplica build_tmp.
Esta VERIFICADO que es correcto: el precio ejecutado cae en el MID (mediana 0,500 sobre 2.503
pares contra bid/ask reales), asi que el agregado NO lleva el spread dentro.

Uso:  python analisis/gate_premium_real.py [desde_fecha]
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "analisis"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import backtest_st3_orb as B
from synth_premium import calibra
from simulador_st import simular, CAPITAL_0

ET = ZoneInfo("America/New_York")
MDB = os.path.join(RAIZ, "massive_premium.db")
TMP_REAL = os.path.join(RAIZ, "_tmp_premium_real.db")
HORA_INTRINSECO = "15:55"

VARIANTES = {
    "A": dict(intrinseco=True, ventana=3),
    "B": dict(intrinseco=False, ventana=0),      # 0 = sin fallback: o hay barra, o se descarta
    "C": dict(intrinseco=False, ventana=5),
}


def ro(p):
    return sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True, timeout=30)


def hora_et(ms):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone(ET).strftime("%H:%M")


def mm(h):
    return int(h[:2]) * 60 + int(h[3:5])


def barras_massive(fk):
    """{(right, strike): {hora: close}} de los contratos de ese dia que hay descargados."""
    if not os.path.exists(MDB):
        return {}
    c = ro(MDB)
    out = {}
    for t, in c.execute("select ticker from hechos where fecha=? and estado='OK'", (fk,)):
        right = t[11]
        strike = int(t[12:]) / 1000.0
        serie = {}
        for ts, cl in c.execute("select ts,close from aggs where ticker=? and close is not null",
                                (t,)):
            serie[hora_et(ts)] = cl
        if serie:
            out[(right, strike)] = serie
    c.close()
    return out


def construir_bd(fk, rth, datos, cfg):
    """premium_minute REAL para simular(). Devuelve (ruta, imputadas, intrinsecos)."""
    spy = {h: cl for h, o, hi, lo, cl in rth}
    if os.path.exists(TMP_REAL):
        os.remove(TMP_REAL)
    d = sqlite3.connect(TMP_REAL)
    d.execute("CREATE TABLE bars_minute (fecha TEXT,hora TEXT,open REAL,high REAL,low REAL,"
              "close REAL,volume REAL)")
    d.executemany("insert into bars_minute values (?,?,?,?,?,?,0)",
                  [(fk, h, o, hi, lo, cl) for h, o, hi, lo, cl in rth])
    d.execute("CREATE TABLE premium_minute (fecha TEXT,hora TEXT,expiry TEXT,strike REAL,"
              "right TEXT,bid REAL,ask REAL)")
    dk = fk.replace("-", "")
    filas = []
    imput = intr_n = 0
    for (right, strike), serie in datos.items():
        for h in sorted(spy):
            px = serie.get(h)
            if px is None and cfg["intrinseco"] and h >= HORA_INTRINSECO:
                s = spy[h]
                px = max(0.0, s - strike) if right == "C" else max(0.0, strike - s)
                px = max(px, 0.01)
                intr_n += 1
            if px is None and cfg["ventana"]:
                m0 = mm(h)
                for k in range(1, cfg["ventana"] + 1):
                    prev = "%02d:%02d" % divmod(m0 - k, 60)
                    if prev in serie:
                        px = serie[prev]
                        imput += 1
                        break
            if px is None:
                continue
            filas.append((fk, h, dk, float(strike), right, px * 0.99, px * 1.01))
    d.executemany("insert into premium_minute values (?,?,?,?,?,?,?)", filas)
    d.commit()
    d.close()
    return TMP_REAL, imput, intr_n


def main():
    desde = sys.argv[1] if len(sys.argv) > 1 else "2025-08-01"
    if not os.path.exists(MDB):
        print("no existe massive_premium.db"); return 1

    c = ro(MDB)
    dias_ok = sorted({r[0] for r in c.execute(
        "select distinct fecha from hechos where estado='OK' and fecha>=?", (desde,))})
    c.close()
    if not dias_ok:
        print("todavia no hay dias descargados desde %s" % desde); return 0

    print("=" * 88)
    print("GATE CON PREMIUM REAL  ·  %d sesiones descargadas desde %s" % (len(dias_ok), desde))
    print("=" * 88)

    modelo = calibra(B.DIAS_CALIBRACION)
    ses = {fk: (bars, rth) for fk, bars, rth in B.sesiones() if fk in dias_ok}
    print("  sesiones utilizables (con barras del SPY): %d" % len(ses))
    if not ses:
        return 0

    res = {}
    for etq in ("A", "B", "C"):
        cfg = VARIANTES[etq]
        tot_s = tot_r = 0.0
        n_ops = imp = ints = 0
        for fk in sorted(ses):
            bars, rth = ses[fk]
            datos = barras_massive(fk)
            if not datos:
                continue
            dk = fk.replace("-", "")
            sen = sorted(B.orb_senal(bars) + B.sen_principal(bars))
            if not sen:
                continue
            # sintetico (referencia)
            B.build_tmp(modelo, fk, dk, rth)
            ops_s, cap_s = simular(fk, senales=sen, trail=99.0, db_velas=B.TMP, db_tape=None,
                                   expiry=dk, mid=False, mag_umbral=None, size_cap=B.SIZE_CAP,
                                   salir_en_flip=True, max_trades=B.MAX_TRADES)
            # real
            ruta, i1, i2 = construir_bd(fk, rth, datos, cfg)
            ops_r, cap_r = simular(fk, senales=sen, trail=99.0, db_velas=ruta, db_tape=None,
                                   expiry=dk, mid=False, mag_umbral=None, size_cap=B.SIZE_CAP,
                                   salir_en_flip=True, max_trades=B.MAX_TRADES)
            tot_s += cap_s - CAPITAL_0
            tot_r += cap_r - CAPITAL_0
            n_ops += len(ops_r)
            imp += i1
            ints += i2
        res[etq] = (tot_s, tot_r, n_ops, imp, ints)

    print("\n  %-6s %12s %12s %12s %7s %10s %10s"
          % ("var", "SINTETICO", "REAL", "diferencia", "ops", "imputados", "intrinsec"))
    print("  " + "-" * 78)
    et = {"A": "A intr+3m", "B": "B descarta", "C": "C prev 5m"}
    for k in ("A", "B", "C"):
        s, r, n, i, x = res[k]
        print("  %-10s %+11.2f$ %+11.2f$ %+11.2f$ %7d %10d %10d"
              % (et[k], s, r, r - s, n, i, x))

    # --- SUBCONJUNTO LIMPIO: sesiones SIN ningun hueco en los extremos de sus operaciones.
    # No depende de ninguna regla de imputacion, asi que es el dato mas solido que hay.
    print("\n" + "=" * 88)
    print("SUBCONJUNTO LIMPIO (sesiones sin ningun hueco en entradas ni salidas)")
    print("=" * 88)
    lim_s = lim_r = 0.0
    n_lim = n_ops_lim = 0
    con_hueco = []
    for fk in sorted(ses):
        bars, rth = ses[fk]
        datos = barras_massive(fk)
        if not datos:
            continue
        dk = fk.replace("-", "")
        sen = sorted(B.orb_senal(bars) + B.sen_principal(bars))
        if not sen:
            continue
        B.build_tmp(modelo, fk, dk, rth)
        ops_s, cap_s = simular(fk, senales=sen, trail=99.0, db_velas=B.TMP, db_tape=None,
                               expiry=dk, mid=False, mag_umbral=None, size_cap=B.SIZE_CAP,
                               salir_en_flip=True, max_trades=B.MAX_TRADES)
        # ¿alguna operacion de esta sesion tiene hueco en un extremo?
        hueco = 0
        for o in ops_s:
            serie = datos.get((o["right"], float(o["strike"])), {})
            for h in (str(o.get("entrada"))[:5], str(o.get("salida"))[:5]):
                if h and h not in serie:
                    hueco += 1
        if hueco:
            con_hueco.append((fk, hueco, len(ops_s), cap_s - CAPITAL_0))
            continue
        ruta, _, _ = construir_bd(fk, rth, datos, VARIANTES["A"])
        ops_r, cap_r = simular(fk, senales=sen, trail=99.0, db_velas=ruta, db_tape=None,
                               expiry=dk, mid=False, mag_umbral=None, size_cap=B.SIZE_CAP,
                               salir_en_flip=True, max_trades=B.MAX_TRADES)
        lim_s += cap_s - CAPITAL_0
        lim_r += cap_r - CAPITAL_0
        n_lim += 1
        n_ops_lim += len(ops_r)
    if n_lim:
        print("  sesiones limpias: %d de %d  |  operaciones: %d" % (n_lim, len(ses), n_ops_lim))
        print("  SINTETICO %+.2f$   REAL %+.2f$   diferencia %+.2f$" % (lim_s, lim_r, lim_r - lim_s))
        if lim_s:
            print("  el real es el %.0f%% del sintetico" % (100.0 * lim_r / lim_s))
        print("  -> Este numero NO depende de ninguna regla de imputacion.")
    else:
        print("  ninguna sesion esta libre de huecos")

    # --- ¿los huecos se concentran en pocos dias o se reparten? ---
    print("\n" + "=" * 88)
    print("¿SE CONCENTRAN LOS HUECOS? (si eliminan un TIPO de dia, el descarte no es neutral)")
    print("=" * 88)
    if con_hueco:
        con_hueco.sort(key=lambda x: -x[1])
        print("  sesiones con hueco: %d de %d (%.0f%%)"
              % (len(con_hueco), len(ses), 100.0 * len(con_hueco) / len(ses)))
        pos = sum(1 for _, _, _, p in con_hueco if p > 0)
        print("  de esas, %d cerraron en POSITIVO y %d en negativo (sinteticamente)"
              % (pos, len(con_hueco) - pos))
        pnl_h = sum(p for _, _, _, p in con_hueco)
        print("  P&L sintetico de las sesiones con hueco: %+.2f$ (del total %+.2f$)"
              % (pnl_h, res["A"][0]))
        print("\n  las 6 con mas huecos:")
        for fk, h, n, p in con_hueco[:6]:
            print("    %s  %d huecos en %d ops  |  P&L sintetico %+8.2f$" % (fk, h, n, p))
    else:
        print("  ninguna sesion tiene huecos")

    print("\n" + "=" * 88)
    print("LECTURA")
    print("=" * 88)
    difs = [res[k][1] - res[k][0] for k in ("A", "B", "C")]
    print("  diferencia real-sintetico segun variante: %s"
          % ", ".join("%+.0f$" % d for d in difs))
    if max(difs) - min(difs) < 0.15 * max(1.0, abs(sum(difs) / 3)):
        print("  -> Las tres variantes coinciden: la regla de imputacion NO decide el resultado.")
    else:
        print("  -> Las variantes DIFIEREN: el resultado depende de una convencion y hay que")
        print("     publicarlo asi, no elegir la mas favorable.")
    if os.path.exists(TMP_REAL):
        os.remove(TMP_REAL)
    if os.path.exists(B.TMP):
        os.remove(B.TMP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
