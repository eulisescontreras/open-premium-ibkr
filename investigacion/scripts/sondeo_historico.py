# Sondeo: que acepta IBKR para historico del SPY. NO descarga el ano entero.
# 3 peticiones sueltas para medir barras/segundos por peticion. clientId 33 (la app usa 7).
import time, sys
from ib_insync import IB, Stock

HOST, PORT, CID = "127.0.0.1", 4002, 33
OUT = []


def p(s):
    print(s)
    OUT.append(s)


ib = IB()
try:
    ib.connect(HOST, PORT, clientId=CID, timeout=10)
except Exception as e:
    p(f"NO CONECTA: {type(e).__name__}: {e}")
    sys.exit(1)
p(f"Conectado clientId={CID} a {HOST}:{PORT}")

spy = Stock("SPY", "SMART", "USD")
ib.qualifyContracts(spy)
p(f"Contrato: conId={spy.conId} exchange={spy.exchange} primary={spy.primaryExchange}")
p("")

PRUEBAS = [
    ("1 Y", "1 day", True),
    ("1 M", "1 min", True),
    ("1 Y", "1 min", True),   # se espera que IBKR lo rechace; el error dira el limite real
    ("2 D", "1 min", True),
]

for dur, size, rth in PRUEBAS:
    t0 = time.time()
    try:
        b = ib.reqHistoricalData(spy, "", dur, size, "TRADES",
                                 useRTH=rth, keepUpToDate=False, timeout=120)
        dt = time.time() - t0
        n = len(b) if b else 0
        if n:
            p(f"OK   dur={dur:5} size={size:6} RTH={rth} -> {n:7} barras en {dt:6.2f}s"
              f"   {b[0].date}  ..  {b[-1].date}")
            p(f"     muestra ultima: o={b[-1].open} h={b[-1].high} l={b[-1].low} "
              f"c={b[-1].close} vol={b[-1].volume} vwap={b[-1].average} n={b[-1].barCount}")
        else:
            p(f"VACIO dur={dur:5} size={size:6} RTH={rth} -> 0 barras en {dt:6.2f}s")
    except Exception as e:
        dt = time.time() - t0
        p(f"FALLA dur={dur:5} size={size:6} RTH={rth} -> {type(e).__name__}: {e}  ({dt:.2f}s)")
    ib.sleep(2)   # respeta el pacing entre peticiones

ib.disconnect()
p("")
p("Desconectado.")

with open("sondeo_historico.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT) + "\n")
