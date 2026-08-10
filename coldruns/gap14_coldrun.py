# -*- coding: utf-8 -*-
"""
COLD RUN GAP 14 - LIMITE DURO DE 1 CONTRATO.

Episodio real 2026-08-10 10:55 (ejecuciones confirmadas por IBKR):
   10:55:18  BUY PUT @1.04 (925)      10:55:40 -> SE LLENO  (22 s tras "cancelarla")
   10:55:22  BUY PUT @1.10 (926)      10:55:34 -> SE LLENO  (12 s tras "cancelarla")
   10:55:26  BUY PUT @1.10 (927)      10:55:28 -> SE LLENO
   Resultado: 3 contratos. Las guardas anteriores LIMPIABAN (vendio x3) pero NO IMPEDIAN.

La causa: mirar solo la posicion CONFIRMADA. En el instante de colocar cada orden la
posicion era 0 de verdad; los contratos llegaron despues. Hay que contar lo EN VUELO.

Funciones REALES (_place, trade_poll, _sync_pos), BD :memory:.
"""
import sqlite3
import sys
import time

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


class _ET:
    def weekday(self):
        return 0
    def strftime(self, f):
        return "11:00"


S.now_et = lambda: _ET()


class C:
    def __init__(self, strike, right, conId):
        self.strike = strike; self.right = right; self.conId = conId
        self.symbol = "SPY"; self.secType = "OPT"; self.exchange = "SMART"
        self.localSymbol = "SPY %g%s" % (strike, right)
        self.lastTradeDateOrContractMonth = "20260810"


class Tk:
    def __init__(self, b, a):
        self.bid = b; self.ask = a; self.last = b
        self.volume = 0.0; self.modelGreeks = None; self.time = None
        self.callOpenInterest = float("nan"); self.putOpenInterest = float("nan")


class P:
    def __init__(self, c, q):
        self.contract = c; self.position = q; self.avgCost = 110.0


class IB:
    """IBKR realista: openTrades() refleja la CACHE LOCAL, que puede decir que una orden
    esta cancelada mientras el broker todavia la puede llenar."""
    def __init__(self):
        self.placed = []; self._pos = []; self._open = []
        self._tk = {774.0: Tk(1.02, 1.06)}
    def isConnected(self):
        return True
    def sleep(self, s):
        pass
    def positions(self):
        return list(self._pos)
    def openTrades(self):
        return list(self._open)          # vacia: la cache local dice "no hay nada vivo"
    def cancelOrder(self, o):
        pass
    def reqContractDetails(self, c):
        return []
    def accountSummary(self):
        return []
    def reqMktData(self, c, g, s, r):
        return self._tk.get(c.strike)
    def cancelMktData(self, c):
        pass
    def qualifyContracts(self, *cs):
        return list(cs)
    def ticker(self, c):
        return self._tk.get(c.strike, Tk(float("nan"), float("nan")))
    def placeOrder(self, c, o):
        class St:
            status = "Submitted"; filled = 0.0; avgFillPrice = 0.0
        class T:
            pass
        t = T(); t.contract = c; t.order = o; t.orderStatus = St()
        self.placed.append(t)
        return t


def nueva():
    a = S.SpyDirection(demo=True)
    a.db.close(); a.db = sqlite3.connect(":memory:"); a._init_db()
    a.demo = False; a.ib = IB(); a.trading = True; a.reconciled = True
    a.expiry = "20260810"; a.spy_price = 773.95
    a.strikes = [float(x) for x in range(765, 786)]
    a.buy_call = C(774.0, "C", 7740); a.buy_put = C(774.0, "P", 7741)
    a.min_tick = {7740: 0.01, 7741: 0.01}
    a.ib._tk[774.0] = Tk(1.02, 1.06)
    return a


print("=" * 76)
print("COLD RUN GAP 14 - limite duro de 1 contrato (se IMPIDE, no solo se limpia)")
print("=" * 76)

print("\n== T1: reproduccion del episodio 10:55 - 3 compras seguidas ==")
a = nueva()
a.pos = "FLAT"; a.pos_qty = 0.0; a.target = "PUT"
a.last_sync = 9e9
for i in range(3):
    a.order = None                     # la cache local dice que la anterior murio
    a.open_deadline = 0.0
    a.trade_poll()                     # metodo REAL
compras = [t for t in a.ib.placed if t.order.action == "BUY"]
check(len(compras) == 1,
      "se envio 1 SOLA compra en 3 intentos (%d) - antes se enviaban 3" % len(compras))
check(a.buys_pend == 1, "cupo comprometido = %g" % a.buys_pend)
print("     msg: %s" % a.trade_msg)

print("\n== T2: con posicion ya confirmada tampoco compra ==")
b = nueva()
b.pos = "PUT"; b.pos_qty = 1.0; b.target = "PUT"
b.ib._pos = [P(C(774.0, "P", 7741), 1.0)]
b.last_sync = 9e9
b.order = None
b.trade_poll()
check(len([t for t in b.ib.placed if t.order.action == "BUY"]) == 0,
      "con 1 contrato en cartera no se compra otro")

print("\n== T3: el cupo NO se libera antes de tiempo (fill tardio posible) ==")
c = nueva()
c.pos = "FLAT"; c.pos_qty = 0.0; c.target = "PUT"; c.last_sync = 9e9
c.order = None
c.trade_poll()                         # 1a compra -> cupo ocupado
check(c.buys_pend == 1, "cupo ocupado tras la compra (%g)" % c.buys_pend)
c.ib._pos = []                         # IBKR sigue diciendo FLAT (el fill aun no llego)
c.last_sync = 0.0
c._sync_pos()                          # metodo REAL: no debe liberar, han pasado <25 s
check(c.buys_pend == 1,
      "sigue ocupado: han pasado %.0fs (<%.0fs) -> no se libera"
      % (time.monotonic() - c.last_buy_ts, S.BUY_SETTLE_SECS))
c.order = None
c.trade_poll()
check(len([t for t in c.ib.placed if t.order.action == "BUY"]) == 1,
      "y por tanto NO se envia una segunda compra")

print("\n== T4: pasado el margen y sin ordenes vivas, el cupo SI se libera ==")
c.last_buy_ts = time.monotonic() - (S.BUY_SETTLE_SECS + 5)
c.last_sync = 0.0
c._sync_pos()
check(c.buys_pend == 0,
      "cupo liberado tras %.0fs sin fills y sin ordenes vivas" % (S.BUY_SETTLE_SECS + 5))
c.order = None
c.trade_poll()
check(len([t for t in c.ib.placed if t.order.action == "BUY"]) == 2,
      "ahora si puede volver a comprar (%d compras en total)"
      % len([t for t in c.ib.placed if t.order.action == "BUY"]))

print("\n== T5: las VENTAS no consumen cupo (hay que poder salir siempre) ==")
e = nueva()
e.pos = "PUT"; e.pos_qty = 1.0; e.target = "CALL"
e.ib._pos = [P(C(774.0, "P", 7741), 1.0)]
e.buys_pend = 1                        # cupo ocupado
e.last_sync = 9e9
e.order = None
e.trade_poll()
ventas = [t for t in e.ib.placed if t.order.action == "SELL"]
check(len(ventas) == 1, "con el cupo ocupado la VENTA si se coloca (%d)" % len(ventas))

print("\n== T6: reset_day limpia el cupo ==")
e.reset_day()
check(e.buys_pend == 0 and e.last_buy_ts == 0.0, "tras reset_day el cupo queda limpio")

print()
if FAILS:
    print("GAP 14 NO CERRADO: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("GAP 14 CERRADO: todos los checks pasaron")
sys.exit(0)
