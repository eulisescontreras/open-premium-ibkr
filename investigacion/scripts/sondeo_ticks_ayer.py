# SONDEO (2 peticiones, no descarga nada masivo): que devuelve reqHistoricalTicks para
# el SPY del 2026-08-12, y si se puede reconstruir el AGRESOR.
# clientId 33: la app en vivo usa el 7, no se toca su conexion ni sus suscripciones.
import time
from datetime import datetime

from ib_insync import IB, Stock

HOST, PORT, CID = "127.0.0.1", 4002, 33
OUT = []


def p(s):
    print(s)
    OUT.append(str(s))


ib = IB()
try:
    ib.connect(HOST, PORT, clientId=CID, timeout=10)
except Exception as e:
    p(f"NO CONECTA: {type(e).__name__}: {e}")
    raise SystemExit(1)
p(f"Conectado clientId={CID} (la app sigue con el 7, intacta)")

spy = Stock("SPY", "SMART", "USD")
ib.qualifyContracts(spy)

ini = datetime(2026, 8, 12, 9, 30, 0)
fin = datetime(2026, 8, 12, 9, 31, 0)

# --- 1) TRADES ---
t0 = time.time()
try:
    tr = ib.reqHistoricalTicks(spy, ini, fin, 1000, "TRADES", useRth=True)
    dt = time.time() - t0
    p(f"TRADES  -> {len(tr)} ticks en {dt:.2f}s")
    if tr:
        p(f"  primero: {tr[0]}")
        p(f"  ultimo : {tr[-1]}")
        p(f"  campos : {[a for a in dir(tr[0]) if not a.startswith('_')]}")
except Exception as e:
    p(f"TRADES  -> FALLA {type(e).__name__}: {e}")

ib.sleep(2)

# --- 2) BID_ASK (hace falta para clasificar COMPRA/VENTA) ---
t0 = time.time()
try:
    ba = ib.reqHistoricalTicks(spy, ini, fin, 1000, "BID_ASK", useRth=True)
    dt = time.time() - t0
    p(f"BID_ASK -> {len(ba)} ticks en {dt:.2f}s")
    if ba:
        p(f"  primero: {ba[0]}")
except Exception as e:
    p(f"BID_ASK -> FALLA {type(e).__name__}: {e}")

ib.disconnect()
p("Desconectado. La app de hoy no se ha tocado.")

with open("sondeo_ticks_ayer.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT) + "\n")
