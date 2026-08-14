# -*- coding: utf-8 -*-
"""TAREA 1: velas con PREMARKET (useRTH=False) + Supertrend(7,3) -> señales del 08-12.
Objetivo: ver si el ST calculado con premarket reproduce las 7 señales del Webull del usuario.
Control: el 08-13 debe dar las 6 que el agente ya validó (09:36 C,10:44 P,12:05 C,13:33 P,14:15 C,15:13 P).

La funcion supertrend() es COPIA VERBATIM de investigacion/scripts/supertrend.py (ese modulo corre
al importarse, por eso se copia en vez de importar). clientId=22 (app parada). Read-only IBKR.
"""
import sys
from datetime import timezone, timedelta
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from ib_insync import IB, Stock

ET = timezone(timedelta(hours=-4))   # EDT (agosto)
P, MULT = 7, 3.0
WEBULL_0812 = "09:30 PUT, 10:27 CALL, 10:33 PUT, 12:02 CALL, 13:12 PUT, 14:12 CALL, 14:57 PUT"
AGENTE_0813 = "09:36 C, 10:44 P, 12:05 C, 13:33 P, 14:15 C, 15:13 P"

def supertrend(hi, lo, cl, p, mult):
    """COPIA VERBATIM de investigacion/scripts/supertrend.py (ATR Wilder, banda (hi+lo)/2, arrastre)."""
    n = len(cl)
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    atr = [None] * n
    if n > p:
        atr[p] = sum(tr[1:p + 1]) / p
        for i in range(p + 1, n):
            atr[i] = (atr[i - 1] * (p - 1) + tr[i]) / p
    tend = [0] * n
    fu = fl = None
    d = 1
    for i in range(n):
        if atr[i] is None:
            continue
        med = (hi[i] + lo[i]) / 2
        bu = med + mult * atr[i]
        bl = med - mult * atr[i]
        fu = bu if (fu is None or bu < fu or cl[i - 1] > fu) else fu
        fl = bl if (fl is None or bl > fl or cl[i - 1] < fl) else fl
        if d == 1 and cl[i] < fl:
            d = -1
        elif d == -1 and cl[i] > fu:
            d = 1
        tend[i] = d
    return tend

def main():
    ib = IB(); print("conectando clientId=22 ...", flush=True)
    ib.connect("127.0.0.1", 4002, clientId=22, timeout=20); print("conectado", flush=True)
    spy = Stock("SPY", "SMART", "USD"); ib.qualifyContracts(spy)
    bars = ib.reqHistoricalData(spy, endDateTime="20260813 23:59:59 US/Eastern",
                                durationStr="5 D", barSizeSetting="1 min",
                                whatToShow="TRADES", useRTH=False, formatDate=1)
    ib.disconnect()
    print(f"barras recibidas: {len(bars)}", flush=True)
    # agrupar por fecha ET
    dias = {}
    for b in bars:
        dt = b.date
        et = dt.astimezone(ET) if dt.tzinfo else dt
        f = et.strftime("%Y-%m-%d"); h = et.strftime("%H:%M")
        dias.setdefault(f, []).append((h, b.high, b.low, b.close))
    for f in sorted(dias):
        n_pm = sum(1 for h,_,_,_ in dias[f] if h < "09:30")
        print(f"  {f}: {len(dias[f])} velas (premarket: {n_pm})", flush=True)

    def señales(f):
        b = dias.get(f, [])
        if not b: return []
        hi=[x[1] for x in b]; lo=[x[2] for x in b]; cl=[x[3] for x in b]; ho=[x[0] for x in b]
        tend = supertrend(hi, lo, cl, P, MULT)
        out=[]; prev=None
        for i in range(len(b)):
            if ho[i] < "09:30" or ho[i] > "16:00": continue
            d = tend[i]
            if d == 0: continue
            if prev is None or d != prev:
                out.append((ho[i], "CALL" if d>0 else "PUT"))
            prev = d
        return out

    for f, ref in (("2026-08-13", AGENTE_0813), ("2026-08-12", WEBULL_0812)):
        s = señales(f)
        print(f"\n=== {f} — señales ST(7,3) con premarket ===", flush=True)
        print("  mias:", ", ".join(f"{h} {lado}" for h,lado in s))
        print("  ref :", (AGENTE_0813 if f=="2026-08-13" else WEBULL_0812))

if __name__ == "__main__":
    main()
