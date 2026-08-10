# -*- coding: utf-8 -*-
"""COLD RUN de la vista de CUENTA: _read_account, resumen_cuenta y el acumulado
de P&L que alimenta _on_filled. Funciones REALES, BD :memory:."""
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


class Row:
    def __init__(self, tag, value):
        self.tag = tag
        self.value = value
        self.currency = "USD"


class FakeIB:
    def __init__(self, net, avail):
        self.net = net
        self.avail = avail
    def accountSummary(self):
        return [Row("NetLiquidation", str(self.net)),
                Row("AvailableFunds", str(self.avail)),
                Row("BuyingPower", str(self.avail))]


class FakeStatus:
    def __init__(self, filled, avg):
        self.filled = filled
        self.avgFillPrice = avg
        self.status = "Filled"


class FakeOrd:
    def __init__(self, filled, avg):
        self.orderStatus = FakeStatus(filled, avg)


def nueva():
    a = S.SpyDirection(demo=True)
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.demo = False
    return a


print("=" * 70)
print("COLD RUN VISTA DE CUENTA")
print("=" * 70)

print("\n== T1: primera lectura fija la BASE del dia ==")
a = nueva()
a.ib = FakeIB(397.13, 397.13)
a._read_account()                                  # metodo REAL
check(a.acct_net == 397.13 and a.acct_net_open == 397.13,
      "net=%.2f base=%.2f (la base se captura una sola vez)" % (a.acct_net, a.acct_net_open))

print("\n== T2: la base NO se mueve aunque la cuenta cambie ==")
a.ib = FakeIB(374.10, 329.90)
a._read_account()
check(a.acct_net == 374.10 and a.acct_net_open == 397.13,
      "net=%.2f, base sigue en %.2f" % (a.acct_net, a.acct_net_open))
txt = a.resumen_cuenta()                            # metodo REAL
print("     vista -> %s" % txt)
check("-23.03" in txt and "-5.8%" in txt,
      "el DIA sale correcto: 374.10 - 397.13 = -23.03 (-5.8%)")

print("\n== T3: el P&L realizado se acumula en cada VENTA llenada ==")
b = nueva()
b.ib = FakeIB(400.0, 400.0)
b._read_account()
for entrada, salida in ((1.00, 1.30), (0.9505, 0.40), (0.38, 0.38)):
    b.entry_price = entrada
    b.order_action, b.order_side = "SELL", "CALL"
    b.order_contract = S.Option(S.SYMBOL, "20260810", 773, "C", "SMART", tradingClass=S.SYMBOL)
    b.order = FakeOrd(1.0, salida)
    b._on_filled()                                  # metodo REAL
esperado = (1.30 - 1.00) * 100 + (0.40 - 0.9505) * 100 + 0.0
check(abs(b.pnl_realizado - esperado) < 1e-6,
      "realizado=%.2f (esperado %.2f = +30.00 -55.05 +0.00)" % (b.pnl_realizado, esperado))
check(b.n_trades == 3 and b.n_wins == 1,
      "ops=%d ganadoras=%d (solo la primera fue positiva)" % (b.n_trades, b.n_wins))
print("     vista -> %s" % b.resumen_cuenta())

print("\n== T4: reset_day limpia el acumulado y la base ==")
b.reset_day()                                       # metodo REAL
check(b.pnl_realizado == 0.0 and b.n_trades == 0 and b.n_wins == 0
      and b.acct_net_open is None,
      "tras reset_day: realizado=%.2f ops=%d base=%s"
      % (b.pnl_realizado, b.n_trades, b.acct_net_open))

print("\n== T5: robustez ==")
c = nueva()
check("leyendo" in c.resumen_cuenta(), "sin datos aun -> texto de espera")


class IBRoto:
    def accountSummary(self):
        raise Exception("IBKR caido")


c.ib = IBRoto()
c._read_account()
check(c.acct_net is None, "accountSummary fallando no crashea ni ensucia el estado")

print()
if FAILS:
    print("VISTA DE CUENTA NO OK: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("VISTA DE CUENTA OK: todos los checks pasaron")
sys.exit(0)
