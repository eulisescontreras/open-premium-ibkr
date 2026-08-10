# -*- coding: utf-8 -*-
"""
COLD RUN GAP 12 (regresion introducida por el arreglo del GAP 8).
Al reapuntar buy_call/buy_put al contrato de ib.positions(), ese objeto NO tiene
market data -> _mid() devuelve None -> no hay precio/P&L en pantalla y, peor,
_place() NO coloca la VENTA: la posicion queda ATRAPADA.

Observado en produccion:
   10:04:29,561  GIRO -> UP
   10:04:29,728  TRADE esperando MID para SELL PUT (sin bid/ask)

Verifica con las FUNCIONES REALES (_adoptar_posicion, _ensure_mkt, _reconcile,
_sync_pos, _mid, _place, trade_poll).
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


class FakeContract:
    def __init__(self, strike, right, conId):
        self.strike = strike
        self.right = right
        self.conId = conId
        self.symbol = "SPY"
        self.secType = "OPT"
        self.localSymbol = "SPY   260810P00772000"
        self.lastTradeDateOrContractMonth = "20260810"


class FakeTicker:
    def __init__(self, bid, ask, last=None):
        self.bid = bid
        self.ask = ask
        self.last = last if last is not None else bid
        self.volume = 0.0
        self.callOpenInterest = float("nan")
        self.putOpenInterest = float("nan")
        self.modelGreeks = None
        self.time = None


class FakePos:
    def __init__(self, contract, position=1.0, avgCost=95.05):
        self.contract = contract
        self.position = position
        self.avgCost = avgCost


class FakeIB:
    """Simula el comportamiento REAL: ib.ticker() solo devuelve cotizacion para
    contratos a los que se les pidio reqMktData. Sin suscripcion -> ticker vacio."""
    def __init__(self):
        self._suscritos = {}      # conId -> FakeTicker
        self._cotiz = {}          # conId -> (bid, ask) disponible SI se suscribe
        self._pos = []
        self._open = []
        self.placed = []
        self.reqs = []            # historial de reqMktData
    def isConnected(self):
        return True
    def sleep(self, s):
        pass
    def positions(self):
        return list(self._pos)
    def openTrades(self):
        return list(self._open)
    def cancelOrder(self, o):
        pass
    def reqContractDetails(self, c):
        return []
    def accountSummary(self):
        return []
    def reqMktData(self, c, gen, snap, reg):
        self.reqs.append(c.conId)
        b, a = self._cotiz.get(c.conId, (float("nan"), float("nan")))
        self._suscritos[c.conId] = FakeTicker(b, a)
        return self._suscritos[c.conId]
    def ticker(self, c):
        # SIN suscripcion -> ticker vacio (bid/ask NaN), igual que IBKR
        return self._suscritos.get(c.conId, FakeTicker(float("nan"), float("nan")))
    def placeOrder(self, c, o):
        class _St:
            status = "Submitted"
            filled = 0.0
            avgFillPrice = 0.0
        class _Tr:
            pass
        t = _Tr()
        t.contract = c
        t.order = o
        t.orderStatus = _St()
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
    a.expiry = "20260810"
    a.spy_price = 773.5
    a.min_tick = {}
    return a


print("=" * 76)
print("COLD RUN GAP 12 - el contrato adoptado de ib.positions() debe tener cotizacion")
print("=" * 76)

POSEIDO = 111
BID, ASK = 0.47, 0.48

# ---------------------------------------------------------------- T1
print("\n== T1: sin suscripcion, _mid() es None (reproduce el bug) ==")
a = nueva()
con = FakeContract(772, "P", POSEIDO)
a.ib._cotiz[POSEIDO] = (BID, ASK)          # la cotizacion EXISTE en IBKR...
a.buy_put = con                             # ...pero nadie pidio reqMktData
a.min_tick[POSEIDO] = 0.01
check(a._mid(con) is None,
      "reproducido: _mid() = %s sin reqMktData (por eso 'esperando MID')" % a._mid(con))

# ---------------------------------------------------------------- T2
print("\n== T2: _adoptar_posicion suscribe y _mid() empieza a funcionar ==")
b = nueva()
con2 = FakeContract(772, "P", POSEIDO)
b.ib._cotiz[POSEIDO] = (BID, ASK)
b.min_tick[POSEIDO] = 0.01
b._adoptar_posicion(FakePos(con2), "PUT")   # metodo REAL
mid = b._mid(b.buy_put)
check(POSEIDO in b.ib.reqs, "se pidio reqMktData del contrato en cartera (reqs=%s)" % b.ib.reqs)
check(mid is not None and abs(mid - 0.47) < 0.011,
      "_mid() ahora devuelve %s (esperado ~%.2f = (%.2f+%.2f)/2)" % (mid, 0.475, BID, ASK))

# ---------------------------------------------------------------- T3
print("\n== T3: entrada recuperada de avgCost (tras reiniciar la app) ==")
check(abs(b.entry_price - 0.9505) < 1e-9,
      "entry_price = %.4f desde avgCost=95.05 (antes quedaba en None -> 'entrada=0.00')"
      % b.entry_price)

# ---------------------------------------------------------------- T4
print("\n== T4: no re-suscribe ni cambia el objeto en llamadas repetidas ==")
obj_antes = b.buy_put
for _ in range(5):
    b._adoptar_posicion(FakePos(FakeContract(772, "P", POSEIDO)), "PUT")
check(b.ib.reqs.count(POSEIDO) == 1,
      "reqMktData pedido UNA sola vez tras 6 llamadas (reqs=%s)" % b.ib.reqs)
check(b.buy_put is obj_antes,
      "el objeto contrato NO cambia si el conId es el mismo (si cambiara se perderia el ticker)")

# ---------------------------------------------------------------- T5
print("\n== T5: la VENTA ya se coloca (antes quedaba atrapada) ==")
c = nueva()
conc = FakeContract(772, "P", POSEIDO)
c.ib._cotiz[POSEIDO] = (BID, ASK)
c.ib._pos = [FakePos(conc)]
c.min_tick[POSEIDO] = 0.01
c.reconciled = False
c.buy_call = FakeContract(774, "C", 222)
c.buy_put = FakeContract(773, "P", 333)     # contrato "viejo" de setup_contracts
# FASE 1: arranque -> _reconcile adopta la posicion y fija target=pos ("mantener hasta
# el proximo flip", linea 1095). Aqui NO debe vender: es el comportamiento de diseno.
c.trade_poll()                               # metodo REAL (dispara _reconcile)
check(c.pos == "PUT" and c.buy_put.conId == POSEIDO,
      "fase 1: reconcile adopto la posicion real (pos=%s conId=%s target=%s)"
      % (c.pos, c.buy_put.conId, c.target))
check(len([t for t in c.ib.placed if t.order.action == "SELL"]) == 0,
      "fase 1: no vende al arrancar (target=pos por diseno)")
# FASE 2: llega el giro a UP -> target=CALL -> AHORA si debe vender la put
c.target = "CALL"
c.last_sync = 9e9                            # no dejar que _sync_pos pise el target
c.trade_poll()                               # metodo REAL
ventas = [t for t in c.ib.placed if t.order.action == "SELL"]
check(len(ventas) == 1,
      "SE COLOCO la venta (%d orden) - antes: 'esperando MID' y posicion atrapada" % len(ventas))
if ventas:
    check(abs(ventas[0].order.lmtPrice - 0.47) < 0.011,
          "la venta va al MID %.2f, no al bid ni al ask" % ventas[0].order.lmtPrice)
    check(ventas[0].order.totalQuantity == 1,
          "cantidad = la REAL en cartera (%g)" % ventas[0].order.totalQuantity)

# ---------------------------------------------------------------- T6
print("\n== T6: _sync_pos tambien adopta y asegura cotizacion ==")
e = nueva()
cone = FakeContract(772, "P", POSEIDO)
e.ib._cotiz[POSEIDO] = (BID, ASK)
e.ib._pos = [FakePos(cone)]
e.min_tick[POSEIDO] = 0.01
e.pos = "FLAT"
e._sync_pos()                                # metodo REAL
check(e.pos == "PUT" and e.pos_qty == 1.0, "sync detecta PUT x%g" % e.pos_qty)
check(POSEIDO in e.ib.reqs and e._mid(e.buy_put) is not None,
      "_sync_pos dejo el contrato con cotizacion: _mid=%s" % e._mid(e.buy_put))
check(abs(e.entry_price - 0.9505) < 1e-9, "entrada recuperada: %.4f" % e.entry_price)

# ---------------------------------------------------------------- T7
print("\n== T7: sin posicion no se suscribe nada (no gasta lineas de market data) ==")
f = nueva()
f.ib._pos = []
f._sync_pos()
check(len(f.ib.reqs) == 0 and f.pos == "FLAT",
      "FLAT -> 0 reqMktData (reqs=%s)" % f.ib.reqs)

# ---------------------------------------------------------------- T8
print("\n== T8: el contrato de ib.positions() viene SIN exchange (IBKR 321) ==")


class IBEstricto(FakeIB):
    """Replica el rechazo REAL de IBKR: sin exchange responde
    321 'Please enter exchange' y la suscripcion NUNCA llega."""
    def reqMktData(self, c, gen, snap, reg):
        if not getattr(c, "exchange", ""):
            raise Exception("IBKR 321: Please enter exchange [%s]" % c.localSymbol)
        return FakeIB.reqMktData(self, c, gen, snap, reg)


g = nueva()
g.ib = IBEstricto()
cong = FakeContract(772, "P", POSEIDO)
cong.exchange = ""                           # tal cual lo devuelve ib.positions()
g.ib._cotiz[POSEIDO] = (BID, ASK)
g.ib._pos = [FakePos(cong)]
g.min_tick[POSEIDO] = 0.01
g._sync_pos()                                # metodo REAL
check(getattr(g.buy_put, "exchange", "") == "SMART",
      "se rellena exchange='SMART' antes de pedir market data (era '')")
check(POSEIDO in g.ib.reqs, "la suscripcion SI llega (reqs=%s) - antes: 321 y sin cotizacion"
      % g.ib.reqs)
check(g._mid(g.buy_put) is not None,
      "_mid() funciona contra el IB estricto: %s" % g._mid(g.buy_put))

print()
if FAILS:
    print("GAP 12 NO CERRADO: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("GAP 12 CERRADO: todos los checks pasaron")
sys.exit(0)
