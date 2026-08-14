# -*- coding: utf-8 -*-
"""Descarga ~1 año de velas 1-min CON premarket (useRTH=False) y VOLUMEN, paginando hacia atras.
Guarda en spy_bars_year.db (bars: fecha,hora,open,high,low,close,volume,wap). Resumable.
clientId=CLIENTID. Reintenta ante pacing. El volumen sirve para el proxy de magnitud."""
import os, sys, sqlite3, time
from datetime import timezone, timedelta, datetime
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from ib_insync import IB, Stock

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ET = timezone(timedelta(hours=-4))
# argv: FIN INICIO DBname  (defaults = año 1 ya bajado)
FIN = sys.argv[1] if len(sys.argv) > 1 else "20260813"
INICIO = sys.argv[2] if len(sys.argv) > 2 else "20250801"
DB = os.path.join(RAIZ, sys.argv[3] if len(sys.argv) > 3 else "spy_bars_year.db")
CLIENTID = int(sys.argv[4]) if len(sys.argv) > 4 else 26
CHUNK = "10 D"                   # por peticion

def ensure(c):
    c.execute("""CREATE TABLE IF NOT EXISTS bars(
        fecha TEXT, hora TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, wap REAL,
        PRIMARY KEY(fecha,hora))""")
    c.commit()

def main():
    db = sqlite3.connect(DB); ensure(db)
    ib = IB(); print("conectando clientId=CLIENTID ...", flush=True)
    ib.connect("127.0.0.1", 4002, clientId=CLIENTID, timeout=20); print("conectado", flush=True)
    spy = Stock("SPY", "SMART", "USD"); ib.qualifyContracts(spy)
    end = f"{FIN} 23:59:59 US/Eastern"
    lim = datetime.strptime(INICIO, "%Y%m%d")
    guard = 0
    while True:
        guard += 1
        if guard > 120:
            print("STOP guardia"); break
        try:
            bars = ib.reqHistoricalData(spy, endDateTime=end, durationStr=CHUNK,
                                        barSizeSetting="1 min", whatToShow="TRADES",
                                        useRTH=False, formatDate=1)
        except Exception as e:
            print(f"  error {e}; reintento/reconecto", flush=True); time.sleep(5)
            try:
                if not ib.isConnected():
                    ib.connect("127.0.0.1", 4002, clientId=CLIENTID, timeout=20); print("  reconectado", flush=True)
            except Exception as e2:
                print(f"  reconnect fail {e2}", flush=True); time.sleep(10)
            continue
        if not bars:
            print("sin mas barras -> fin"); break
        n = 0; fmin = None
        for b in bars:
            dt = b.date; et = dt.astimezone(ET) if getattr(dt, 'tzinfo', None) else dt
            f = et.strftime("%Y-%m-%d"); h = et.strftime("%H:%M")
            db.execute("INSERT OR IGNORE INTO bars VALUES(?,?,?,?,?,?,?,?)",
                       (f, h, b.open, b.high, b.low, b.close, b.volume, b.average))
            n += 1
            if fmin is None or et < fmin: fmin = et
        db.commit()
        dias = db.execute("select count(distinct fecha) from bars").fetchone()[0]
        print(f"  {end[:8]}: +{n} barras (earliest {fmin.strftime('%Y-%m-%d %H:%M')})  total dias={dias}", flush=True)
        if fmin.replace(tzinfo=None) <= lim:
            print("alcanzado INICIO -> fin"); break
        end = fmin.strftime("%Y%m%d %H:%M:%S US/Eastern")
        time.sleep(1.0)
    ib.disconnect()
    dias = db.execute("select count(distinct fecha) from bars").fetchone()[0]
    tot = db.execute("select count(*) from bars").fetchone()[0]
    db.close()
    print(f"\nLISTO: {tot} barras, {dias} dias en {os.path.basename(DB)}")

if __name__ == "__main__":
    main()
