# -*- coding: utf-8 -*-
"""COLD RUN del DISPARADOR POR MEDIA CORTA (2026-08-12) — el que decide desde hoy.

Ejercita las FUNCIONES REALES `_senal_media()` y `trade_poll()` con FakeIB (patron de
`ventana_horaria_coldrun.py` y `gapsA_coldrun.py`, regla 9). No reimplementa la regla.

LO QUE DEBE QUEDAR DEMOSTRADO:
  1. La regla es CONTRAINTUITIVA y va en el sentido correcto: precio ARRIBA de la media -> PUT.
  2. Dentro de la banda NO hay señal -> no se abre nada (el sistema se queda FLAT).
  3. Se MANTIENE la posicion hasta MINUTOS_POS aunque la señal gire (es lo que se midio).
  4. Al cumplir MINUTOS_POS se vende con razon "tiempo".
  5. REENTRADA: tras vender se puede volver a comprar, SIN duplicar posicion ni solapar ordenes.
  6. Sin media (ta_vals vacio) NO se opera y se AVISA (no puede quedarse mudo en silencio).
  7. Con USAR_MEDIA=False el comportamiento vuelve a ser el anterior (interruptor A/B limpio).

Correr:  python coldruns/media_coldrun.py     Exit 0 = OK
"""
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
import spy_direction as S                                            # noqa: E402

S.ENABLE_TOAST = False
S.ENABLE_SOUND = False
import logging as _lg                                                # noqa: E402
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


# RELOJ INYECTADO. Sin esto la suite corre con la hora REAL: si se ejecuta despues de las
# 15:45 TODO se va por la rama del EOD (`exit_reason='eod'`, target=FLAT) y los 7 checks de
# trade_poll fallan por un motivo que no tiene nada que ver con lo que se quiere probar.
# Mismo patron que ventana_horaria_coldrun.py: se sustituye la FUENTE de tiempo, no la funcion.
import datetime as _dt                                               # noqa: E402
_TZ = None
try:
    _TZ = S.now_et().tzinfo
except Exception:
    pass


def set_et(hhmm, dia=12):
    """12-ago-2026 = miercoles (habil)."""
    h, m = (int(x) for x in hhmm.split(":"))
    fake = _dt.datetime(2026, 8, dia, h, m, 0, tzinfo=_TZ)
    S.now_et = lambda: fake


set_et("11:00")          # mitad de sesion: ni pre-market, ni STOP_NEW, ni EOD


class FakeIB:
    def isConnected(self):
        return True

    def openTrades(self):
        return []

    def positions(self):
        return []


class FakeTicker:
    """Lo minimo que `_place` necesita para calcular el MID (patron de gapsA_coldrun)."""
    def __init__(self, bid=None, ask=None, contract=None):
        self.bid = bid
        self.ask = ask
        self.last = None
        self.volume = None
        self.modelGreeks = None
        self.contract = contract
        self.callOpenInterest = float("nan")
        self.putOpenInterest = float("nan")


class FakeIBOrdenes(FakeIB):
    """FakeIB que CAPTURA placeOrder, para poder ejercer el `_place` REAL y con el su guard."""
    def __init__(self):
        self._tk = {}
        self.ordenes = []

    def ticker(self, c):
        return self._tk.get(c.conId)

    def placeOrder(self, contract, order):
        self.ordenes.append((contract, order))

        class T:
            pass
        t = T()
        t.order = order

        class OS:
            status = "Submitted"
            filled = 0
            remaining = 1
            avgFillPrice = 0.0
        t.orderStatus = OS()
        return t


def nueva(spy, media):
    """App lista para que trade_poll evalue de verdad, con la media inyectada."""
    a = S.SpyDirection(demo=True)
    a.demo = False                 # demo=True cortocircuita trade_poll; se quiere la rama real
    a.ib = FakeIB()
    a.trading = True
    a.reconciled = True
    a.order = None
    a.pos = "FLAT"
    a.pos_qty = 0
    a.buys_pend = 0
    a.target = "FLAT"
    a.trade_open = None
    a.spy_price = spy
    a.ta_vals = {"vwap": media}
    a.buy_call = S.Option(S.SYMBOL, "20260812", 773, "C", "SMART", tradingClass=S.SYMBOL)
    a.buy_put = S.Option(S.SYMBOL, "20260812", 772, "P", "SMART", tradingClass=S.SYMBOL)
    a._colocadas = []
    a._place = lambda c, act, tgt=None, qty=None: a._colocadas.append((act, tgt))
    a._sync_pos = lambda: None
    a._live_orders = lambda: []
    a.refresh_strikes = lambda: None
    a._mid = lambda c: 0.75
    a._can_afford = lambda px: True
    return a


D = S.MEDIA_DIST
print("CONFIG REAL DEL MODULO: USAR_MEDIA=%s MEDIA_DIST=%.2f MINUTOS_POS=%d"
      % (S.USAR_MEDIA, D, S.MINUTOS_POS))
print()

print("=" * 78)
print("TEST 1 - LA REGLA: se compra HACIA la media (contraintuitivo)")
print("=" * 78)
a = nueva(773.00 + D + 0.05, 773.00)
check(a._senal_media() == "PUT",
      "precio %.2f ARRIBA de la media 773.00 (dist +%.2f) -> PUT" % (a.spy_price, D + 0.05))
a = nueva(773.00 - D - 0.05, 773.00)
check(a._senal_media() == "CALL",
      "precio %.2f ABAJO de la media 773.00 (dist -%.2f) -> CALL" % (a.spy_price, D + 0.05))
a = nueva(773.00 + D - 0.02, 773.00)
check(a._senal_media() is None,
      "dentro de la banda (dist +%.2f < %.2f) -> SIN señal" % (D - 0.02, D))
a = nueva(773.00, None)
check(a._senal_media() is None, "sin media -> None (no se inventa direccion)")
a = nueva(float("nan"), 773.00)
check(a._senal_media() is None, "precio NaN -> None")

print()
print("=" * 78)
print("TEST 2 - JUSTO EN EL UMBRAL (el borde exacto, donde se equivocan los '>=' )")
print("=" * 78)
a = nueva(773.00 + D, 773.00)
check(a._senal_media() == "PUT", "dist == +MEDIA_DIST exacto -> SI dispara (es >=)")
a = nueva(773.00 - D, 773.00)
check(a._senal_media() == "CALL", "dist == -MEDIA_DIST exacto -> SI dispara")

print()
print("=" * 78)
print("TEST 3 - trade_poll REAL: sin señal NO se abre nada")
print("=" * 78)
a = nueva(773.00, 773.00)                      # dentro de la banda
a.trade_poll()
check(not a._colocadas and a.target == "FLAT",
      "dentro de la banda: target=%s, ordenes=%s" % (a.target, a._colocadas))

print()
print("=" * 78)
print("TEST 4 - MANTENER hasta MINUTOS_POS aunque la señal GIRE")
print("=" * 78)
a = nueva(773.00 + D + 0.10, 773.00)
a.pos = "PUT"
a.pos_qty = 1
a.trade_open = {"ts": time.monotonic(), "hora": "10:00:00"}
a.target = "PUT"
a.spy_price = 773.00 - D - 0.10                # la señal se INVIERTE (ahora diria CALL)
a.trade_poll()
check(a.target == "PUT" and not a._colocadas,
      "señal invertida pero solo lleva 0 min -> MANTIENE (target=%s, ordenes=%s). "
      "Salir al invertirse da PEOR resultado (+133/+117 vs +154/+313)"
      % (a.target, a._colocadas))

print()
print("=" * 78)
print("TEST 5 - SALIDA POR TIEMPO al cumplir MINUTOS_POS")
print("=" * 78)
a = nueva(773.00 + D + 0.10, 773.00)
a.pos = "PUT"
a.pos_qty = 1
a.target = "PUT"
a.trade_open = {"ts": time.monotonic() - (S.MINUTOS_POS * 60.0 + 1), "hora": "10:00:00"}
a.trade_poll()
check(a.target == "FLAT", "%d min cumplidos -> target=FLAT (era %s)" % (S.MINUTOS_POS, "PUT"))
check(a.exit_reason == "tiempo", "la razon de salida es 'tiempo' -> %s" % a.exit_reason)
check(any(x[0] == "SELL" for x in a._colocadas),
      "y se coloca la VENTA -> %s" % a._colocadas)

# justo por debajo del tope NO sale
a = nueva(773.00 + D + 0.10, 773.00)
a.pos = "PUT"
a.pos_qty = 1
a.target = "PUT"
a.trade_open = {"ts": time.monotonic() - (S.MINUTOS_POS * 60.0 - 30), "hora": "10:00:00"}
a.trade_poll()
check(a.target == "PUT", "a falta de 30s NO sale todavia -> target=%s" % a.target)

print()
print("=" * 78)
print("TEST 6 - REENTRADA: tras vender se vuelve a comprar SIN duplicar posicion")
print("=" * 78)
a = nueva(773.00 + D + 0.10, 773.00)
a.pos = "FLAT"                                  # ya se vendio
a.pos_qty = 0
a.trade_open = None
a.target = "FLAT"
a.trade_poll()
check(a.target == "PUT", "la señal sigue activa -> target vuelve a PUT (%s)" % a.target)
compras = [x for x in a._colocadas if x[0] == "BUY"]
check(len(compras) == 1, "se coloca UNA sola compra -> %s" % a._colocadas)
# EL GUARD DE NO DUPLICAR vive DENTRO de `_place` (limite duro de QTY contando lo que va EN
# VUELO). Con `_place` mockeado NO se ejecuta y el check pasaria en falso, asi que aqui se usa
# el `_place` REAL contra un FakeIB que captura placeOrder (regla 3: la funcion de verdad).
# Es el riesgo numero 1 de este cambio: con ~18 operaciones/dia, vender y recomprar en el mismo
# ciclo no puede acabar en dos contratos.
b = nueva(773.00 + D + 0.10, 773.00)
b.ib = FakeIBOrdenes()
b._place = S.SpyDirection._place.__get__(b)      # el REAL, no el mock
b.min_tick[b.buy_put.conId] = 0.01
b.ib._tk[b.buy_put.conId] = FakeTicker(bid=0.74, ask=0.76, contract=b.buy_put)
b.pos = "FLAT"
b.pos_qty = 0
b.buys_pend = 0
b.trade_poll()
check(len(b.ib.ordenes) == 1, "con el _place REAL se envia UNA compra -> %d" % len(b.ib.ordenes))
check(b.buys_pend == 1, "y el cupo queda ocupado (buys_pend=%g)" % b.buys_pend)
b.trade_poll()                                    # segundo ciclo, cupo ya comprometido
check(len(b.ib.ordenes) == 1,
      "segundo ciclo con el cupo ocupado: NO se duplica la compra -> %d ordenes totales"
      % len(b.ib.ordenes))
# Y con la orden YA resuelta (para saltarse el guard de "orden viva") sigue sin duplicar:
# aqui el que frena es el limite duro de `_place`, contando `buys_pend` como comprometido.
b.order = None
b.trade_poll()
check(len(b.ib.ordenes) == 1,
      "sin orden viva pero con buys_pend=1: el limite duro de _place tampoco deja duplicar "
      "-> %d ordenes" % len(b.ib.ordenes))
check("comprometido" in (b.trade_msg or ""),
      "y el panel dice POR QUE no compra -> '%s'" % b.trade_msg)

print()
print("=" * 78)
print("TEST 7 - SIN MEDIA: no opera Y AVISA (nada de quedarse mudo en silencio)")
print("=" * 78)
a = nueva(773.00, None)
a.ta_vals = {}
avisos = []
S.ACT.info = lambda *x, **k: avisos.append(str(x[0]) % tuple(x[1:]) if len(x) > 1 else str(x[0]))
a.trade_poll()
S.ACT.info = lambda *x, **k: None
check(not a._colocadas and a.target == "FLAT", "sin media no se abre nada")
check(any("NO hay media" in v for v in avisos),
      "y queda AVISADO en el log -> %s" % ([v[:60] for v in avisos] or "SIN AVISO"))

print()
print("=" * 78)
print("TEST 8 - INTERRUPTOR A/B: con USAR_MEDIA=False vuelve el comportamiento anterior")
print("=" * 78)
_orig = S.USAR_MEDIA
S.USAR_MEDIA = False
a = nueva(773.00 + D + 0.10, 773.00)
check(a._senal_media() is None, "con USAR_MEDIA=False la señal se apaga -> None")
a.target = "CALL"                               # lo fijaria M1
a.pos = "FLAT"
a.trade_poll()
check(a.target == "CALL",
      "y trade_poll YA NO pisa el target: lo decide el disparador anterior -> %s" % a.target)
S.USAR_MEDIA = _orig

print()
if FAILS:
    print("MEDIA: NO CERRADO - %d checks fallaron" % len(FAILS))
    for f in FAILS:
        print("   - %s" % f)
    sys.exit(1)
print("MEDIA: TODO VERDE")
sys.exit(0)
