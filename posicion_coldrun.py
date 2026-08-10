# -*- coding: utf-8 -*-
"""
Cold run HEADLESS del registro de OPERACIONES, greeks del contrato, acumulado NETO por strike,
ventanas moviles e auto-recuperacion del stream de barras (GAP 17).

Ejercita el CODIGO REAL (metodos de SpyDirection con un FakeIB), NO reimplementaciones:
  _greeks_de, _on_filled, _trade_abrir, _trade_cerrar, _pos_snapshot, _seguir_extremos,
  _on_ticks, _persist_accum, _load_accum/_load_estado_dia, _flujo_ventana,
  _chequear_barras, _subscribe_bars.

Mismo patron de FakeIB que spy_walls_coldrun.py (regla 9: reusar, no recrear).

Correr:  python posicion_coldrun.py
Exit 0 = todo OK ; Exit 1 = fallo (imprime el detalle).
"""
import sqlite3
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import spy_direction as S

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


# ---------------------------------------------------------------- Fakes
class FakeGreeks:
    def __init__(self, delta=None, gamma=None, theta=None, vega=None, iv=None, und=None):
        self.delta = delta
        self.gamma = gamma
        self.theta = theta
        self.vega = vega
        self.impliedVol = iv
        self.undPrice = und


class FakeTicker:
    def __init__(self, bid=None, ask=None, last=None, volume=None, greeks=None,
                 contract=None, right="C", oi=None):
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
        self.localSymbol = "SPY  %s%s" % (expiry, right)


class FakeOrderStatus:
    def __init__(self, avgFillPrice, filled, status="Filled"):
        self.avgFillPrice = avgFillPrice
        self.filled = filled
        self.status = status


class FakeTrade:
    def __init__(self, avgFillPrice, filled):
        self.orderStatus = FakeOrderStatus(avgFillPrice, filled)
        self.order = object()


class FakeIB:
    """Solo lo que tocan los metodos bajo prueba."""
    def __init__(self):
        self._tk = {}          # conId -> FakeTicker
        self.bars_pedidas = 0  # cuantas veces se repidio el stream (backoff)
        self.cancels = 0

    def isConnected(self):
        return True

    def ticker(self, c):
        return self._tk.get(c.conId)

    def reqHistoricalData(self, *a, **k):
        self.bars_pedidas += 1
        return ["BAR-NUEVA"]

    def cancelHistoricalData(self, bars):
        self.cancels += 1

    def positions(self):
        return []

    def openTrades(self):
        return []


def nueva_app():
    app = S.SpyDirection(demo=True)
    app.db.close()
    app.db = sqlite3.connect(":memory:")
    app._init_db()
    app.ib = FakeIB()
    app.demo = False            # que el codigo siga las rutas REALES, no las de demo
    app.expiry = "20260814"
    app.spy_price = 773.00
    return app


# ================================================================ TEST A: greeks del contrato
print("== TEST A: _greeks_de (el contrato operado NO tiene greeks propias) ==")
app = nueva_app()

# contrato de EJECUCION: su ticker NO trae modelGreeks (se suscribe con genericTickList="")
ejec = FakeContract(773, "C", 1001)
app.ib._tk[1001] = FakeTicker(bid=0.78, ask=0.82, greeks=None, contract=ejec)
# el MISMO contrato en la BANDA: objeto distinto, conId distinto (ib_insync indexa por
# id(objeto)), y SU ticker si trae greeks porque la banda pide "100,101,106"
banda = FakeContract(773, "C", 2001)
app.ib._tk[2001] = FakeTicker(bid=0.78, ask=0.82,
                              greeks=FakeGreeks(delta=0.47, gamma=0.26, theta=-0.31,
                                                vega=0.09, iv=0.18, und=773.0),
                              contract=banda)
app.band_contracts = [banda]

check(app.ib.ticker(ejec).modelGreeks is None,
      "el ticker del contrato de EJECUCION no tiene modelGreeks (reproduce el bug real)")
g = app._greeks_de(ejec)
check(g["delta"] == 0.47 and g["gamma"] == 0.26 and g["theta"] == -0.31,
      "_greeks_de recupera delta/gamma/theta del ticker de la BANDA -> %s" % g)
check(g["iv"] == 0.18 and g["und_price"] == 773.0, "_greeks_de trae iv y undPrice -> %s/%s"
      % (g["iv"], g["und_price"]))

# strike que NO esta en la banda -> todo None, NUNCA un valor inventado (regla 13)
fuera = FakeContract(999, "C", 1002)
g2 = app._greeks_de(fuera)
check(all(v is None for v in g2.values()),
      "strike fuera de la banda -> todas las greeks None (no se inventa nada)")
# distinto RIGHT en el mismo strike no debe colarse
g3 = app._greeks_de(FakeContract(773, "P", 1003))
check(all(v is None for v in g3.values()), "773P no toma por error las greeks de 773C")
# distinta EXPIRY tampoco
g4 = app._greeks_de(FakeContract(773, "C", 1004, expiry="20260815"))
check(all(v is None for v in g4.values()), "otra expiry no toma las greeks de la banda")


# ================================================================ TEST B: ciclo real BUY -> SELL
print("== TEST B: _on_filled REAL, ciclo completo BUY -> SELL ==")
app = nueva_app()
ejec = FakeContract(773, "C", 1001)
banda = FakeContract(773, "C", 2001)
app.ib._tk[1001] = FakeTicker(bid=0.78, ask=0.82, contract=ejec)
app.ib._tk[2001] = FakeTicker(bid=0.78, ask=0.82,
                              greeks=FakeGreeks(delta=0.47, gamma=0.26, theta=-0.31,
                                                vega=0.09, iv=0.18, und=773.0),
                              contract=banda)
app.band_contracts = [banda]
app.min_tick[1001] = 0.01
app.buy_call = ejec

# --- COMPRA (recorre _on_filled real) ---
app.order = FakeTrade(0.80, 1)
app.order_action, app.order_side, app.order_contract = "BUY", "CALL", ejec
app._on_filled()

check(app.pos == "CALL" and app.entry_price == 0.80, "tras el fill de compra: pos=CALL @0.80")
check(app.trade_id is not None, "se abrio un trade -> id=%s" % app.trade_id)
row = app.db.execute("SELECT strike,right,side,entry_price,delta_entrada,gamma_entrada,"
                     "iv_entrada,spy_entrada FROM trades WHERE trade_id=?",
                     (app.trade_id,)).fetchone()
check(row is not None and row[0] == 773 and row[2] == "CALL" and row[3] == 0.80,
      "fila en 'trades' con strike/side/entrada -> %s" % (row,))
check(row[4] == 0.47 and row[5] == 0.26 and row[6] == 0.18,
      "las GREEKS de entrada quedaron guardadas -> delta=%s gamma=%s iv=%s"
      % (row[4], row[5], row[6]))
n_ent = app.db.execute("SELECT COUNT(*) FROM posicion_minuto WHERE tipo='entrada'").fetchone()[0]
check(n_ent == 1, "hay 1 fila de recorrido tipo 'entrada' -> %d" % n_ent)

# --- RECORRIDO a 1 Hz: sube a 2.10 y baja a 1.25 (el episodio real del 2026-08-10) ---
for px in (0.86, 1.04, 1.84, 2.10, 1.90, 1.50, 1.25):
    app._seguir_extremos(px)
check(app.mfe == 2.10, "MFE sigue el maximo del recorrido -> %s" % app.mfe)
check(app.mae == 0.80, "MAE se queda en el minimo (la propia entrada) -> %s" % app.mae)

# --- VENTA ---
app.ib._tk[1001] = FakeTicker(bid=1.23, ask=1.27, contract=ejec)
app.exit_reason = "giro"
app.order = FakeTrade(1.25, 1)
app.order_action, app.order_side, app.order_contract = "SELL", "CALL", ejec
app._on_filled()

check(app.pos == "FLAT" and app.trade_id is None, "tras el fill de venta: FLAT y trade cerrado")
row = app.db.execute("SELECT exit_price,profit,pct,mfe,mae,razon_salida,segundos,hora_salida "
                     "FROM trades ORDER BY trade_id DESC LIMIT 1").fetchone()
check(row[0] == 1.25, "exit_price guardado -> %s" % row[0])
check(abs(row[1] - 45.0) < 1e-6, "profit +45.00 (entrada 0.80 -> salida 1.25) -> %s" % row[1])
check(row[3] == 2.10 and row[4] == 0.80, "MFE/MAE persistidos -> %s / %s" % (row[3], row[4]))
check(row[5] == "giro", "razon_salida='giro' -> %s" % row[5])
check(row[7] is not None, "hora_salida rellenada -> %s" % row[7])
# EL DATO QUE MOTIVA TODO: cuanto se dejo sobre la mesa
dejado = (row[3] - row[0]) * 100.0
check(abs(dejado - 85.0) < 1e-6,
      "se puede calcular lo DEJADO SOBRE LA MESA = (MFE-salida)*100 = %.0f $" % dejado)
n_sal = app.db.execute("SELECT COUNT(*) FROM posicion_minuto WHERE tipo='salida'").fetchone()[0]
check(n_sal == 1, "hay 1 fila de recorrido tipo 'salida' -> %d" % n_sal)

# una operacion de 10 s (sin ninguna fila de 'minuto') conserva su recorrido igual
n_tot = app.db.execute("SELECT COUNT(*) FROM posicion_minuto").fetchone()[0]
check(n_tot == 2, "operacion corta: 2 filas (entrada+salida) SIN muestreo de minuto -> %d" % n_tot)


# ================================================================ TEST B-bis: contexto entrada
print("== TEST B-bis: contexto de MERCADO guardado en la compra ==")
r = app.db.execute("SELECT rsi_entrada,ta_score_entrada,ta_dir_entrada,atr_pct_entrada,"
                   "bb_ancho_entrada,dist_vwap_entrada,gex_entrada,regime_entrada,"
                   "dist_flip_entrada,dist_prem_center_entrada,dist_call_wall_entrada,"
                   "minuto_sesion_entrada FROM trades ORDER BY trade_id DESC LIMIT 1").fetchone()
check(r is not None, "la fila de trades tiene las columnas de contexto")
check(r[11] is not None, "minuto_sesion_entrada calculado -> %s" % r[11])
# sin TA ni walls cargados, el contexto va a NULL: NO se inventa (regla 13)
check(r[0] is None and r[6] is None,
      "sin TA/GEX disponibles el contexto va a NULL, no a 0 -> rsi=%s gex=%s" % (r[0], r[6]))

# con TA y walls reales, el contexto se rellena y son DISTANCIAS al precio
app_ctx = nueva_app()
app_ctx.spy_price = 773.60
app_ctx.ta_vals = {"rsi": 55.0, "score": 2, "dir": "BULL", "atr_pct": 0.02,
                   "bb_up": 774.50, "bb_low": 773.50, "bb_mid": 774.00, "vwap": 773.00}
app_ctx.walls = {"prem_center": 773.00, "call_wall": 775.0, "put_wall": 772.0}
app_ctx.gex = {"gex_total": 2.5e11, "regime": "LONG", "gamma_flip": 772.50}
ctx = app_ctx._contexto_entrada()
check(abs(ctx["dist_vwap"] - 0.60) < 1e-9,
      "dist_vwap = precio - vwap = +0.60 (distancia, no valor absoluto) -> %s" % ctx["dist_vwap"])
check(abs(ctx["dist_flip"] - 1.10) < 1e-9, "dist_flip = +1.10 -> %s" % ctx["dist_flip"])
check(abs(ctx["dist_call_wall"] + 1.40) < 1e-9,
      "dist_call_wall = -1.40 (precio por DEBAJO de la wall) -> %s" % ctx["dist_call_wall"])
check(abs(ctx["bb_ancho"] - (1.0 / 774.0 * 100.0)) < 1e-9,
      "bb_ancho en %% del precio (precursor M7) -> %s" % ctx["bb_ancho"])
check(ctx["regime"] == "LONG" and ctx["ta_dir"] == "BULL", "regime y ta_dir copiados")


# ================================================================ TEST C: recorrido por minuto
print("== TEST C: _pos_snapshot('minuto') con greeks y spread ==")
app_c = app
app_c.pos = "CALL"
app_c.entry_price = 0.80
app_c.trade_id = 1
app_c.trade_open = {"hora": S.datetime.now().strftime("%H:%M:%S")}
app_c.buy_call = ejec
app_c.ib._tk[1001] = FakeTicker(bid=1.20, ask=1.30, contract=ejec)
app_c._pos_snapshot("minuto")
r = app_c.db.execute("SELECT bid,ask,mid,pnl,pnl_pct,delta,gamma,spy,seg_desde_entrada "
                     "FROM posicion_minuto WHERE tipo='minuto' ORDER BY rowid DESC "
                     "LIMIT 1").fetchone()
check(r is not None and r[0] == 1.20 and r[1] == 1.30, "bid/ask crudos guardados -> %s/%s" % (r[0], r[1]))
check(r[2] == 1.25, "mid = (bid+ask)/2 -> %s" % r[2])
check(abs(r[3] - 45.0) < 1e-6, "pnl del recorrido -> %s" % r[3])
check(r[5] == 0.47 and r[6] == 0.26, "greeks en la fila de recorrido -> %s/%s" % (r[5], r[6]))
check(r[8] is not None and r[8] >= 0, "seg_desde_entrada calculado -> %s" % r[8])


# ================================================================ TEST D: acumulado NETO
print("== TEST D: _on_ticks REAL -> cum_net por strike, SIN tocar la senal ==")
app = nueva_app()
c_sig = FakeContract(773, "C", 3001)      # strike de SENAL
p_sig = FakeContract(773, "P", 3002)
c_base = FakeContract(775, "C", 3003)     # strike de BASELINE (no señal)
app.call, app.put = c_sig, p_sig
app.info_base[3003] = ("20260814", 775, "C")

def tick(c, last, bid, ask, vol):
    return FakeTicker(bid=bid, ask=ask, last=last, volume=vol, contract=c,
                      right=c.right)

# 1a pasada: fija la base de volumen (no acumula nada)
app._on_ticks([tick(c_sig, 1.00, 0.98, 1.02, 100),
               tick(p_sig, 1.00, 0.98, 1.02, 100),
               tick(c_base, 1.00, 0.98, 1.02, 100)])
nc0, np0 = app.net_call, app.net_put
check(nc0 == 0 and np0 == 0, "1a pasada solo fija la base de volumen")

# 2a pasada: compras agresivas en 773C (last>=ask), ventas agresivas en 773P (last<=bid),
# y en 775C (baseline) una venta agresiva
app._on_ticks([tick(c_sig, 1.02, 0.98, 1.02, 110),     # +10 x 1.02 x100 = +1020 (COMPRA)
               tick(p_sig, 0.98, 0.98, 1.02, 110),     # -10 x 0.98 x100 = -980  (VENTA)
               tick(c_base, 0.98, 0.98, 1.02, 110)])   # baseline, venta agresiva

k_sig_c = ("20260814", 773, "C")
k_sig_p = ("20260814", 773, "P")
k_base = ("20260814", 775, "C")
check(abs(app.accum[k_sig_c] - 1020.0) < 1e-6, "BRUTO 773C = +1020 (solo suma) -> %s" % app.accum[k_sig_c])
check(abs(app.accum_net[k_sig_c] - 1020.0) < 1e-6, "NETO 773C = +1020 (compra agresiva)")
check(abs(app.accum[k_sig_p] - 980.0) < 1e-6, "BRUTO 773P = +980 (POSITIVO aunque sea venta)")
check(abs(app.accum_net[k_sig_p] + 980.0) < 1e-6,
      "NETO 773P = -980 (venta agresiva) -> %s" % app.accum_net[k_sig_p])
check(app.accum[k_base] > 0 and app.accum_net[k_base] < 0,
      "BASELINE 775C: bruto positivo y neto NEGATIVO (antes el neto ni se calculaba)")
# INVARIANTE CRITICA: la senal solo mira los strikes de senal
check(abs(app.net_call - 1020.0) < 1e-6,
      "net_call SOLO suma el strike de SENAL (el baseline NO entra) -> %s" % app.net_call)
check(abs(app.net_put + 980.0) < 1e-6, "net_put -> %s" % app.net_put)

# flujo DENTRO del spread: no se puede atribuir -> neto 0, bruto sí suma
app._on_ticks([tick(c_sig, 1.00, 0.98, 1.02, 120)])
check(abs(app.accum_net[k_sig_c] - 1020.0) < 1e-6,
      "trade DENTRO del spread no cambia el NETO (no se puede atribuir) -> %s"
      % app.accum_net[k_sig_c])
check(app.accum[k_sig_c] > 1020.0, "pero el BRUTO sí lo cuenta -> %s" % app.accum[k_sig_c])

# persistencia + restauracion
app._intradia_ok = True
app._persist_accum()
r = app.db.execute("SELECT cum_prem,cum_net FROM strike_accum WHERE strike=773 AND right='P'").fetchone()
check(r is not None and r[0] > 0 and r[1] < 0,
      "strike_accum guarda cum_prem>0 y cum_net<0 en el mismo strike -> %s" % (r,))
r2 = app.db.execute("SELECT day_prem,day_net FROM strike_daily WHERE strike=773 AND right='P'").fetchone()
check(r2 is not None and r2[1] < 0, "strike_daily.day_net guardado -> %s" % (r2,))


# ================================================================ TEST E: ventanas moviles
print("== TEST E: _flujo_ventana (se guarda, NO decide) ==")
app = nueva_app()
ahora = time.monotonic()
app.flow_hist = [(ahora - 600.0, 1000.0, 500.0),
                 (ahora - 240.0, 3000.0, 900.0),
                 (ahora - 30.0, 5000.0, 1000.0)]
app.net_call, app.net_put = 6000.0, 1200.0
c5 = app._flujo_ventana(300.0)
check(c5 == (3000.0, 300.0),
      "ventana 5 min usa el punto MAS CERCANO a t-300s (no uno de hace 600s) -> %s" % (c5,))
# solo hay 600 s de historia: una ventana de 15 min NO se puede calcular. Devolver el punto
# mas viejo seria etiquetar 10 min de flujo como "15 min" -> dato falso. Debe ser None.
c15 = app._flujo_ventana(900.0)
check(c15 == (None, None),
      "ventana 15 min con solo 10 min de historia -> None, NO un valor falseado -> %s" % (c15,))
# y en cuanto la historia cubre la ventana, si devuelve valor
app.flow_hist.insert(0, (ahora - 1000.0, 100.0, 50.0))
c15b = app._flujo_ventana(900.0)
check(c15b == (5900.0, 1150.0), "con historia suficiente, la ventana 15 min calcula -> %s" % (c15b,))
app2 = nueva_app()
check(app2._flujo_ventana(300.0) == (None, None),
      "sin historia suficiente devuelve None (se guarda NULL, no un 0 falso)")


# ================================================================ TEST F: GAP 17
print("== TEST F: GAP 17 auto-recuperacion del stream de barras ==")
app = nueva_app()
app.spy_stock = FakeContract(0, "C", 9999)
app.bars = ["BAR-VIEJA"]
app.last_bar_time = "2026-08-10 13:24:00"
S.BARS_STALE_SECS = 0.05          # acelerar el reloj del cold run
app.is_market_open = lambda: True

rows = [{"date": "2026-08-10 13:24:00"}]
app._chequear_barras(rows)
check(app.bars_stale is False, "1a lectura: se toma como referencia, no marca stale")
time.sleep(0.08)
app._chequear_barras(rows)        # MISMA fecha -> no avanza
check(app.bars_stale is True,
      "detecta el stream ESTANCADO por FRESCURA, sin que IBKR mande ningun error")

# reponer: se llama al metodo REAL
antes = app.last_bar_time
ok = app._subscribe_bars()
check(ok is True and app.ib.bars_pedidas == 1, "_subscribe_bars repidio el stream")
check(app.ib.cancels == 1, "cancelo la suscripcion vieja antes de repedir (evita pacing)")
check(app.last_bar_time == antes,
      "last_bar_time NO se toca al reponer (si no, se perderia un minuto entero)")
check(app.bars_stale is False, "tras reponer, deja de estar stale")

# la deteccion por EVENTO (10182) tambien marca
app.bars_stale = False
app._on_error(1547, 10182, "Failed to request live updates (disconnected).", None)
check(app.bars_stale is True, "code=10182 marca stale por la via del evento")

# vuelta a la normalidad cuando el dato avanza de verdad
app._chequear_barras([{"date": "2026-08-10 13:25:00"}])
check(app.bars_stale is False, "cuando bars[-1].date AVANZA, se limpia el stale solo")

# los walls escritos mientras estaba stale quedan MARCADOS
app.bars_stale = True
app.walls = {"spot": 773.03, "put_wall": 772, "call_wall": 773,
             "max_pain_static": 771, "max_pain_dyn": 773, "prem_center": 773.2}
app.gex = {"gex_total": 1.0, "regime": "LONG", "gamma_flip": 772.4}
app._persist_walls({}, {}, {}, {})
r = app.db.execute("SELECT spot,spot_stale FROM walls_snapshot ORDER BY rowid DESC LIMIT 1").fetchone()
check(r is not None and r[1] == 1,
      "walls_snapshot.spot_stale=1 cuando el spot venia de un stream muerto -> %s" % (r,))
app.bars_stale = False
app._persist_walls({}, {}, {}, {})
r = app.db.execute("SELECT spot_stale FROM walls_snapshot ORDER BY rowid DESC LIMIT 1").fetchone()
check(r[0] == 0, "y spot_stale=0 cuando el dato es bueno")


# ================================================================ TEST G: reinicio
print("== TEST G: reinicio con posicion abierta (readopcion del trade) ==")
app = nueva_app()
hoy = S.datetime.now().strftime("%Y-%m-%d")
app.db.execute("INSERT INTO trades(fecha,expiry,strike,right,side,hora_entrada,entry_price,"
               "qty,mfe,mae,hora_mfe) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (hoy, "20260814", 773, "P", "PUT", "12:20:44", 0.80, 1, 2.10, 0.78, "12:43:10"))
app.db.commit()
app._intradia_ok = True
app._load_estado_dia()
check(app.trade_id is not None, "trade abierto readoptado tras el reinicio -> id=%s" % app.trade_id)
check(app.mfe == 2.10 and app.hora_mfe == "12:43:10",
      "el MFE acumulado ANTES del reinicio no se pierde -> %s a las %s" % (app.mfe, app.hora_mfe))
check(app.trade_open and app.trade_open.get("hora") == "12:20:44",
      "hora de entrada recuperada (la duracion se mide por reloj de pared, no monotonic)")
segs = app._segs_desde("12:20:44")
check(segs is not None, "_segs_desde funciona con la hora restaurada -> %s" % segs)

# y si la posicion ya no existe en IBKR, el trade se cierra en vez de quedar abierto para siempre
app.pos = "PUT"
app.pos_qty = 1
app._sync_pos()                 # FakeIB.positions() devuelve [] -> FLAT
r = app.db.execute("SELECT hora_salida,razon_salida FROM trades ORDER BY trade_id DESC "
                   "LIMIT 1").fetchone()
check(r[0] is not None and r[1] == "externa",
      "posicion desaparecida de IBKR -> el trade se cierra como 'externa' -> %s" % (r,))
check(app.trade_id is None, "y el trade_id queda libre")


# ================================================================
print()
if FAILS:
    print("FALLOS (%d):" % len(FAILS))
    for f in FAILS:
        print("   - " + f)
    sys.exit(1)
print("TODO VERDE")
sys.exit(0)
