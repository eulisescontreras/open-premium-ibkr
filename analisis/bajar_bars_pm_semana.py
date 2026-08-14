# -*- coding: utf-8 -*-
"""Descarga velas 1min CON premarket (useRTH=False) de la semana y las guarda en
spy_bars_pm.db (tabla bars_pm: fecha,hora,high,low,close). Una sola peticion IBKR.
clientId=25 para no chocar con la descarga de tape (clientId=22)."""
import os, sys, sqlite3
from datetime import timezone, timedelta
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from ib_insync import IB, Stock

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DB = os.path.join(RAIZ, "spy_bars_pm.db")
ET = timezone(timedelta(hours=-4))

ib = IB(); print("conectando IBKR clientId=25 ...", flush=True)
ib.connect("127.0.0.1", 4002, clientId=25, timeout=20); print("conectado", flush=True)
spy = Stock("SPY", "SMART", "USD"); ib.qualifyContracts(spy)
bars = ib.reqHistoricalData(spy, endDateTime="20260813 23:59:59 US/Eastern",
                            durationStr="7 D", barSizeSetting="1 min",
                            whatToShow="TRADES", useRTH=False, formatDate=1)
ib.disconnect()
print(f"barras recibidas: {len(bars)}", flush=True)

con = sqlite3.connect(DB)
con.execute("DROP TABLE IF EXISTS bars_pm")
con.execute("CREATE TABLE bars_pm (fecha TEXT, hora TEXT, high REAL, low REAL, close REAL)")
dias = {}
for b in bars:
    dt = b.date; et = dt.astimezone(ET) if dt.tzinfo else dt
    f = et.strftime("%Y-%m-%d"); h = et.strftime("%H:%M")
    con.execute("insert into bars_pm values (?,?,?,?,?)", (f, h, b.high, b.low, b.close))
    dias.setdefault(f, [0, 0]); dias[f][0] += 1
    if h < "09:30": dias[f][1] += 1
con.commit()
for f in sorted(dias):
    print(f"  {f}: {dias[f][0]} velas (premarket {dias[f][1]})")
con.close()
print(f"guardado en {os.path.basename(DB)}")
