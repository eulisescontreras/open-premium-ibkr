# Descarga el TAPE DEL SUBYACENTE (SPY) del 2026-08-12 desde IBKR y lo PERSISTE lote a lote.
#
# Aprendido a la mala (2026-08-13 14:27): la version anterior acumulaba 312.526 ticks en RAM y
# escribia al final. Un TypeError en la ultima linea destruyo 75 minutos de descarga. Ahora
# cada lote se escribe a spy_tape_ayer.db en cuanto llega, y el script es REANUDABLE: si se
# corta, al relanzarlo sigue desde el ultimo tick guardado.
#
# El .txt lo genera tape_ayer_txt.py, que lee esta BD y puede ejecutarse en CUALQUIER momento,
# incluso con la descarga a medias.
#
# NO toca la app en vivo: conexion propia con clientId 33 (la app usa el 7).
import os
import sqlite3
import sys
from datetime import datetime, timedelta

from ib_insync import IB, Stock

HOST, PORT, CID = "127.0.0.1", 4002, 33
DB = "spy_tape_ayer.db"
LOG = "tape_ayer_progreso.txt"
PAUSA = 11.0          # segundos entre peticiones: el limite de IBKR es 60 por 10 min
UTC_A_ET = -4         # agosto 2026 = EDT = UTC-4
MAX_IT = 700          # guard anti-bucle. Con 400 se corto en las 15:08 sin cubrir el dia.

H_INI = sys.argv[1] if len(sys.argv) > 2 else "09:30"
H_FIN = sys.argv[2] if len(sys.argv) > 2 else "16:00"


def log(s):
    linea = f"{datetime.now():%H:%M:%S}  {s}"
    print(linea, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def a_et(dt):
    """UTC (aware, como lo devuelve IBKR) -> ET naive, que es como se PIDEN los ticks."""
    return dt.replace(tzinfo=None) + timedelta(hours=UTC_A_ET) if dt.tzinfo else dt


# ---------- BD: se crea ANTES de pedir nada, y admite reanudacion ----------
db = sqlite3.connect(DB)
db.execute("""CREATE TABLE IF NOT EXISTS trades_raw (
    ts_et TEXT, minuto TEXT, price REAL, size REAL, exchange TEXT, cond TEXT,
    UNIQUE(ts_et, price, size, exchange, cond))""")
db.commit()

hi = datetime.strptime(f"2026-08-12 {H_INI}", "%Y-%m-%d %H:%M")
hf = datetime.strptime(f"2026-08-12 {H_FIN}", "%Y-%m-%d %H:%M")

ya = db.execute("select count(*), max(ts_et) from trades_raw").fetchone()
if ya[0]:
    hi = datetime.strptime(f"2026-08-12 {ya[1]}", "%Y-%m-%d %H:%M:%S")
    log(f"REANUDA: la BD ya tiene {ya[0]} ticks, el ultimo en {ya[1]}. Se sigue desde ahi.")
else:
    log(f"ARRANCA de cero {H_INI}-{H_FIN}. La app en vivo (clientId 7) no se toca.")

ib = IB()
ib.connect(HOST, PORT, clientId=CID, timeout=15)
log(f"conectado clientId={CID}")
spy = Stock("SPY", "SMART", "USD")
ib.qualifyContracts(spy)

t = hi
total = ya[0]
for it in range(MAX_IT):
    try:
        lote = ib.reqHistoricalTicks(spy, t, hf, 1000, "TRADES", useRth=True)
    except Exception as e:
        log(f"  error {type(e).__name__}: {e} -- reintento unico")
        ib.sleep(PAUSA)
        try:
            lote = ib.reqHistoricalTicks(spy, t, hf, 1000, "TRADES", useRth=True)
        except Exception as e2:
            log(f"  ABANDONA en {t:%H:%M:%S}: {e2}")
            break
    if not lote:
        log(f"  lote vacio en {t:%H:%M:%S} -> fin")
        break

    filas = []
    for x in lote:
        et = a_et(x.time)
        filas.append((et.strftime("%H:%M:%S"), et.strftime("%H:%M"), float(x.price),
                      float(x.size), x.exchange, x.specialConditions))
    # INSERT OR IGNORE + UNIQUE: el dedup lo hace la BD, no un set en memoria que se pierde
    antes = db.execute("select count(*) from trades_raw").fetchone()[0]
    db.executemany("insert or ignore into trades_raw values (?,?,?,?,?,?)", filas)
    db.commit()
    total = db.execute("select count(*) from trades_raw").fetchone()[0]
    nuevos = total - antes

    ult = a_et(lote[-1].time)
    log(f"  it={it+1} desde {t:%H:%M:%S} -> {len(lote)} ticks, {nuevos} nuevos, "
        f"GUARDADOS {total}, va por {ult:%H:%M:%S}")
    if ult >= hf:
        log("  alcanzado el final del rango")
        break
    t = ult + timedelta(seconds=1) if nuevos == 0 else ult
    ib.sleep(PAUSA)

ib.disconnect()
n, ini_, fin_ = db.execute("select count(*), min(ts_et), max(ts_et) from trades_raw").fetchone()
log(f"FIN. {n} ticks guardados en {DB}, de {ini_} a {fin_}")
db.close()
