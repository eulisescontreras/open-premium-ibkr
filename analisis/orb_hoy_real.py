# -*- coding: utf-8 -*-
"""¿QUE HABRIA HECHO EL ORB HOY, con PRECIOS REALES?

Ejecuta la FUNCION REAL `SpyDirection._orb_check` sobre las barras de 1 min de la sesion
indicada (por defecto hoy) y, si dispara, simula la operacion con el premium REAL guardado en
`premium_minute` (bid/ask de IBKR), NO con el modelo sintetico.

Es la primera vez que el ORB se evalua contra precios reales: el backtest de 2 años usa premium
sintetico, que es el gate abierto del proyecto.

Reglas de ejecucion, tal como las fija la spec congelada v2:
  - contrato: el ITM MAS PROFUNDO que quepa en el tope (CAPITAL_FRAC_MAX * capital)
  - COMPRA AL ASK, VENDE AL BID  (no al mid: el spread es coste real)
  - salida: flip-exit del ST-3. Si no hay flip, se aguanta.

Uso:  python analisis/orb_hoy_real.py [fecha]
"""
import os
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import logging as _lg
import spy_direction as S
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

FECHA = sys.argv[1] if len(sys.argv) > 1 else "2026-08-14"
DK = FECHA.replace("-", "")
DB = os.path.join(RAIZ, "spy_history_%s.db" % DK)
CAPITAL = 400.0


def con_ro(p):
    return sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True, timeout=20)


def barras(fecha):
    c = con_ro(DB)
    r = c.execute("select hora,open,high,low,close from bars_minute where fecha=? "
                  "order by hora", (fecha,)).fetchall()
    c.close()
    y, m, d = map(int, fecha.split("-"))
    return [dict(date=datetime(y, m, d, int(h[:2]), int(h[3:5])), open=o, high=hi, low=lo,
                 close=cl) for h, o, hi, lo, cl in r]


def precio_real(hora, right, strike):
    """bid/ask REAL del contrato 0DTE en ese minuto."""
    c = con_ro(DB)
    r = c.execute("select bid,ask from premium_minute where fecha=? and expiry=? and hora=? "
                  "and right=? and strike=? and bid is not null and ask is not null",
                  (FECHA, DK, hora, right, strike)).fetchone()
    c.close()
    return r


def cadena(hora, right):
    """Todos los strikes con precio en ese minuto, para elegir contrato."""
    c = con_ro(DB)
    r = c.execute("select strike,bid,ask from premium_minute where fecha=? and expiry=? "
                  "and hora=? and right=? and bid is not null and ask is not null "
                  "and ask>0 order by strike", (FECHA, DK, hora, right)).fetchall()
    c.close()
    return r


def main():
    if not os.path.exists(DB):
        print("no existe %s" % os.path.basename(DB))
        return 1
    bars = barras(FECHA)
    if len(bars) < 16:
        print("solo %d barras de %s, insuficiente" % (len(bars), FECHA))
        return 1

    print("=" * 78)
    print("ORB DEL %s CON PRECIOS REALES" % FECHA)
    print("=" * 78)
    print("  barras 1-min disponibles: %d  (%s .. %s)"
          % (len(bars), bars[0]["date"].strftime("%H:%M"), bars[-1]["date"].strftime("%H:%M")))

    # --- FUNCION REAL, alimentada minuto a minuto como hace ta_poll ---
    app = S.SpyDirection.__new__(S.SpyDirection)
    app.demo = False
    app.orb_hi = app.orb_lo = None
    app.orb_hecho = False
    app.orb_senal = None
    app.orb_modulo = None

    disparo = None
    for i in range(2, len(bars) + 1):
        S.SpyDirection._orb_check(app, bars[:i])
        if app.orb_senal:
            disparo = (bars[i - 2]["date"].strftime("%H:%M"), app.orb_senal,
                       bars[i - 2]["close"])
            break

    print("\n--- RANGO DE APERTURA (09:30-09:39) ---")
    if app.orb_hi is None:
        print("  no se llego a calcular")
        return 0
    amp = app.orb_hi - app.orb_lo
    print("  alto  %.2f" % app.orb_hi)
    print("  bajo  %.2f" % app.orb_lo)
    print("  amplitud %.2f   (minimo exigido %.2f)  ->  %s"
          % (amp, S.ORB_RANGO_MIN, "PASA" if amp >= S.ORB_RANGO_MIN else "DESCARTADO"))

    if not disparo:
        print("\n--- RESULTADO ---")
        print("  NO HUBO SEÑAL: el precio no cerro fuera del rango entre 09:40 y 09:44.")
        ven = [b for b in bars if "09:40" <= b["date"].strftime("%H:%M") < "09:45"]
        print("\n  cierres de la ventana:")
        for b in ven:
            h = b["date"].strftime("%H:%M")
            cl = b["close"]
            d = "dentro"
            if cl > app.orb_hi:
                d = "POR ENCIMA"
            elif cl < app.orb_lo:
                d = "POR DEBAJO"
            print("    %s  close=%.2f   %s del rango [%.2f, %.2f]"
                  % (h, cl, d, app.orb_lo, app.orb_hi))
        return 0

    hora, sen, cl = disparo
    right = "P" if sen == "DOWN" else "C"
    print("\n--- DISPARO ---")
    print("  hora %s | cierre %.2f | %s el rango -> REVERSION -> %s"
          % (hora, cl, "POR ENCIMA de" if sen == "DOWN" else "POR DEBAJO de",
             "PUT" if right == "P" else "CALL"))

    # --- contrato: el ITM mas profundo que quepa en el tope ---
    tope = CAPITAL * S.CAPITAL_FRAC_MAX
    ch = cadena(hora, right)
    if not ch:
        print("\n  SIN PRECIOS REALES en %s para %s -> no se puede simular" % (hora, right))
        return 0
    spot = cl
    cand = []
    for K, b, a in ch:
        intr = (spot - K) if right == "C" else (K - spot)
        if intr <= 0:
            continue                      # solo ITM
        if a * 100.0 <= tope:
            cand.append((intr, K, b, a))
    if not cand:
        print("\n  ningun contrato ITM cabe en %.0f$ -> el sistema NO habria operado" % tope)
        return 0
    cand.sort(reverse=True)               # el MAS profundo que cabe
    prof, K, b0, a0 = cand[0]
    coste = a0 * 100.0
    print("\n--- CONTRATO (ITM mas profundo que cabe en %.0f$) ---" % tope)
    print("  strike %g%s | profundidad ITM %.2f | ask %.2f -> coste %.0f$" % (K, right, prof, a0, coste))

    # --- recorrido con precios REALES, vendiendo al BID ---
    c = con_ro(DB)
    curva = c.execute("select hora,bid,ask from premium_minute where fecha=? and expiry=? "
                      "and right=? and strike=? and hora>=? and bid is not null "
                      "order by hora", (FECHA, DK, right, K, hora)).fetchall()
    c.close()
    if not curva:
        print("  sin curva de precios posterior")
        return 0

    print("\n--- RECORRIDO (compra al ASK %.2f, se valora al BID) ---" % a0)
    print("  %-7s %8s %8s %10s %9s" % ("hora", "bid", "ask", "valor", "P&L"))
    mejor = peor = None
    for h, bb, aa in curva:
        pnl = (bb - a0) * 100.0
        if mejor is None or pnl > mejor[1]:
            mejor = (h, pnl)
        if peor is None or pnl < peor[1]:
            peor = (h, pnl)
    # muestra cada 15 min para no inundar
    for i, (h, bb, aa) in enumerate(curva):
        if i % 15 == 0 or i == len(curva) - 1:
            print("  %-7s %8.2f %8.2f %10.0f$ %+8.0f$" % (h, bb, aa, bb * 100.0, (bb - a0) * 100.0))

    h_fin, b_fin, a_fin = curva[-1]
    pnl_fin = (b_fin - a0) * 100.0
    print("\n--- RESULTADO CON PRECIOS REALES ---")
    print("  entrada %s  al ASK  %.2f   (coste %.0f$)" % (hora, a0, coste))
    print("  ultimo dato %s al BID %.2f   (valor %.0f$)" % (h_fin, b_fin, b_fin * 100.0))
    print("  P&L                        %+.0f$   (%.1f%% del capital de %.0f$)"
          % (pnl_fin, 100.0 * pnl_fin / CAPITAL, CAPITAL))
    print("  mejor momento %s  %+.0f$   |   peor %s  %+.0f$"
          % (mejor[0], mejor[1], peor[0], peor[1]))
    print("\n  OJO: sin flip del ST-3 la posicion sigue abierta; el dato termina donde termina")
    print("  el registro de la app, no en el cierre de mercado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
