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

print("\n== T5: COMISION real de las dos patas (2026-08-12) ==")
# POR QUE: `profit` es BRUTO. Se comprobo el 2026-08-12 que (exit-entry)*qty*100 reproduce el
# valor guardado con diferencia 0.00 en las 3 operaciones cerradas de ese dia, o sea que la
# comision no estaba en ningun sitio. Con permanencias de decenas de segundos y 7 patas en una
# manana, no saber la comision es no saber si el dia fue positivo.
# REGLA: None significa "no lo se" y NUNCA 0. El commissionReport de IBKR llega ASINCRONO y
# puede tardar mas que el fill; guardar 0 haria que el neto pareciera igual al bruto.


class FakeCR:
    def __init__(self, com):
        self.commission = com


class FakeFill:
    def __init__(self, com):
        self.commissionReport = FakeCR(com) if com is not None else None


class FakeOrdCom(FakeOrd):
    def __init__(self, filled, avg, coms=()):
        FakeOrd.__init__(self, filled, avg)
        self.fills = [FakeFill(x) for x in coms]


d = nueva()
d.order = FakeOrdCom(1.0, 1.0, (0.65, 0.35))
check(abs((d._comision_de_orden() or 0) - 1.00) < 1e-9,
      "5.1 suma los fills de la orden -> %s" % S._fmt(d._comision_de_orden()))
d.order = FakeOrdCom(1.0, 1.0, (None,))
check(d._comision_de_orden() is None,
      "5.2 fill SIN commissionReport -> None (no lo se), nunca 0")
d.order = FakeOrd(1.0, 1.0)
check(d._comision_de_orden() is None,
      "5.3 orden sin atributo `fills` -> None (no rompe con ordenes antiguas)")
d.order = FakeOrdCom(1.0, 1.0, (0.65, None))
check(abs((d._comision_de_orden() or 0) - 0.65) < 1e-9,
      "5.4 mezcla: suma lo que hay y descarta lo que falta -> %s" % S._fmt(d._comision_de_orden()))

# --- END-TO-END por el flujo REAL: la COMPRA abre la fila (via _trade_abrir dentro de
# _on_filled) y la VENTA la cierra. No se pre-inserta nada: hacerlo daba un falso FAIL porque
# _on_filled abre su PROPIA fila y la pre-insertada se quedaba huerfana.
e = nueva()
e.ib = FakeIB(400.0, 400.0)
e._read_account()
e.order_contract = S.Option(S.SYMBOL, "20260812", 773, "C", "SMART", tradingClass=S.SYMBOL)
e.order_action, e.order_side = "BUY", "CALL"
e.order = FakeOrdCom(1.0, 1.00, (0.65,))
e._on_filled()                                        # metodo REAL: abre el trade
check(e._com_entrada == 0.65,
      "5.5 la compra guarda su comision hasta el cierre -> %s" % S._fmt(e._com_entrada))
tid = e.trade_id
check(tid is not None, "5.5 la compra abrio la fila del trade -> #%s" % tid)
e.entry_price = 1.00
e.order_action = "SELL"
e.order = FakeOrdCom(1.0, 1.30, (0.65,))
e._on_filled()                                        # metodo REAL: la cierra
row = e.db.execute("SELECT profit, comision FROM trades WHERE trade_id=?", (tid,)).fetchone()
check(row is not None and row[1] is not None and abs(row[1] - 1.30) < 1e-9,
      "5.6 la fila guarda la comision de las DOS patas (0.65+0.65) -> %s" % (row[1] if row else None))
check(row is not None and abs(row[0] - 30.0) < 1e-6,
      "5.7 `profit` sigue siendo BRUTO (30.00): la comision va aparte, no se resta sola -> %s"
      % (row[0] if row else None))
check(e._com_entrada is None, "5.8 se limpia tras cerrar (no contamina el siguiente trade)")

# 5.9 sin commissionReport en ninguna pata -> NULL, y el trade se cierra igual
f = nueva()
f.ib = FakeIB(400.0, 400.0)
f._read_account()
f.order_contract = S.Option(S.SYMBOL, "20260812", 773, "P", "SMART", tradingClass=S.SYMBOL)
f.order_action, f.order_side = "BUY", "PUT"
f.order = FakeOrd(1.0, 1.00)                          # sin `fills`: como las ordenes de antes
f._on_filled()
tid2 = f.trade_id
f.entry_price = 1.00
f.order_action = "SELL"
f.order = FakeOrd(1.0, 1.20)
f._on_filled()
row2 = f.db.execute("SELECT profit, comision, hora_salida FROM trades WHERE trade_id=?",
                    (tid2,)).fetchone()
check(row2 is not None and row2[1] is None and row2[2] is not None,
      "5.9 sin commissionReport -> comision NULL y el trade se cierra igual -> %s" % (row2,))

print()
if FAILS:
    print("VISTA DE CUENTA NO OK: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("VISTA DE CUENTA OK: todos los checks pasaron")
sys.exit(0)
