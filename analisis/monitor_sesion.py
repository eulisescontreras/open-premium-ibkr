# MONITOREO SOLO-LECTURA de la BD del dia. No escribe nada, no toca la app.
import sqlite3, os
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = r"C:\Users\eulis\proyectos\open-premium-ibkr"
HOY = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")
DB = os.path.join(BASE, "spy_history_%s.db" % HOY)
FECHA = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

print("BD: %s  (%.2f MB)" % (os.path.basename(DB), os.path.getsize(DB) / 1024 / 1024))
print("Hora ET: %s\n" % datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S"))

c = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True, timeout=20)
tablas = [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

print("%-22s %9s  %s" % ("TABLA", "FILAS", "ULTIMO REGISTRO DE HOY"))
print("-" * 68)
for t in tablas:
    n = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    cols = [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)]
    ult = ""
    if "hora" in cols and "fecha" in cols:
        r = c.execute("SELECT MAX(hora) FROM %s WHERE fecha=?" % t, (FECHA,)).fetchone()
        nh = c.execute("SELECT COUNT(*) FROM %s WHERE fecha=?" % t, (FECHA,)).fetchone()[0]
        ult = ("ultima %s  (%d filas hoy)" % (r[0], nh)) if r and r[0] else "sin filas de hoy"
    elif "fecha" in cols:
        nh = c.execute("SELECT COUNT(*) FROM %s WHERE fecha=?" % t, (FECHA,)).fetchone()[0]
        ult = "%d filas de hoy" % nh
    print("%-22s %9d  %s" % (t, n, ult))

print("\n" + "=" * 68)
print("SEÑAL / PRECIO (ultimos minutos)")
print("=" * 68)
try:
    for f, h, spy, td in c.execute(
            "SELECT fecha,hora,spy,ta_dir FROM ta_minute WHERE fecha=? "
            "ORDER BY hora DESC LIMIT 5", (FECHA,)):
        print("  %s %s  SPY=%.2f  ta_dir=%s" % (f, h, spy or 0, td))
except Exception as e:
    print("  ta_minute:", e)

print("\n" + "=" * 68)
print("BARRAS 1-MIN (fuente del Supertrend)")
print("=" * 68)
try:
    for h, o, hi, lo, cl, v in c.execute(
            "SELECT hora,open,high,low,close,volume FROM bars_minute WHERE fecha=? "
            "ORDER BY hora DESC LIMIT 5", (FECHA,)):
        print("  %s  O=%.2f H=%.2f L=%.2f C=%.2f vol=%s" % (h, o, hi, lo, cl, v))
except Exception as e:
    print("  bars_minute:", e)

print("\n" + "=" * 68)
print("POSICION / TRADES")
print("=" * 68)
try:
    n = c.execute("SELECT COUNT(*) FROM trades WHERE fecha=?", (FECHA,)).fetchone()[0]
    print("  trades de hoy: %d" % n)
    for r in c.execute("SELECT hora_entrada,right,strike,side,entry_price FROM trades "
                       "WHERE fecha=? ORDER BY id DESC LIMIT 5", (FECHA,)):
        print("   ", r)
except Exception as e:
    print("  trades:", e)
try:
    r = c.execute("SELECT hora,pos,pos_qty FROM posicion_minuto WHERE fecha=? "
                  "ORDER BY hora DESC LIMIT 3", (FECHA,)).fetchall()
    print("  posicion_minuto (ultimas): %s" % (r if r else "vacio"))
except Exception as e:
    print("  posicion_minuto:", e)

print("\n" + "=" * 68)
print("TAPE (ticks del subyacente)")
print("=" * 68)
try:
    n = c.execute("SELECT COUNT(*) FROM tape WHERE fecha=?", (FECHA,)).fetchone()[0]
    r = c.execute("SELECT MAX(hora) FROM tape WHERE fecha=?", (FECHA,)).fetchone()
    print("  filas hoy: %d   ultima: %s" % (n, r[0] if r else "-"))
except Exception as e:
    print("  tape:", e)
c.close()
