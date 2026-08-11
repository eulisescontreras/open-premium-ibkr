# -*- coding: utf-8 -*-
"""COLD RUN del PRECIO por minuto de los contratos (2026-08-11, peticion del usuario).

Hasta ahora premium_minute guardaba cuanto DINERO pasa por cada strike pero NO cuanto VALE el
contrato: el unico precio de toda la BD era el del contrato comprado, en posicion_minuto, y solo
mientras la posicion estaba abierta.

LO QUE HAY QUE DEMOSTRAR:
  1. _precio_de encuentra el ticker en las 3 fuentes (banda, baseline, senal).
  2. mid=(bid+ask)/2 y spread=ask-bid, comprobados A MANO.
  3. NaN / 0 de IBKR -> None -> NULL (no un 0 falso: un contrato no cotiza a cero).
  4. Contrato SIN ticker (expiry ya vencida que sigue en accum) -> todo NULL, sin excepcion.
  5. EL CASO CRITICO: _log_minute y _persist_walls escriben sobre la MISMA clave. Hay que
     probar que el precio NO borra OI/gamma/net_prem y que OI/gamma NO borran el precio,
     en los DOS ordenes posibles.
  6. Los 40 de la banda reciben precio CADA MINUTO (antes solo cada 3 min).
  7. Coste en tiempo de _log_minute.

Se ejercitan las FUNCIONES REALES _precio_de, _log_minute y _persist_walls.
"""
import math
import sqlite3
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
import logging as _lg
import spy_direction as S

S.ENABLE_TOAST = False
LINEAS = []


class Captura(_lg.Handler):
    def emit(self, record):
        LINEAS.append(record.getMessage())


for _l in (S.ACT, S.LOG):
    _l.handlers = []
S.ACT.addHandler(Captura())
S.LOG.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


# ------------------------------------------------------------------ dobles
class FakeTicker:
    def __init__(self, bid=None, ask=None, last=None, gamma=None, oi=None):
        self.bid, self.ask, self.last = bid, ask, last
        self.volume = 1000.0
        self.callOpenInterest = oi
        self.putOpenInterest = oi
        self.modelGreeks = type("G", (), {"gamma": gamma})() if gamma is not None else None


class FakeIB:
    """ib_insync indexa por id(objeto); aqui se replica con un dict por id()."""
    def __init__(self):
        self._t = {}

    def poner(self, contrato, ticker):
        self._t[id(contrato)] = ticker

    def ticker(self, c):
        return self._t.get(id(c))

    def isConnected(self):
        return True


def opt(strike, right, expiry="20260811"):
    return S.Option(S.SYMBOL, expiry, strike, right, "SMART", tradingClass=S.SYMBOL)


def nueva():
    a = S.SpyDirection(demo=True)
    a.demo = False
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.ib = FakeIB()
    a.spy_price = 773.0
    a.expiry = "20260811"
    a.state = "UP"
    a.net_call = a.net_put = 0.0
    a.last_diff = a.last_thr = a.last_momentum = 0.0
    a.accum = {}
    a.today_prem = {}
    a.today_net = {}
    a.accum_net = {}
    a.net_prem = {}
    a.today_vol = {}
    a.band_contracts = []
    a.info_base = {}
    a._base_ct = {}
    a.call = a.put = None
    return a


# ============================================================ 1
print("=" * 78)
print("1) _precio_de encuentra el ticker en las 3 fuentes")
print("=" * 78)
app = nueva()

c_banda = opt(773, "C")
app.band_contracts = [c_banda]
app.ib.poner(c_banda, FakeTicker(bid=1.20, ask=1.24, last=1.22, gamma=0.13, oi=5000))

c_base = opt(775, "P", "20260813")
c_base.conId = 555001
app.info_base = {555001: ("20260813", 775.0, "P")}
app._base_ct = {555001: c_base}
app.ib.poner(c_base, FakeTicker(bid=2.00, ask=2.10, last=2.05))

c_sig = opt(772, "C")
app.call = c_sig
app.ib.poner(c_sig, FakeTicker(bid=1.80, ask=1.86, last=1.84))

p1 = app._precio_de("20260811", 773.0, "C")
check(p1["bid"] == 1.20 and p1["ask"] == 1.24 and p1["last"] == 1.22,
      f"BANDA   773C -> bid={p1['bid']} ask={p1['ask']} last={p1['last']}")
p2 = app._precio_de("20260813", 775.0, "P")
check(p2["bid"] == 2.00 and p2["ask"] == 2.10,
      f"BASELINE 775P (expiry futura) -> bid={p2['bid']} ask={p2['ask']}")
p3 = app._precio_de("20260811", 772.0, "C")
check(p3["bid"] == 1.80 and p3["ask"] == 1.86,
      f"SENAL   772C -> bid={p3['bid']} ask={p3['ask']}")

# ============================================================ 2
print()
print("=" * 78)
print("2) mid y spread: comprobados A MANO")
print("=" * 78)
check(abs(p1["mid"] - (1.20 + 1.24) / 2) < 1e-9, f"mid 773C = {p1['mid']} == (1.20+1.24)/2 = 1.22")
check(abs(p1["spread"] - (1.24 - 1.20)) < 1e-9, f"spread 773C = {p1['spread']} == 1.24-1.20 = 0.04")
check(abs(p2["mid"] - 2.05) < 1e-9, f"mid 775P = {p2['mid']} == 2.05")
check(abs(p2["spread"] - 0.10) < 1e-9, f"spread 775P = {p2['spread']} == 0.10")

# ============================================================ 3
print()
print("=" * 78)
print("3) NaN y 0 de IBKR -> None (NULL), nunca un 0 falso")
print("=" * 78)
c_nan = opt(780, "C")
app.band_contracts.append(c_nan)
app.ib.poner(c_nan, FakeTicker(bid=float("nan"), ask=float("nan"), last=float("nan")))
pn = app._precio_de("20260811", 780.0, "C")
check(all(pn[k] is None for k in ("bid", "ask", "mid", "last", "spread")),
      f"ticker con NaN -> todo None: {pn}")

c_cero = opt(781, "C")
app.band_contracts.append(c_cero)
app.ib.poner(c_cero, FakeTicker(bid=0.0, ask=0.0, last=0.0))
pz = app._precio_de("20260811", 781.0, "C")
check(all(pz[k] is None for k in ("bid", "ask", "mid", "last")),
      f"ticker con 0 -> None (un contrato no cotiza a cero, es 'sin cotizacion'): {pz}")

c_medio = opt(782, "C")
app.band_contracts.append(c_medio)
app.ib.poner(c_medio, FakeTicker(bid=0.50, ask=float("nan"), last=0.52))
pm = app._precio_de("20260811", 782.0, "C")
check(pm["bid"] == 0.50 and pm["ask"] is None and pm["mid"] is None and pm["spread"] is None,
      f"con bid pero sin ask: mid/spread None, NO se inventan -> {pm}")

# ============================================================ 4
print()
print("=" * 78)
print("4) Contrato SIN ticker (expiry VENCIDA que sigue en accum) -> todo NULL")
print("=" * 78)
pv = app._precio_de("20260810", 773.0, "C")     # venció ayer: no hay contrato suscrito
check(all(pv[k] is None for k in ("bid", "ask", "mid", "last", "spread")),
      f"expiry vencida 20260810 -> todo None: {pv}")

# ============================================================ 5  (EL CRITICO)
print()
print("=" * 78)
print("5) CRITICO: _log_minute y _persist_walls sobre la MISMA clave, sin pisarse")
print("=" * 78)
app2 = nueva()
cb = opt(773, "C")
app2.band_contracts = [cb]
app2.ib.poner(cb, FakeTicker(bid=1.20, ask=1.24, last=1.22, gamma=0.13, oi=5000))
app2.accum = {("20260811", 773.0, "C"): 900000.0}
app2.today_prem = {("20260811", 773.0, "C"): 500000.0}
app2.net_prem = {("20260811", 773.0, "C"): -1234.0}
app2.today_vol = {("20260811", 773.0, "C"): 4321.0}
app2.walls = {"spot": 773.0, "put_wall": 770, "call_wall": 776,
              "max_pain_static": 772, "max_pain_dyn": 773, "prem_center": 773.1}
app2.gex = {"gex_total": 1.0e11, "regime": "LONG", "gamma_flip": 772.5}
app2.bars_stale = False

SQL = ("SELECT cum_prem,day_prem,net_prem,open_interest,gamma,day_vol,bid,ask,mid,last,spread "
       "FROM premium_minute WHERE strike=773 AND right='C'")

# --- orden A: primero el precio (_log_minute), despues walls (_persist_walls) ---
app2._log_minute(None, "2026-08-11 12:00:00")
r_a1 = app2.db.execute(SQL).fetchone()
check(r_a1 and r_a1[6] == 1.20 and r_a1[8] == 1.22,
      f"A) tras _log_minute: precio guardado -> bid={r_a1[6]} mid={r_a1[8]}")

import datetime as _dt
_orig = S.datetime


class _FakeDT:
    @staticmethod
    def now():
        return _dt.datetime(2026, 8, 11, 12, 0, 0)     # MISMO minuto


S.datetime = _FakeDT
try:
    app2._persist_walls({773.0: 5000.0}, {}, {773.0: 0.13}, {})
finally:
    S.datetime = _orig
r_a2 = app2.db.execute(SQL).fetchone()
check(r_a2[3] == 5000.0 and r_a2[4] == 0.13,
      f"A) _persist_walls escribio OI={r_a2[3]} gamma={r_a2[4]}")
check(r_a2[6] == 1.20 and r_a2[8] == 1.22,
      f"A) ...y NO borro el precio -> bid={r_a2[6]} mid={r_a2[8]}   <-- EL CASO CRITICO")
check(r_a2[2] == -1234.0 and r_a2[5] == 4321.0,
      f"A) net_prem={r_a2[2]} y day_vol={r_a2[5]} intactos")

# --- orden B: primero walls, despues el precio ---
app3 = nueva()
cb3 = opt(773, "C")
app3.band_contracts = [cb3]
app3.ib.poner(cb3, FakeTicker(bid=1.20, ask=1.24, last=1.22, gamma=0.13, oi=5000))
app3.accum = {("20260811", 773.0, "C"): 900000.0}
app3.today_prem = {("20260811", 773.0, "C"): 500000.0}
app3.net_prem = {("20260811", 773.0, "C"): -1234.0}
app3.today_vol = {("20260811", 773.0, "C"): 4321.0}
app3.walls = dict(app2.walls)
app3.gex = dict(app2.gex)
app3.bars_stale = False
S.datetime = _FakeDT
try:
    app3._persist_walls({773.0: 5000.0}, {}, {773.0: 0.13}, {})
finally:
    S.datetime = _orig
app3._log_minute(None, "2026-08-11 12:00:00")
r_b = app3.db.execute(SQL).fetchone()
check(r_b[3] == 5000.0 and r_b[4] == 0.13,
      f"B) tras _log_minute: OI={r_b[3]} gamma={r_b[4]} SIGUEN ahi  <-- EL CASO CRITICO")
check(r_b[6] == 1.20 and r_b[8] == 1.22, f"B) y el precio esta -> bid={r_b[6]} mid={r_b[8]}")
check(r_b[2] == -1234.0 and r_b[5] == 4321.0,
      f"B) net_prem={r_b[2]} y day_vol={r_b[5]} intactos")

# ============================================================ 6
print()
print("=" * 78)
print("6) Los contratos de la BANDA reciben precio CADA MINUTO (antes solo cada 3)")
print("=" * 78)
app4 = nueva()
banda = []
for k in range(770, 780):
    for rgt in ("C", "P"):
        c = opt(float(k), rgt)
        banda.append(c)
        app4.ib.poner(c, FakeTicker(bid=1.0 + k / 1000, ask=1.02 + k / 1000, last=1.01 + k / 1000))
app4.band_contracts = banda
app4.accum = {}          # NADA en accum: la banda no esta ahi, es justo el punto
app4._log_minute(None, "2026-08-11 12:05:00")
n = app4.db.execute("SELECT COUNT(*) FROM premium_minute WHERE hora='12:05'").fetchone()[0]
check(n == len(banda),
      f"{n} filas de banda escritas por _log_minute (esperadas {len(banda)}), sin estar en accum")
con_precio = app4.db.execute("SELECT COUNT(*) FROM premium_minute WHERE hora='12:05' "
                             "AND bid IS NOT NULL AND mid IS NOT NULL").fetchone()[0]
check(con_precio == len(banda), f"las {con_precio} traen bid y mid")
# y no se crean filas vacias para contratos sin cotizacion
c_mudo = opt(799, "C")
app4.band_contracts.append(c_mudo)
app4.ib.poner(c_mudo, FakeTicker())
app4._log_minute(None, "2026-08-11 12:06:00")
n799 = app4.db.execute("SELECT COUNT(*) FROM premium_minute WHERE hora='12:06' "
                       "AND strike=799").fetchone()[0]
check(n799 == 0, "un contrato sin cotizacion NO crea una fila vacia")

# ============================================================ 6b (REGRESION REAL)
print()
print("=" * 78)
print("6b) Contrato SIN lastTradeDateOrContractMonth no puede tumbar la persistencia")
print("=" * 78)
# Regresion REAL detectada por el diferencial el 2026-08-11: spy_walls_coldrun paso de 58 a 56
# checks. _precio_de accedia a c.lastTradeDateOrContractMonth directamente; un contrato sin ese
# atributo lanzaba AttributeError DENTRO del try de _persist_walls -> el bucle abortaba y
# walls se quedaba con CERO filas en premium_minute, sin mas aviso que una linea de log.


class ContratoMinimo:
    """Como el FakeContract de spy_walls_coldrun: sin expiry."""
    def __init__(self, strike, right):
        self.strike, self.right = strike, right
        self.symbol, self.secType = "SPY", "OPT"


app6 = nueva()
cm = ContratoMinimo(773.0, "C")
app6.band_contracts = [cm]
app6.ib.poner(cm, FakeTicker(bid=1.10, ask=1.14, last=1.12, gamma=0.12, oi=300))
app6.expiry = "20260814"
app6.walls = {"spot": 773.0, "put_wall": 765, "call_wall": 775,
              "max_pain_static": 770, "max_pain_dyn": 770, "prem_center": 773.0}
app6.gex = {"gex_total": 1.0, "regime": "LONG", "gamma_flip": 772.0}
app6.bars_stale = False
try:
    app6._persist_walls({773.0: 300.0}, {}, {773.0: 0.12}, {})
    sin_excepcion = True
except Exception as e:
    sin_excepcion = False
    print("      excepcion:", type(e).__name__, e)
check(sin_excepcion, "_persist_walls no revienta con un contrato sin expiry")
fila = app6.db.execute("SELECT open_interest,gamma,bid,mid FROM premium_minute "
                       "WHERE strike=773 AND right='C'").fetchone()
check(fila is not None, f"LA FILA SE ESCRIBE (era el fallo: 0 filas) -> {fila}")
if fila:
    check(fila[0] == 300.0 and fila[1] == 0.12,
          f"open_interest={fila[0]} y gamma={fila[1]} persistidos  <-- LA REGRESION")
    check(fila[2] == 1.10 and fila[3] == 1.12,
          f"y ademas el precio: bid={fila[2]} mid={fila[3]}")
p6 = app6._precio_de("20260814", 773.0, "C")
check(p6["bid"] == 1.10, f"_precio_de resuelve por strike/right cuando falta la expiry -> {p6['bid']}")

# ============================================================ 7
print()
print("=" * 78)
print("7) Coste en tiempo de _log_minute")
print("=" * 78)
app5 = nueva()
banda5 = []
for k in range(763, 785):
    for rgt in ("C", "P"):
        c = opt(float(k), rgt)
        banda5.append(c)
        app5.ib.poner(c, FakeTicker(bid=1.0, ask=1.02, last=1.01))
app5.band_contracts = banda5
for i, exp in enumerate(("20260812", "20260813", "20260814")):
    for k in range(769, 779):
        c = opt(float(k), "C", exp)
        c.conId = 900000 + i * 100 + k
        app5.info_base[c.conId] = (exp, float(k), "C")
        app5._base_ct[c.conId] = c
        app5.ib.poner(c, FakeTicker(bid=1.0, ask=1.02, last=1.01))
        app5.accum[(exp, float(k), "C")] = 1000.0
        app5.today_prem[(exp, float(k), "C")] = 500.0
t0 = time.perf_counter()
for i in range(10):
    app5._log_minute(None, "2026-08-11 13:%02d:00" % i)
ms = (time.perf_counter() - t0) / 10 * 1000
filas = app5.db.execute("SELECT COUNT(*) FROM premium_minute").fetchone()[0]
check(ms < 200, f"_log_minute con {len(banda5)} de banda + {len(app5.accum)} de accum: "
                f"{ms:.1f} ms/llamada ({filas} filas en 10 minutos)")

print()
print("=" * 78)
print(("TODO VERDE" if not FAILS else f"{len(FAILS)} FALLOS: " + " | ".join(FAILS)))
print("=" * 78)
sys.exit(1 if FAILS else 0)
