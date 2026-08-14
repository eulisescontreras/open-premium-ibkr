# -*- coding: utf-8 -*-
"""
Cold run HEADLESS de los 5 arreglos que NO dependian de datos:
  GAP 2  doble conteo del premium en los strikes de SENAL
  GAP 4  posicion huerfana EOD -> cruce de spread a las 15:50
  GAP 5  momentum por TIEMPO en vez de por numero de eventos
  M2     P&L realizado leido de IBKR en vez de calculado
  M12    tif='DAY' explicito en la orden

Ejercita los METODOS REALES con FakeIB (mismo patron que spy_walls_coldrun.py, regla 9).
Correr:  python gapsA_coldrun.py     Exit 0 = OK
"""
import sqlite3
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import spy_direction as S

# 2026-08-12: esta suite ejercita el disparador ANTERIOR (M1 / diff-thr) o el flujo generico de
# compra. Desde hoy el default es USAR_MEDIA=True, que exige `ta_vals["vwap"]`, y las apps
# minimas de las cold runs no lo tienen -> `_senal_media()` devuelve None, el target se queda
# en FLAT y NADA compra. Sin esta linea fallan 7 suites por una sola causa.
# Un test A/B tiene que FIJAR la variable que prueba, no heredarla del default (misma leccion
# que ENTRADA_RETROCESO en gap14 el mismo dia).
S.USAR_MEDIA = False
S.USAR_ST3 = False   # 2026-08-14: idem para el disparador nuevo (Supertrend). Esta suite prueba
                     # el giro por diff/thr; USAR_ST3=True usa self.bars (que la app minima no
                     # tiene) y no giraria. El ST-3 tiene su cold run (coldruns/st3_signal_coldrun.py).

S.ENABLE_TOAST = False
S.ENABLE_SOUND = False

import logging as _lg
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


class FakeGreeks:
    def __init__(self, gamma=0.2):
        self.gamma = gamma
        self.delta = 0.5
        self.theta = -0.3
        self.vega = 0.1
        self.impliedVol = 0.2
        self.undPrice = 773.0


class FakeTicker:
    def __init__(self, bid=None, ask=None, last=None, volume=None, greeks=None,
                 contract=None, right="C", oi=100.0):
        self.bid = bid
        self.ask = ask
        self.last = last
        self.volume = volume
        self.modelGreeks = greeks
        self.contract = contract
        self.callOpenInterest = oi if right == "C" else float("nan")
        self.putOpenInterest = oi if right == "P" else float("nan")
        self.time = "2026-08-11 10:00:00"


class FakeContract:
    def __init__(self, strike, right, conId, expiry="20260814"):
        self.strike = strike
        self.right = right
        self.conId = conId
        self.lastTradeDateOrContractMonth = expiry
        self.symbol = "SPY"
        self.secType = "OPT"
        self.localSymbol = "SPY"


class FakeAcct:
    def __init__(self, tag, value):
        self.tag = tag
        self.value = value


class FakeIB:
    def __init__(self, acct=None):
        self._tk = {}
        self.ordenes = []          # (contract, order)
        self._acct = acct or []

    def isConnected(self):
        return True

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
            avgFillPrice = 0.0
        t.orderStatus = OS()
        return t

    def openTrades(self):
        return []

    def positions(self):
        return []

    def accountSummary(self):
        return self._acct

    def reqContractDetails(self, c):
        return []


def nueva_app(acct=None):
    app = S.SpyDirection(demo=True)
    app.db.close()
    app.db = sqlite3.connect(":memory:")
    app._init_db()
    app.ib = FakeIB(acct)
    app.demo = False
    app.expiry = "20260814"
    app.spy_price = 773.00
    return app


# ================================================================ M12
print("== M12: tif='DAY' explicito (elimina los avisos 10349) ==")
app = nueva_app()
c = FakeContract(773, "C", 1001)
app.ib._tk[1001] = FakeTicker(bid=0.98, ask=1.02, contract=c)
app.min_tick[1001] = 0.01
app.trading = True
app._place(c, "BUY", "CALL")
check(len(app.ib.ordenes) == 1, "se coloco 1 orden")
o = app.ib.ordenes[0][1]
check(getattr(o, "tif", None) == "DAY", "la orden lleva tif='DAY' -> %r" % getattr(o, "tif", None))
check(o.lmtPrice == 1.00, "sigue siendo LIMIT al MID -> %s" % o.lmtPrice)


# ================================================================ GAP 4
print("== GAP 4: cruce de spread en el EOD (venta que no puede quedar huerfana) ==")
_real_now_et = S.now_et


class FakeET:
    """now_et() falso para controlar la hora sin esperar a las 15:50."""
    def __init__(self, hhmm, wd=0):
        self.h, self.m = [int(x) for x in hhmm.split(":")]
        self.wd = wd

    def strftime(self, f):
        return "%02d:%02d" % (self.h, self.m)

    def weekday(self):
        return self.wd


app = nueva_app()
c = FakeContract(773, "C", 1001)
app.ib._tk[1001] = FakeTicker(bid=1.00, ask=1.40, contract=c)   # spread ANCHO
app.min_tick[1001] = 0.01
app.trading = True
app.pos = "CALL"
app.pos_qty = 1

# --- antes de las 15:50: al MID, como siempre ---
S.now_et = lambda: FakeET("15:46")
app.ib.ordenes = []
app._place(c, "SELL", "CALL", qty=1)
px_mid = app.ib.ordenes[0][1].lmtPrice
check(px_mid == 1.20, "15:46 -> vende al MID 1.20 (regla dura intacta) -> %s" % px_mid)

# --- 15:51: TODAVIA al MID. Actualizado 2026-08-10: el cruce se movio de 15:50 a 15:55
#     (CROSS_HHMM) porque ir al BID regala el spread; ahora se insiste al MID 10 minutos. ---
S.now_et = lambda: FakeET("15:51")
app.ib.ordenes = []
app._place(c, "SELL", "CALL", qty=1)
check(app.ib.ordenes[0][1].lmtPrice == 1.20,
      "15:51 -> SIGUE al MID 1.20, ya no cruza (el cruce es a las %s) -> %s"
      % (S.CROSS_HHMM, app.ib.ordenes[0][1].lmtPrice))

# --- 15:56: ultimos 5 min, AHORA si cruza al BID ---
S.now_et = lambda: FakeET("15:56")
app.ib.ordenes = []
app._place(c, "SELL", "CALL", qty=1)
px_cruce = app.ib.ordenes[0][1].lmtPrice
check(px_cruce == 1.00, "15:56 -> CRUZA y vende al BID 1.00 -> %s" % px_cruce)
check(px_cruce < px_mid, "el precio de cruce es peor que el MID: ultimo recurso para SALIR")

# --- una COMPRA nunca cruza, ni a esa hora ---
app.pos = "FLAT"
app.pos_qty = 0
app.buys_pend = 0
app.ib.ordenes = []
app._place(c, "BUY", "CALL")
check(len(app.ib.ordenes) == 0 or app.ib.ordenes[0][1].lmtPrice == 1.20,
      "una COMPRA a las 15:56 no cruza el spread (o ni se coloca)")

# --- end_session con posicion abierta deja constancia y cierra el trade ---
app = nueva_app()
app.pos = "CALL"
app.pos_qty = 1
hoy = S.datetime.now().strftime("%Y-%m-%d")
app.db.execute("INSERT INTO trades(fecha,expiry,strike,right,side,hora_entrada,entry_price,qty)"
               " VALUES(?,?,?,?,?,?,?,?)", (hoy, "20260814", 773, "C", "CALL", "10:00:00", 1.0, 1))
app.db.commit()
app.trade_id = 1
app.trade_open = {"hora": "10:00:00"}
app.end_session()
r = app.db.execute("SELECT razon_salida FROM trades WHERE trade_id=1").fetchone()
check(r and r[0] == "expirada",
      "end_session con posicion -> el trade se cierra como 'expirada' -> %s" % (r,))
S.now_et = _real_now_et


# ================================================================ GAP 5
print("== GAP 5: momentum por TIEMPO, no por numero de eventos ==")
app = nueva_app()
app.call = FakeContract(773, "C", 3001)
app.put = FakeContract(773, "P", 3002)
app._intradia_ok = True      # GAP 18: sin esto _update_signal ni evalua (ver test del GAP 18)

# RAFAGA: muchos eventos en el mismo instante. Antes (MOMENTUM_WIN=8 muestras) la ventana se
# llenaba en milisegundos y el momentum salia enorme. Ahora no hay 30 s de historia -> 0.
for i in range(20):
    app.net_call = 1000.0 * i
    app._update_signal()
check(app.last_momentum == 0.0,
      "20 eventos en milisegundos -> momentum 0 (antes habria sido enorme) -> %s"
      % app.last_momentum)

# con historia REAL de mas de MOMENTUM_SECS, mide el cambio del diff en esa ventana
app = nueva_app()
app._intradia_ok = True      # GAP 18
ahora = time.monotonic()
app.flow_hist = [(ahora - 40.0, 1000.0, 500.0)]     # hace 40 s: diff = 500
app.net_call, app.net_put = 3000.0, 700.0            # ahora: diff = 2300
app._update_signal()
check(abs(app.last_momentum - 1800.0) < 1e-6,
      "momentum = diff_ahora - diff_hace_30s = 2300 - 500 = 1800 -> %s" % app.last_momentum)
check(not hasattr(app, "diff_hist"),
      "diff_hist ELIMINADO (no queda estado huerfano)")


# ================================================================ M2
print("== M2: P&L realizado desde IBKR ==")
app = nueva_app(acct=[FakeAcct("NetLiquidation", "350.00"),
                      FakeAcct("AvailableFunds", "250.00"),
                      FakeAcct("RealizedPnL", "-54.00"),
                      FakeAcct("UnrealizedPnL", "12.00")])
app.pnl_realizado = -98.11          # el calculo interno, desviado (caso real del 2026-08-10)
app._read_account()
check(app.pnl_ibkr == -54.0, "lee RealizedPnL de IBKR -> %s" % app.pnl_ibkr)
check(app.pnl_ibkr_unreal == 12.0, "lee UnrealizedPnL -> %s" % app.pnl_ibkr_unreal)
txt = app.resumen_cuenta()
check("-54.00 (IBKR)" in txt, "el panel muestra el de IBKR -> %s" % txt)
check("interno -98.11" in txt, "y deja ver el interno cuando se desvia")

# si IBKR NO da el dato, se usa el interno y se dice explicitamente
app2 = nueva_app(acct=[FakeAcct("NetLiquidation", "350.00"),
                       FakeAcct("AvailableFunds", "250.00")])
app2.pnl_realizado = 25.10
app2._read_account()
check(app2.pnl_ibkr is None, "sin RealizedPnL de IBKR -> pnl_ibkr None")
check("(interno)" in app2.resumen_cuenta(),
      "el panel marca el dato como interno -> %s" % app2.resumen_cuenta())


# ================================================================ GAP 2
print("== GAP 2: doble conteo del premium en los strikes de SENAL ==")
app = nueva_app()
sig_c = FakeContract(773, "C", 4001)     # SENAL (y tambien esta en la banda)
otro = FakeContract(775, "C", 4002)      # solo banda
app.call = sig_c
app.put = None
app.band_contracts = [sig_c, otro]
app.ib._tk[4001] = FakeTicker(bid=0.98, ask=1.02, last=1.02, volume=100.0,
                              greeks=FakeGreeks(), contract=sig_c, oi=500.0)
app.ib._tk[4002] = FakeTicker(bid=0.98, ask=1.02, last=1.02, volume=100.0,
                              greeks=FakeGreeks(), contract=otro, oi=300.0)
app.compute_walls()                       # 1a: fija la base de volumen
app.ib._tk[4001] = FakeTicker(bid=0.98, ask=1.02, last=1.02, volume=150.0,
                              greeks=FakeGreeks(), contract=sig_c, oi=500.0)
app.ib._tk[4002] = FakeTicker(bid=0.98, ask=1.02, last=1.02, volume=150.0,
                              greeks=FakeGreeks(), contract=otro, oi=300.0)
app.compute_walls()                       # 2a: +50 de volumen en ambos

k_sig = ("20260814", 773, "C")
k_otro = ("20260814", 775, "C")
check(app.today_prem.get(k_sig, 0.0) == 0.0,
      "el strike de SENAL NO suma premium en compute_walls (lo cuenta _on_ticks) -> %s"
      % app.today_prem.get(k_sig, 0.0))
check(app.today_prem.get(k_otro, 0.0) > 0,
      "un strike NO-senal si suma su premium aqui -> %s" % app.today_prem.get(k_otro))
# lo que SI se sigue contando para el strike de senal (nadie mas lo escribe):
check(app.today_vol.get(k_sig, 0.0) == 50.0,
      "today_vol del strike de senal SI se cuenta (alimenta el magneto dinamico) -> %s"
      % app.today_vol.get(k_sig))
check(app.net_prem.get(k_sig, 0.0) != 0.0,
      "net_prem del strike de senal SI se cuenta -> %s" % app.net_prem.get(k_sig))

# y el premium del strike de senal lo aporta _on_ticks, UNA sola vez
app.prev_vol = {}
tk1 = FakeTicker(bid=0.98, ask=1.02, last=1.02, volume=200.0, contract=sig_c, right="C")
app._on_ticks([tk1])
tk2 = FakeTicker(bid=0.98, ask=1.02, last=1.02, volume=260.0, contract=sig_c, right="C")
app._on_ticks([tk2])
check(abs(app.today_prem.get(k_sig, 0.0) - 6120.0) < 1e-6,
      "_on_ticks aporta el premium del strike de senal, sin duplicar -> %s"
      % app.today_prem.get(k_sig))


# ================================================================ premium POR VELA
print("== PREMIUM POR VELA: cuanto entro en ESE minuto, call y put por separado ==")
app = nueva_app()
app.expiry = "20260814"

# primer minuto: no hay referencia anterior -> None, NO un delta inventado
v = app._prem_de_la_vela()
check(v == (None, None, None, None),
      "1er minuto sin referencia -> None (no se inventa un delta) -> %s" % (v,))

# vela 1: entran 1000 en calls y 400 en puts
app.today_prem[("20260814", 773, "C")] = 1000.0
app.today_prem[("20260814", 773, "P")] = 400.0
app.today_net[("20260814", 773, "C")] = 800.0
app.today_net[("20260814", 773, "P")] = -300.0
v1 = app._prem_de_la_vela()
check(v1 == (1000.0, 400.0, 800.0, -300.0), "vela 1: C=1000 P=400 netC=800 netP=-300 -> %s" % (v1,))

# vela 2: el ACUMULADO sube a 1500/500, luego en ESTA vela entraron 500 y 100
app.today_prem[("20260814", 773, "C")] = 1500.0
app.today_prem[("20260814", 773, "P")] = 500.0
app.today_net[("20260814", 773, "C")] = 900.0
app.today_net[("20260814", 773, "P")] = -450.0
v2 = app._prem_de_la_vela()
check(v2 == (500.0, 100.0, 100.0, -150.0),
      "vela 2: el delta es 500/100 aunque el acumulado sea 1500/500 -> %s" % (v2,))
check(v2[0] < v1[0], "el premium POR VELA puede BAJAR (el acumulado nunca) -> clave para M10")

# suma de varios strikes del mismo lado
app.today_prem[("20260814", 774, "C")] = 250.0
v3 = app._prem_de_la_vela()
check(v3[0] == 250.0, "agrega todos los strikes del mismo lado -> %s" % v3[0])

# otra expiry NO contamina la vela de la expiry en curso
app.today_prem[("20260815", 773, "C")] = 999999.0
v4 = app._prem_de_la_vela()
check(v4[0] == 0.0, "el premium de OTRA expiry no entra en la vela -> %s" % v4[0])

# tras un reinicio (snapshot perdido) no se guarda un delta gigante
app._prem_snap = None
v5 = app._prem_de_la_vela()
check(v5 == (None, None, None, None), "tras reinicio: None en vez de un delta enorme")

# referencia de otra sesion -> delta bruto negativo -> se descarta
app._prem_snap = (99999999.0, 99999999.0, 0.0, 0.0)
v6 = app._prem_de_la_vela()
check(v6 == (None, None, None, None),
      "delta bruto negativo (imposible) -> se descarta en vez de guardar basura")

# ================================================================ panel: estado de trading
print("== PANEL: el mensaje de trading no puede mentir sobre si esta armado ==")
_te = S.TRADING_ENABLED
S.TRADING_ENABLED = True
app = nueva_app()
check("ARMADO" in app.trade_msg,
      "arrancando con TRADING_ENABLED=True el panel dice ARMADO -> '%s'" % app.trade_msg)
S.TRADING_ENABLED = False
app_off = nueva_app()
check("OFF" in app_off.trade_msg,
      "con TRADING_ENABLED=False dice OFF -> '%s'" % app_off.trade_msg)
S.TRADING_ENABLED = _te

# en REPOSO (posicion ya en el objetivo) el mensaje refleja el estado real, no se congela.
# last_sync recien puesto: se evita que _sync_pos (FakeIB sin posiciones) lo lleve a FLAT,
# que es otro camino distinto del que se quiere probar aqui.
# HORA FIJA a proposito (2026-08-10): sin esto el test depende del reloj REAL y falla si se
# corre despues de FLATTEN_HHMM, porque el EOD fuerza target=FLAT y toma la rama de venta.
_now_bak = S.now_et
S.now_et = lambda: FakeET("14:30")
app = nueva_app()
app.trading = True
app.pos = "CALL"
app.pos_qty = 1
app.target = "CALL"
app.buy_call = FakeContract(773, "C", 1001)
app.buy_put = FakeContract(772, "P", 1002)
app.ib._tk[1001] = FakeTicker(bid=0.98, ask=1.02, contract=app.buy_call)
app.reconciled = True
app.order = None
app.last_sync = time.monotonic()
app.trade_msg = "trading OFF"          # mensaje viejo pegado
app.trade_poll()
check("ARMADO" in app.trade_msg and "CALL" in app.trade_msg,
      "en reposo con posicion, el panel dice que esta armado y en que -> '%s'" % app.trade_msg)

app2 = nueva_app()
app2.trading = True
app2.pos = "FLAT"
app2.pos_qty = 0
app2.target = "FLAT"
app2.buy_call = FakeContract(773, "C", 1001)
app2.buy_put = FakeContract(772, "P", 1002)
app2.reconciled = True
app2.order = None
app2.last_sync = time.monotonic()
app2.trade_msg = "trading OFF"
app2.trade_poll()
check("ARMADO" in app2.trade_msg and "FLAT" in app2.trade_msg,
      "en reposo y plano, tambien -> '%s'" % app2.trade_msg)
S.now_et = _now_bak

# ================================================================ sesion_config
print("== SELLO DE SESION: sesion_config deja de ser un CREATE TABLE huerfano ==")
app = nueva_app()
check(app.db.execute("SELECT COUNT(*) FROM sesion_config").fetchone()[0] == 0,
      "arranca vacia")
app._sellar_sesion()                       # metodo REAL
n = app.db.execute("SELECT COUNT(*) FROM sesion_config").fetchone()[0]
check(n == 1, "tras sellar hay 1 fila -> %d" % n)

r = app.db.execute("SELECT fecha,arranque,qty,signal_threshold,adapt_frac,momentum_win,"
                   "reprice_secs,walls_band,strike_exec,walls_criterio,trading,cross_hhmm,"
                   "bars_stale_secs,pos_log_secs,gaps_activos,notas "
                   "FROM sesion_config").fetchone()
check(r[2] == S.QTY and r[3] == S.SIGNAL_THRESHOLD and r[4] == S.ADAPT_FRAC,
      "guarda los parametros VIVOS (qty=%s thr=%s adapt=%s)" % (r[2], r[3], r[4]))
check(r[5] == S.MOMENTUM_SECS,
      "momentum_win guarda los SEGUNDOS de MOMENTUM_SECS -> %s" % r[5])
check("SEGUNDOS" in (r[15] or ""), "y las notas lo explican, para no leerlo como muestras")
check(r[6] == S.REPRICE_SECS and r[7] == S.WALLS_BAND, "reprice y banda correctos")
# 2026-08-12: el valor esperado se DERIVA de la constante, no se escribe a mano. Antes se
# comparaba contra el literal "ATM real" -- que era justo el bug: la columna escribia ese texto
# a fuego sin leer EJECUCION_ITM, y el test lo bendecia. Un test que fija el literal viejo
# convierte un bug de auditoria en "comportamiento esperado".
_exec_esperado = "ITM mas profundo que quepa" if S.EJECUCION_ITM else "ATM real"
check(r[8] == _exec_esperado and r[9] == "gamma",
      "sella el CRITERIO REAL (exec=%s walls=%s) y no un literal fijo: es lo que cambio el "
      "2026-08-10 sin dejar rastro" % (r[8], r[9]))
check(r[11] == S.CROSS_HHMM and r[12] == S.BARS_STALE_SECS and r[13] == S.POS_LOG_SECS,
      "sella los parametros de los arreglos nuevos")
check(r[14] and "GAP17" in r[14] and "GAP2" in r[14],
      "gaps_activos dice QUE arreglos estaban vivos -> %s" % r[14])

# dos arranques el MISMO dia -> DOS filas distintas. Es el objetivo del sello: trocear el dia
# en tramos, para saber que codigo genero cada dato (el 2026-08-10 hubo 10 arranques).
_orig = S.datetime
hoy_real = _orig.now().strftime("%Y-%m-%d")


class _D:
    """Reloj fijo en otra hora del MISMO dia: simula un segundo arranque."""
    def strftime(self, f):
        return {"%Y-%m-%d": hoy_real, "%H:%M": "23:58", "%H:%M:%S": "23:58:07"}[f]


class _FakeDT:
    @staticmethod
    def now():
        return _D()


app._sello_arranque = None
S.datetime = _FakeDT
app._sellar_sesion()
S.datetime = _orig
n2 = app.db.execute("SELECT COUNT(*) FROM sesion_config").fetchone()[0]
check(n2 == 2, "un segundo arranque el mismo dia deja OTRA fila (no se pisan) -> %d" % n2)
horas = [x[0] for x in app.db.execute(
    "SELECT arranque FROM sesion_config ORDER BY arranque").fetchall()]
check(len(set(horas)) == 2, "las dos filas tienen arranques distintos -> %s" % horas)

# el sello NUNCA puede tumbar el arranque
app_roto = nueva_app()
app_roto.db.close()                       # BD cerrada -> cualquier escritura falla
try:
    app_roto._sellar_sesion()
    ok_no_revienta = True
except Exception:
    ok_no_revienta = False
check(ok_no_revienta, "si falla la escritura NO propaga excepcion (no bloquea setup_contracts)")

# ================================================================ EOD: MID insistente
print("== EOD: MID recotizando rapido; BID solo en los ultimos 5 min ==")
_real_now = S.now_et
app = nueva_app()
c = FakeContract(773, "C", 1001)
app.ib._tk[1001] = FakeTicker(bid=0.54, ask=0.58, contract=c)   # mid = 0.56
app.min_tick[1001] = 0.01
app.trading = True
app.pos = "CALL"
app.pos_qty = 1

# --- fuera del EOD: deadline normal ---
S.now_et = lambda: FakeET("14:30")
app.ib.ordenes = []
app.order = None
t0 = time.monotonic()
app._place(c, "SELL", "CALL", qty=1)
d_normal = app.order_deadline - t0
check(abs(d_normal - S.REPRICE_SECS) < 0.3,
      "fuera del EOD el deadline es REPRICE_SECS=%.1fs -> %.1fs" % (S.REPRICE_SECS, d_normal))

# --- 15:46 (EOD): al MID y recotizando RAPIDO ---
S.now_et = lambda: FakeET("15:46")
app.ib.ordenes = []
app.order = None
t0 = time.monotonic()
app._place(c, "SELL", "CALL", qty=1)
px = app.ib.ordenes[0][1].lmtPrice
d_eod = app.order_deadline - t0
check(px == 0.56, "15:46 -> vende al MID 0.56 (NO al bid 0.54) -> %s" % px)
check(abs(d_eod - S.EOD_REPRICE_SECS) < 0.3,
      "15:46 -> recotiza cada EOD_REPRICE_SECS=%.1fs -> %.1fs" % (S.EOD_REPRICE_SECS, d_eod))
# CORREGIDO 2026-08-10 (GAP 19): antes se exigia que el EOD fuera MAS RAPIDO. Con 1.5s se
# recolocaban ordenes encima de una cancelacion sin resolver. Ahora el EOD es MAS LENTO a
# proposito: la recotizacion no acelera el llenado, solo multiplica ordenes en vuelo.
check(d_eod > d_normal,
      "en el EOD recotiza MAS DESPACIO (12s vs 4s): respeta la latencia del broker")

# --- 15:46 con spread ANCHO: sigue al MID, no se rinde antes de tiempo ---
app.ib._tk[1001] = FakeTicker(bid=0.40, ask=0.80, contract=c)   # mid = 0.60
app.ib.ordenes = []
app.order = None
app._place(c, "SELL", "CALL", qty=1)
check(app.ib.ordenes[0][1].lmtPrice == 0.60,
      "spread ANCHO a las 15:46 -> sigue al MID 0.60, NO cruza -> %s"
      % app.ib.ordenes[0][1].lmtPrice)

# --- 15:56 (ultimos 5 min): AHORA si cruza al BID ---
S.now_et = lambda: FakeET("15:56")
app.ib.ordenes = []
app.order = None
app._place(c, "SELL", "CALL", qty=1)
check(app.ib.ordenes[0][1].lmtPrice == 0.40,
      "15:56 -> ULTIMO RECURSO: cruza al BID 0.40 -> %s" % app.ib.ordenes[0][1].lmtPrice)

# --- 15:54 todavia NO cruza (el limite es 15:55) ---
S.now_et = lambda: FakeET("15:54")
app.ib.ordenes = []
app.order = None
app._place(c, "SELL", "CALL", qty=1)
check(app.ib.ordenes[0][1].lmtPrice == 0.60,
      "15:54 -> aun al MID (el cruce empieza a las %s) -> %s"
      % (S.CROSS_HHMM, app.ib.ordenes[0][1].lmtPrice))

# --- una COMPRA nunca usa el reloj del EOD ---
S.now_et = lambda: FakeET("15:46")
app.pos = "FLAT"
app.pos_qty = 0
app.buys_pend = 0
app.ib.ordenes = []
app.order = None
t0 = time.monotonic()
app._place(c, "BUY", "CALL")
if app.ib.ordenes:
    check(abs((app.order_deadline - t0) - S.REPRICE_SECS) < 0.3,
          "una COMPRA en el EOD conserva el deadline normal")
else:
    check(True, "la COMPRA ni se coloca en el EOD (mejor aun)")
S.now_et = _real_now


# ================================================================ GAP 18
print("== GAP 18: sin restaurar el estado NO se evalua la senal ==")
app = nueva_app()
app.call = FakeContract(773, "C", 5001)
app.put = FakeContract(773, "P", 5002)
# El GIRO se provoca por la via REAL de produccion: M1 con su retardo. Antes se provocaba con
# net_call=-10640 (diff < -thr), pero desde USAR_M1=True esa rama de _update_signal esta MUERTA
# (el `elif diff < -thr` va detras de `if USAR_M1:`), asi que el test giraba por un camino que
# el sistema ya no usa y desde el 08-12 fallaba sin que la logica tuviera nada roto. El flujo se
# deja igual: sigue siendo el caso REAL del 14:52:29, y ahora ademas demuestra que NO gira por
# el.  m1_hist se alimenta igual que en modo demo (spy_direction.py:2535): un sello que YA
# cumplio el retardo, para no esperar RETARDO_M1_MIN minutos reales.
app.m1_hist = [(time.monotonic() - (S.RETARDO_M1_MIN * 60.0 + 5.0), "DOWN")]
app._intradia_ok = False              # como en los ~4 s del arranque
app.state = "UP"
app.net_call, app.net_put = -10640.0, 0.0     # el caso REAL del 14:52:29
app._update_signal()
check(app.state == "UP", "con _intradia_ok=False el estado NO cambia -> %s" % app.state)
n_tr = app.db.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]
check(n_tr == 0, "y NO escribe filas falsas en transitions -> %d" % n_tr)
check(app.flow_hist == [], "tampoco contamina la historia de flujo")

# tras restaurar, la senal funciona con normalidad (no se rompio nada)
app._intradia_ok = True
app.net_call, app.net_put = -10640.0, 0.0
app._update_signal()
check(app.state == "DOWN",
      "con _intradia_ok=True la senal gira normalmente -> %s" % app.state)
n_tr = app.db.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]
check(n_tr >= 1, "y ahora si registra el giro -> %d" % n_tr)

# _load_intradia deja la bandera en True aunque no haya nada que restaurar
app2 = nueva_app()
check(app2._intradia_ok is False, "arranca en False")
app2._load_intradia()
check(app2._intradia_ok is True,
      "_load_intradia la pone en True aunque la BD este vacia (no bloquea la senal para siempre)")


# ================================================================ GAP 19
print("== GAP 19: NO recolocar sobre una orden que IBKR aun no ha cancelado de verdad ==")


class FakeIBLatente(FakeIB):
    """FakeIB que REPRODUCE el fallo real del 2026-08-10 15:45.

    Los 14 cold runs pasaron en verde con el bug dentro porque el FakeIB normal cancelaba
    al instante. Aqui se imita a IBKR: al cancelar, la orden pasa a 'Cancelled' (estado
    FINAL, sale de openTrades) pero SIGUE VIVA por dentro y puede ejecutarse despues."""
    def __init__(self):
        super().__init__()
        self.vivas_de_verdad = []      # lo que IBKR tiene realmente, aunque diga otra cosa
        self.rechazos_margen = 0

    def placeOrder(self, contract, order):
        # si ya hay una venta viva DE VERDAD, IBKR la rechazaria por margen (short descubierto)
        if order.action == "SELL" and self.vivas_de_verdad:
            self.rechazos_margen += 1
        t = super().placeOrder(contract, order)
        if order.action == "SELL":
            self.vivas_de_verdad.append(t)
        return t

    def cancelOrder(self, order):
        # IBKR responde 'Cancelled' -> la orden desaparece de openTrades()...
        for t in self.ordenes:
            if t[1] is order:
                pass
        for t in list(self.vivas_de_verdad):
            if t.order is order:
                t.orderStatus.status = "Cancelled"     # ...pero NO se quita de vivas_de_verdad
        return None

    def openTrades(self):
        # replica ib_insync: excluye DoneStates ('Filled','Cancelled','ApiCancelled')
        return [t for t in self.vivas_de_verdad
                if t.orderStatus.status not in ("Filled", "Cancelled", "ApiCancelled")]


app = nueva_app()
app.ib = FakeIBLatente()
c = FakeContract(773, "C", 1001)
app.ib._tk[1001] = FakeTicker(bid=0.30, ask=0.34, contract=c)
app.min_tick[1001] = 0.01
app.trading = True
app.pos = "CALL"
app.pos_qty = 1

# 1) primera venta
app.order = None
app._place(c, "SELL", "CALL", qty=1)
check(len(app.ib.ordenes) == 1, "coloca la 1a venta -> %d" % len(app.ib.ordenes))
tr = app.ib.ordenes[0][1]

# 2) se cancela: IBKR dice 'Cancelled' y desaparece de openTrades, PERO sigue viva
app.ib.cancelOrder(tr)
app.last_cancel_ts = time.monotonic()
check(app.ib.openTrades() == [], "tras el cancel, openTrades() esta VACIO (IBKR dice cancelada)")
check(len(app.ib.vivas_de_verdad) == 1, "pero la orden SIGUE VIVA en IBKR (el escenario real)")
check(app._live_orders() == [],
      "_live_orders() tampoco la ve: NINGUN estado la habria detectado")

# 3) el arreglo: _place NO coloca durante el cooldown, aunque no vea nada vivo
n_antes = len(app.ib.ordenes)
app._place(c, "SELL", "CALL", qty=1)
check(len(app.ib.ordenes) == n_antes,
      "GAP 19: NO coloca durante CANCEL_SETTLE_SECS aunque openTrades este vacio -> %d ordenes"
      % len(app.ib.ordenes))
check(app.ib.rechazos_margen == 0,
      "y por tanto IBKR no habria rechazado nada por margen -> %d rechazos" % app.ib.rechazos_margen)
check("cancelacion" in app.trade_msg, "el panel explica por que espera -> '%s'" % app.trade_msg)

# 4) repetido 4 veces seguidas (como paso a las 15:45) -> sigue sin colocar
for _ in range(4):
    app._place(c, "SELL", "CALL", qty=1)
check(len(app.ib.ordenes) == n_antes,
      "4 intentos seguidos y NINGUNO coloca (a las 15:45 se colocaron 4) -> %d"
      % len(app.ib.ordenes))
check(app.ib.rechazos_margen == 0, "cero rechazos por margen (el 2026-08-10 hubo 4)")

# 5) pasado el cooldown, si coloca (no bloquea la salida para siempre)
app.ib.vivas_de_verdad = []               # IBKR ya resolvio la anterior
app.last_cancel_ts = time.monotonic() - (S.CANCEL_SETTLE_SECS + 1)
app.order = None
app._place(c, "SELL", "CALL", qty=1)
check(len(app.ib.ordenes) == n_antes + 1,
      "pasado el cooldown SI vuelve a colocar (no bloquea la salida) -> %d" % len(app.ib.ordenes))

# 6) el parametro que causo el fallo
check(S.EOD_REPRICE_SECS >= 10.0,
      "EOD_REPRICE_SECS ya no es mas rapido que la latencia del broker -> %.1fs"
      % S.EOD_REPRICE_SECS)
check(S.CANCEL_SETTLE_SECS >= 5.0, "CANCEL_SETTLE_SECS razonable -> %.1fs" % S.CANCEL_SETTLE_SECS)


# ================================================================ ventana 16:00-16:15
print("== RECOLECTAR hasta %s NO puede significar OPERAR hasta %s ==" % (S.CLOSE_HHMM, S.CLOSE_HHMM))
_now_bak2 = S.now_et
app = nueva_app()
c = FakeContract(773, "C", 1001)
app.ib._tk[1001] = FakeTicker(bid=0.30, ask=0.34, contract=c)
app.min_tick[1001] = 0.01
app.buy_call = c
app.buy_put = FakeContract(772, "P", 1002)
app.ib._tk[1002] = FakeTicker(bid=0.30, ask=0.34, contract=app.buy_put)
app.trading = True
app.reconciled = True
app.pos = "FLAT"
app.pos_qty = 0
app.target = "CALL"          # la senal querria comprar
app.last_sync = time.monotonic()
app.last_cancel_ts = 0.0

S.now_et = lambda: FakeET("16:05")
app.ib.ordenes = []
app.order = None
app.trade_poll()
check(len(app.ib.ordenes) == 0,
      "16:05 -> RECOLECTA pero NO abre posiciones -> %d ordenes" % len(app.ib.ordenes))
check(app.target == "FLAT", "16:05 -> el objetivo sigue forzado a FLAT -> %s" % app.target)

# y a las 15:30 (sesion normal) SI podria abrir: no se ha roto el comportamiento normal
S.now_et = lambda: FakeET("13:00")
app.target = "CALL"
app.ib.ordenes = []
app.order = None
app.buys_pend = 0
app.trade_poll()
check(len(app.ib.ordenes) == 1,
      "13:00 -> en sesion normal SI abre (no se rompio nada) -> %d" % len(app.ib.ordenes))
S.now_et = _now_bak2

print()
if FAILS:
    print("FALLOS (%d):" % len(FAILS))
    for f in FAILS:
        print("   - " + f)
    sys.exit(1)
print("TODO VERDE")
sys.exit(0)
