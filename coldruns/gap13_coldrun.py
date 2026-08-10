# -*- coding: utf-8 -*-
"""
COLD RUN GAP 13 — la app perdia fills y llegaba a intentar SHORTS DESCUBIERTOS.

Observado en produccion 2026-08-10:
   10:22:37  ORDEN SELL CALL @ 1.09 (reqId 450)   <- se LLENO, sin cancel ni reject
   10:22:41  ORDEN SELL CALL @ 1.10 (451) -> RECHAZADA 201 (margen 15596 = call naked)
   10:22:45  ORDEN SELL CALL @ 1.08 (452) -> RECHAZADA 201
   10:22:49  ORDEN SELL CALL @ 1.08 (453) -> RECHAZADA 201
   10:22:53  ORDEN SELL CALL @ 1.08 (454) -> RECHAZADA 201
   10:22:57  SYNC posicion REAL de IBKR=FLAT x0 | la app creia CALL x1
No hay ninguna linea FILL SELL CALL: el sondeo de estado se perdio el fill.
Solo el control de margen de IBKR evito 4 shorts descubiertos.

Verifica con las FUNCIONES REALES (connect, _on_exec, trade_poll, _sync_pos, _place).
"""
import sqlite3
import sys

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


class _FakeET:
    def weekday(self):
        return 0
    def strftime(self, f):
        return "11:00"


S.now_et = lambda: _FakeET()


class FakeEvent:
    """Replica el operador += de los eventos de ib_insync y cuenta suscripciones."""
    def __init__(self):
        self.handlers = []
    def __iadd__(self, h):
        self.handlers.append(h)
        return self


class FakeContract:
    def __init__(self, strike, right, conId):
        self.strike = strike
        self.right = right
        self.conId = conId
        self.symbol = "SPY"
        self.secType = "OPT"
        self.localSymbol = "SPY   260810C00774000"
        self.lastTradeDateOrContractMonth = "20260810"
        self.exchange = "SMART"


class FakeTicker:
    def __init__(self, bid, ask):
        self.bid = bid
        self.ask = ask
        self.last = bid
        self.volume = 0.0
        self.callOpenInterest = float("nan")
        self.putOpenInterest = float("nan")
        self.modelGreeks = None
        self.time = None


class FakePos:
    def __init__(self, contract, position=1.0, avgCost=100.0):
        self.contract = contract
        self.position = position
        self.avgCost = avgCost


class FakeIB:
    def __init__(self):
        self.errorEvent = FakeEvent()
        self.pendingTickersEvent = FakeEvent()
        self.execDetailsEvent = FakeEvent()
        self._tk = {}
        self._pos = []
        self.placed = []
        self.conectado = 0
    def connect(self, h, p, clientId, timeout):
        self.conectado += 1
    def reqMarketDataType(self, n):
        pass
    def isConnected(self):
        return True
    def sleep(self, s):
        pass
    def positions(self):
        return list(self._pos)
    def openTrades(self):
        return []
    def cancelOrder(self, o):
        pass
    def reqContractDetails(self, c):
        return []
    def accountSummary(self):
        return []
    def reqMktData(self, c, g, s, r):
        self._tk.setdefault(c.conId, FakeTicker(float("nan"), float("nan")))
        return self._tk[c.conId]
    def ticker(self, c):
        return self._tk.get(c.conId, FakeTicker(float("nan"), float("nan")))
    def placeOrder(self, c, o):
        class _St:
            status = "Submitted"
            filled = 0.0
            avgFillPrice = 0.0
        class _Tr:
            pass
        t = _Tr(); t.contract = c; t.order = o; t.orderStatus = _St()
        self.placed.append(t)
        return t


class FakeExecution:
    def __init__(self, side, shares, price):
        self.side = side
        self.shares = shares
        self.price = price


class FakeFill:
    def __init__(self, contract, side, shares, price):
        self.contract = contract
        self.execution = FakeExecution(side, shares, price)


class FakeOrder:
    def __init__(self, oid):
        self.orderId = oid
        self.action = "SELL"
        self.totalQuantity = 1
        self.lmtPrice = 1.09


class FakeTrade:
    def __init__(self, oid):
        self.order = FakeOrder(oid)


def nueva():
    a = S.SpyDirection(demo=True)
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.demo = False
    a.ib = FakeIB()
    a.trading = True
    a.reconciled = True
    a.expiry = "20260810"
    a.spy_price = 773.5
    return a


print("=" * 76)
print("COLD RUN GAP 13 - fills perdidos y shorts descubiertos")
print("=" * 76)

CID = 774

# ---------------------------------------------------------------- T1
print("\n== T1: handlers suscritos UNA sola vez pese a varias reconexiones ==")
a = nueva()
for _ in range(4):
    a.connect()                                  # metodo REAL
check(a.ib.conectado == 4, "se llamo connect() 4 veces (conectado=%d)" % a.ib.conectado)
check(len(a.ib.errorEvent.handlers) == 1
      and len(a.ib.pendingTickersEvent.handlers) == 1
      and len(a.ib.execDetailsEvent.handlers) == 1,
      "handlers: error=%d ticks=%d exec=%d (esperado 1/1/1; antes se acumulaban)"
      % (len(a.ib.errorEvent.handlers), len(a.ib.pendingTickersEvent.handlers),
         len(a.ib.execDetailsEvent.handlers)))
check(a.ib.execDetailsEvent.handlers[0] == a._on_exec,
      "el handler de ejecuciones REALES esta enganchado")

# ---------------------------------------------------------------- T2
print("\n== T2: _on_exec fuerza re-sincronizacion inmediata ==")
b = nueva()
b.last_sync = 9e9                                # como si acabara de sincronizar
con = FakeContract(774, "C", CID)
b._on_exec(FakeTrade(450), FakeFill(con, "SLD", 1, 1.09))   # metodo REAL
check(b.last_sync == 0.0,
      "tras un EXEC real, last_sync=%s -> el proximo trade_poll re-sincroniza ya" % b.last_sync)

# ---------------------------------------------------------------- T3
print("\n== T3: EL CASO REAL - la venta ya se lleno pero la app cree tener la CALL ==")
c = nueva()
c.pos = "CALL"                                   # lo que la app CREE
c.pos_qty = 1.0
c.target = "PUT"                                 # giro a DOWN -> quiere vender
c.buy_call = FakeContract(774, "C", CID)
c.buy_put = FakeContract(772, "P", 772)
c.ib._tk[CID] = FakeTicker(1.05, 1.13)
c.ib._pos = []                                   # REALIDAD: ya no hay posicion
c.min_tick = {CID: 0.01}
# last_sync ALTO a proposito: asi NO salta la sincronizacion periodica del inicio de
# trade_poll y el flujo llega hasta la GUARDA de la rama SELL, que es lo que se prueba.
c.last_sync = 9e9
c.trade_poll()                                   # metodo REAL
ventas = [t for t in c.ib.placed if t.order.action == "SELL"]
check(len(ventas) == 0,
      "NO se coloco ninguna venta en descubierto (ventas=%d)" % len(ventas))
check("sin posicion real" in c.trade_msg,
      "fue la GUARDA de la rama SELL la que lo impidio -> msg='%s'" % c.trade_msg)
check(c.pos == "FLAT" and c.pos_qty == 0.0,
      "la app se corrigio sola contra IBKR: pos=%s qty=%g" % (c.pos, c.pos_qty))

# ---------------------------------------------------------------- T4
print("\n== T4: control - con la posicion REALMENTE abierta, SI vende ==")
d = nueva()
d.pos = "CALL"
d.pos_qty = 1.0
d.target = "PUT"
d.buy_call = FakeContract(774, "C", CID)
d.buy_put = FakeContract(772, "P", 772)
d.ib._tk[CID] = FakeTicker(1.05, 1.13)
d.ib._pos = [FakePos(FakeContract(774, "C", CID), 1.0)]      # la posicion SI existe
d.min_tick = {CID: 0.01}
d.last_sync = 0.0
d.trade_poll()                                   # metodo REAL
ventas_d = [t for t in d.ib.placed if t.order.action == "SELL"]
check(len(ventas_d) == 1,
      "con posicion real SI coloca la venta (%d) al MID %.2f"
      % (len(ventas_d), ventas_d[0].order.lmtPrice if ventas_d else 0))

# ---------------------------------------------------------------- T5
print("\n== T5: control - varias llamadas seguidas no generan ventas duplicadas ==")
e = nueva()
e.pos = "CALL"
e.pos_qty = 1.0
e.target = "PUT"
e.buy_call = FakeContract(774, "C", CID)
e.buy_put = FakeContract(772, "P", 772)
e.ib._tk[CID] = FakeTicker(1.05, 1.13)
e.ib._pos = [FakePos(FakeContract(774, "C", CID), 1.0)]
e.min_tick = {CID: 0.01}
for _ in range(4):
    e.last_sync = 0.0
    e.trade_poll()
ventas_e = [t for t in e.ib.placed if t.order.action == "SELL"]
check(len(ventas_e) == 1,
      "4 ticks con orden viva -> 1 sola venta colocada (%d)" % len(ventas_e))

print()
if FAILS:
    print("GAP 13 NO CERRADO: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("GAP 13 CERRADO: todos los checks pasaron")
sys.exit(0)
