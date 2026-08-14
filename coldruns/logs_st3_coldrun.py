# -*- coding: utf-8 -*-
"""CORRIDA EN FRIO de los LOGS del ST-3 anadidos el 2026-08-14.
Reutiliza el patron de coldruns/st3_signal_coldrun.py (R9): barras REALES de spy_bars_year.db,
stream que crece minuto a minuto, y se llama la FUNCION REAL SpyDirection._st3_dir.
Verifica que el log cuenta: serie usada, calentamiento del ATR, direccion, y que NO hace spam.
"""
import os, sys, sqlite3, logging
from datetime import datetime

REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, REPO)
os.chdir(REPO)
import spy_direction as S

DB = os.path.join(REPO, "spy_bars_year.db")
DIA = "2026-03-10"

# --- capturar lo que escribe ACT (el logger real de actividad) ---
CAP = []
class Cap(logging.Handler):
    def emit(self, r):
        CAP.append(r.getMessage())
S.ACT.addHandler(Cap())
S.ACT.setLevel(logging.INFO)

class _Bar:
    __slots__ = ("high", "low", "close", "date")
    def __init__(self, h, l, c, d): self.high=h; self.low=l; self.close=c; self.date=d

con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
filas = con.execute("select hora,high,low,close from bars where fecha=? and hora<='16:00' "
                    "order by hora", (DIA,)).fetchall()
con.close()
y, m, dd = map(int, DIA.split("-"))
bars = [_Bar(h_, l_, c_, datetime(y, m, dd, int(ho[:2]), int(ho[3:5]))) for ho, h_, l_, c_ in filas]
print("Barras REALES del %s: %d" % (DIA, len(bars)))

# instancia real, sin __init__ (igual que los cold runs del repo)
app = S.SpyDirection.__new__(S.SpyDirection)
app.demo = True
app.bars = None
app.bars_st3 = None

print("\n" + "=" * 76)
print("A) SIN barras -> el log debe DECIRLO (antes era un return None mudo)")
print("=" * 76)
CAP.clear()
r = app._st3_dir()
print("  _st3_dir() = %r" % r)
for l in CAP: print("  LOG> %s" % l)
okA = any("SIN BARRAS" in l for l in CAP)
print("  => %s" % ("OK" if okA else "FAIL: no se logueo la ausencia de barras"))

print("\n" + "=" * 76)
print("B) CALENTAMIENTO del ATR + DIRECCION, alimentando minuto a minuto")
print("=" * 76)
CAP.clear()
dirs, vistos = [], []
for i in range(2, len(bars) + 1):
    app.bars_st3 = bars[:i]
    d = app._st3_dir()
    dirs.append(d)
n_cal = sum(1 for l in CAP if "calentando ATR" in l)
n_dir = sum(1 for l in CAP if "direccion=" in l)
n_fue = sum(1 for l in CAP if "serie=" in l)
print("  pasos evaluados      : %d" % len(dirs))
print("  primera direccion en : paso %s" % next((i for i, x in enumerate(dirs) if x), None))
print("  direcciones +1/-1    : %d" % sum(1 for x in dirs if x in (1, -1)))
print("  --- lineas de log emitidas (ANTI-SPAM: %d pasos) ---" % len(dirs))
print("  serie=...      : %d" % n_fue)
print("  calentando ATR : %d" % n_cal)
print("  direccion=...  : %d" % n_dir)
print("  TOTAL          : %d" % len(CAP))
print("\n  --- muestra ---")
for l in CAP[:3]: print("  LOG> %s" % l)
print("  ...")
for l in CAP[-3:]: print("  LOG> %s" % l)
okB1 = n_fue == 1                       # la serie no cambia -> 1 sola linea
okB2 = n_cal >= 1 and n_dir >= 1
okB3 = len(CAP) < len(dirs) / 3         # anti-spam real
print("\n  serie logueada 1 sola vez (no spam) : %s" % ("OK" if okB1 else "FAIL (%d)" % n_fue))
print("  hay calentamiento y direccion       : %s" % ("OK" if okB2 else "FAIL"))
print("  log << pasos (anti-spam)            : %s" % ("OK" if okB3 else "FAIL"))

print("\n" + "=" * 76)
print("C) DEGRADACION a RTH-only -> el log debe AVISAR")
print("=" * 76)
CAP.clear()
app.bars_st3 = None
app.bars = bars[:200]
app._st3_diag = {}
app._st3_dir()
for l in CAP: print("  LOG> %s" % l)
okC = any("RTH-only" in l and "DEGRADADO" in l for l in CAP)
print("  => %s" % ("OK" if okC else "FAIL: no avisa de la degradacion"))

print("\n" + "=" * 76)
print("RESULTADO")
print("=" * 76)
todo = okA and okB1 and okB2 and okB3 and okC
print("  %s" % ("TODOS LOS LOGS VERIFICADOS CON DATOS REALES" if todo else "*** HAY FALLOS ***"))
sys.exit(0 if todo else 1)
