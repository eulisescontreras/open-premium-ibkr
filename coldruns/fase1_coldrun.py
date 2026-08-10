# -*- coding: utf-8 -*-
"""
COLD RUN FASE 1 — verifica el arreglo de GAP 1 (reconexion) + GAP 8 (_reconcile reapunta
el contrato de salida). Ejercita run_gui REAL con Tkinter y _reconcile REAL con FakeIB.

T1  caida de socket a mitad de sesion -> SI reconecta (antes: nunca)
T2  la reconexion NO llama reset_day  -> net_call se CONSERVA
T3  reset_day se llama exactamente 1 vez (solo en el arranque del dia)
T4  los reintentos respetan el cooldown RECONNECT_SECS (no martillean el Gateway)
T5  _reconcile con 1 posicion de strike distinto -> buy_call apunta al contrato POSEIDO
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


class FakeIB:
    def __init__(self):
        self.connected = False
        self._pos = []
        self.cancelled = []
    def isConnected(self):
        return self.connected
    def sleep(self, s):
        pass
    def disconnect(self):
        self.connected = False
    def openTrades(self):
        return []
    def positions(self):
        return list(self._pos)
    def cancelOrder(self, o):
        self.cancelled.append(o)
    def ticker(self, c):
        raise KeyError(c)


class FakeContract:
    def __init__(self, strike, right, conId):
        self.strike = strike
        self.right = right
        self.conId = conId
        self.symbol = "SPY"
        self.secType = "OPT"
        self.localSymbol = "SPY %g%s" % (strike, right)
        self.lastTradeDateOrContractMonth = "20260810"


class FakePos:
    def __init__(self, contract, position=1.0):
        self.contract = contract
        self.position = position
        self.avgCost = 150.0


def construir(cls):
    a = cls(demo=True)
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.demo = False
    a.ib = FakeIB()
    return a


# =============================================================== T1..T4 (run_gui REAL)
def correr_gui(ticks_totales, tirar_en=None, permitir_reconexion=True, reconnect_secs=None):
    """Corre run_gui REAL. Devuelve los contadores observados."""
    cont = {"connect": 0, "setup": 0, "reset_day": 0, "intentos_t": []}
    permitido = {"ok": True}

    class AppFix(S.SpyDirection):
        def connect(self):
            cont["connect"] += 1
            cont["intentos_t"].append(time.monotonic())
            if not permitido["ok"]:
                raise Exception("simulado: Gateway caido")
            self.ib.connected = True
        def setup_contracts(self):
            cont["setup"] += 1
            self.spy_price = 773.0
            self.expiry = "20260810"
            return True
        def reset_day(self):
            cont["reset_day"] += 1
            return S.SpyDirection.reset_day(self)
        def is_market_open(self):
            return True
        def trade_poll(self):
            pass
        def ta_poll(self):
            pass
        def compute_walls(self):
            pass
        def _persist_accum(self):
            pass
        def _mid(self, c):
            return None
        def _cancel_working(self):
            pass

    import tkinter as _tk
    ref_refresh = S.REFRESH_SECS
    ref_recon = S.RECONNECT_SECS
    S.REFRESH_SECS = 0.05
    if reconnect_secs is not None:
        S.RECONNECT_SECS = reconnect_secs

    app = construir(AppFix)
    estado = {"n": 0}

    def vigilar(root):
        estado["n"] += 1
        # Inyectar la senal DESPUES de la conexion inicial (que si debe llamar reset_day)
        # y ANTES de la caida: es lo que tiene que sobrevivir a la reconexion.
        if tirar_en is not None and estado["n"] == max(1, tirar_en - 4):
            app.net_call = 5000.0
            app.net_put = 1000.0
        if tirar_en is not None and estado["n"] == tirar_en:
            app.ib.connected = False          # CAIDA DEL SOCKET
            permitido["ok"] = permitir_reconexion
        if estado["n"] >= ticks_totales:
            try:
                root.destroy()
            except Exception:
                pass
            return
        root.after(60, lambda: vigilar(root))

    _orig = _tk.Tk.mainloop

    def _ml(self, *a, **k):
        self.after(60, lambda: vigilar(self))
        return _orig(self, *a, **k)

    _tk.Tk.mainloop = _ml
    try:
        S.run_gui(app)                         # FUNCION REAL
    finally:
        _tk.Tk.mainloop = _orig
        S.REFRESH_SECS = ref_refresh
        S.RECONNECT_SECS = ref_recon
    return cont, app


print("=" * 74)
print("COLD RUN FASE 1 - arreglo GAP 1 (reconexion) + GAP 8 (_reconcile)")
print("=" * 74)

print("\n== T1/T2/T3: caida de socket a mitad de sesion ==")
c, app = correr_gui(ticks_totales=40, tirar_en=10, permitir_reconexion=True, reconnect_secs=0.4)
check(c["connect"] >= 2,
      "T1 reconecto tras la caida: connect() llamado %d veces (antes del arreglo: 1)" % c["connect"])
check(app.net_call == 5000.0 and app.net_put == 1000.0,
      "T2 la senal SOBREVIVE a la reconexion: net_call=%.0f net_put=%.0f (esperado 5000/1000)"
      % (app.net_call, app.net_put))
check(c["reset_day"] == 1,
      "T3 reset_day llamado %d vez (solo arranque de dia, NO en cada reconexion)" % c["reset_day"])
check(c["setup"] >= 2,
      "     setup_contracts rehecho tras reconectar: %d veces (recalcula strikes)" % c["setup"])

print("\n== T4: cooldown entre reintentos (no saturar el Gateway) ==")
c2, _ = correr_gui(ticks_totales=45, tirar_en=3, permitir_reconexion=False, reconnect_secs=0.5)
ts = c2["intentos_t"]
gaps = [ts[i] - ts[i - 1] for i in range(1, len(ts))]
min_gap = min(gaps) if gaps else 999
dur = (ts[-1] - ts[0]) if len(ts) > 1 else 0
check(len(gaps) == 0 or min_gap >= 0.45,
      "T4 %d reintentos en %.1fs, separacion minima %.2fs (cooldown=0.50s) -> respeta el cooldown"
      % (len(ts), dur, min_gap))
check(len(ts) < 20,
      "     no martillea: %d intentos (sin cooldown habrian sido ~%d, uno por tick)"
      % (len(ts), 45))

print("\n== T5: GAP 8 - _reconcile reapunta el contrato de salida al POSEIDO ==")
a5 = construir(S.SpyDirection)
a5.expiry = "20260810"
a5.spy_price = 781.0
# setup_contracts habria elegido 782C con el precio nuevo, pero en cartera hay una 774C vieja
a5.buy_call = FakeContract(782, "C", 999)
a5.buy_put = FakeContract(780, "P", 998)
poseido = FakeContract(774, "C", 111)
a5.ib._pos = [FakePos(poseido)]
strike_antes = a5.buy_call.strike
a5._reconcile()                                  # metodo REAL
check(a5.pos == "CALL", "posicion detectada desde IBKR -> pos=%s" % a5.pos)
check(a5.buy_call.conId == 111 and a5.buy_call.strike == 774,
      "T5 buy_call reapuntado al contrato POSEIDO: strike %g -> %g (conId %d) | "
      "sin el arreglo se venderia el 782C que NO se posee (corto descubierto)"
      % (strike_antes, a5.buy_call.strike, a5.buy_call.conId))

# control: sin posiciones no debe tocar nada
a6 = construir(S.SpyDirection)
a6.buy_call = FakeContract(782, "C", 999)
a6.ib._pos = []
a6._reconcile()
check(a6.pos == "FLAT" and a6.buy_call.conId == 999,
      "     control: sin posiciones -> pos=FLAT y buy_call intacto (no se toca)")

print()
if FAILS:
    print("FASE 1 FALLIDA: %d checks fallaron" % len(FAILS))
    for f in FAILS:
        print("   - " + f)
    sys.exit(1)
print("FASE 1 OK: todos los checks pasaron")
sys.exit(0)
