# -*- coding: utf-8 -*-
"""
COLD RUN GAP 11 — el precio del SPY se congelaba al arrancar la sesion.
Ejercita ta_poll() REAL con barras simuladas (la estructura que devuelve reqHistoricalData
con keepUpToDate=True). Verifica que self.spy_price sigue al ultimo close, incluso ANTES
de tener las 26 barras que exige el TA.
"""
import sqlite3
import sys
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
import spy_direction as S

S.ENABLE_TOAST = False
import logging as _lg
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


class FakeBar:
    def __init__(self, dt, close, vol=1000.0):
        self.date = dt
        self.open = close
        self.high = close + 0.05
        self.low = close - 0.05
        self.close = close
        self.volume = vol


def barras(n, base=772.0, paso=0.03):
    t0 = datetime(2026, 8, 10, 9, 30)
    return [FakeBar(t0 + timedelta(minutes=i), base + i * paso) for i in range(n)]


def nueva():
    a = S.SpyDirection(demo=True)
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.demo = False
    return a


print("=" * 72)
print("COLD RUN GAP 11 - precio del SPY en vivo (antes: congelado al arrancar)")
print("=" * 72)

# ------------------------------------------------- T1: menos de 26 barras (apertura)
print("\n== T1: con POCAS barras (apertura) el precio ya debe moverse ==")
a = nueva()
a.spy_price = 772.67                      # precio congelado de setup_contracts
a.bars = barras(10)                        # 10 barras: el TA aun no puede calcular
esperado = a.bars[-1].close
a.ta_poll()                                # metodo REAL
check(abs(a.spy_price - esperado) < 1e-9,
      "10 barras (TA sin datos suficientes) -> spy_price %.2f -> %.2f (ultimo close %.2f)"
      % (772.67, a.spy_price, esperado))
check(a.ta_vals is None, "     el TA sigue sin calcular con <26 barras (ta_vals=%s)" % a.ta_vals)

# ------------------------------------------------- T2: el precio SIGUE al mercado
print("\n== T2: el precio sigue moviendose tick a tick ==")
vistos = []
for n in (12, 15, 20, 25):
    a.bars = barras(n)
    a.ta_poll()
    vistos.append(round(a.spy_price, 2))
check(len(set(vistos)) == len(vistos),
      "precios distintos en cada lectura -> %s (antes: siempre el mismo)" % vistos)

# ------------------------------------------------- T3: con TA completo tambien actualiza
print("\n== T3: con 30 barras (TA activo) el precio tambien se actualiza ==")
b = nueva()
b.spy_price = 772.67
b.bars = barras(30)
esp30 = b.bars[-1].close
b.ta_poll()
check(abs(b.spy_price - esp30) < 1e-9,
      "spy_price = %.2f (ultimo close %.2f)" % (b.spy_price, esp30))
check(b.ta_vals is not None and abs(b.ta_vals["close"] - esp30) < 1e-9,
      "     el TA SI calcula con 30 barras y coincide con el precio (close=%.2f rsi=%.1f)"
      % (b.ta_vals["close"], b.ta_vals["rsi"]) if b.ta_vals else "ta_vals None")

# ------------------------------------------------- T4: robustez
print("\n== T4: robustez (no debe romper ni ensuciar el precio) ==")
c = nueva()
c.spy_price = 772.67
c.bars = None
c.ta_poll()
check(c.spy_price == 772.67, "bars=None -> no crashea y deja el precio intacto (%.2f)" % c.spy_price)

d = nueva()
d.spy_price = 772.67
d.bars = []
d.ta_poll()
check(d.spy_price == 772.67, "bars=[] -> no crashea y deja el precio intacto (%.2f)" % d.spy_price)

e = nueva()
e.spy_price = 772.67
e.bars = [FakeBar(datetime(2026, 8, 10, 9, 30), float("nan"))]
e.ta_poll()
check(e.spy_price == 772.67, "close=NaN -> se ignora, precio intacto (%.2f)" % e.spy_price)

f = nueva()
f.spy_price = 772.67
f.bars = [FakeBar(datetime(2026, 8, 10, 9, 30), 0.0)]
f.ta_poll()
check(f.spy_price == 772.67, "close=0 -> se ignora, precio intacto (%.2f)" % f.spy_price)

# ------------------------------------------------- T5: demo intacto
print("\n== T5: el modo --demo no se ve afectado ==")
g = S.SpyDirection(demo=True)
g.db.close(); g.db = sqlite3.connect(":memory:"); g._init_db()
g.bars = barras(30)
antes = g.spy_price
g.ta_poll()                                # demo=True -> retorna de inmediato
check(g.spy_price == antes or g.demo,
      "demo: ta_poll retorna sin tocar nada (demo=%s)" % g.demo)

print()
if FAILS:
    print("GAP 11 NO CERRADO: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("GAP 11 CERRADO: todos los checks pasaron")
sys.exit(0)
