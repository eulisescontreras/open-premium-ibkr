# -*- coding: utf-8 -*-
"""
COLD RUN GAP 9 — "ordenes fantasma / mas de 1 contrato".
Reproduce el escenario REAL observado hoy 2026-08-10 en la apertura:
  4 ordenes BUY PUT colocadas, la app vio 1 fill y 1 venta, y quedaron 3 puts en IBKR
  mientras self.pos decia FLAT -> nadie las cerraria nunca.

Ejercita el CODIGO REAL (trade_poll, _place, _sync_pos, _on_filled, _live_orders) con FakeIB.
REQUISITO DEL USUARIO: 1 sola posicion, 1 solo contrato. Se cierra y solo despues se abre otro.
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


# hora fija a mitad de sesion (determinista: ni STOP_NEW ni FLATTEN)
class _FakeET:
    def weekday(self):
        return 0
    def strftime(self, f):
        return "11:00"


S.now_et = lambda: _FakeET()


class FakeContract:
    def __init__(self, strike, right, conId):
        self.strike = strike
        self.right = right
        self.conId = conId
        self.symbol = "SPY"
        self.secType = "OPT"
        self.localSymbol = "SPY %g%s" % (strike, right)
        self.lastTradeDateOrContractMonth = "20260810"


class FakeTicker:
    def __init__(self, bid=0.90, ask=1.10, last=1.0):
        self.bid = bid
        self.ask = ask
        self.last = last
        self.volume = 0.0
        self.callOpenInterest = float("nan")
        self.putOpenInterest = float("nan")
        self.modelGreeks = None
        self.time = None


class FakeStatus:
    def __init__(self, status="Submitted", filled=0.0, avg=0.0):
        self.status = status
        self.filled = filled
        self.avgFillPrice = avg


class FakeOrder:
    def __init__(self, action, qty, lmt):
        self.action = action
        self.totalQuantity = qty
        self.lmtPrice = lmt
        self.orderId = 1


class FakeTrade:
    def __init__(self, contract, order, status="Submitted", filled=0.0, avg=0.0):
        self.contract = contract
        self.order = order
        self.orderStatus = FakeStatus(status, filled, avg)


class FakePos:
    def __init__(self, contract, position):
        self.contract = contract
        self.position = position
        self.avgCost = 92.9


class FakeIB:
    def __init__(self):
        self._tk = {}
        self._pos = []
        self._open = []
        self.placed = []
        self.cancelled = []
    def isConnected(self):
        return True
    def sleep(self, s):
        pass
    def ticker(self, c):
        return self._tk.get(c.conId, FakeTicker())
    def positions(self):
        return list(self._pos)
    def openTrades(self):
        return list(self._open)
    def cancelOrder(self, o):
        self.cancelled.append(o)
    def reqContractDetails(self, c):
        return []
    def accountSummary(self):
        return []
    def reqMktData(self, c, g, s, r):
        return self._tk.get(c.conId)
    def placeOrder(self, c, o):
        t = FakeTrade(c, o)
        self.placed.append(t)
        return t


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
    a.spy_price = 772.0
    a.buy_call = FakeContract(773, "C", 10)
    a.buy_put = FakeContract(772, "P", 11)
    a.ib._tk[10] = FakeTicker(1.30, 1.44)
    a.ib._tk[11] = FakeTicker(0.86, 0.94)
    a.min_tick = {10: 0.01, 11: 0.01}
    return a


print("=" * 76)
print("COLD RUN GAP 9 - ordenes fantasma / 1 sola posicion, 1 solo contrato")
print("=" * 76)

# ---------------------------------------------------------------- G1
print("\n== G1: orden 'Cancelled' que SI se llenó -> debe procesarse como FILL ==")
a = nueva()
a.pos = "FLAT"
a.target = "CALL"
a.order_action, a.order_side = "BUY", "CALL"
a.order_contract = a.buy_call
a.order = FakeTrade(a.buy_call, FakeOrder("BUY", 1, 1.37), status="Cancelled",
                    filled=1.0, avg=1.37)
a.trade_poll()                                   # metodo REAL
check(a.pos == "CALL" and a.pos_qty == 1.0,
      "cancelada-pero-llenada detectada: pos=%s qty=%g entrada=%s "
      "(antes: se perdia y la app creia FLAT)" % (a.pos, a.pos_qty, a.entry_price))

# control: cancelada de verdad (filled=0) NO debe crear posicion
b = nueva()
b.pos = "FLAT"
b.target = "FLAT"
b.order_action, b.order_side = "BUY", "CALL"
b.order_contract = b.buy_call
b.order = FakeTrade(b.buy_call, FakeOrder("BUY", 1, 1.37), status="Cancelled", filled=0.0)
b.trade_poll()
check(b.pos == "FLAT" and b.order is None,
      "control: cancelada SIN llenar -> pos=FLAT y order liberada (%s)" % b.order)

# ---------------------------------------------------------------- G2
print("\n== G2: _sync_pos - la posicion REAL de IBKR manda sobre self.pos ==")
c = nueva()
c.pos = "FLAT"          # lo que la app CREE (el bug de hoy)
c.pos_qty = 0.0
poseido = FakeContract(772, "P", 555)
c.ib._pos = [FakePos(poseido, 3.0)]              # la REALIDAD: 3 puts
c._sync_pos()                                    # metodo REAL
check(c.pos == "PUT" and c.pos_qty == 3.0,
      "la app creia FLAT x0 -> corregido a %s x%g leyendo IBKR" % (c.pos, c.pos_qty))
check(c.buy_put.conId == 555,
      "buy_put reapuntado al contrato POSEIDO (conId %d) para poder cerrarlo" % c.buy_put.conId)

# ---------------------------------------------------------------- G3
print("\n== G3: GUARDA DURA - no comprar si ya hay contratos (1 sola posicion) ==")
d = nueva()
d.pos = "FLAT"                                   # la app cree que puede comprar
d.pos_qty = 0.0
d.target = "CALL"
d.ib._pos = [FakePos(FakeContract(772, "P", 556), 1.0)]   # pero IBKR ya tiene 1 put
d.last_sync = 0.0
d.trade_poll()                                   # metodo REAL
compras = [t for t in d.ib.placed if t.order.action == "BUY"]
check(len(compras) == 0,
      "NO se coloco ninguna compra teniendo posicion (compras=%d) | msg='%s'"
      % (len(compras), d.trade_msg))

# ---------------------------------------------------------------- G4
print("\n== G4: EXCESO de contratos -> aplanar TODO y vender la cantidad REAL ==")
e = nueva()
e.pos = "PUT"
e.pos_qty = 3.0
e.target = "CALL"                                # la senal quiere girar a CALL
# La posicion tiene que EXISTIR en IBKR: desde el GAP 13 la rama SELL confirma contra
# ib.positions() antes de vender (guarda anti-descubierto). Sin esto se niega, y hace bien.
e.ib._pos = [FakePos(FakeContract(772, "P", 11), 3.0)]
e.last_sync = 9e9                                # evitar la sincronizacion periodica del inicio
e.trade_poll()                                   # metodo REAL
ventas = [t for t in e.ib.placed if t.order.action == "SELL"]
check(e.target == "FLAT",
      "con %g contratos (max %d) el target se fuerza a FLAT -> %s" % (3.0, S.QTY, e.target))
check(len(ventas) == 1 and ventas[0].order.totalQuantity == 3,
      "se vende la cantidad REAL: %s lote(s) (antes vendia QTY=1 y dejaba 2 huerfanos)"
      % (ventas[0].order.totalQuantity if ventas else "ninguna"))

# ---------------------------------------------------------------- G5
print("\n== G5: _place no coloca si IBKR ya reporta una orden VIVA ==")
f = nueva()
f.pos = "FLAT"
f.target = "CALL"
viva = FakeTrade(f.buy_call, FakeOrder("BUY", 1, 1.37), status="Submitted")
f.ib._open = [viva]                              # IBKR dice: hay una viva
f._place(f.buy_call, "BUY", "CALL")              # metodo REAL
check(len(f.ib.placed) == 0,
      "guarda dura: 0 ordenes nuevas con una viva en IBKR | msg='%s'" % f.trade_msg)
f.ib._open = []
f._place(f.buy_call, "BUY", "CALL")
check(len(f.ib.placed) == 1,
      "control: sin ordenes vivas SI coloca (placed=%d)" % len(f.ib.placed))

# ---------------------------------------------------------------- G6
print("\n== G6: escenario REAL de hoy - 3 puts huerfanas y la app creyendose FLAT ==")
g = nueva()
g.pos = "FLAT"                                   # exactamente lo que paso a las 09:31
g.pos_qty = 0.0
g.target = "CALL"                                # la senal decia UP
g.ib._pos = [FakePos(FakeContract(772, "P", 777), 3.0)]
g.last_sync = 0.0
g.trade_poll()                                   # metodo REAL
compras_g = [t for t in g.ib.placed if t.order.action == "BUY"]
ventas_g = [t for t in g.ib.placed if t.order.action == "SELL"]
check(g.pos == "PUT" and g.pos_qty == 3.0,
      "detecta las 3 puts que la app no sabia que tenia -> pos=%s x%g" % (g.pos, g.pos_qty))
check(len(compras_g) == 0, "NO compra encima (compras=%d)" % len(compras_g))
check(len(ventas_g) == 1 and ventas_g[0].order.totalQuantity == 3,
      "coloca la venta de los 3 lotes para dejar la cuenta limpia (%s)"
      % (ventas_g[0].order.totalQuantity if ventas_g else "ninguna"))

print()
if FAILS:
    print("GAP 9 NO CERRADO: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("GAP 9 CERRADO: todos los checks pasaron")
sys.exit(0)
