# -*- coding: utf-8 -*-
"""COLD RUN del GAP D: PREMIUM FANTASMA al soltar y volver a seguir un contrato.

EL BUG (observado en vivo el 2026-08-11):
    12:24:11  SENAL call re-centrada -> 771C
    12:23  net_call=-1.257.061   vela C=   19.159
    12:24  net_call=  +652.900   vela C=1.909.961   <- +1,9M en un minuto: IMPOSIBLE

MECANISMO (leido en logica ejecutable, no en comentarios):
  - `_on_ticks:1823-1827` calcula  dvol = tk.volume - prev_vol[conId].  `tk.volume` es el
    volumen ACUMULADO DEL DIA de ese contrato.
  - `refresh_strikes` sustituye self.call/self.put y llama a `_soltar_mkt`, que cancelaba el
    market data pero NO borraba `prev_vol[conId]`.
  - Si el SPY vuelve sobre sus pasos, ese strike se re-suscribe. Su volumen ha seguido
    creciendo TODO el rato. El primer tick hace dvol = volumen_de_ahora - volumen_de_entonces
    y mete de golpe todo lo negociado mientras no mirabamos.
  - El bloque de la LINEA BASE ya hacia `prev_vol.pop(cid)`; SENAL, EJECUCION y BANDA no.

ADEMAS (corrige una hipotesis previa mia): el bloque del TAPE esta DENTRO del guard
`if dvol <= 0: continue`, asi que el fantasma tambien contamina el tape: no solo la columna
`premium_dvol`, sino la EXISTENCIA de la fila.

LO QUE HAY QUE DEMOSTRAR:
  1. `_soltar_mkt` REAL olvida prev_vol y band_prev_vol.
  2. Escenario completo con `_on_ticks` y `refresh_strikes` REALES: soltar -> el contrato
     sigue negociando -> volver a seguirlo NO genera premium fantasma.
  3. CONTROL: el flujo normal (sin soltar) se sigue contando igual. No se rompe el caso feliz.
  4. Si `cancelMktData` LANZA, los pop se hacen igual (van fuera del try).
  5. El tape no gana filas fantasma.
  6. La LINEA BASE, que ya funcionaba, sigue funcionando.
"""
import math
import os
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Permite apuntar a una copia BASELINE del codigo para el diferencial A/B.
BASE = os.environ.get("SPYDIR_BASE", r"C:\Users\eulis\proyectos\open-premium-ibkr")
sys.path.insert(0, BASE)
import logging as _lg
import spy_direction as S

S.ENABLE_TOAST = False
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


class TK:
    def __init__(self, contract, last, volume, bid, ask, lastSize=None):
        self.contract, self.last, self.volume = contract, last, volume
        self.bid, self.ask, self.lastSize = bid, ask, lastSize


class FakeIB:
    """Solo la frontera con el broker. La logica bajo prueba es la REAL."""
    def __init__(self, romper_cancel=False):
        self.cancelados, self.pedidos = [], []
        self.romper_cancel = romper_cancel

    def cancelMktData(self, c):
        if self.romper_cancel:
            raise RuntimeError("IB caido")
        self.cancelados.append(c.conId)

    def reqMktData(self, c, *a, **k):
        self.pedidos.append(c.conId)

    def qualifyContracts(self, *a, **k):
        return list(a)

    def isConnected(self):
        return True


def opt(strike, right, expiry="20260811"):
    o = S.Option(S.SYMBOL, expiry, strike, right, "SMART", tradingClass=S.SYMBOL)
    o.conId = int(strike * 10 + (1 if right == "C" else 2))
    return o


def nueva(romper_cancel=False):
    a = S.SpyDirection(demo=True)
    a.demo = False
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.ib = FakeIB(romper_cancel)
    a._update_signal = lambda: None
    a._nuevo_opt = lambda s, r: opt(s, r)
    a.expiry = "20260811"
    a.strikes = [768.0, 769.0, 770.0, 771.0, 772.0, 773.0, 774.0, 775.0]
    a.call, a.put = opt(771, "C"), opt(772, "P")
    a.info_base, a._base_ct, a.base_expiries = {}, {}, []
    a.band_contracts = []
    a.accum, a.today_prem, a.accum_net, a.today_net = {}, {}, {}, {}
    a.prev_vol, a.band_prev_vol = {}, {}
    a.net_call = a.net_put = 0.0
    a._tape_buf, a._tape_n = [], 0
    a.pos, a.order = "FLAT", None
    return a


K771C = ("20260811", 771.0, "C")

# ============================================================ 1
print("=" * 78)
print("1) `_soltar_mkt` REAL olvida el volumen previo")
print("=" * 78)
app = nueva()
c = app.call
app.prev_vol[c.conId] = 5000.0
app.band_prev_vol[c.conId] = 7000.0
app._soltar_mkt(c)
check(c.conId not in app.prev_vol, "prev_vol olvidado tras soltar")
check(c.conId not in app.band_prev_vol, "band_prev_vol olvidado tras soltar")
check(c.conId in app.ib.cancelados, "y se cancelo el market data (no se rompio lo de antes)")

# ============================================================ 2  (EL PUNTO)
print()
print("=" * 78)
print("2) EL PUNTO: soltar -> sigue negociando -> volver a seguirlo")
print("=" * 78)
app = nueva()
c771 = app.call
app._on_ticks([TK(c771, 1.00, 1000, 0.99, 1.01)])          # siembra prev_vol
app._on_ticks([TK(c771, 1.00, 1200, 0.99, 1.01)])          # dvol=200 real
legitimo = app.today_prem.get(K771C, 0.0)
check(abs(legitimo - 1.00 * 200 * 100) < 1e-6,
      f"flujo legitimo antes de soltar = {legitimo:,.0f}")

# el SPY sube -> refresh_strikes REAL re-centra la call a 773 y suelta la 771
app.spy_price = 773.4
app.refresh_strikes()
check(app.call.strike == 773.0, f"la senal se re-centro -> {app.call.strike}C")
check(c771.conId in app.ib.cancelados, "la 771C fue soltada")

# mientras no la miramos, la 771C sigue negociando: su volumen del dia llega a 90.000
# el SPY vuelve -> refresh_strikes REAL la re-suscribe
app.spy_price = 771.2
app.refresh_strikes()
check(app.call.strike == 771.0, f"la senal vuelve a la 771C -> {app.call.strike}C")
app.call.conId = c771.conId
app._on_ticks([TK(app.call, 1.00, 90000, 0.99, 1.01)])

despues = app.today_prem.get(K771C, 0.0)
fantasma = despues - legitimo
check(abs(fantasma) < 1e-6,
      f"NO hay premium fantasma al volver a seguirla -> inyectado {fantasma:,.0f} "
      f"(con el bug serian {(90000 - 1200) * 1.00 * 100:,.0f})")

# ============================================================ 3  CONTROL
print()
print("=" * 78)
print("3) CONTROL: el flujo normal se sigue contando igual")
print("=" * 78)
app._on_ticks([TK(app.call, 1.00, 90500, 0.99, 1.01)])     # dvol=500 tras la siembra
ctrl = app.today_prem.get(K771C, 0.0) - despues
check(abs(ctrl - 1.00 * 500 * 100) < 1e-6,
      f"el siguiente tick SI cuenta su delta -> {ctrl:,.0f} (esperado 50.000)")

app2 = nueva()
cc = app2.call
app2._on_ticks([TK(cc, 2.00, 100, 1.99, 2.01)])
app2._on_ticks([TK(cc, 2.00, 300, 1.99, 2.01)])
check(abs(app2.today_prem.get(K771C, 0.0) - 2.00 * 200 * 100) < 1e-6,
      "sin soltar nada, el acumulado es exactamente el de siempre")

# ============================================================ 4
print()
print("=" * 78)
print("4) Si `cancelMktData` LANZA, los pop se hacen igual")
print("=" * 78)
app3 = nueva(romper_cancel=True)
c3 = app3.call
app3.prev_vol[c3.conId] = 1234.0
app3.band_prev_vol[c3.conId] = 4321.0
app3._soltar_mkt(c3)
check(c3.conId not in app3.prev_vol,
      "prev_vol olvidado aunque cancelMktData reviente (los pop van FUERA del try)")
check(c3.conId not in app3.band_prev_vol, "band_prev_vol olvidado igualmente")

# ============================================================ 5
print()
print("=" * 78)
print("5) El TAPE no gana filas fantasma")
print("=" * 78)
app4 = nueva()
c4 = app4.call
app4._on_ticks([TK(c4, 1.00, 1000, 0.99, 1.01, lastSize=5)])
app4._on_ticks([TK(c4, 1.00, 1100, 0.99, 1.01, lastSize=100)])
app4._flush_tape(forzar=True)
n_antes = app4.db.execute("SELECT COUNT(*) FROM tape").fetchone()[0]
app4._soltar_mkt(c4)
app4._on_ticks([TK(c4, 1.00, 80000, 0.99, 1.01, lastSize=7)])
app4._flush_tape(forzar=True)
n_despues = app4.db.execute("SELECT COUNT(*) FROM tape").fetchone()[0]
check(n_despues == n_antes,
      f"el 1er tick tras re-suscribir solo SIEMBRA, no deja fila -> {n_antes} -> {n_despues}")
peor = app4.db.execute("SELECT MAX(dvol) FROM tape").fetchone()[0] or 0
check(peor <= 100,
      f"ninguna fila del tape lleva un dvol fantasma -> max dvol = {peor:,.0f}")

# ============================================================ 6
print()
print("=" * 78)
print("6) La LINEA BASE, que ya funcionaba, sigue funcionando")
print("=" * 78)
app5 = nueva()
cb = opt(770, "C", "20260812")
app5.info_base[cb.conId] = ("20260812", 770.0, "C")
app5._base_ct[cb.conId] = cb
app5.prev_vol[cb.conId] = 999.0
app5._soltar_mkt(cb)
check(cb.conId not in app5.prev_vol, "el contrato de baseline tambien olvida su volumen")

print()
print("=" * 78)
if FAILS:
    print("FALLOS: %d" % len(FAILS))
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("GAP D OK: todos los checks pasaron")
