# -*- coding: utf-8 -*-
"""
PROBE OI + GAMMA (correr el LUNES con MERCADO ABIERTO, 9:30-16:00 ET).
Verifica que IB Gateway (paper 4002, clientId 7) entrega Open Interest (tick 101) Y
gamma (modelGreeks, tick 106) REALES para opciones de SPY, antes de confiar en el panel
Walls/GEX/Flip en vivo. NO opera. NO toca produccion. Se puede borrar tras usar.

Uso:  python probe_oi_gamma.py
Exito = imambos OI y gamma con numeros reales (no NaN) en varios strikes.
Si sale 10197 / NaN en todo -> datos no disponibles (finde/mantenimiento/sin OPRA) -> reintentar.
"""
import math
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from datetime import datetime
from ib_insync import IB, Stock, Option, util

HOST, PORT, CLIENT_ID, SYMBOL = "127.0.0.1", 4002, 7, "SPY"
BAND = 5   # strikes a cada lado del ATM


def main():
    util.patchAsyncio()
    ib = IB()
    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=8)
    except Exception as e:
        print(f"SIN CONEXION a IB Gateway {HOST}:{PORT} -> {e}")
        return 1
    print(f"Conectado (clientId={CLIENT_ID}).")
    ib.reqMarketDataType(1)   # LIVE

    spy = Stock(SYMBOL, "SMART", "USD")
    ib.qualifyContracts(spy)
    t = ib.reqMktData(spy, "", False, False)
    ib.sleep(2.0)
    spot = t.marketPrice()
    if spot is None or math.isnan(spot):
        spot = t.last if (t.last and not math.isnan(t.last)) else t.close
    ib.cancelMktData(spy)
    print(f"SPY spot = {spot}")
    if spot is None or math.isnan(spot):
        print("No hay precio de SPY -> abortando (revisar datos de mercado).")
        ib.disconnect()
        return 1

    chains = ib.reqSecDefOptParams(spy.symbol, "", spy.secType, spy.conId)
    chain = next((c for c in chains if c.exchange == "SMART" and c.tradingClass == SYMBOL), None) \
        or next((c for c in chains if c.exchange == "SMART"), None)
    today = datetime.now().strftime("%Y%m%d")
    exps = sorted(chain.expirations)
    expiry = next((e for e in exps if e >= today), exps[0])
    strikes = sorted(chain.strikes)
    below = [s for s in strikes if s <= spot][-BAND:]
    above = [s for s in strikes if s > spot][:BAND]
    band = below + above
    print(f"Expiracion cercana = {expiry} | banda ATM+-{BAND}: {band}")

    contracts = []
    for s in band:
        contracts.append(Option(SYMBOL, expiry, s, "C", "SMART", tradingClass=SYMBOL))
        contracts.append(Option(SYMBOL, expiry, s, "P", "SMART", tradingClass=SYMBOL))
    ib.qualifyContracts(*contracts)

    # STREAMING (como en la app): suscribir, esperar a que lleguen OI/greeks, leer.
    tickers = [ib.reqMktData(c, "100,101,106", False, False) for c in contracts]
    print("Esperando datos (8s)...")
    ib.sleep(8.0)

    ok_oi = ok_g = 0
    print("\n strike right |        OI |      gamma |   last |   volume")
    print(" ------------ + --------- + ---------- + ------ + --------")
    for c, tk in zip(contracts, tickers):
        oi = tk.callOpenInterest if c.right == "C" else tk.putOpenInterest
        g = tk.modelGreeks.gamma if tk.modelGreeks else None
        oi_ok = oi is not None and not (isinstance(oi, float) and math.isnan(oi))
        g_ok = g is not None and not (isinstance(g, float) and math.isnan(g))
        ok_oi += 1 if oi_ok else 0
        ok_g += 1 if g_ok else 0
        print(f" {c.strike:>10g} {c.right:>4} | {str(oi):>9} | {str(g):>10} | "
              f"{str(tk.last):>6} | {str(tk.volume):>8}")
        ib.cancelMktData(c)

    n = len(contracts)
    print(f"\nRESUMEN: OI reales {ok_oi}/{n} | gamma reales {ok_g}/{n}")
    if ok_oi >= n * 0.6 and ok_g >= n * 0.6:
        print("PROBE OK -> IBKR entrega OI y gamma reales. El panel Walls/GEX puede confiar en vivo.")
        rc = 0
    else:
        print("PROBE INCOMPLETO -> faltan OI/gamma. Revisar suscripcion OPRA, horario RTH o 10197. Reintentar.")
        rc = 2
    ib.disconnect()
    return rc


if __name__ == "__main__":
    sys.exit(main())
