# -*- coding: utf-8 -*-
"""DESCARGA tape del SPY (TRADES) via IBKR reqHistoricalTicks -> spy_tape.db (BD nueva, separada).
Pagina hacia atras (1000 ticks/peticion) desde el cierre hasta la apertura, por dia. RESUMABLE.
clientId=22 (app usa 7). NO toca ninguna BD de produccion.

Uso: python analisis/descarga_tape_spy.py 20260806 20260812   (rango inclusive, dias habiles)
"""
import sqlite3, sys, time
from datetime import datetime, timedelta
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from ib_insync import IB, Stock

INI = sys.argv[1] if len(sys.argv) > 1 else "20260806"
FIN = sys.argv[2] if len(sys.argv) > 2 else "20260812"
DB = "spy_tape.db"
ESPERA = 0.4   # entre peticiones (gentil con pacing)

def ensure(c):
    c.execute("""CREATE TABLE IF NOT EXISTS trades(
        fecha TEXT, ts TEXT, price REAL, size REAL, exch TEXT, PRIMARY KEY(fecha,ts,price,size,exch))""")
    c.execute("CREATE TABLE IF NOT EXISTS dias_listos(fecha TEXT PRIMARY KEY, n INTEGER, ts TEXT)")
    c.commit()

def dias_habiles(ini, fin):
    d0 = datetime.strptime(ini, "%Y%m%d"); d1 = datetime.strptime(fin, "%Y%m%d")
    out = []; d = d0
    while d <= d1:
        if d.weekday() < 5: out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out

def baja_dia(ib, spy, db, dia):
    fkey = f"{dia[:4]}-{dia[4:6]}-{dia[6:]}"
    end = f"{dia} 16:00:00 US/Eastern"
    vistos = set(); total = 0; guard = 0
    while True:
        guard += 1
        if guard > 4000:
            print(f"  {dia}: STOP guardia (demasiadas peticiones)"); break
        try:
            ticks = ib.reqHistoricalTicks(spy, "", end, 1000, "TRADES", useRth=True)
        except Exception as e:
            print(f"  {dia}: error {e}; espero"); time.sleep(ESPERA*5); continue
        if not ticks:
            break
        nuevos = 0; earliest = None
        for t in ticks:
            key = (t.time.isoformat(), t.price, t.size, t.exchange)
            if key in vistos: continue
            vistos.add(key)
            ts = t.time.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            db.execute("INSERT OR IGNORE INTO trades VALUES(?,?,?,?,?)",
                       (fkey, ts, float(t.price), float(t.size), t.exchange))
            nuevos += 1
            if earliest is None or t.time < earliest: earliest = t.time
        db.commit(); total += nuevos
        # avanzar hacia atras: nuevo end = el tick mas temprano recibido (datetime UTC DIRECTO,
        # sin formatear con etiqueta de zona -> ese era el bug que lo devolvia al cierre).
        if earliest is None or nuevos == 0:
            break                                  # pagina toda duplicada -> llegamos al inicio
        # apertura 09:30 ET = 13:30 UTC (EDT, agosto). earliest es tz-aware UTC.
        utcmin = earliest.hour * 60 + earliest.minute
        if utcmin <= 13*60 + 30:
            break
        end = earliest                             # pasar el datetime directamente a reqHistoricalTicks
        if total % 20000 < 1000:
            print(f"  {dia}: {total} trades... (earliest UTC {earliest.strftime('%H:%M:%S')})", flush=True)
        time.sleep(ESPERA)
    db.execute("INSERT OR REPLACE INTO dias_listos VALUES(?,?,?)", (fkey, total, datetime.now().isoformat(timespec='seconds')))
    db.commit()
    print(f"  {dia}: LISTO {total} trades")

def main():
    db = sqlite3.connect(DB); ensure(db)
    listos = {r[0] for r in db.execute("select fecha from dias_listos")}
    ib = IB(); print("conectando clientId=22 ..."); ib.connect("127.0.0.1", 4002, clientId=22, timeout=20); print("conectado")
    spy = Stock("SPY", "SMART", "USD"); ib.qualifyContracts(spy)
    for dia in dias_habiles(INI, FIN):
        fkey = f"{dia[:4]}-{dia[4:6]}-{dia[6:]}"
        if fkey in listos:
            print(f"  {dia}: ya descargado, salto"); continue
        print(f"descargando {dia} ...")
        baja_dia(ib, spy, db, dia)
    ib.disconnect()
    n = db.execute("select count(*) from trades").fetchone()[0]
    d = db.execute("select count(*) from dias_listos").fetchone()[0]
    print(f"\nLISTO: {n} trades, {d} dias en {DB}")

if __name__ == "__main__":
    main()
