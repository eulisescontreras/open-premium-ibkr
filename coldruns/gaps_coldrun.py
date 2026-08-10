# -*- coding: utf-8 -*-
"""
COLD RUN DE VERIFICACION DE LOS 7 GAPS (SPY Direction).

Objetivo: DEMOSTRAR ejecutando el CODIGO REAL que cada gap ocurre de verdad, o
DESCARTARLO. No reimplementa logica: importa spy_direction y llama a sus funciones
y metodos reales (_on_ticks, compute_walls, _persist_walls, _log_minute, end_session,
trade_poll, _update_signal, run_gui). El unico stub es la frontera IBKR (FakeIB), igual
que hace spy_walls_coldrun.py.

NO toca la BD de produccion: cada app usa sqlite :memory:.
NO coloca ordenes reales: FakeIB.

Salida: por cada gap -> CONFIRMADO / DESCARTADO + la evidencia numerica.
"""
import math
import os
import sqlite3
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
import spy_direction as S

S.ENABLE_TOAST = False          # no lanzar toasts durante la verificacion
import logging as _lg           # no contaminar los logs de produccion
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

RES = []


def veredicto(gap, confirmado, evidencia):
    marca = "CONFIRMADO" if confirmado else "DESCARTADO "
    print("  [%s] %s" % (marca, evidencia))
    RES.append((gap, confirmado, evidencia))


def nueva_app(demo_real=False):
    """SpyDirection real con BD en memoria. demo=True al construir para NO abrir
    spy_history.db de produccion; luego se apaga el flag para que actue como app real."""
    a = S.SpyDirection(demo=True)
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.demo = demo_real
    return a


class FakeGreeks:
    def __init__(self, gamma):
        self.gamma = gamma


class FakeTicker:
    def __init__(self, contract, oi=None, gamma=None, volume=0.0, last=1.0, bid=0.9, ask=1.1):
        self.contract = contract
        r = contract.right
        self.callOpenInterest = oi if r == "C" else float("nan")
        self.putOpenInterest = oi if r == "P" else float("nan")
        self.modelGreeks = FakeGreeks(gamma) if gamma is not None else None
        self.volume = volume
        self.last = last
        self.bid = bid
        self.ask = ask
        self.time = "2026-08-10 10:00:00"


class FakeContract:
    def __init__(self, strike, right, conId, expiry="20260810"):
        self.strike = strike
        self.right = right
        self.conId = conId
        self.symbol = "SPY"
        self.secType = "OPT"
        self.lastTradeDateOrContractMonth = expiry
        self.localSymbol = "SPY %s%s" % (strike, right)


class FakeIB:
    def __init__(self):
        self._tk = {}
        self.cancelled = []
        self.disconnected = False
        self.connected = True
        self.placed = []
    def isConnected(self):
        return self.connected
    def ticker(self, c):
        return self._tk[c.conId]
    def sleep(self, s):
        pass
    def openTrades(self):
        return list(self._open_trades) if hasattr(self, "_open_trades") else []
    def positions(self):
        return []
    def cancelOrder(self, o):
        self.cancelled.append(o)
    def disconnect(self):
        self.disconnected = True
        self.connected = False
    def placeOrder(self, c, o):
        self.placed.append((c, o))
        tr = FakeTrade(c, o)
        return tr
    def reqContractDetails(self, c):
        return []
    def accountSummary(self):
        return []


class FakeOrderStatus:
    def __init__(self, status="Submitted"):
        self.status = status
        self.avgFillPrice = 0.0


class FakeTrade:
    def __init__(self, contract, order):
        self.contract = contract
        self.order = order
        self.orderStatus = FakeOrderStatus()


print("=" * 78)
print("COLD RUN DE VERIFICACION DE LOS 7 GAPS - ejecutando el CODIGO REAL")
print("=" * 78)


# ============================================================ GAP 2 (primero: es el mas directo)
print("\n== GAP 2: doble conteo de today_prem en los strikes ATM ==")
print("   Metodo: _on_ticks REAL y compute_walls REAL sobre el MISMO contrato (mismo conId),")
print("           con el mismo delta de volumen. Si today_prem suma 2x -> confirmado.")
app = nueva_app()
app.ib = FakeIB()
app.expiry = "20260810"
app.spy_price = 773.0
LAST = 2.00
c_atm = FakeContract(773, "C", 1)                 # ATM call: esta en la SENAL y en la BANDA
app.call = c_atm
app.put = FakeContract(773, "P", 2)
app.band_contracts = [c_atm]                      # el mismo contrato tambien esta en la banda
app.ib._tk[1] = FakeTicker(c_atm, oi=500, gamma=0.05, volume=0.0, last=LAST, bid=1.9, ask=2.1)

key = ("20260810", 773, "C")
# 1) linea base de volumen en AMBOS caminos (prev None -> no acumulan)
app._on_ticks([app.ib._tk[1]])                    # metodo REAL
app.compute_walls()                               # metodo REAL
base = app.today_prem.get(key, 0.0)

# 2) llega volumen: 100 contratos operados
app.ib._tk[1].volume = 100.0
app._on_ticks([app.ib._tk[1]])                    # camino SENAL suma
tras_ticks = app.today_prem.get(key, 0.0)
app.compute_walls()                               # camino WALLS suma OTRA VEZ el mismo delta
tras_walls = app.today_prem.get(key, 0.0)

esperado = LAST * 100.0 * 100.0                   # last * dvol * 100
veredicto("GAP 2", abs(tras_walls - 2 * esperado) < 1e-6 and abs(tras_ticks - esperado) < 1e-6,
          "base=%.0f | tras _on_ticks=%.0f (esperado %.0f) | tras compute_walls=%.0f "
          "(=%.1fx el real)" % (base, tras_ticks, esperado, tras_walls,
                                (tras_walls / esperado) if esperado else 0))
print("      -> prev_vol=%s  band_prev_vol=%s  (dicts SEPARADOS, por eso ambos suman)"
      % (app.prev_vol, app.band_prev_vol))


# ============================================================ GAP 7
print("\n== GAP 7: _log_minute borra net_prem/open_interest/gamma escritos por _persist_walls ==")
print("   Metodo: _persist_walls REAL escribe 10 columnas; luego _log_minute REAL escribe 7")
print("           sobre la MISMA PK (fecha,hora,expiry,strike,right). Se relee la fila.")
app7 = nueva_app()
app7.ib = FakeIB()
app7.expiry = "20260810"
app7.spy_price = 773.0
k7 = ("20260810", 773, "C")
app7.accum = {k7: 50000.0}
app7.today_prem = {k7: 12000.0}
app7.net_prem = {k7: 7000.0}
app7.walls = {"put_wall": 770.0, "call_wall": 775.0, "max_pain_static": 773.0,
              "max_pain_dyn": 773.0, "prem_center": 773.2, "spot": 773.0}
app7.gex = {"gex_total": 1.5e9, "regime": "LONG", "gamma_flip": 772.5}
app7._persist_walls({773: 500.0}, {}, {773: 0.05}, {})     # metodo REAL

import datetime as _dt
ahora = _dt.datetime.now()
fila_antes = app7.db.execute(
    "SELECT open_interest,gamma,net_prem FROM premium_minute "
    "WHERE strike=773 AND right='C'").fetchone()

# _log_minute REAL con un bar_dt que cae en la MISMA fecha/hora "%Y-%m-%d %H:%M"
bar_dt = ahora.strftime("%Y-%m-%d %H:%M:00")
vals = {"close": 773.2, "rsi": 55.0, "ema8": 773.0, "ema21": 772.5, "ema50": 772.0,
        "macd_line": 0.1, "macd_signal": 0.05, "macd_hist": 0.05, "bb_up": 775.0,
        "bb_mid": 773.0, "bb_low": 771.0, "atr": 1.2, "atr_pct": 0.15, "vwap": 773.1,
        "obv_trend": "bullish", "score": 3, "dir": "BULL"}
app7._log_minute(vals, bar_dt)                              # metodo REAL
fila_despues = app7.db.execute(
    "SELECT open_interest,gamma,net_prem FROM premium_minute "
    "WHERE strike=773 AND right='C'").fetchone()

perdio = (fila_antes is not None and fila_antes[0] is not None
          and fila_despues is not None and fila_despues[0] is None)
veredicto("GAP 7", perdio,
          "antes de _log_minute: (OI,gamma,net_prem)=%s  ->  despues: %s"
          % (fila_antes, fila_despues))


# ============================================================ GAP 4
print("\n== GAP 4: posicion huerfana si la venta EOD no llena antes de las 16:00 ==")
print("   Metodo: trade_poll REAL a las 15:50 con posicion abierta -> coloca SELL; la orden")
print("           NO llena; luego end_session REAL (lo que hace tick() a las 16:00).")
app4 = nueva_app()
app4.ib = FakeIB()
app4.trading = True
app4.reconciled = True
app4.pos = "CALL"
app4.target = "CALL"
app4.expiry = "20260810"
app4.spy_price = 773.0
app4.buy_call = FakeContract(774, "C", 10)
app4.buy_put = FakeContract(772, "P", 11)
app4.ib._tk[10] = FakeTicker(app4.buy_call, last=1.50, bid=1.40, ask=1.60)
app4.ib._tk[11] = FakeTicker(app4.buy_put, last=1.50, bid=1.40, ask=1.60)
app4.min_tick = {10: 0.01, 11: 0.01}

_orig_now_et = S.now_et


class _FakeET:
    def __init__(self, wd, hhmm):
        self._wd = wd
        self._hhmm = hhmm
    def weekday(self):
        return self._wd
    def strftime(self, f):
        return self._hhmm


S.now_et = lambda: _FakeET(0, "15:50")      # lunes 15:50 ET -> pasado FLATTEN_HHMM
app4.trade_poll()                            # metodo REAL -> debe poner target FLAT y vender
target_tras = app4.target
orden_puesta = app4.order is not None
app4.ib._open_trades = []                    # la orden sigue viva pero no llena
S.now_et = _orig_now_et

pos_antes_cierre = app4.pos
app4.end_session()                           # metodo REAL: lo que hace tick() a las 16:00
huerfana = (pos_antes_cierre == "CALL" and app4.pos == "CALL" and app4.ib.disconnected)
veredicto("GAP 4", huerfana,
          "15:50 -> target=%s, orden SELL colocada=%s | tras end_session(): pos=%s, "
          "desconectado=%s -> la posicion SIGUE ABIERTA sin nadie que la cierre"
          % (target_tras, orden_puesta, app4.pos, app4.ib.disconnected))


# ============================================================ GAP 5  (ARREGLADO 2026-08-10)
# Este test DEMOSTRABA el gap: con MOMENTUM_WIN=8 EVENTOS la ventana se llenaba en
# milisegundos, asi que el "momentum" no medía ningun intervalo temporal (el aviso WARN y el
# FLIP llegaban a saltar en el mismo milisegundo). Ahora el momentum se mide sobre
# MOMENTUM_SECS segundos reales, asi que el test se invierte: se comprueba que una RAFAGA de
# eventos instantaneos YA NO genera momentum.
print("\n== GAP 5 (ARREGLADO): el momentum mide TIEMPO, no numero de eventos ==")
print("   Metodo: rafaga de _update_signal REAL; el momentum debe quedarse en 0 porque no han")
print("           pasado MOMENTUM_SECS=%.0f s de tiempo real." % S.MOMENTUM_SECS)
app5 = nueva_app()
app5.net_call = 0.0
app5.net_put = 0.0
t0 = time.perf_counter()
for i in range(20):
    app5.net_call += 1000.0
    app5._update_signal()                    # metodo REAL
dt_ventana = time.perf_counter() - t0
veredicto("GAP 5", dt_ventana < 0.5 and app5.last_momentum == 0.0,
          "20 eventos en %.4f s de tiempo real -> momentum=%.0f (antes habria sido enorme). "
          "La ventana ya NO se llena con rafagas: exige %.0f s reales"
          % (dt_ventana, app5.last_momentum, S.MOMENTUM_SECS))


# ============================================================ GAP 3
print("\n== GAP 3: strikes de ejecucion congelados (setup_contracts corre 1 vez/sesion) ==")
print("   Metodo: se mueve spy_price y se corre trade_poll REAL; se comprueba si buy_call")
print("           cambia de strike sin volver a llamar setup_contracts.")
app3 = nueva_app()
app3.ib = FakeIB()
app3.trading = True
app3.reconciled = True
app3.expiry = "20260810"
app3.spy_price = 773.0
app3.buy_call = FakeContract(774, "C", 20)   # OTM al precio de apertura 773
app3.buy_put = FakeContract(772, "P", 21)
strike_inicial = app3.buy_call.strike
app3.spy_price = 781.0                        # SPY sube 8 dolares durante el dia
app3.target = "FLAT"
app3.pos = "FLAT"
app3.trade_poll()                             # metodo REAL
strike_final = app3.buy_call.strike
dist = strike_final - app3.spy_price
veredicto("GAP 3", strike_inicial == strike_final,
          "SPY 773 -> 781 | buy_call.strike sigue en %g (era %g) -> queda %+.0f$ ITM, "
          "ya no es 'ATM del lado OTM'" % (strike_final, strike_inicial, -dist))


# ============================================================ GAP 6
print("\n== GAP 6: numero de lineas de market data simultaneas ==")
print("   Metodo: aritmetica sobre las CONSTANTES REALES del modulo + evidencia del log de hoy.")
n_senal = 2
n_ejec = 2
n_base = S.BASELINE_EXPIRIES * 2 * (1 + S.ITM_DEPTH)
n_banda = S.WALLS_BAND * 2 * 2
total = n_senal + n_ejec + n_base + n_banda
veredicto("GAP 6", total > 60,
          "senal=%d + ejecucion=%d + baseline=%d (%d exp x 2 lados x %d strikes) + "
          "banda=%d (%d strikes x 2 rights) = %d lineas (limite IBKR ~100)"
          % (n_senal, n_ejec, n_base, S.BASELINE_EXPIRIES, 1 + S.ITM_DEPTH,
             n_banda, S.WALLS_BAND * 2, total))
print("      -> el log REAL de hoy confirma la banda: 'WALLS banda lista (streaming): 40 contratos'")


# ============================================================ GAP 1 (el mas dificil: vive en run_gui)
print("\n== GAP 1: sin reconexion (la logica vive en el closure tick() de run_gui) ==")
print("   Metodo: se ejecuta run_gui REAL con Tkinter y un FakeIB. Tras N ticks conectado,")
print("           se simula la caida del socket y se cuenta si vuelve a llamar connect().")

llamadas = {"connect": 0, "setup": 0}


class AppGap1(S.SpyDirection):
    """SpyDirection REAL; solo se instrumenta la frontera IBKR y se cuentan las reconexiones."""
    def connect(self):
        llamadas["connect"] += 1
        self.ib.connected = True
    def setup_contracts(self):
        llamadas["setup"] += 1
        self.spy_price = 773.0
        self.expiry = "20260810"
        return True
    def is_market_open(self):
        return True                      # forzamos "mercado abierto" todo el test
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


try:
    import tkinter as _tkmod
    S.REFRESH_SECS = 0.05                # acelerar el test (real: 1.0 s)
    g1 = AppGap1(demo=True)
    g1.db.close()
    g1.db = sqlite3.connect(":memory:")
    g1._init_db()
    g1.demo = False
    g1.ib = FakeIB()
    g1.ib.connected = False              # arranca desconectado -> el primer tick conecta

    estado = {"ticks": 0, "caida_en": None}
    _orig_after = None

    def _vigilar(root):
        """Cada 150 ms: a los ~8 ticks tira el socket; a los ~30 cierra la ventana."""
        estado["ticks"] += 1
        if estado["ticks"] == 8:
            g1.ib.connected = False      # CAIDA DEL SOCKET a mitad de sesion
            estado["caida_en"] = llamadas["connect"]
        if estado["ticks"] >= 30:
            try:
                root.destroy()
            except Exception:
                pass
            return
        root.after(150, lambda: _vigilar(root))

    _orig_mainloop = _tkmod.Tk.mainloop

    def _mainloop_con_vigilante(self, *a, **k):
        self.after(150, lambda: _vigilar(self))
        return _orig_mainloop(self, *a, **k)

    _tkmod.Tk.mainloop = _mainloop_con_vigilante
    S.run_gui(g1)                        # FUNCION REAL
    _tkmod.Tk.mainloop = _orig_mainloop

    reconecto = llamadas["connect"] > estado["caida_en"] if estado["caida_en"] else None
    veredicto("GAP 1", reconecto is False,
              "connect() llamado %d vez/veces en total; en el momento de la caida iban %s. "
              "Tras tirar el socket NO hubo reintento -> la app queda muda sin error"
              % (llamadas["connect"], estado["caida_en"]))
except Exception as e:
    print("  [NO VERIFICADO] no se pudo correr run_gui headless: %s" % e)
    RES.append(("GAP 1", None, "NO VERIFICADO: %s" % e))


# ============================================================ resumen
print("\n" + "=" * 78)
print("RESUMEN")
print("=" * 78)
for gap, ok, ev in RES:
    if ok is None:
        print("  %-7s NO VERIFICADO" % gap)
    else:
        print("  %-7s %s" % (gap, "CONFIRMADO - ocurre de verdad" if ok else "DESCARTADO - no ocurre"))
conf = sum(1 for _, ok, _ in RES if ok)
print("\n%d de %d gaps CONFIRMADOS ejecutando el codigo real." % (conf, len(RES)))
