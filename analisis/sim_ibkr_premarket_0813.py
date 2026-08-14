# -*- coding: utf-8 -*-
"""08-13 "TODO COMO SI VINIERA DE IBKR":
  - SENALES: Supertrend(7,3) sobre velas IBKR CON premarket (useRTH=False)  [el ST correcto]
  - TAPE (magnitud + cierres del trail): descarga densa IBKR (spy_tape_20260813_denso.db, 377k)
  - trail 0.10% + magnitud 0.8 + capital compuesto + ITM ask/bid (simulador REAL)

Persiste las velas premarket en spy_bars_pm_20260813.db (para reproducir sin re-descargar).
supertrend() = COPIA VERBATIM de st_check_premarket.py (el que reprodujo el Webull).
"""
import os, sys, sqlite3
from datetime import timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from simulador_st import simular, FUENTES, CAPITAL_0, SENALES_MANUALES

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DENSO = os.path.join(RAIZ, "spy_tape_20260813_denso.db")
PMDB = os.path.join(RAIZ, "spy_bars_pm_20260813.db")
ET = timezone(timedelta(hours=-4))
P, MULT = 7, 3.0


def supertrend(hi, lo, cl, p, mult):
    """COPIA VERBATIM de st_check_premarket.py (el ST que reprodujo el Webull)."""
    n = len(cl); tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    atr = [None] * n
    if n > p:
        atr[p] = sum(tr[1:p + 1]) / p
        for i in range(p + 1, n):
            atr[i] = (atr[i - 1] * (p - 1) + tr[i]) / p
    tend = [0] * n; fu = fl = None; d = 1
    for i in range(n):
        if atr[i] is None:
            continue
        med = (hi[i] + lo[i]) / 2
        bu = med + mult * atr[i]; bl = med - mult * atr[i]
        fu = bu if (fu is None or bu < fu or cl[i - 1] > fu) else fu
        fl = bl if (fl is None or bl > fl or cl[i - 1] < fl) else fl
        if d == 1 and cl[i] < fl: d = -1
        elif d == -1 and cl[i] > fu: d = 1
        tend[i] = d
    return tend


def bajar_premarket_0813():
    """Descarga velas 1min con premarket del 08-13 y las persiste. Devuelve lista (h,hi,lo,cl) del dia."""
    if os.path.exists(PMDB):
        con = sqlite3.connect(PMDB)
        rows = con.execute("select hora,high,low,close from bars_pm where fecha='2026-08-13' order by hora").fetchall()
        con.close()
        if rows:
            print(f"[premarket] reuso {os.path.basename(PMDB)}: {len(rows)} velas")
            return rows
    from ib_insync import IB, Stock
    ib = IB(); print("[premarket] conectando IBKR clientId=23 ...", flush=True)
    ib.connect("127.0.0.1", 4002, clientId=23, timeout=20)
    spy = Stock("SPY", "SMART", "USD"); ib.qualifyContracts(spy)
    bars = ib.reqHistoricalData(spy, endDateTime="20260813 23:59:59 US/Eastern",
                                durationStr="2 D", barSizeSetting="1 min",
                                whatToShow="TRADES", useRTH=False, formatDate=1)
    ib.disconnect()
    con = sqlite3.connect(PMDB)
    con.execute("CREATE TABLE IF NOT EXISTS bars_pm (fecha TEXT, hora TEXT, high REAL, low REAL, close REAL)")
    dia = []
    for b in bars:
        dt = b.date; et = dt.astimezone(ET) if dt.tzinfo else dt
        f = et.strftime("%Y-%m-%d"); h = et.strftime("%H:%M")
        con.execute("insert into bars_pm values (?,?,?,?,?)", (f, h, b.high, b.low, b.close))
        if f == "2026-08-13":
            dia.append((h, b.high, b.low, b.close))
    con.commit(); con.close()
    npm = sum(1 for h, *_ in dia if h < "09:30")
    print(f"[premarket] descargadas y guardadas {len(dia)} velas 08-13 (premarket: {npm})")
    return dia


def senales_premarket(dia):
    hi = [x[1] for x in dia]; lo = [x[2] for x in dia]; cl = [x[3] for x in dia]; ho = [x[0] for x in dia]
    tend = supertrend(hi, lo, cl, P, MULT)
    out = []; prev = None
    for i in range(len(dia)):
        if ho[i] < "09:30" or ho[i] > "16:00":
            continue
        d = tend[i]
        if d == 0:
            continue
        if prev is None or d != prev:
            out.append((ho[i], "C" if d > 0 else "P"))   # formato simulador: 'C'/'P'
        prev = d
    return out


F = "2026-08-13"
dbv, dbt_vivo, exp = FUENTES[F]

dia = bajar_premarket_0813()
sen_pm = senales_premarket(dia)
print(f"\nSENALES ST(7,3) PREMARKET (IBKR): {len(sen_pm)}  ->  " + "  ".join(f"{h}{r}" for h, r in sen_pm))
print("manual/Webull 08-13           :  09:36C 10:44P 12:05C 13:37P 14:34C 15:17P")

print("\n" + "=" * 80)
print("SIMULADOR  ·  senales ST premarket (IBKR)  ·  TAPE DENSO IBKR  ·  todo IBKR")
print("=" * 80)
ops, cap = simular(F, senales=sen_pm, db_velas=dbv, db_tape=DENSO, expiry=exp, verbose=True)
g = cap - CAPITAL_0
print(f"  {F}: {len(ops)} ops   {g:+.2f}$")

print("\nreferencias:  manual+tape = +480.84$   |   tape-auto denso = +576.84$")
