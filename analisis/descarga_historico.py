# -*- coding: utf-8 -*-
"""DESCARGA DE HISTORICO SPY 1-MIN DESDE IBKR  ->  BD SEPARADA

NO TOCA spy_history.db. Escribe en historico_spy.db, que se crea al lado.

Uso:
    python analisis/descarga_historico.py            # 12 meses
    python analisis/descarga_historico.py 6          # 6 meses
    python analisis/descarga_historico.py 12 4002 21 # meses, puerto, clientId

Es REANUDABLE: si lo cortas, al volver a lanzarlo salta las semanas que ya tiene.
"""
import sqlite3
import sys
import time
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from ib_insync import IB, Stock

MESES = int(sys.argv[1]) if len(sys.argv) > 1 else 12
PUERTO = int(sys.argv[2]) if len(sys.argv) > 2 else 4002
CLIENT_ID = int(sys.argv[3]) if len(sys.argv) > 3 else 21   # la app usa el 7: NO reutilizar

DB = "historico_spy.db"          # BD NUEVA, separada de spy_history.db
CHUNK = "1 W"                    # una semana por peticion
ESPERA = 11.0                    # segundos entre peticiones (limite: 60 por 10 min)


def ensure_db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS bars_historico (
                   fecha TEXT, hora TEXT, open REAL, high REAL, low REAL,
                   close REAL, volume REAL, PRIMARY KEY(fecha, hora))""")
    c.execute("""CREATE TABLE IF NOT EXISTS descargas (
                   fin TEXT PRIMARY KEY, filas INTEGER, ts TEXT)""")
    c.commit()
    return c


def main():
    db = ensure_db()
    ya = {r[0] for r in db.execute("select fin from descargas")}

    ib = IB()
    print(f"conectando a 127.0.0.1:{PUERTO} clientId={CLIENT_ID} ...")
    ib.connect("127.0.0.1", PUERTO, clientId=CLIENT_ID, timeout=20)
    print("conectado")

    spy = Stock("SPY", "SMART", "USD")
    ib.qualifyContracts(spy)

    # ventanas semanales hacia atras desde hoy
    fines = []
    cur = datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)
    for _ in range(int(MESES * 4.4) + 1):
        fines.append(cur)
        cur = cur - timedelta(days=7)

    total_nuevas = 0
    for k, fin in enumerate(fines, 1):
        clave = fin.strftime("%Y%m%d")
        if clave in ya:
            print(f"[{k}/{len(fines)}] {clave}  ya descargada, salto")
            continue
        try:
            bars = ib.reqHistoricalData(
                spy,
                endDateTime=fin.strftime("%Y%m%d %H:%M:%S US/Eastern"),
                durationStr=CHUNK,
                barSizeSetting="1 min",
                whatToShow="TRADES",     # precio negociado, no MIDPOINT
                useRTH=True,             # SOLO sesion regular 09:30-16:00
                formatDate=1,
            )
        except Exception as e:
            print(f"[{k}/{len(fines)}] {clave}  ERROR: {e}")
            time.sleep(ESPERA * 2)
            continue

        n = 0
        for b in bars:
            dt = b.date
            f = dt.strftime("%Y-%m-%d")
            h = dt.strftime("%H:%M")
            db.execute(
                "INSERT OR IGNORE INTO bars_historico VALUES(?,?,?,?,?,?,?)",
                (f, h, b.open, b.high, b.low, b.close, b.volume))
            n += 1
        db.execute("INSERT OR REPLACE INTO descargas VALUES(?,?,?)",
                   (clave, n, datetime.now().isoformat(timespec="seconds")))
        db.commit()
        total_nuevas += n
        print(f"[{k}/{len(fines)}] {clave}  {n:5d} barras   (acumulado {total_nuevas})")
        time.sleep(ESPERA)

    ib.disconnect()
    dias = db.execute("select count(distinct fecha) from bars_historico").fetchone()[0]
    filas = db.execute("select count(*) from bars_historico").fetchone()[0]
    r = db.execute("select min(fecha), max(fecha) from bars_historico").fetchone()
    print("\n" + "=" * 70)
    print(f"LISTO: {dias} sesiones, {filas} barras, de {r[0]} a {r[1]}")
    print(f"BD: {DB}")
    print("=" * 70)


if __name__ == "__main__":
    main()
