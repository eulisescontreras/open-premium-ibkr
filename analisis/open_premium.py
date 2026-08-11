"""
open_premium.py — READ-ONLY

EL OPEN PREMIUM, tal como lo definio el usuario:

  1. Por CADA strike y CADA lado (C y P):  neto = SUMA(compras) - SUMA(ventas), en $.
     Ejemplo suyo: en el 500C dos compras de 200$ y 300$ y una venta de 350$ -> +150$.
     NO es el bruto: el bruto mezcla compras y ventas y no dice cuanto dinero hay
     realmente puesto en ese strike.
  2. Se suman TODOS los strikes del lado CALL en una columna y TODOS los del lado PUT
     en otra. Ejemplo suyo: 500P=50.000 + 600P=20.000 -> PUT 70.000;
     500C=20.000 + 600C=30.000 -> CALL 50.000.
  3. Solo ATM e ITM, que es lo que el sistema sigue (call strike<=spot, put strike>=spot).
  4. Al lado: precio del SPY, el TA y el GEX, para ver como se movieron.

FUENTE: `premium_minute.net_prem`, que es el neto FIRMADO por strike (agresor bid/ask).
Se usa el DELTA contra la lectura anterior de ese mismo strike, porque la columna guarda
el acumulado del dia (`_on_ticks:1458` la suma sobre si misma).

⚠️ CADENCIA: `net_prem` lo escribe `_persist_walls` cada 3 minutos, no cada minuto. Y el
GEX se escribe en la MISMA pasada -> ambas columnas estan perfectamente alineadas
(verificado: 139/139 horas el 08-10 y 128/128 el 08-11). Cada fila es, por tanto, el
flujo NETO de un intervalo de ~3 minutos, no de 1.

⚠️ EL AGRESOR ES UNA INFERENCIA: en toda opcion negociada hay comprador Y vendedor. Se
clasifica quien CRUZO EL SPREAD (last>=ask compra, last<=bid venta). Lo que se cruza
dentro del spread no se puede atribuir y NO entra en el neto: por eso el neto es menor
que el bruto, y por eso hay una parte del mercado que este numero no ve.

Uso:
    python analisis\open_premium.py                # ultima fecha
    python analisis\open_premium.py 2026-08-10
"""
import os
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "spy_history.db")


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    F, horas, por_hora, walls, ta, arranques = _cargar(argv[0] if argv else None)
    _pintar(F, horas, por_hora, walls, ta, arranques)


def _cargar(F=None):
    """Carga y agrega. Separado para que el analisis predictivo use EXACTAMENTE
    los mismos numeros que la tabla, y no una segunda version que pueda divergir."""
    db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    c = db.cursor()
    fechas = [x[0] for x in c.execute(
        "SELECT DISTINCT fecha FROM premium_minute ORDER BY fecha").fetchall()]
    F = F or fechas[-1]
    if F not in fechas:
        print("Sin datos para %s. Hay: %s" % (F, ", ".join(fechas)))
        sys.exit(2)
    EXP = F.replace("-", "")

    filas = c.execute(
        "SELECT hora, strike, right, net_prem FROM premium_minute "
        "WHERE fecha=? AND expiry=? AND net_prem IS NOT NULL ORDER BY hora",
        (F, EXP)).fetchall()
    walls = {x[0]: x[1:] for x in c.execute(
        "SELECT hora, spot, gex_total, regime, spot_stale FROM walls_snapshot "
        "WHERE fecha=?", (F,)).fetchall()}
    TA = ["rsi", "ta_score", "ta_dir", "macd_hist", "atr_pct", "vwap", "obv_trend"]
    ta = {}
    for r in c.execute("SELECT hora,%s FROM ta_minute WHERE fecha=?"
                       % ",".join(TA), (F,)).fetchall():
        ta[r[0]] = dict(zip(TA, r[1:]))
    # REINICIOS: al relanzar, `_load_intradia` repone net_prem desde la BD y el delta
    # contra la lectura anterior deja de ser flujo. Verificado hoy: los -3,5M de las
    # 09:48 y los -4,9M de las 10:15 caen justo en un arranque. Se marcan con R y NO
    # se suman al total: es un artefacto, no dinero que se movio.
    arranques = [x[0][:5] for x in c.execute(
        "SELECT arranque FROM sesion_config WHERE fecha=? ORDER BY arranque",
        (F,)).fetchall()]
    db.close()

    if not filas:
        print("Sin net_prem para %s." % F)
        sys.exit(2)

    # delta del neto por strike -> flujo NETO de ese intervalo
    prev = {}
    por_hora = {}
    horas = []
    for h, strike, right, np_ in filas:
        if h not in por_hora:
            por_hora[h] = []
            horas.append(h)
        key = (strike, right)
        antes = prev.get(key)
        prev[key] = np_
        if antes is None:
            continue
        por_hora[h].append((strike, right, np_ - antes))

    return F, horas, por_hora, walls, ta, arranques


def lados(por_hora_h, spot):
    """(neto_call, neto_put, n_call, n_put) sumando SOLO los strikes ATM/ITM.
    call ATM/ITM = strike <= spot ; put ATM/ITM = strike >= spot."""
    sc = sp = 0.0
    nc = np_ = 0
    if spot is None:
        return sc, sp, nc, np_
    for strike, right, d in por_hora_h:
        if right == "C" and strike <= spot:
            sc += d
            nc += 1
        elif right == "P" and strike >= spot:
            sp += d
            np_ += 1
    return sc, sp, nc, np_


def hubo_reinicio(anterior, h, arranques):
    def M(x):
        return int(x[:2]) * 60 + int(x[3:5])
    return any(anterior is not None and M(anterior) < M(a) <= M(h) for a in arranques)


def _pintar(F, horas, por_hora, walls, ta, arranques):
    EXP = F.replace("-", "")
    cab = ["MINUTO", "CALL $", "PUT $", "SPY", "GANA", "nC", "nP", "GEX Bn", "REG",
           "RSI", "SC", "DIR", "MACDh", "ATR%", "VWAP", "OBV"]
    anchos = [7, 13, 13, 8, 5, 3, 3, 9, 6, 5, 3, 7, 7, 5, 8, 8]

    def linea(i, m, d):
        return i + m.join("─" * (a + 2) for a in anchos) + d

    def fila(v):
        return "│ " + " │ ".join("%*s" % (anchos[i], v[i]) for i in range(len(v))) + " │"

    # --------- 1a pasada: se arma cada fila y se guarda lo necesario para medir
    reg = []          # (spot, dict de senales direccionales, reinicio)
    filas_txt = []

    tc = tp = 0.0
    n_reinicio = 0
    anterior = None
    for h in horas:
        reinicio = hubo_reinicio(anterior, h, arranques)
        anterior = h
        w = walls.get(h)
        spot = w[0] if w else None
        sc, sp, nc, np_ = lados(por_hora[h], spot)
        if reinicio:
            n_reinicio += 1                 # artefacto: NO entra en el total
        else:
            tc += sc
            tp += sp
        t = ta.get(h, {})

        def n(v, dec=2):
            return "" if v is None else "%.*f" % (dec, v)

        gana = "" if reinicio else ("CALL" if sc > sp else ("PUT" if sp > sc else "="))
        gex = w[1] if (w and w[1] is not None) else None
        filas_txt.append(fila([
            h + ("R" if reinicio else ("!" if (w and w[3]) else "")),
            "%+.0f" % sc, "%+.0f" % sp,
            n(spot),
            # lado GANADOR del minuto: el que se lleva mas premium NETO.
            # En las filas de reinicio se deja vacio: el delta es un artefacto y
            # declarar un ganador sobre un artefacto seria inventarselo.
            gana,
            str(nc), str(np_),
            n(gex / 1e9, 1) if gex is not None else "",
            (w[2] or "")[:6] if w else "",
            n(t.get("rsi"), 1), n(t.get("ta_score"), 0), t.get("ta_dir") or "",
            n(t.get("macd_hist"), 3), n(t.get("atr_pct"), 2), n(t.get("vwap")),
            (t.get("obv_trend") or "")[:8]]))

        # DIRECCION que declara cada columna: +1 alcista, -1 bajista, None si esa
        # columna no dice nada direccional (ATR%, nC, nP) o falta el dato.
        def sg(v, umbral=0.0):
            return None if v is None else (1 if v > umbral else (-1 if v < umbral else None))

        senales = {
            "CALL $": None if reinicio else sg(sc),
            "PUT $": None if reinicio else (None if sp == 0 else (-1 if sp > 0 else 1)),
            "GANA": None if not gana or gana == "=" else (1 if gana == "CALL" else -1),
            "GEX Bn": sg(gex),
            "RSI": sg(t.get("rsi"), 50.0),
            "SC": sg(t.get("ta_score")),
            "DIR": {"BULL": 1, "BEAR": -1}.get(t.get("ta_dir")),
            "MACDh": sg(t.get("macd_hist")),
            "VWAP": (None if (spot is None or t.get("vwap") is None)
                     else sg(spot - t["vwap"])),
            "OBV": {"bullish": 1, "bearish": -1}.get(t.get("obv_trend")),
        }
        reg.append((spot, senales))

    # --------- 2a pasada: % de acierto de cada columna contra el SIGUIENTE intervalo
    aciertos = {}
    n_val = {}
    subidas = 0
    n_mov = 0
    for i in range(len(reg) - 1):
        a, b = reg[i][0], reg[i + 1][0]
        if a is None or b is None or b == a:
            continue
        real = 1 if b > a else -1
        n_mov += 1
        if real > 0:
            subidas += 1
        for k, v in reg[i][1].items():
            if v is None:
                continue
            n_val[k] = n_val.get(k, 0) + 1
            if v == real:
                aciertos[k] = aciertos.get(k, 0) + 1
    base_up = 100.0 * subidas / n_mov if n_mov else 0
    base = max(base_up, 100 - base_up)

    def pct(k):
        if n_val.get(k, 0) < 10:
            return "-"
        return "%.0f%%" % (100.0 * aciertos.get(k, 0) / n_val[k])

    fila_pct = fila(["%ACIERTO"] + [pct(x) if x in reg[0][1] else "-" for x in cab[1:]])

    out = []
    out.append("OPEN PREMIUM NETO (compras - ventas) POR LADO — %s — expiry 0DTE %s" % (F, EXP))
    out.append("Cada fila = un intervalo de ~3 min (la cadencia a la que se mide el neto y el GEX).")
    out.append("CALL $ / PUT $ = suma del neto de TODOS los strikes ATM/ITM de ese lado.")
    out.append("nC / nP = cuantos strikes entraron en cada suma.  REG = regimen de GEX.")
    out.append("")
    out.append("%%ACIERTO = de las %d veces que el SPY se movio, cuantas acerto esa columna la"
               % n_mov)
    out.append("  direccion del SIGUIENTE intervalo. ⚠️ COMPARAR CONTRA LA TASA BASE: hoy el SPY")
    out.append("  bajo el %.0f%% de las veces, asi que decir SIEMPRE 'baja' ya acierta el %.0f%%."
               % (100 - base_up, base))
    out.append("  Una columna solo aporta algo si supera ese %.0f%%." % base)
    out.append("")
    out.append(linea("┌", "┬", "┐"))
    out.append(fila(cab))
    out.append(fila_pct)
    out.append(linea("├", "┼", "┤"))
    out.extend(filas_txt)

    out.append(linea("├", "┼", "┤"))
    out.append(fila(["TOTAL", "%+.0f" % tc, "%+.0f" % tp,
                     "", "CALL" if tc > tp else ("PUT" if tp > tc else "="),
                     "", "", "", "", "", "", "", "", "", "", ""]))
    out.append(linea("└", "┴", "┘"))
    out.append("")
    out.append("R junto a la hora = en ese intervalo hubo un REINICIO de la app: el delta no es")
    out.append("  flujo, es un artefacto. Esas %d filas NO se suman al total." % n_reinicio)
    out.append("! junto a la hora = walls_snapshot.spot_stale=1: el precio de esa fila estaba")
    out.append("  congelado (murio el stream de barras). Esas filas NO son de fiar.")
    out.append("Arranques de esta sesion: %s" % ", ".join(arranques))

    txt = "\n".join(out)
    print(txt)
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "open_premium_%s.txt" % F)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print()
    print("ESCRITO: %s" % ruta)


if __name__ == "__main__":
    main()
