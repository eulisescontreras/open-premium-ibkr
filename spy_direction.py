# -*- coding: utf-8 -*-
"""
SPY Direction — Open-Premium casero via IBKR (proyecto INDEPENDIENTE, no toca el bot)
------------------------------------------------------------------------------------
Para SCALPING de SPY. Dos partes:

1) SEÑAL EN VIVO (pantalla UP/DOWN): usa el vencimiento MAS CERCANO (el proximo a
   expirar; puede ser 0DTE o a pocos dias) y los strikes ATM/ITM (call<=precio,
   put>=precio, nunca OTM). Mide el NETO de premium call vs put desde la apertura.

2) LINEA BASE (fechas posteriores): acumula el premium ATM/ITM de VARIAS
   expiraciones FUTURAS, guardando un ACUMULADO en la BD desde el primer dia de uso.
   Sirve para, al abrir el dia siguiente, ver si ese valor cambia fuerte (señal temprana).

Persistencia en SQLite (viaja con la app). Requiere IB Gateway abierto+logueado con
API habilitada (puerto 4002 paper). El flujo por-trade real necesita datos de
opciones OPRA en tiempo real; si solo hay 'delayed', la app lo indica.
"""

import math
import os
import sys
import time
import sqlite3
import subprocess
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime, timezone, timedelta

try:
    import pandas as pd
    HAVE_PD = True
except Exception:
    HAVE_PD = False

try:
    import winsound
    HAVE_SOUND = True
except Exception:
    HAVE_SOUND = False

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = None  # fallback: EDT (UTC-4) mas abajo

from ib_insync import IB, Stock, Option, LimitOrder, util


def now_et():
    """Hora actual en ET. Usa zoneinfo; si no hay tzdata, cae a EDT (UTC-4)."""
    if _ET is not None:
        return datetime.now(_ET)
    return datetime.now(timezone.utc) + timedelta(hours=-4)

# ----------------------- CONFIG (editable) -----------------------
HOST = "127.0.0.1"
PORT = 4002          # IB Gateway paper. Live=4001. TWS: 7497 paper / 7496 live.
CLIENT_ID = 7
SYMBOL = "SPY"
SIGNAL_THRESHOLD = 5000.0   # US$ de premium neto para cambiar de estado (anti-parpadeo)
REFRESH_SECS = 1.0
# Aviso anticipado de "posible giro" (heuristica de momentum):
WARN_BAND_FRAC = 0.6
MOMENTUM_WIN = 8
MOMENTUM_MIN = 3000.0
ENABLE_SOUND = False        # SOLO banner visual (sin sonido)
ENABLE_TOAST = True         # notificacion nativa de Windows (esquina inferior derecha)
# Linea base (fechas posteriores):
ITM_DEPTH = 3               # ademas del ATM, cuantos strikes ITM por lado
BASELINE_EXPIRIES = 3       # cuantas expiraciones FUTURAS seguir (posteriores a la cercana)
SNAPSHOT_SECS = 120         # cada cuanto persistir el acumulado en la BD
OPEN_JUMP_FACTOR = 1.5      # si hoy supera prev*este factor -> marca "cambio fuerte"
# --- Umbrales ADAPTATIVOS (auto-ajuste a la magnitud real) ---
ADAPTIVE = True
ADAPT_FRAC = 0.15           # umbral = ADAPT_FRAC * (|net_call|+|net_put|)
MOM_FRAC = 0.6             # momentum minimo = MOM_FRAC * umbral
# --- EJECUCION AUTOMATICA (rotar 1 opcion) ---
TRADING_ENABLED = True      # ARRANCA ARMADO (2026-08-10, orden del usuario). Boton = DESARMAR.
QTY = 1                     # contratos por señal (cuenta pequeña)
REPRICE_SECS = 4.0          # re-precia al mid si no llena en este tiempo
MAX_FILL_SECS = 60.0        # tiempo maximo intentando llenar una entrada
FLATTEN_HHMM = "15:45"      # ET: cerrar cualquier opcion abierta
STOP_NEW_HHMM = "15:40"     # ET: no abrir nuevas cerca del cierre
RECONNECT_SECS = 15.0       # espera entre reintentos si se cae el socket (no saturar el Gateway)
SYNC_POS_SECS = 20.0        # cada cuanto re-sincronizar la posicion CONTRA IBKR (la realidad manda)
# --- Walls / GEX / Gamma Flip (informativo, "como el TA": se guarda y se analiza vs la grafica) ---
WALLS_ENABLED = True        # calcular walls/GEX/flip. NO toca la senal UP/DOWN ni la ejecucion.
WALLS_BAND = 10             # strikes a CADA lado del precio a escanear (banda). Bajo por limite de lineas IBKR.
WALLS_RECALC_SECS = 180.0   # cada 3 min: snapshot de la banda (no satura el gateway; MarketSnack usa 5 min)
# Convencion de signo del GEX (dealers +gamma calls / -gamma puts). HIPOTESIS estandar: validar vs precio real.
GEX_CALL_SIGN = 1.0
GEX_PUT_SIGN = -1.0
# ----------------------------------------------------------------


def _fmt(x):
    """Formato None-safe para logs/pantalla."""
    return f"{x:.2f}" if isinstance(x, (int, float)) else "-"


def _money(v):
    """Formato compacto de dinero: 1.2M / 34k / 120."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{v / 1e3:.0f}k"
    return f"{v:.0f}"


def _max_pain(call_oi, put_oi):
    """Strike de Max Pain (minimiza el pago total) a partir del OI. Funcion pura.
    call_oi/put_oi: dict strike->OI. Devuelve el strike o None. NO usa el spot."""
    strikes = sorted(set(call_oi) | set(put_oi))
    if not strikes:
        return None
    best_k, best_pay = None, None
    for K in strikes:
        pay = (sum(call_oi.get(s, 0) * max(0.0, K - s) for s in strikes)
               + sum(put_oi.get(s, 0) * max(0.0, s - K) for s in strikes))
        if best_pay is None or pay < best_pay:
            best_pay, best_k = pay, K
    return best_k


def compute_walls_from_oi(call_oi, put_oi, spot):
    """Funcion pura y testeable. call_oi/put_oi: dict strike->OI. Devuelve walls + max pain."""
    strikes = sorted(set(call_oi) | set(put_oi))
    if not strikes:
        return None
    put_wall = max(put_oi, key=lambda k: put_oi.get(k, 0)) if put_oi else None
    call_wall = max(call_oi, key=lambda k: call_oi.get(k, 0)) if call_oi else None
    return {"put_wall": put_wall, "call_wall": call_wall,
            "max_pain": _max_pain(call_oi, put_oi), "spot": spot}


def compute_prem_center(weight_by_strike):
    """Centro de masa (strike) ponderado por la MAGNITUD de dinero por strike = 'hacia donde
    hay mas peso'. weight_by_strike: dict strike->$ (se usa |valor|). Funcion pura."""
    num = den = 0.0
    for K, w in weight_by_strike.items():
        a = abs(w)
        num += K * a
        den += a
    return (num / den) if den > 0 else None


def compute_gex_from_greeks(call_oi, put_oi, call_gamma, put_gamma, spot,
                            call_sign=1.0, put_sign=-1.0):
    """GEX (Gamma Exposure) neto y Gamma Flip. Funcion pura y testeable.
    - GEX por strike = 100 * spot^2 * (call_sign*gamma_c*OI_c + put_sign*gamma_p*OI_p)
    - gex_total>0 -> dealers LONG gamma (mean-reverting) ; <0 -> SHORT gamma (tendencial)
    - gamma_flip (PROXY): strike donde la suma ACUMULADA por strike del GEX neto cruza cero
      (interpolado). Aprox: no repreciamos gamma por cada S (no hay BS aqui). Documentado.
    Devuelve dict o None si no hay datos."""
    strikes = sorted(set(call_oi) | set(put_oi) | set(call_gamma) | set(put_gamma))
    if not strikes:
        return None
    factor = 100.0 * spot * spot
    per = {}
    gex_total = 0.0
    for K in strikes:
        g = 0.0
        cg = call_gamma.get(K)
        pg = put_gamma.get(K)
        if cg is not None and not math.isnan(cg):
            g += call_sign * cg * call_oi.get(K, 0)
        if pg is not None and not math.isnan(pg):
            g += put_sign * pg * put_oi.get(K, 0)
        per[K] = g * factor
        gex_total += per[K]
    regime = "LONG" if gex_total > 0 else ("SHORT" if gex_total < 0 else "FLAT")
    # gamma flip (proxy): cruce por cero de la acumulada por strike
    flip = None
    cum = 0.0
    cum_vals = []
    for K in strikes:
        cum += per[K]
        cum_vals.append((K, cum))
    for i in range(1, len(cum_vals)):
        k0, c0 = cum_vals[i - 1]
        k1, c1 = cum_vals[i]
        if (c0 <= 0.0 <= c1) or (c0 >= 0.0 >= c1):
            flip = k0 + (0.0 - c0) / (c1 - c0) * (k1 - k0) if c1 != c0 else k1
            break
    return {"gex_total": gex_total, "regime": regime, "gamma_flip": flip,
            "spot": spot, "gex_by_strike": per}


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _make_logger(name, filename):
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    lg.propagate = False
    try:
        h = TimedRotatingFileHandler(os.path.join(_app_dir(), filename),
                                     when="midnight", backupCount=120, encoding="utf-8")
    except Exception:
        h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    lg.addHandler(h)
    return lg


# LOG = errores/excepciones ; ACT = actividad exhaustiva del dia (que hizo el sistema)
LOG = _make_logger("spyd", "spy_direction.log")
ACT = _make_logger("spyd.act", "spy_activity.log")


def _excepthook(exctype, value, tb):
    LOG.error("EXCEPCION NO CAPTURADA", exc_info=(exctype, value, tb))


sys.excepthook = _excepthook


class TAEngine:
    """Replica del TA del bot (src/ta/indicators.py) aplicado a barras de 1 min:
    RSI(14), EMA(8/21/50), MACD(12/26/9), Bollinger(20,2), ATR(14), VWAP aprox, OBV."""

    def compute(self, df):
        if not HAVE_PD or df is None or len(df) < 26:
            return None
        close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = float((100.0 - 100.0 / (1.0 + rs)).iloc[-1])
        ema8 = float(close.ewm(span=8, adjust=False).mean().iloc[-1])
        ema21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        e12 = close.ewm(span=12, adjust=False).mean()
        e26 = close.ewm(span=26, adjust=False).mean()
        macd_line = e12 - e26
        macd_sig = macd_line.ewm(span=9, adjust=False).mean()
        ml = float(macd_line.iloc[-1]); ms = float(macd_sig.iloc[-1]); mh = ml - ms
        sma = close.rolling(20).mean(); sd = close.rolling(20).std()
        bb_up = float((sma + 2 * sd).iloc[-1]); bb_mid = float(sma.iloc[-1])
        bb_low = float((sma - 2 * sd).iloc[-1])
        tr = pd.concat([high - low, (high - close.shift()).abs(),
                        (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        price = float(close.iloc[-1])
        atr_pct = (atr / price) * 100.0 if price else 0.0
        vwap = float(((high + low + close) / 3.0).rolling(5).mean().iloc[-1])
        obv = [0.0]
        cl = close.values; vv = vol.values
        for i in range(1, len(cl)):
            if cl[i] > cl[i - 1]:
                obv.append(obv[-1] + vv[i])
            elif cl[i] < cl[i - 1]:
                obv.append(obv[-1] - vv[i])
            else:
                obv.append(obv[-1])
        obv_s = pd.Series(obv)
        ma_obv = float(obv_s.rolling(20).mean().iloc[-1]); cur = float(obv_s.iloc[-1])
        if ma_obv and cur > ma_obv * 1.05:
            obv_trend = "bullish"
        elif ma_obv and cur < ma_obv * 0.95:
            obv_trend = "bearish"
        else:
            obv_trend = "neutral"
        # scores (identicos al bot)
        r = rsi
        s_rsi = 3 if r < 25 else 2 if r < 35 else 1 if r < 45 else 0 if r <= 55 else -1 if r <= 65 else -2 if r <= 75 else -3
        rng = bb_up - bb_low
        s_bb = 2 if (rng > 0 and price <= bb_low + rng * 0.2) else (-2 if (rng > 0 and price >= bb_up - rng * 0.2) else 0)
        sc = {
            "rsi": s_rsi,
            "ema": 2 if ema8 > ema21 else -2,
            "macd": 2 if mh > 0 else -2,
            "bb": s_bb,
            "atr": 1 if atr_pct > 1.0 else (-1 if atr_pct < 0.3 else 0),
            "vwap": 1 if price > vwap else -1,
            "obv": 1 if obv_trend == "bullish" else (-1 if obv_trend == "bearish" else 0),
        }
        total = sum(sc.values())
        bull = sum(1 for v in sc.values() if v > 0)
        bear = sum(1 for v in sc.values() if v < 0)
        dirn = "BULL" if total > 0 else ("BEAR" if total < 0 else "NEUTRAL")
        return {"close": price, "rsi": rsi, "ema8": ema8, "ema21": ema21, "ema50": ema50,
                "macd_line": ml, "macd_signal": ms, "macd_hist": mh,
                "bb_up": bb_up, "bb_mid": bb_mid, "bb_low": bb_low,
                "atr": atr, "atr_pct": atr_pct, "vwap": vwap, "obv_trend": obv_trend,
                "score": total, "dir": dirn, "bull": bull, "bear": bear}


class SpyDirection:
    def __init__(self, demo=False):
        self.ib = IB()
        self.demo = demo
        self.demo_i = 0
        self.mode = "DEMO" if demo else "?"
        self.spy_price = float("nan")
        self.expiry = None            # vencimiento mas cercano (para la señal)
        self.call = None              # ATM/ITM call (señal)
        self.put = None               # ATM/ITM put (señal)
        self.net_call = 0.0
        self.net_put = 0.0
        self.prev_vol = {}            # conId -> volumen acumulado previo (delta)
        self.state = "-"
        self.transitions = []
        self.status = "Iniciando..."
        # alertas
        self.diff_hist = []
        self.alert_text = ""
        self.alert_kind = ""
        self.alert_until = 0.0
        self.pending_sound = None
        self.last_warn_side = None
        # --- linea base (fechas posteriores) ---
        self.info_base = {}           # conId -> (expiry, strike, right)
        self.accum = {}               # (expiry,strike,right) -> premium acumulado (persistente, desde dia 1)
        self.today_prem = {}          # (expiry,strike,right) -> premium de HOY
        self.base_prev = {}           # (expiry,strike,right) -> premium del dia previo
        self.base_expiries = []       # lista de expiraciones futuras seguidas
        self.last_snapshot = 0.0
        # --- Walls / GEX / Gamma Flip (informativo, "como el TA": se guarda por 3 min y se analiza) ---
        self.band_contracts = []      # contratos de la banda (expiracion CERCANA) para snapshot
        self.band_prev_vol = {}       # conId -> volumen previo (delta entre lecturas de 3 min)
        self.prev_gamma = {}          # conId -> gamma previo (detectar dato estancado/viejo)
        self.today_vol = {}           # (expiry,strike,right) -> volumen del dia (banda)
        self.net_prem = {}            # (expiry,strike,right) -> premium neto firmado ('peso' de dinero)
        self.walls = None             # dict: put_wall/call_wall/max_pain_static/max_pain_dyn/prem_center
        self.gex = None               # dict: gex_total/regime/gamma_flip
        self.last_walls_calc = 0.0
        # --- ejecucion automatica (rotar 1 opcion) ---
        self.trading = TRADING_ENABLED   # ON/OFF (boton en la GUI)
        self.buy_call = None             # contrato de EJECUCION call (ATM lado OTM: strike > precio)
        self.buy_put = None              # contrato de EJECUCION put  (ATM lado OTM: strike < precio)
        self.pos = "FLAT"                # FLAT / CALL / PUT (lo que tenemos)
        self.pos_qty = 0.0               # cantidad REAL en cartera segun IBKR (no se asume)
        self.last_sync = 0.0             # ultimo _sync_pos (la realidad de IBKR manda sobre self.pos)
        self.target = "FLAT"             # lado deseado segun ultima señal
        self.order = None                # Trade activo (ib_insync)
        self.order_action = None         # BUY / SELL
        self.order_side = None           # CALL / PUT
        self.order_deadline = 0.0        # monotonic: re-precia al vencer
        self.order_giveup = 0.0          # (sin uso) compatibilidad
        self.order_aggr = 0              # (sin uso) compatibilidad
        self.open_deadline = 0.0         # limite de tiempo para llenar una COMPRA (BUY)
        self.min_tick = {}               # conId -> minTick
        self._mkt_subs = set()           # conIds con market data ya pedido (evita re-suscribir)
        self.trade_msg = "trading OFF"   # ultima accion (para la pantalla)
        self.entry_price = None          # precio de entrada del contrato comprado (para la linea)
        self.contract_price = None       # precio ACTUAL del contrato comprado (tiempo real, P&L)
        self.last_diff = 0.0             # ultimos valores de la senal (para log exhaustivo)
        self.last_thr = 0.0
        self.last_momentum = 0.0
        self._last_trade_log = ""        # dedupe del log de decision de trading
        self.eod_flat = False            # ya se aplano hoy
        self.reconciled = False
        # --- TA de 1 min + registro por minuto ---
        self.ta = TAEngine()
        self.bars = None                 # BarDataList (reqHistoricalData keepUpToDate)
        self.ta_vals = None              # dict con ultimos indicadores
        self.last_bar_time = None        # detectar cierre de minuto
        # --- SQLite ---
        self.db = sqlite3.connect(
            os.path.join(_app_dir(), "spy_history_demo.db" if demo else "spy_history.db"))
        self._init_db()

    def _init_db(self):
        c = self.db
        c.execute("CREATE TABLE IF NOT EXISTS transitions ("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, hora TEXT, "
                  "estado TEXT, tipo TEXT, spy REAL, net_call REAL, net_put REAL, modo TEXT)")
        # Acumulado persistente (desde el primer dia de uso)
        c.execute("CREATE TABLE IF NOT EXISTS strike_accum ("
                  "expiry TEXT, strike REAL, right TEXT, cum_prem REAL, updated TEXT, "
                  "PRIMARY KEY(expiry,strike,right))")
        # Premium por dia (para comparar apertura vs dia previo)
        c.execute("CREATE TABLE IF NOT EXISTS strike_daily ("
                  "fecha TEXT, expiry TEXT, strike REAL, right TEXT, day_prem REAL, "
                  "PRIMARY KEY(fecha,expiry,strike,right))")
        # Registro POR MINUTO: TA del SPY + precio + estado de premium
        c.execute("CREATE TABLE IF NOT EXISTS ta_minute ("
                  "fecha TEXT, hora TEXT, spy REAL, rsi REAL, ema8 REAL, ema21 REAL, ema50 REAL, "
                  "macd_line REAL, macd_signal REAL, macd_hist REAL, bb_up REAL, bb_mid REAL, "
                  "bb_low REAL, atr REAL, atr_pct REAL, vwap REAL, obv_trend TEXT, "
                  "ta_score REAL, ta_dir TEXT, net_call REAL, net_put REAL, prem_state TEXT, "
                  "PRIMARY KEY(fecha,hora))")
        # Registro POR MINUTO: premium call/put por strike seguido
        # (+ net_prem/open_interest/gamma por strike de la banda de walls, cada 3 min)
        c.execute("CREATE TABLE IF NOT EXISTS premium_minute ("
                  "fecha TEXT, hora TEXT, expiry TEXT, strike REAL, right TEXT, "
                  "cum_prem REAL, day_prem REAL, net_prem REAL, open_interest REAL, gamma REAL, "
                  "PRIMARY KEY(fecha,hora,expiry,strike,right))")
        # migracion para BD existentes: agregar columnas nuevas si faltan
        for col in ("net_prem REAL", "open_interest REAL", "gamma REAL"):
            try:
                c.execute("ALTER TABLE premium_minute ADD COLUMN " + col)
            except Exception:
                pass  # ya existe
        # Registro cada 3 min: walls/GEX/flip agregados (para analizar vs la grafica del precio)
        c.execute("CREATE TABLE IF NOT EXISTS walls_snapshot ("
                  "fecha TEXT, hora TEXT, expiry TEXT, spot REAL, "
                  "put_wall REAL, call_wall REAL, "
                  "max_pain_static REAL, max_pain_dyn REAL, prem_center REAL, "
                  "gex_total REAL, regime TEXT, gamma_flip REAL, "
                  "PRIMARY KEY(fecha,hora,expiry))")
        c.commit()

    # ---------------- historial de giros ----------------
    def _save(self, estado, tipo):
        try:
            now = datetime.now()
            self.db.execute(
                "INSERT INTO transitions(fecha,hora,estado,tipo,spy,net_call,net_put,modo)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), estado, tipo,
                 self.spy_price, self.net_call, self.net_put, self.mode))
            self.db.commit()
        except Exception:
            pass

    def recent(self, n=10):
        try:
            return self.db.execute(
                "SELECT fecha,hora,estado,tipo,spy FROM transitions "
                "ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        except Exception:
            return []

    # ---------------- conexion ----------------
    def connect(self):
        self.ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=8)
        self.ib.reqMarketDataType(1)
        self.ib.errorEvent += self._on_error
        self.ib.pendingTickersEvent += self._on_ticks
        ACT.info("Conectado a IB Gateway %s:%s (clientId=%s)", HOST, PORT, CLIENT_ID)

    def _on_error(self, reqId, code, msg, contract):
        sym = getattr(contract, "localSymbol", "") or getattr(contract, "symbol", "") if contract else ""
        ACT.info("IBKR code=%s reqId=%s %s%s", code, reqId, msg, (f" [{sym}]" if sym else ""))
        if code in (354, 10167, 10168, 10197, 10089, 10091):
            if self.mode not in ("DELAYED", "DEMO"):
                self.mode = "DELAYED"
                self.status = "Datos DELAYED (sin OPRA live) - sin flujo por-trade real"
                try:
                    self.ib.reqMarketDataType(3)
                except Exception:
                    pass

    def is_market_open(self):
        """SENCILLO: RTH = dia habil (Lun-Vie) y 09:30 <= hora ET < 16:00. (No maneja festivos.)"""
        et = now_et()
        return et.weekday() < 5 and "09:30" <= et.strftime("%H:%M") < "16:00"

    def reset_day(self):
        """Nuevo dia de mercado: limpiar acumuladores intradia (la senal arranca en 0)."""
        self.net_call = 0.0; self.net_put = 0.0
        self.today_prem = {}; self.net_prem = {}; self.today_vol = {}
        self.prev_vol = {}; self.band_prev_vol = {}; self.prev_gamma = {}
        self.diff_hist = []; self.transitions = []; self.state = "-"
        self.entry_price = None; self.contract_price = None
        ACT.info("NUEVO DIA - acumuladores intradia reiniciados (senal en 0)")

    def end_session(self):
        """Mercado cerrado: persistir, cancelar ordenes vivas y desconectar (reconecta al reabrir)."""
        try:
            self._persist_accum()
        except Exception:
            pass
        try:
            if self.ib.isConnected():
                self._cancel_working()
                self.ib.disconnect()
        except Exception:
            LOG.exception("Error al cerrar sesion de mercado")
        self.reconciled = False
        self.mode = "?"
        ACT.info("MERCADO CERRADO - sesion detenida y desconectada (recoleccion se reanuda al abrir)")

    # ---------------- seleccion de contratos ----------------
    def _read_price(self, spy):
        price = float("nan")
        for mdt, label in [(1, "LIVE"), (2, "FROZEN"), (3, "DELAYED"), (4, "DELAYED")]:
            self.ib.reqMarketDataType(mdt)
            t = self.ib.reqMktData(spy, "", False, False)
            self.ib.sleep(2.5)
            p = t.marketPrice()
            if p is None or math.isnan(p):
                p = t.last if (t.last and not math.isnan(t.last)) else t.close
            self.ib.cancelMktData(spy)
            if p and not math.isnan(p):
                self.mode = label
                return float(p)
        return price

    def _band(self, strikes, price):
        """Devuelve (call_strikes, put_strikes) ATM+ITM (nunca OTM)."""
        below = [s for s in strikes if s <= price]
        above = [s for s in strikes if s >= price]
        call_strikes = below[-(1 + ITM_DEPTH):] if below else []
        put_strikes = above[:(1 + ITM_DEPTH)] if above else []
        return call_strikes, put_strikes

    def setup_contracts(self):
        spy = Stock(SYMBOL, "SMART", "USD")
        self.ib.qualifyContracts(spy)
        price = self._read_price(spy)
        if math.isnan(price):
            self.status = "No pude leer precio de SPY (revisa suscripcion de datos)"
            return False
        self.spy_price = price

        chains = self.ib.reqSecDefOptParams(spy.symbol, "", spy.secType, spy.conId)
        chain = next((c for c in chains
                      if c.exchange == "SMART" and c.tradingClass == SYMBOL), None) \
            or next((c for c in chains if c.exchange == "SMART"), None)
        if chain is None or not chain.strikes or not chain.expirations:
            self.status = "No obtuve la cadena de opciones de SPY"
            return False

        today = datetime.now().strftime("%Y%m%d")
        exps = sorted(chain.expirations)
        self.expiry = next((e for e in exps if e >= today), exps[0])  # mas cercano
        strikes = sorted(chain.strikes)

        # --- señal: ATM call/put del vencimiento mas cercano ---
        below = [s for s in strikes if s <= self.spy_price]
        above = [s for s in strikes if s >= self.spy_price]
        if not below or not above:
            self.status = "No hay strikes ATM/ITM alrededor del precio"
            return False
        call_strike, put_strike = max(below), min(above)
        self.call = Option(SYMBOL, self.expiry, call_strike, "C", "SMART", tradingClass=SYMBOL)
        self.put = Option(SYMBOL, self.expiry, put_strike, "P", "SMART", tradingClass=SYMBOL)
        self.ib.qualifyContracts(self.call, self.put)
        self.ib.reqMktData(self.call, "233", False, False)
        self.ib.reqMktData(self.put, "233", False, False)

        # --- EJECUCION: ATM del lado OTM (call strike > precio, put strike < precio) ---
        above_otm = [s for s in strikes if s > self.spy_price]
        below_otm = [s for s in strikes if s < self.spy_price]
        bc = min(above_otm) if above_otm else call_strike
        bp = max(below_otm) if below_otm else put_strike
        self.buy_call = Option(SYMBOL, self.expiry, bc, "C", "SMART", tradingClass=SYMBOL)
        self.buy_put = Option(SYMBOL, self.expiry, bp, "P", "SMART", tradingClass=SYMBOL)
        self.ib.qualifyContracts(self.buy_call, self.buy_put)
        self.ib.reqMktData(self.buy_call, "", False, False)   # bid/ask para el MID
        self.ib.reqMktData(self.buy_put, "", False, False)

        # --- linea base: ATM/ITM de las siguientes expiraciones FUTURAS ---
        self.base_expiries = [e for e in exps if e > self.expiry][:BASELINE_EXPIRIES]
        base_contracts = []
        for exp in self.base_expiries:
            cs, ps = self._band(strikes, self.spy_price)
            for s in cs:
                base_contracts.append(Option(SYMBOL, exp, s, "C", "SMART", tradingClass=SYMBOL))
            for s in ps:
                base_contracts.append(Option(SYMBOL, exp, s, "P", "SMART", tradingClass=SYMBOL))
        if base_contracts:
            self.ib.qualifyContracts(*base_contracts)
            for c in base_contracts:
                if not c.conId:
                    continue
                self.info_base[c.conId] = (c.lastTradeDateOrContractMonth, c.strike, c.right)
                self.ib.reqMktData(c, "233", False, False)

        # --- WALLS/GEX: contratos de la banda (expiracion CERCANA). Se piden por SNAPSHOT cada 3 min ---
        self.band_contracts = []
        if WALLS_ENABLED:
            below = [s for s in strikes if s <= self.spy_price][-WALLS_BAND:]
            above = [s for s in strikes if s > self.spy_price][:WALLS_BAND]
            wc = []
            for s in (below + above):
                wc.append(Option(SYMBOL, self.expiry, s, "C", "SMART", tradingClass=SYMBOL))
                wc.append(Option(SYMBOL, self.expiry, s, "P", "SMART", tradingClass=SYMBOL))
            try:
                self.ib.qualifyContracts(*wc)
                self.band_contracts = [c for c in wc if c.conId]
                # STREAMING persistente: una suscripcion por contrato (NO repite requests -> no satura).
                # OI(101)+volumen(100)+greeks(106/modelGreeks). Se RECALCULA/guarda cada 3 min.
                for c in self.band_contracts:
                    self.ib.reqMktData(c, "100,101,106", False, False)
                ACT.info("WALLS banda lista (streaming): %d contratos (%d strikes, +-%d por lado)",
                         len(self.band_contracts), len(below + above), WALLS_BAND)
            except Exception:
                LOG.exception("Error suscribiendo banda de walls")

        self._load_accum()

        # barras de 1 min en vivo (fuente del TA)
        try:
            self.bars = self.ib.reqHistoricalData(
                spy, "", "1 D", "1 min", "TRADES", useRTH=True, keepUpToDate=True)
        except Exception:
            self.bars = None

        self.status = (f"OK  SPY={self.spy_price:.2f}  cercano={self.expiry}  "
                       f"senal C{call_strike:g}/P{put_strike:g} (ATM/ITM)  "
                       f"opera C{bc:g}/P{bp:g} (OTM)  "
                       f"| baseline exps={len(self.base_expiries)}  [{self.mode}]")
        print(self.status)
        ACT.info("SETUP %s", self.status)
        return True

    # ---------------- acumulado persistente ----------------
    def _load_accum(self):
        """Carga el acumulado historico y el premium del dia previo desde la BD."""
        try:
            for exp, strike, right, cp in self.db.execute(
                    "SELECT expiry,strike,right,cum_prem FROM strike_accum").fetchall():
                self.accum[(exp, strike, right)] = cp
            hoy = datetime.now().strftime("%Y-%m-%d")
            rows = self.db.execute(
                "SELECT expiry,strike,right,day_prem FROM strike_daily WHERE fecha=("
                "SELECT MAX(fecha) FROM strike_daily WHERE fecha < ?)", (hoy,)).fetchall()
            for exp, strike, right, dp in rows:
                self.base_prev[(exp, strike, right)] = dp
        except Exception:
            pass

    def _persist_accum(self):
        """Guarda el acumulado (persistente) y el premium de HOY en la BD."""
        try:
            now = datetime.now()
            hoy = now.strftime("%Y-%m-%d")
            ts = now.strftime("%H:%M:%S")
            for key, cp in self.accum.items():
                exp, strike, right = key
                self.db.execute(
                    "INSERT INTO strike_accum(expiry,strike,right,cum_prem,updated) "
                    "VALUES(?,?,?,?,?) ON CONFLICT(expiry,strike,right) "
                    "DO UPDATE SET cum_prem=excluded.cum_prem, updated=excluded.updated",
                    (exp, strike, right, cp, ts))
            for key, dp in self.today_prem.items():
                exp, strike, right = key
                self.db.execute(
                    "INSERT INTO strike_daily(fecha,expiry,strike,right,day_prem) "
                    "VALUES(?,?,?,?,?) ON CONFLICT(fecha,expiry,strike,right) "
                    "DO UPDATE SET day_prem=excluded.day_prem",
                    (hoy, exp, strike, right, dp))
            self.db.commit()
        except Exception:
            pass

    # ---------------- Walls / GEX / Gamma Flip (informativo) ----------------
    def compute_walls(self):
        """Snapshot de la banda (cada WALLS_RECALC_SECS, no satura el gateway) -> walls/GEX/flip.
        INFORMATIVO: NO toca la senal UP/DOWN ni la ejecucion. Guarda TODO en la BD
        (walls_snapshot agregado + premium_minute por strike) y en el log, para acumular datos
        y luego analizar la precision de los cambios de direccion vs la grafica del precio."""
        if not WALLS_ENABLED or not self.band_contracts or not self.ib.isConnected():
            return
        # Leer los tickers YA vivos (streaming persistente). NO se piden snapshots.
        # IBKR actualiza cada campo a SU ritmo (OI=EOD; gamma/vol/precio=en vivo); detectamos
        # 'staleness' comparando gamma con el recalculo anterior + hora del ultimo tick.
        tks = [self.ib.ticker(c) for c in self.band_contracts]

        call_oi = {}; put_oi = {}; call_g = {}; put_g = {}
        oi_est_c = {}; oi_est_p = {}; gross = {}
        miss_oi = miss_g = 0
        g_changed = 0
        last_tick_time = None
        detail = []
        for c, tk in zip(self.band_contracts, tks):
            s = c.strike; right = c.right
            key = (self.expiry, s, right)
            oi = tk.callOpenInterest if right == "C" else tk.putOpenInterest
            g = tk.modelGreeks.gamma if tk.modelGreeks else None
            oi = None if (oi is None or (isinstance(oi, float) and math.isnan(oi))) else float(oi)
            g = None if (g is None or (isinstance(g, float) and math.isnan(g))) else float(g)
            if oi is None:
                miss_oi += 1
            if g is None:
                miss_g += 1
            # staleness: contar cuantos gamma cambiaron vs el recalculo anterior + hora del ult. tick
            if g is not None:
                if self.prev_gamma.get(c.conId) != g:
                    g_changed += 1
                self.prev_gamma[c.conId] = g
            tt = getattr(tk, "time", None)
            if tt is not None and (last_tick_time is None or tt > last_tick_time):
                last_tick_time = tt
            # delta de volumen entre lecturas (3 min) -> premium neto firmado por strike ('peso')
            vol = tk.volume; last = tk.last
            if (vol is not None and not math.isnan(vol)
                    and last is not None and not math.isnan(last)):
                prev = self.band_prev_vol.get(c.conId)
                self.band_prev_vol[c.conId] = vol
                if prev is not None and vol - prev > 0:
                    dvol = vol - prev
                    prem = float(last) * dvol * 100.0
                    self.today_vol[key] = self.today_vol.get(key, 0.0) + dvol
                    self.today_prem[key] = self.today_prem.get(key, 0.0) + prem
                    bid = tk.bid if (tk.bid and not math.isnan(tk.bid)) else None
                    ask = tk.ask if (tk.ask and not math.isnan(tk.ask)) else None
                    signed = 0.0
                    if ask is not None and last >= ask:
                        signed = prem
                    elif bid is not None and last <= bid:
                        signed = -prem
                    self.net_prem[key] = self.net_prem.get(key, 0.0) + signed
            gv = self.today_vol.get(key, 0.0)
            if right == "C":
                if oi is not None:
                    call_oi[s] = oi
                if g is not None:
                    call_g[s] = g
                oi_est_c[s] = (oi or 0.0) + gv
            else:
                if oi is not None:
                    put_oi[s] = oi
                if g is not None:
                    put_g[s] = g
                oi_est_p[s] = (oi or 0.0) + gv
            gross[s] = gross.get(s, 0.0) + self.today_prem.get(key, 0.0)
            detail.append(f"{s:g}{right}:OI={_fmt(oi)},g={_fmt(g)},"
                          f"net={self.net_prem.get(key, 0.0):+.0f}")

        spot = self.spy_price
        w = compute_walls_from_oi(call_oi, put_oi, spot)
        self.walls = {
            "put_wall": w["put_wall"] if w else None,
            "call_wall": w["call_wall"] if w else None,
            "max_pain_static": w["max_pain"] if w else None,
            "max_pain_dyn": _max_pain(oi_est_c, oi_est_p),
            "prem_center": compute_prem_center(gross),
            "spot": spot,
        }
        self.gex = compute_gex_from_greeks(call_oi, put_oi, call_g, put_g, spot,
                                           GEX_CALL_SIGN, GEX_PUT_SIGN)
        self._persist_walls(call_oi, put_oi, call_g, put_g)
        g = self.gex or {}
        gxt = g.get("gex_total")
        n_g = len(self.band_contracts) - miss_g   # cuantos strikes trajeron gamma
        ACT.info("WALLS spot=%.2f PW=%s CW=%s magneto est=%s/din=%s peso=%s | "
                 "GEX=%s regime=%s flip=%s | faltan OI=%d greeks=%d de %d | "
                 "frescura: gamma cambiaron=%d/%d ult_tick=%s",
                 spot, _fmt(self.walls["put_wall"]), _fmt(self.walls["call_wall"]),
                 _fmt(self.walls["max_pain_static"]), _fmt(self.walls["max_pain_dyn"]),
                 _fmt(self.walls["prem_center"]),
                 (f"{gxt/1e9:+.3f}Bn" if isinstance(gxt, (int, float)) else "-"),
                 g.get("regime", "-"), _fmt(g.get("gamma_flip")),
                 miss_oi, miss_g, len(self.band_contracts),
                 g_changed, n_g, (str(last_tick_time) if last_tick_time else "-"))
        if n_g > 0 and g_changed == 0:
            ACT.info("WALLS AVISO: ningun gamma cambio desde el ultimo recalculo -> posible dato "
                     "ESTANCADO/viejo (revisar suscripcion OPRA o fuera de RTH)")
        ACT.info("WALLS detalle por strike: %s", " | ".join(detail))

    def _persist_walls(self, call_oi, put_oi, call_g, put_g):
        """Guarda walls_snapshot (agregado) + premium_minute por strike de la banda."""
        try:
            now = datetime.now()
            fecha = now.strftime("%Y-%m-%d"); hora = now.strftime("%H:%M")
            g = self.gex or {}
            self.db.execute(
                "INSERT OR REPLACE INTO walls_snapshot(fecha,hora,expiry,spot,put_wall,call_wall,"
                "max_pain_static,max_pain_dyn,prem_center,gex_total,regime,gamma_flip) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, self.expiry, self.walls.get("spot"),
                 self.walls.get("put_wall"), self.walls.get("call_wall"),
                 self.walls.get("max_pain_static"), self.walls.get("max_pain_dyn"),
                 self.walls.get("prem_center"), g.get("gex_total"), g.get("regime"),
                 g.get("gamma_flip")))
            strikes = sorted(set(call_oi) | set(put_oi) | set(call_g) | set(put_g))
            for s in strikes:
                for right, oimap, gmap in (("C", call_oi, call_g), ("P", put_oi, put_g)):
                    key = (self.expiry, s, right)
                    self.db.execute(
                        "INSERT OR REPLACE INTO premium_minute(fecha,hora,expiry,strike,right,"
                        "cum_prem,day_prem,net_prem,open_interest,gamma) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (fecha, hora, self.expiry, s, right,
                         self.accum.get(key, 0.0), self.today_prem.get(key, 0.0),
                         self.net_prem.get(key, 0.0), oimap.get(s), gmap.get(s)))
            self.db.commit()
        except Exception:
            LOG.exception("Error guardando walls_snapshot/premium_minute (banda)")

    def baseline_summary(self):
        """Por cada expiracion futura: (exp, call_hoy, call_prev, put_hoy, put_prev)."""
        out = []
        for exp in self.base_expiries:
            ch = cp = ph = pp = 0.0
            for (e, s, r), v in self.today_prem.items():
                if e != exp:
                    continue
                if r == "C":
                    ch += v
                else:
                    ph += v
            for (e, s, r), v in self.base_prev.items():
                if e != exp:
                    continue
                if r == "C":
                    cp += v
                else:
                    pp += v
            out.append((exp, ch, cp, ph, pp))
        return out

    def ladder_rows(self):
        """Datos para la Gamma Ladder (SOLO lectura, estilo MarketSnack). Barras = premium $ por
        strike de la banda (call+put), coloreadas por lado del precio. Marca CW/PW/precio/flip.
        Devuelve dict {rows:[(strike,prem,side,tag)], price, flip, magnet, state, max_prem}."""
        strikes = sorted({c.strike for c in self.band_contracts}, reverse=True)
        w = self.walls or {}
        cw = w.get("call_wall"); pw = w.get("put_wall")
        magnet = w.get("max_pain_dyn") if w.get("max_pain_dyn") is not None else w.get("max_pain_static")
        flip = (self.gex or {}).get("gamma_flip")
        price = self.spy_price
        rows = []
        max_prem = 0.0
        for s in strikes:
            prem = (self.today_prem.get((self.expiry, s, "C"), 0.0)
                    + self.today_prem.get((self.expiry, s, "P"), 0.0))
            side = "call" if (price is None or math.isnan(price) or s >= price) else "put"
            tag = "CW" if (cw is not None and s == cw) else ("PW" if (pw is not None and s == pw) else "")
            if magnet is not None and s == magnet:      # magneto como marca, estilo PW/CW
                tag = (tag + "M") if tag else "MAG"
            rows.append((s, prem, side, tag))
            if prem > max_prem:
                max_prem = prem
        # contrato comprado (solo si hay posicion real): strike + entrada + precio ACTUAL (P&L)
        contract = None
        if self.pos == "CALL" and self.buy_call is not None:
            contract = {"strike": self.buy_call.strike, "side": "CALL",
                        "entry": self.entry_price, "price": self.contract_price}
        elif self.pos == "PUT" and self.buy_put is not None:
            contract = {"strike": self.buy_put.strike, "side": "PUT",
                        "entry": self.entry_price, "price": self.contract_price}
        return {"rows": rows, "price": price, "flip": flip, "magnet": magnet,
                "state": self.state, "max_prem": max_prem, "contract": contract}

    # ---------------- procesamiento de trades ----------------
    def _on_ticks(self, tickers):
        signal_ids = {c.conId for c in (self.call, self.put) if c is not None}
        for tk in tickers:
            c = tk.contract
            is_signal = c.conId in signal_ids
            is_base = c.conId in self.info_base
            if not (is_signal or is_base):
                continue
            vol = tk.volume
            last = tk.last
            if vol is None or math.isnan(vol) or last is None or math.isnan(last):
                continue
            prev = self.prev_vol.get(c.conId)
            self.prev_vol[c.conId] = vol
            if prev is None:
                continue
            dvol = vol - prev
            if dvol <= 0:
                continue
            premium = float(last) * float(dvol) * 100.0
            # premium BRUTO por strike (señal + baseline) para historial/estadisticas
            key = (c.lastTradeDateOrContractMonth, c.strike, c.right)
            self.accum[key] = self.accum.get(key, 0.0) + premium
            self.today_prem[key] = self.today_prem.get(key, 0.0) + premium
            if is_signal:
                bid = tk.bid if (tk.bid and not math.isnan(tk.bid)) else None
                ask = tk.ask if (tk.ask and not math.isnan(tk.ask)) else None
                signed = 0.0
                if ask is not None and last >= ask:
                    signed = premium
                elif bid is not None and last <= bid:
                    signed = -premium
                if c.right == "C":
                    self.net_call += signed
                else:
                    self.net_put += signed
        self._update_signal()

    def _update_signal(self):
        diff = self.net_call - self.net_put
        hhmmss = datetime.now().strftime("%H:%M:%S")
        self.diff_hist.append(diff)
        self.diff_hist[:] = self.diff_hist[-max(MOMENTUM_WIN, 2):]
        momentum = self.diff_hist[-1] - self.diff_hist[0]

        # umbral ADAPTATIVO: escala con la magnitud real del flujo (miles->millones)
        if ADAPTIVE:
            thr = max(SIGNAL_THRESHOLD, ADAPT_FRAC * (abs(self.net_call) + abs(self.net_put)))
        else:
            thr = SIGNAL_THRESHOLD
        mom_min = MOM_FRAC * thr
        self.last_diff = diff; self.last_thr = thr; self.last_momentum = momentum  # para log exhaustivo

        band = thr * WARN_BAND_FRAC
        if self.state == "UP" and diff < band and momentum <= -mom_min:
            if self.last_warn_side != "DOWN":
                self._raise_alert("WARN", f"posible GIRO a DOWN ({hhmmss})", "warn")
                self._save("DOWN", "WARN")
                self.last_warn_side = "DOWN"
        elif self.state == "DOWN" and diff > -band and momentum >= mom_min:
            if self.last_warn_side != "UP":
                self._raise_alert("WARN", f"posible GIRO a UP ({hhmmss})", "warn")
                self._save("UP", "WARN")
                self.last_warn_side = "UP"

        new = self.state
        if diff > thr:
            new = "UP"
        elif diff < -thr:
            new = "DOWN"
        if new != self.state and new in ("UP", "DOWN"):
            self.state = new
            self.transitions.append((hhmmss, new))
            self.transitions[:] = self.transitions[-8:]
            self.last_warn_side = None
            self._raise_alert("FLIP", f"CAMBIO -> {new}  ({hhmmss})", "flip")
            self._save(new, "FLIP")
            # objetivo de posicion segun la nueva direccion
            self.target = "CALL" if new == "UP" else "PUT"
            ACT.info("GIRO -> %s (net_call=%.0f net_put=%.0f thr=%.0f)",
                     new, self.net_call, self.net_put, thr)

    def _raise_alert(self, kind, text, sound):
        self.alert_kind = kind
        self.alert_text = text
        self.alert_until = time.monotonic() + 6.0
        ACT.info("ALERTA %s: %s", kind, text)
        if ENABLE_SOUND:
            self.pending_sound = sound
        if ENABLE_TOAST and kind == "FLIP":
            self._toast("SPY: CAMBIO DE DIRECCION", text)

    def _toast(self, title, msg):
        title = str(title).replace("'", " ").replace('"', " ")
        msg = str(msg).replace("'", " ").replace('"', " ")
        ps = (
            "$ErrorActionPreference='SilentlyContinue';"
            "[void][Windows.UI.Notifications.ToastNotificationManager,"
            "Windows.UI.Notifications,ContentType=WindowsRuntime];"
            "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            "$x=$t.GetElementsByTagName('text');"
            f"[void]$x.Item(0).AppendChild($t.CreateTextNode('{title}'));"
            f"[void]$x.Item(1).AppendChild($t.CreateTextNode('{msg}'));"
            "$toast=[Windows.UI.Notifications.ToastNotification]::new($t);"
            "$n=[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('SPY Direction');"
            "$n.Show($toast)")
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def simulate_step(self):
        t = self.demo_i
        self.demo_i += 1
        diff = 12000.0 * math.sin(t / 6.0)
        self.net_call = 2000.0 + max(0.0, diff) + t * 8
        self.net_put = 2000.0 + max(0.0, -diff) + t * 4
        self.spy_price = 773.0 + math.sin(t / 6.0) * 0.8
        self.status = "MODO DEMO - entradas simuladas (no es dato real)"
        self._update_signal()
        self._demo_walls(t)

    def _demo_walls(self, t):
        """SOLO --demo: genera datos de prueba SINTETICOS (no reales) para VER moverse la
        Gamma Ladder, walls/GEX/flip y la linea de contrato comprado. No toca IBKR ni la BD real."""
        self.expiry = "DEMO"
        center = round(self.spy_price)
        if not self.band_contracts:
            strikes = [center - 5 + i for i in range(11)]     # 11 strikes alrededor del precio
            self.band_contracts = []
            for s in strikes:
                self.band_contracts.append(Option(SYMBOL, self.expiry, s, "C", "SMART", tradingClass=SYMBOL))
                self.band_contracts.append(Option(SYMBOL, self.expiry, s, "P", "SMART", tradingClass=SYMBOL))
        # strike "caliente" que se desplaza -> el pico de premium se mueve (barras respiran)
        hot = self.spy_price + 2.0 * math.sin(t / 10.0)
        for c in self.band_contracts:
            s = c.strike
            bump = math.exp(-((s - hot) ** 2) / 6.0)          # gaussiana movil
            wobble = 1.0 + 0.35 * math.sin(t / 3.0 + s)
            base = 1_200_000.0 if c.right == "C" else 900_000.0
            self.today_prem[(self.expiry, s, c.right)] = base * bump * wobble
        # walls sinteticos: CW arriba, PW abajo, magnetos y centro de peso
        cw = center + 2
        pw = center - 2
        self.walls = {
            "put_wall": float(pw), "call_wall": float(cw),
            "max_pain_static": float(center),
            "max_pain_dyn": float(center + round(math.sin(t / 8.0))),
            "prem_center": hot, "spot": self.spy_price,
        }
        gex_total = 3.0e9 * math.sin(t / 7.0)                  # cambia de signo -> LONG/SHORT alterna
        self.gex = {
            "gex_total": gex_total,
            "regime": "LONG" if gex_total > 0 else ("SHORT" if gex_total < 0 else "FLAT"),
            "gamma_flip": self.spy_price - 1.0 + 0.6 * math.sin(t / 5.0),
            "spot": self.spy_price,
        }
        # contrato comprado SIMULADO: sigue la señal; cada ~18 ticks queda FLAT 3 ticks (para ver
        # que la linea DESAPARECE al vender y reaparece al recomprar)
        prev_pos = self.pos
        prev_entry = self.entry_price
        prev_price = self.contract_price
        if (t % 18) < 3:
            self.pos = "FLAT"; self.entry_price = None; self.contract_price = None
        elif self.state == "UP":
            self.pos = "CALL"
            self.buy_call = Option(SYMBOL, self.expiry, center + 1, "C", "SMART", tradingClass=SYMBOL)
            self.entry_price = 1.05
            self.contract_price = round(1.05 + 0.45 * math.sin(t / 4.0), 2)   # precio en vivo (oscila)
        elif self.state == "DOWN":
            self.pos = "PUT"
            self.buy_put = Option(SYMBOL, self.expiry, center - 1, "P", "SMART", tradingClass=SYMBOL)
            self.entry_price = 2.05
            self.contract_price = round(2.05 + 0.55 * math.sin(t / 4.0), 2)
        # notificacion DEMO de compra/venta al cambiar la posicion (con profit al vender)
        if ENABLE_TOAST and self.pos != prev_pos:
            if prev_pos in ("CALL", "PUT"):
                prof = ((prev_price if prev_price is not None else prev_entry or 0.0)
                        - (prev_entry or 0.0)) * 100.0 * QTY
                self._toast("SPY: VENTA (demo) LLENADA", f"SPY {prev_pos} vendida  Profit {prof:+.0f}$")
            if self.pos in ("CALL", "PUT"):
                bc = self.buy_call if self.pos == "CALL" else self.buy_put
                rl = "C" if self.pos == "CALL" else "P"
                self._toast("SPY: COMPRA (demo) LLENADA", f"SPY {bc.strike:g}{rl} @ {self.entry_price:.2f}")

    # ================= EJECUCION AUTOMATICA (rotar 1 opcion) =================
    def _minTick(self, contract):
        if contract.conId in self.min_tick:
            return self.min_tick[contract.conId]
        mt = 0.01
        try:
            cds = self.ib.reqContractDetails(contract)
            if cds and cds[0].minTick:
                mt = cds[0].minTick
        except Exception:
            pass
        self.min_tick[contract.conId] = mt
        return mt

    def _mid(self, contract):
        """SIEMPRE el MID (bid+ask)/2 redondeado al minTick. NUNCA bid/ask/market.
        Devuelve None si no hay bid/ask (entonces NO se coloca; se espera cotizacion)."""
        tk = self.ib.ticker(contract)
        bid = tk.bid if (tk and tk.bid and not math.isnan(tk.bid) and tk.bid > 0) else None
        ask = tk.ask if (tk and tk.ask and not math.isnan(tk.ask) and tk.ask > 0) else None
        if bid is None or ask is None or ask < bid:
            return None
        mt = self._minTick(contract)
        mid = (bid + ask) / 2.0
        return round(round(mid / mt) * mt, 2)

    def _can_afford(self, price):
        try:
            avail = None
            for r in self.ib.accountSummary():
                if r.tag in ("AvailableFunds", "BuyingPower"):
                    try:
                        v = float(r.value)
                    except Exception:
                        continue
                    if r.tag == "AvailableFunds":
                        avail = v
                        break
                    if avail is None:
                        avail = v
            if avail is None:
                return True  # si no se pudo leer, no bloquear (se vera en paper)
            return avail >= price * 100 * QTY
        except Exception:
            return True

    def _cancel_working(self):
        """Cancela CUALQUIER orden de opciones SPY viva (evita limits huerfanas)."""
        try:
            for tr in self.ib.openTrades():
                c = tr.contract
                if (c.symbol == SYMBOL and c.secType == "OPT"
                        and tr.orderStatus.status in ("PreSubmitted", "Submitted", "PendingSubmit")):
                    self.ib.cancelOrder(tr.order)
                    ACT.info("Cancelada orden huerfana %s", getattr(tr.order, "orderId", "?"))
        except Exception:
            LOG.exception("Error cancelando ordenes huerfanas")

    def _reconcile(self):
        self.reconciled = True
        try:
            self._cancel_working()   # limpiar limits colgadas de una corrida previa
            opts = [p for p in self.ib.positions()
                    if p.contract.symbol == SYMBOL and p.contract.secType == "OPT"
                    and p.position and p.position > 0]
            if len(opts) == 1:
                p = opts[0]
                self.pos = "CALL" if p.contract.right == "C" else "PUT"
                self.target = self.pos            # mantener hasta el proximo flip
                # El contrato a VENDER debe ser el que se POSEE, no el que recalculo
                # setup_contracts: si el precio se movio, el strike nuevo seria otro y
                # venderiamos algo que no tenemos (corto descubierto).
                # _adoptar_posicion ademas le asegura market data (sin ella _mid()=None y
                # la VENTA nunca se colocaria) y recupera la entrada desde avgCost.
                self.pos_qty = float(p.position)
                self._adoptar_posicion(p, self.pos)
                ACT.info("Reconcile: posicion real %s %s x%g -> contrato de salida reapuntado",
                         self.pos, getattr(p.contract, "localSymbol", "?"), self.pos_qty)
            elif len(opts) > 1:
                self.pos = "CALL" if opts[0].contract.right == "C" else "PUT"
                self.target = "FLAT"              # >1 posicion: aplanar todo al MID
                ACT.info("Reconcile: %d posiciones SPY -> aplanar", len(opts))
            else:
                self.pos = "FLAT"; self.target = "FLAT"
        except Exception:
            LOG.exception("Error en reconcile")

    def _live_orders(self):
        """Ordenes de opciones SPY VIVAS segun IBKR (no segun self.order)."""
        try:
            return [tr for tr in self.ib.openTrades()
                    if tr.contract.symbol == SYMBOL and tr.contract.secType == "OPT"
                    and tr.orderStatus.status in ("PreSubmitted", "Submitted",
                                                  "PendingSubmit", "PendingCancel")]
        except Exception:
            return []

    def _ensure_mkt(self, contract):
        """Asegura bid/ask para un contrato en cartera.
        CRITICO: los contratos que devuelve ib.positions() vienen SIN market data (la
        suscripcion la tienen los creados en setup_contracts). Sin ticker, _mid() devuelve
        None -> no hay precio ni P&L en pantalla Y ADEMAS _place() no coloca la VENTA,
        con lo que la posicion se queda atrapada."""
        try:
            cid = getattr(contract, "conId", None)
            if not cid or cid in self._mkt_subs:
                return
            # ib.positions() devuelve el contrato SIN exchange y reqMktData lo exige:
            # IBKR responde 321 "Please enter exchange" y la suscripcion nunca llega.
            if not getattr(contract, "exchange", ""):
                contract.exchange = "SMART"
            self.ib.reqMktData(contract, "", False, False)
            self._mkt_subs.add(cid)
            ACT.info("Market data suscrito para el contrato en cartera %s",
                     getattr(contract, "localSymbol", cid))
        except Exception:
            LOG.exception("Error suscribiendo market data del contrato en cartera")

    def _adoptar_posicion(self, p, lado):
        """Toma el contrato REAL en cartera como contrato de salida: lo reapunta solo si
        cambia (no churn de objetos, o se pierde el ticker), le asegura cotizacion y
        recupera el precio de entrada desde avgCost si la app no lo sabe (tras reiniciar)."""
        con = p.contract
        actual = self.buy_call if lado == "CALL" else self.buy_put
        if actual is None or getattr(actual, "conId", None) != getattr(con, "conId", None):
            if lado == "CALL":
                self.buy_call = con
            else:
                self.buy_put = con
        self._ensure_mkt(self.buy_call if lado == "CALL" else self.buy_put)
        # avgCost de opciones viene por contrato con multiplicador 100 (95.05 -> 0.9505)
        if not self.entry_price:
            try:
                ac = float(getattr(p, "avgCost", 0) or 0)
                if ac > 0:
                    self.entry_price = ac / 100.0
                    ACT.info("Entrada recuperada de IBKR (avgCost=%.2f) -> %.4f",
                             ac, self.entry_price)
            except Exception:
                pass

    def _sync_pos(self):
        """RED DE SEGURIDAD: la posicion REAL de IBKR manda sobre self.pos.
        self.pos es una variable en memoria y puede DIVERGIR de la realidad (una orden
        'cancelada' puede haberse llenado igual). No toca self.target: eso lo decide la senal."""
        try:
            opts = [p for p in self.ib.positions()
                    if p.contract.symbol == SYMBOL and p.contract.secType == "OPT"
                    and p.position and p.position > 0]
            real, qty, pos_obj = "FLAT", 0.0, None
            if opts:
                p = opts[0]
                real = "CALL" if p.contract.right == "C" else "PUT"
                qty = float(p.position)
                pos_obj = p
            if real != self.pos or qty != self.pos_qty:
                ACT.info("SYNC posicion REAL de IBKR=%s x%g | la app creia %s x%g -> corregido",
                         real, qty, self.pos, self.pos_qty)
            if pos_obj is not None:
                # vender SIEMPRE el contrato que se POSEE, con cotizacion asegurada
                self._adoptar_posicion(pos_obj, real)
            self.pos = real
            self.pos_qty = qty
            if real == "FLAT":
                self.entry_price = None
                self.contract_price = None
        except Exception:
            LOG.exception("Error en _sync_pos")

    def _place(self, contract, action, side, qty=None):
        """Coloca SIEMPRE una LimitOrder al MID. Si no hay MID, NO coloca (espera).
        qty=None -> QTY (compras). En las VENTAS se pasa la cantidad REAL en cartera."""
        # GUARDA DURA: si IBKR reporta alguna orden viva, NO colocar otra (invariante
        # "jamas 2 limits vivas"). self.order puede estar en None y aun asi haber una viva.
        vivas = self._live_orders()
        if vivas:
            self.trade_msg = f"{len(vivas)} orden(es) viva(s) en IBKR - no coloco otra"
            return
        px = self._mid(contract)
        if px is None:
            self.trade_msg = f"esperando MID para {action} {side} (sin bid/ask)"
            return
        q = int(qty) if qty else QTY
        if q <= 0:
            return
        try:
            self.order = self.ib.placeOrder(contract, LimitOrder(action, q, px))
            self.order_action = action
            self.order_side = side
            self.order_contract = contract
            self.order_deadline = time.monotonic() + REPRICE_SECS
            self.trade_msg = f"{action} {side} x{q} LIMIT MID @ {px:.2f}"
            ACT.info("ORDEN %s %s x%d LIMIT MID @ %.2f", action, side, q, px)
        except Exception as e:
            self.trade_msg = f"error orden: {e}"
            self.order = None
            LOG.exception("Error colocando orden %s %s", action, side)

    def _on_filled(self):
        act, side = self.order_action, self.order_side
        try:
            px = self.order.orderStatus.avgFillPrice
        except Exception:
            px = 0.0
        # cantidad REALMENTE llenada (puede no ser QTY: fills parciales / venta de varios lotes)
        try:
            nq = float(self.order.orderStatus.filled) or float(QTY)
        except Exception:
            nq = float(QTY)
        # profit al VENDER (usa el precio de entrada ANTES de limpiarlo)
        profit = pct = None
        if act == "SELL" and self.entry_price:
            profit = (px - self.entry_price) * 100.0 * nq
            pct = (px / self.entry_price - 1.0) * 100.0
        rl = "C" if side == "CALL" else "P"
        c = getattr(self, "order_contract", None)
        strike = f"{c.strike:g}{rl}" if c is not None else side
        self.trade_msg = (f"{act} {side} LLENADO @ {px:.2f}"
                          + (f"  Profit {profit:+.2f} ({pct:+.1f}%)" if profit is not None else ""))
        ACT.info("FILL %s %s @ %.2f -> pos=%s%s", act, side, px,
                 "FLAT" if act != "BUY" else side,
                 (f" | PROFIT {profit:+.2f} ({pct:+.1f}%)" if profit is not None else ""))
        # NOTIFICACION en el FILL REAL (cuando la orden se llena, NO al enviarla)
        if ENABLE_TOAST:
            if act == "BUY":
                self._toast(f"SPY: COMPRA {side} LLENADA", f"SPY {strike} @ {px:.2f}")
            else:
                body = f"SPY {strike} @ {px:.2f}"
                if profit is not None:
                    body += f"  |  Profit {profit:+.2f} ({pct:+.1f}%)"
                self._toast(f"SPY: VENTA {side} LLENADA", body)
        # actualizar posicion/entrada DESPUES de calcular el profit
        # (valor PROVISIONAL: _sync_pos lo corrige contra IBKR, que es la fuente de verdad)
        self.pos = side if act == "BUY" else "FLAT"
        self.pos_qty = nq if act == "BUY" else 0.0
        self.entry_price = px if act == "BUY" else None
        if act != "BUY":
            self.contract_price = None
        self.order = None
        self.open_deadline = 0.0

    def trade_poll(self):
        """Motor de ejecucion, se llama en cada tick (no bloquea la GUI)."""
        if self.demo or not self.trading or not self.ib.isConnected():
            return
        if self.buy_call is None or self.buy_put is None:
            return
        if not self.reconciled:
            self._reconcile()

        # RED DE SEGURIDAD: la posicion REAL de IBKR manda sobre self.pos. Sin esto la app
        # puede creerse FLAT teniendo contratos (orden 'cancelada' que se llenó igual).
        if self.order is None and time.monotonic() - self.last_sync > SYNC_POS_SECS:
            self._sync_pos()
            self.last_sync = time.monotonic()

        # CAPITAL BAJO: NUNCA mas de QTY contrato(s). Si hay de mas, aplanar TODO.
        if self.pos_qty > QTY:
            if self.target != "FLAT":
                ACT.info("EXCESO de posicion: %g contratos (maximo %d) -> aplanar TODO",
                         self.pos_qty, QTY)
            self.target = "FLAT"

        et = now_et()
        hhmm = et.strftime("%H:%M")
        weekday = et.weekday() < 5
        in_session = weekday and ("09:30" <= hhmm <= "16:00")
        if weekday and hhmm >= FLATTEN_HHMM:      # EOD: aplanar
            self.target = "FLAT"
        stop_new = (not in_session) or (weekday and hhmm >= STOP_NEW_HHMM)

        now = time.monotonic()
        # ---- orden activa: gestionar fill / re-precio ----
        if self.order is not None:
            st = self.order.orderStatus.status
            if st == "Filled":
                self._on_filled()
                return
            if st in ("Cancelled", "ApiCancelled", "Inactive"):
                # OJO: 'Cancelado' NO significa 'no paso nada'. Entre el cancelOrder y su
                # confirmacion la orden SIGUE siendo ejecutable y puede haberse llenado
                # (total o parcialmente). Si se ignora, la app cree estar FLAT teniendo
                # contratos reales -> posiciones huerfanas que nadie cierra.
                try:
                    llenado = float(self.order.orderStatus.filled or 0)
                except Exception:
                    llenado = 0.0
                if llenado > 0:
                    ACT.info("ORDEN cancelada PERO llenada x%g -> se procesa como FILL", llenado)
                    self._on_filled()
                    return
                self.order = None
            elif now >= self.order_deadline:
                # No lleno al MID: SOLO cancelar. La recotizacion al MID nuevo ocurre cuando
                # el cancel se confirme (order=None) -> jamas 2 limits vivas (no short).
                try:
                    self.ib.cancelOrder(self.order.order)
                except Exception:
                    pass
            return

        # ---- sin orden viva: mover posicion al objetivo (SIEMPRE LimitOrder al MID) ----
        if self.pos != self.target:
            if self.pos in ("CALL", "PUT"):
                # CERRAR: vender al MID, RELENTLESS (reintenta hasta llenar).
                # Se vende la cantidad REAL en cartera (si quedaron 3 lotes, se cierran los 3;
                # vender QTY=1 dejaria 2 huerfanos que nadie cerraria).
                contract = self.buy_call if self.pos == "CALL" else self.buy_put
                self._place(contract, "SELL", self.pos, qty=(self.pos_qty or QTY))
            elif self.target in ("CALL", "PUT") and not stop_new:
                # ABRIR: comprar al MID, con limite de tiempo (si no llena, abandona -> FLAT)
                if not self.open_deadline:
                    self.open_deadline = now + MAX_FILL_SECS
                if now >= self.open_deadline:
                    self.trade_msg = f"BUY {self.target} no lleno al MID - abandonado"
                    self.target = "FLAT"
                    self.open_deadline = 0.0
                else:
                    # GUARDA DURA (capital bajo): 1 SOLA posicion, 1 SOLO contrato.
                    # Se comprueba contra IBKR, NO contra self.pos: una orden 'cancelada'
                    # pudo llenarse y dejarnos con contratos que la app no sabe que tiene.
                    self._sync_pos()
                    self.last_sync = time.monotonic()
                    if self.pos_qty > 0:
                        self.trade_msg = (f"ya hay {self.pos_qty:g} contrato(s) en cartera "
                                          f"- NO se compra hasta cerrarlos")
                        return
                    contract = self.buy_call if self.target == "CALL" else self.buy_put
                    px = self._mid(contract)
                    if px is None:
                        self.trade_msg = "esperando MID (sin bid/ask)"
                    elif self._can_afford(px):
                        self._place(contract, "BUY", self.target)
                    else:
                        self.trade_msg = f"sin buying power para {self.target}"

    def toggle_trading(self):
        self.trading = not self.trading
        self.trade_msg = "TRADING ARMADO" if self.trading else "TRADING OFF (desarmado)"
        ACT.info("TRADING %s por el usuario", "ARMADO" if self.trading else "DESARMADO")
        return self.trading

    # ================= TA 1 min + registro por minuto =================
    def ta_poll(self):
        if self.demo or self.bars is None or not HAVE_PD:
            return
        try:
            rows = [{"high": b.high, "low": b.low, "close": b.close,
                     "volume": b.volume, "date": b.date} for b in self.bars]
        except Exception:
            return
        # PRECIO EN VIVO: self.spy_price solo se fijaba en setup_contracts (1 vez por sesion),
        # asi que quedaba CONGELADO todo el dia -> transitions.spy, walls_snapshot.spot, el GEX
        # (factor spot^2) y la Ladder usaban el precio de la apertura. Las barras ya llegan en
        # vivo (keepUpToDate=True): se reutiliza ese dato, sin pedir nada mas a IBKR.
        # OJO: va ANTES del corte de 26 barras, o el precio seguiria congelado 26 minutos.
        if rows:
            _px = rows[-1]["close"]
            if _px is not None and not math.isnan(_px) and _px > 0:
                self.spy_price = float(_px)
        if len(rows) < 26:
            return
        df = pd.DataFrame(rows)
        self.ta_vals = self.ta.compute(df)          # en vivo (para la pantalla)
        last_time = rows[-1]["date"]
        if self.last_bar_time is None:
            self.last_bar_time = last_time
            return
        if last_time != self.last_bar_time:
            # se cerro un minuto -> registrar la barra ya cerrada (sin la ultima en formacion)
            closed = self.ta.compute(df.iloc[:-1]) if len(df) > 27 else self.ta_vals
            self._log_minute(closed, rows[-2]["date"] if len(rows) >= 2 else last_time)
            self.last_bar_time = last_time

    def _log_minute(self, vals, bar_dt):
        if not vals:
            return
        try:
            if hasattr(bar_dt, "strftime"):
                fecha = bar_dt.strftime("%Y-%m-%d"); hora = bar_dt.strftime("%H:%M")
            else:
                s = str(bar_dt); fecha, hora = s[:10], s[11:16]
            self.db.execute(
                "INSERT OR REPLACE INTO ta_minute(fecha,hora,spy,rsi,ema8,ema21,ema50,"
                "macd_line,macd_signal,macd_hist,bb_up,bb_mid,bb_low,atr,atr_pct,vwap,"
                "obv_trend,ta_score,ta_dir,net_call,net_put,prem_state) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, vals["close"], vals["rsi"], vals["ema8"], vals["ema21"],
                 vals["ema50"], vals["macd_line"], vals["macd_signal"], vals["macd_hist"],
                 vals["bb_up"], vals["bb_mid"], vals["bb_low"], vals["atr"], vals["atr_pct"],
                 vals["vwap"], vals["obv_trend"], vals["score"], vals["dir"],
                 self.net_call, self.net_put, self.state))
            for (exp, strike, right), cp in self.accum.items():
                dp = self.today_prem.get((exp, strike, right), 0.0)
                # NO usar INSERT OR REPLACE: esta fila puede haberla escrito _persist_walls
                # con 10 columnas (incluidos open_interest/gamma/net_prem de la banda) y el
                # REPLACE las dejaria en NULL. ON CONFLICT ... DO UPDATE solo pisa lo que
                # nombra y preserva el resto (mismo idioma que _persist_accum).
                self.db.execute(
                    "INSERT INTO premium_minute(fecha,hora,expiry,strike,right,"
                    "cum_prem,day_prem) VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(fecha,hora,expiry,strike,right) "
                    "DO UPDATE SET cum_prem=excluded.cum_prem, day_prem=excluded.day_prem",
                    (fecha, hora, exp, strike, right, cp, dp))
            self.db.commit()
            # --- LOG EXHAUSTIVO POR MINUTO (respaldo completo del dia por si la BD falla) ---
            ACT.info("MIN %s | SPY=%.2f | TA dir=%s score=%+d rsi=%.1f macd=%.3f/%.3f/%+.3f "
                     "ema8/21/50=%.2f/%.2f/%.2f bb=%.2f/%.2f/%.2f atr=%.2f(%.2f%%) vwap=%.2f obv=%s",
                     hora, vals["close"], vals["dir"], vals["score"], vals["rsi"],
                     vals["macd_line"], vals["macd_signal"], vals["macd_hist"],
                     vals["ema8"], vals["ema21"], vals["ema50"],
                     vals["bb_up"], vals["bb_mid"], vals["bb_low"],
                     vals["atr"], vals["atr_pct"], vals["vwap"], vals["obv_trend"])
            ACT.info("MIN %s | SENAL netC=%.0f netP=%.0f diff=%.0f thr=%.0f mom=%.0f -> estado=%s pos=%s",
                     hora, self.net_call, self.net_put, self.last_diff, self.last_thr,
                     self.last_momentum, self.state, self.pos)
            if self.pos in ("CALL", "PUT"):
                en = self.entry_price or 0.0
                pr = self.contract_price
                pnl = ((pr - en) * 100.0 * QTY) if (pr is not None and en) else 0.0
                ACT.info("MIN %s | CONTRATO %s entrada=%.2f actual=%s pnl=%+.0f$", hora, self.pos,
                         en, (f"{pr:.2f}" if pr is not None else "-"), pnl)
            for (exp, strike, right), dp in sorted(self.today_prem.items()):
                if dp > 0:   # solo strikes con actividad
                    ACT.info("MIN %s | PREM %s %g%s day=%.0f cum=%.0f net=%+.0f", hora, exp,
                             strike, right, dp, self.accum.get((exp, strike, right), 0.0),
                             self.net_prem.get((exp, strike, right), 0.0))
        except Exception:
            LOG.exception("Error guardando registro por minuto")


# ----------------------- GUI Tkinter -----------------------
import tkinter as tk


def _draw_ladder(canvas, app):
    """Dibuja la Gamma Ladder (solo lectura). El PRECIO y el CONTRATO comprado tienen su propio
    carril de etiqueta a la izquierda (NO encima de las barras) y una raya horizontal a su nivel."""
    canvas.delete("all")
    W = int(canvas["width"]); H = int(canvas["height"])
    data = app.ladder_rows()
    rows = data["rows"]
    if not rows:
        canvas.create_text(W // 2, H // 2, text="Gamma Ladder: (esperando OI/premium en vivo...)",
                           fill="#67e8f9", font=("Consolas", 10))
        return
    n = len(rows)
    top = 4
    row_h = max(11, min(20, (H - 8) // n))
    x_strike_r = 42            # etiqueta de strike (anchor e)
    x_mark_r = 100             # carril de marcadores precio/contrato (anchor e) -> NO sobre barras
    x_bar0 = 104               # inicio de las barras
    bar_max = W - x_bar0 - 52  # ancho maximo de barra (deja espacio al valor)
    max_prem = data["max_prem"] or 1.0

    def y_at(i):
        return top + i * row_h + row_h // 2

    def y_of_level(level):
        if level is None:
            return None
        for i in range(len(rows) - 1):
            s0 = rows[i][0]; s1 = rows[i + 1][0]     # s0 > s1 (orden desc)
            if s0 >= level >= s1 and s0 != s1:
                frac = (s0 - level) / (s0 - s1)
                return y_at(i) + frac * (y_at(i + 1) - y_at(i))
        return None

    # separador del carril de marcadores
    canvas.create_line(x_bar0 - 2, top, x_bar0 - 2, top + n * row_h, fill="#1f2937", width=1)

    for i, (s, prem, side, tag) in enumerate(rows):
        y = y_at(i)
        lbl = f"{s:g}{tag}"
        if "CW" in tag:
            col_lbl = "#22c55e"
        elif "PW" in tag:
            col_lbl = "#ef4444"
        elif "M" in tag:                 # magneto (Max Pain)
            col_lbl = "#a78bfa"
        else:
            col_lbl = "#cbd5e1"
        canvas.create_text(x_strike_r, y, text=lbl, fill=col_lbl, font=("Consolas", 8), anchor="e")
        ln = int(bar_max * (prem / max_prem)) if max_prem > 0 else 0
        col = "#16a34a" if side == "call" else "#dc2626"
        if ln > 0:
            canvas.create_rectangle(x_bar0, y - row_h // 2 + 2, x_bar0 + ln, y + row_h // 2 - 2,
                                    fill=col, outline="")
        canvas.create_text(x_bar0 + ln + 4, y, text=_money(prem), fill="#94a3b8",
                           font=("Consolas", 7), anchor="w")

    # --- GAMMA FLIP: raya punteada naranja + etiqueta a la derecha ---
    yf = y_of_level(data["flip"])
    if yf is not None:
        canvas.create_line(x_bar0, yf, W - 2, yf, fill="#f59e0b", width=1, dash=(3, 2))
        canvas.create_text(W - 4, yf + 6, text=f"flip {data['flip']:.2f}",
                           fill="#f59e0b", font=("Consolas", 7), anchor="e")

    # --- PRECIO: raya blanca cruzando las barras + etiqueta en el carril (con estado) ---
    price = data["price"]
    yp = y_of_level(price) if (price is not None and not math.isnan(price)) else None
    if yp is not None:
        st = data["state"]
        stcol = {"UP": "#22c55e", "DOWN": "#ef4444"}.get(st, "#e5e7eb")
        arrow = {"UP": "^", "DOWN": "v"}.get(st, "-")
        canvas.create_line(x_bar0, yp, W - 2, yp, fill="#f8fafc", width=1)
        canvas.create_text(x_mark_r, yp, text=f"{arrow} {price:.2f}", fill=stcol,
                           font=("Consolas", 8, "bold"), anchor="e")

    # --- CONTRATO COMPRADO: raya amarilla al nivel del strike + etiqueta en el carril ---
    ct = data.get("contract")
    if ct is not None:
        yc = y_of_level(ct["strike"])
        if yc is None:
            yce = [y_at(i) for i, r in enumerate(rows) if r[0] == ct["strike"]]
            yc = yce[0] if yce else None
        if yc is not None:
            rl = "C" if ct["side"] == "CALL" else "P"
            pr = ct.get("price"); en = ct.get("entry")
            # color de la raya/etiqueta segun P&L: verde si subio, rojo si bajo, amarillo si sin dato
            ccol = "#fbbf24"
            if pr is not None and en:
                ccol = "#22c55e" if pr >= en else "#ef4444"
            canvas.create_line(x_bar0, yc, W - 2, yc, fill=ccol, width=2)
            ytxt = yc + (9 if (yp is not None and abs(yc - yp) < 9) else 0)
            txt = f">{ct['strike']:g}{rl}"
            if pr is not None:
                txt += f" {pr:.2f}"
            canvas.create_text(x_mark_r, ytxt, text=txt, fill=ccol,
                               font=("Consolas", 8, "bold"), anchor="e")


def run_gui(app):
    root = tk.Tk()
    root.title("SPY Direction")
    root.report_callback_exception = lambda *a: LOG.error("Error en GUI", exc_info=a)
    root.configure(bg="#111111")
    root.geometry("560x940")

    big = tk.Label(root, text="-", font=("Segoe UI", 46, "bold"),
                   fg="#888888", bg="#111111")
    big.pack(pady=(8, 0))

    sub = tk.Label(root, text="", font=("Segoe UI", 12), fg="#dddddd", bg="#111111")
    sub.pack()

    # --- fila de TRADING: indicador + posicion + boton ARMAR ---
    trow = tk.Frame(root, bg="#111111")
    trow.pack(pady=(6, 0))
    trade_ind = tk.Label(trow, text="TRADING OFF", font=("Segoe UI", 11, "bold"),
                         fg="#111111", bg="#ef4444", padx=8, pady=2)
    trade_ind.grid(row=0, column=0, padx=4)
    pos_lbl = tk.Label(trow, text="POSICION: FLAT", font=("Segoe UI", 11, "bold"),
                       fg="#e5e7eb", bg="#111111")
    pos_lbl.grid(row=0, column=1, padx=8)

    def _toggle():
        on = app.toggle_trading()
        btn.config(text="DESARMAR" if on else "ARMAR")
    btn = tk.Button(trow, text=("DESARMAR" if app.trading else "ARMAR"),
                    font=("Segoe UI", 10, "bold"),
                    command=_toggle, bg="#1f2937", fg="#ffffff", activebackground="#374151")
    btn.grid(row=0, column=2, padx=4)

    trade_msg_lbl = tk.Label(root, text="", font=("Consolas", 9), fg="#f59e0b", bg="#111111")
    trade_msg_lbl.pack()

    # Contrato comprado (solo aparece si hay posicion real en IBKR; al vender desaparece)
    contract_lbl = tk.Label(root, text="", font=("Consolas", 10, "bold"), fg="#fbbf24", bg="#111111")
    contract_lbl.pack()

    alert = tk.Label(root, text="", font=("Segoe UI", 15, "bold"),
                     fg="#111111", bg="#111111", pady=6)
    alert.pack(fill="x", padx=10, pady=(6, 0))

    status = tk.Label(root, text="", font=("Consolas", 9), fg="#8ab4f8",
                      bg="#111111", wraplength=480, justify="center")
    status.pack(pady=(6, 2))

    ta_lbl = tk.Label(root, text="TA 1m: (esperando barras...)", font=("Consolas", 9),
                      fg="#c4b5fd", bg="#111111")
    ta_lbl.pack(pady=(0, 2))

    walls_lbl = tk.Label(root, text="Walls/GEX: (esperando OI/greeks...)", font=("Consolas", 9),
                         fg="#67e8f9", bg="#111111", wraplength=520, justify="center")
    walls_lbl.pack(pady=(0, 2))

    # Gamma Ladder (solo lectura, estilo MarketSnack): premium $ por strike
    tk.Label(root, text="Gamma Ladder - premium $ por strike (verde>precio / rojo<precio):",
             font=("Consolas", 8, "bold"), fg="#67e8f9", bg="#111111").pack()
    ladder = tk.Canvas(root, width=540, height=380, bg="#0b0b0b", highlightthickness=0)
    ladder.pack(pady=(2, 6))

    tk.Label(root, text="Linea base (fechas posteriores) - hoy vs dia previo:",
             font=("Consolas", 9, "bold"), fg="#f59e0b", bg="#111111").pack()
    basebox = tk.Text(root, height=3, width=56, bg="#0b0b0b", fg="#e5e7eb",
                      font=("Consolas", 9), bd=0)
    basebox.pack(pady=(2, 6))

    tk.Label(root, text="Historial de giros (SQLite):",
             font=("Consolas", 9, "bold"), fg="#8ab4f8", bg="#111111").pack()
    logbox = tk.Text(root, height=4, width=56, bg="#0b0b0b", fg="#aaaaaa",
                     font=("Consolas", 9), bd=0)
    logbox.pack(pady=(2, 8))

    colors = {"UP": "#22c55e", "DOWN": "#ef4444", "-": "#888888"}
    connected = {"ok": False}
    sesion = {"fecha": None, "reintento": 0.0}   # fecha de la sesion viva + cooldown de reintento

    def try_connect(nuevo_dia):
        try:
            if nuevo_dia:
                # SOLO en dia nuevo: acumuladores intradia en 0. En una RECONEXION no se toca,
                # o cada caida de socket borraria net_call/net_put del dia.
                app.reset_day()
            app.connect()
            if app.setup_contracts():
                connected["ok"] = True
                app.reconciled = False   # re-sincronizar posicion/ordenes tras (re)conectar
        except Exception as e:
            app.status = f"SIN CONEXION a IB Gateway ({e}). Reintentando..."
            LOG.exception("Fallo al conectar/setup")

    def tick():
        if app.demo:
            app.simulate_step()
        elif app.is_market_open():
            # MERCADO ABIERTO (09:30-16:00 ET): arrancar/recolectar. (Trading cesa 15:45 en trade_poll.)
            # La verdad de la conexion es el SOCKET, no una bandera local: si se cae a mitad
            # de sesion hay que reintentar (antes quedaba muda hasta las 16:00, sin error).
            if not app.ib.isConnected():
                if connected["ok"]:
                    connected["ok"] = False
                    ACT.info("DESCONEXION detectada - reintentando cada %.0fs", RECONNECT_SECS)
                hoy = now_et().strftime("%Y-%m-%d")
                if time.monotonic() >= sesion["reintento"]:
                    sesion["reintento"] = time.monotonic() + RECONNECT_SECS
                    try_connect(nuevo_dia=(sesion["fecha"] != hoy))
                    if connected["ok"]:
                        sesion["fecha"] = hoy
                        ACT.info("CONECTADO (sesion %s)", hoy)
            try:
                if app.ib.isConnected():
                    app.ib.sleep(REFRESH_SECS)
                    if time.monotonic() - app.last_snapshot > SNAPSHOT_SECS:
                        app._persist_accum()
                        app.last_snapshot = time.monotonic()
                    app.trade_poll()
                    app.ta_poll()
                    if (WALLS_ENABLED
                            and time.monotonic() - app.last_walls_calc > WALLS_RECALC_SECS):
                        app.compute_walls()   # informativo: recalcula/guarda cada 3 min
                        app.last_walls_calc = time.monotonic()
                    # precio ACTUAL del contrato comprado (tiempo real, para P&L)
                    _cc = app.buy_call if app.pos == "CALL" else (app.buy_put if app.pos == "PUT" else None)
                    if _cc is not None:
                        _m = app._mid(_cc)
                        if _m is not None:
                            app.contract_price = _m
                    # log de cambios de decision de trading (por que opera / por que no)
                    if app.trade_msg != app._last_trade_log:
                        ACT.info("TRADE %s", app.trade_msg)
                        app._last_trade_log = app.trade_msg
            except Exception:
                LOG.exception("Error en el ciclo principal (tick)")
        else:
            # MERCADO CERRADO: detener la sesion una vez y esperar la proxima apertura
            if connected["ok"] or app.ib.isConnected():
                app.end_session()
                connected["ok"] = False
            app.status = "MERCADO CERRADO (ET) - esperando apertura 09:30"

        big.config(text=app.state, fg=colors.get(app.state, "#888888"))
        sub.config(text=(f"SPY {app.spy_price:.2f}    "
                         f"CALL net ${app.net_call:,.0f}   PUT net ${app.net_put:,.0f}"))
        status.config(text=f"[{app.mode}] {app.status}")

        # --- estado de trading ---
        if app.pos == "CALL" and app.call is not None:
            pos_txt = f"LONG CALL {app.buy_call.strike:g}" if app.buy_call else "LONG CALL"
        elif app.pos == "PUT" and app.put is not None:
            pos_txt = f"LONG PUT {app.buy_put.strike:g}" if app.buy_put else "LONG PUT"
        else:
            pos_txt = "FLAT"
        pos_lbl.config(text=f"POSICION: {pos_txt}")
        if app.trading:
            trade_ind.config(text="TRADING ON", bg="#22c55e")
        else:
            trade_ind.config(text="TRADING OFF", bg="#ef4444")
        trade_msg_lbl.config(text=app.trade_msg)

        v = app.ta_vals
        if v:
            ta_lbl.config(text=(f"TA 1m: {v['dir']}  RSI {v['rsi']:.0f}  "
                                f"MACDh {v['macd_hist']:+.2f}  EMA8/21 {v['ema8']:.2f}/{v['ema21']:.2f}"
                                f"  score {v['score']:+d}"))

        if WALLS_ENABLED and app.walls:
            w = app.walls
            gg = app.gex or {}
            gxt = gg.get("gex_total")
            gtxt = f"{gxt/1e9:+.2f}Bn" if isinstance(gxt, (int, float)) else "-"
            walls_lbl.config(text=(
                f"PW {_fmt(w.get('put_wall'))}  CW {_fmt(w.get('call_wall'))}  "
                f"Mag {_fmt(w.get('max_pain_static'))}/{_fmt(w.get('max_pain_dyn'))}  "
                f"peso {_fmt(w.get('prem_center'))}\n"
                f"GEX {gtxt} {gg.get('regime', '-')}  Flip {_fmt(gg.get('gamma_flip'))}"))

        # contrato comprado (SOLO si hay posicion real; al vender/FLAT desaparece).
        # Precio en vivo + P&L, color verde/rojo segun subio/bajo desde la entrada.
        _bc = app.buy_call if app.pos == "CALL" else (app.buy_put if app.pos == "PUT" else None)
        if _bc is not None:
            rl = "C" if app.pos == "CALL" else "P"
            en = app.entry_price
            pr = app.contract_price
            txt = f"Contrato: SPY {_bc.strike:g}{rl} {app.expiry or ''}"
            col = "#fbbf24"
            if en:
                txt += f"  entrada {en:.2f}"
            if pr is not None:
                txt += f"  ->  {pr:.2f}"
                if en:
                    pnl = (pr - en) * 100.0 * QTY
                    pct = (pr / en - 1.0) * 100.0
                    txt += f"  ({pnl:+.0f}$ / {pct:+.1f}%)"
                    col = "#22c55e" if pr >= en else "#ef4444"
            contract_lbl.config(text=txt, fg=col)
        else:
            contract_lbl.config(text="")

        # Gamma Ladder (solo lectura, estilo MarketSnack)
        if WALLS_ENABLED:
            try:
                _draw_ladder(ladder, app)
            except Exception:
                LOG.exception("Error dibujando Gamma Ladder")

        if app.pending_sound is not None:
            if HAVE_SOUND:
                try:
                    if app.pending_sound == "flip":
                        winsound.Beep(880, 300); winsound.Beep(1175, 300)
                    else:
                        winsound.Beep(660, 200)
                except Exception:
                    pass
            app.pending_sound = None
        if app.alert_text and time.monotonic() < app.alert_until:
            bg = "#ef4444" if app.alert_kind == "FLIP" else "#f59e0b"
            alert.config(text="  " + app.alert_text + "  ", bg=bg, fg="#111111")
            try:
                root.attributes("-topmost", True); root.lift()
                root.after(1200, lambda: root.attributes("-topmost", False))
            except Exception:
                pass
        else:
            alert.config(text="", bg="#111111")

        # baseline (fechas posteriores)
        basebox.delete("1.0", tk.END)
        for exp, ch, cp, ph, pp in app.baseline_summary():
            cflag = " STRONG" if (cp > 0 and ch > cp * OPEN_JUMP_FACTOR) else ""
            pflag = " STRONG" if (pp > 0 and ph > pp * OPEN_JUMP_FACTOR) else ""
            basebox.insert(tk.END,
                           f"{exp}  C hoy ${ch:,.0f}/prev ${cp:,.0f}{cflag}\n"
                           f"          P hoy ${ph:,.0f}/prev ${pp:,.0f}{pflag}\n")
        if not app.base_expiries:
            basebox.insert(tk.END, "(sin datos aun / conectando...)\n")

        logbox.delete("1.0", tk.END)
        for fecha, hora, estado, tipo, spy in app.recent(8):
            sp = f"{spy:.2f}" if spy else "-"
            logbox.insert(tk.END, f"  {fecha} {hora}  {tipo:4}  {estado:4}  SPY {sp}\n")

        root.after(int(REFRESH_SECS * 1000), tick)

    root.after(200, tick)
    root.mainloop()

    try:
        app._persist_accum()
    except Exception:
        pass
    try:
        if not app.demo and app.ib.isConnected():
            app._cancel_working()   # no dejar limits huerfanas al cerrar
    except Exception:
        pass
    try:
        app.ib.disconnect()
    except Exception:
        pass
    try:
        app.db.close()
    except Exception:
        pass


def selftest():
    app = SpyDirection()
    try:
        app.connect()
        print(f"Conexion IB Gateway OK ({HOST}:{PORT})")
    except Exception as e:
        print(f"SIN CONEXION: {e}")
        return
    ok = app.setup_contracts()
    print("Resultado setup:", app.status)
    if ok:
        print(f"  Modo datos : {app.mode}")
        print(f"  SPY        : {app.spy_price:.2f}")
        print(f"  Cercano    : {app.expiry}")
        print(f"  CALL/PUT   : {app.call.strike:g}C / {app.put.strike:g}P")
        print(f"  Baseline exps futuras: {app.base_expiries}")
        print(f"  Contratos baseline seguidos: {len(app.info_base)}")
    app.ib.disconnect()


if __name__ == "__main__":
    util.patchAsyncio()
    if "--selftest" in sys.argv:
        selftest()
    elif "--demo" in sys.argv:
        run_gui(SpyDirection(demo=True))
    else:
        run_gui(SpyDirection())
