# -*- coding: utf-8 -*-
"""SONDA de factibilidad: reqHistoricalTicks del SPY (TRADES y BID_ASK) via IBKR.
Mide la DENSIDAD real de ticks para estimar si 1 mes es viable. clientId=22 (app usa 7).
Uso: python analisis/sonda_tape_spy.py [YYYYMMDD]
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from ib_insync import IB, Stock

DIA = sys.argv[1] if len(sys.argv) > 1 else "20260812"
ib = IB()
print(f"conectando 127.0.0.1:4002 clientId=22 ...")
ib.connect("127.0.0.1", 4002, clientId=22, timeout=20)
print("conectado")
spy = Stock("SPY", "SMART", "USD")
ib.qualifyContracts(spy)

def sonda(what, hhmm):
    end = f"{DIA} {hhmm} US/Eastern"
    ticks = ib.reqHistoricalTicks(spy, "", end, 1000, what, useRth=True)
    if not ticks:
        print(f"  {what} @ {hhmm}: 0 ticks (¿sin permiso de datos historicos de ticks?)")
        return
    t0 = ticks[0].time; t1 = ticks[-1].time
    span = (t1 - t0).total_seconds()
    dens = len(ticks) / span if span > 0 else 0
    print(f"  {what} @ {hhmm}: {len(ticks)} ticks cubren {span:.1f} s  -> {dens:.1f} ticks/seg  "
          f"({t0.strftime('%H:%M:%S')}..{t1.strftime('%H:%M:%S')})")
    ej = ticks[-1]
    print(f"     ejemplo: {ej}")
    return dens

print(f"\n=== SONDA densidad de ticks SPY {DIA} ===")
d1 = sonda("TRADES", "10:00:00")
d2 = sonda("TRADES", "15:55:00")
d3 = sonda("BID_ASK", "15:55:00")
ib.disconnect()

# estimacion
import statistics as st
ds = [x for x in (d1, d2) if x]
if ds:
    dprom = st.mean(ds)
    seg_rth = 6.5 * 3600
    ticks_dia = dprom * seg_rth
    peticiones_dia = ticks_dia / 1000
    print(f"\n=== ESTIMACION (TRADES) ===")
    print(f"  densidad media ~{dprom:.1f} ticks/seg -> ~{ticks_dia:,.0f} ticks/dia -> ~{peticiones_dia:,.0f} peticiones/dia")
    print(f"  1 mes (~21 dias): ~{ticks_dia*21:,.0f} ticks, ~{peticiones_dia*21:,.0f} peticiones (TRADES) + otro tanto BID_ASK")
    print(f"  a ~2-4 peticiones/seg con pacing: 1 dia ~ {peticiones_dia/3/60:.0f}-{peticiones_dia/2/60:.0f} min ; 1 mes ~ x21")
