# -*- coding: utf-8 -*-
"""COLD RUN de BARS_DURATION="2 D" (2026-08-11, orden del usuario).

Objetivo: que la SMA200 exista DESDE EL PRIMER MINUTO de sesion. Con "1 D" no habia 200 barras
hasta ~12:50 y la columna quedaba NULL media sesion.

Lo que hay que demostrar:
  1. La constante esta puesta y `_subscribe_bars` la usa (no un literal).
  2. Con el numero de barras que da "2 D" la SMA200 tiene valor; con las de "1 D" en la apertura, no.
  3. EL COSTE, medido y explicito: ema8/21/50 y obv CAMBIAN de valor; rsi/atr/bb/vwap/sma NO.
  4. La duracion queda registrada en `sesion_config` (sin eso, dos tramos incomparables y nada
     lo delata).
  5. Contra IBKR REAL: "2 D" devuelve >=200 barras ahora mismo.
"""
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
import logging as _lg
import spy_direction as S

S.ENABLE_TOAST = False
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


import inspect
import pandas as pd

# ============================================================ 1
print("=" * 78)
print("1) La constante existe y _subscribe_bars la USA (no un literal)")
print("=" * 78)
check(hasattr(S, "BARS_DURATION"), f"BARS_DURATION existe -> {getattr(S,'BARS_DURATION',None)!r}")
check(S.BARS_DURATION == "2 D", f"vale '2 D' -> {S.BARS_DURATION!r}")
src = inspect.getsource(S.SpyDirection._subscribe_bars)
check("BARS_DURATION" in src, "_subscribe_bars usa la constante")
check('"1 D"' not in src, "ya no queda el literal '1 D' en _subscribe_bars")

# ============================================================ 2
print()
print("=" * 78)
print("2) La SMA200 existe con las barras de '2 D' y NO con las de la apertura de '1 D'")
print("=" * 78)
ta = S.TAEngine()


def barras(n):
    return pd.DataFrame([{"high": 773 + i * .01 + .05, "low": 773 + i * .01 - .05,
                          "close": 773 + i * .01, "volume": 1000 + i,
                          "date": "d%05d" % i} for i in range(n)])


v_1d_apertura = ta.compute(barras(52))     # lo que habia hoy a las 10:21 con "1 D"
v_2d = ta.compute(barras(442))             # lo que da "2 D" (medido contra IBKR)
check(v_1d_apertura["sma200"] is None,
      "con 52 barras (apertura con '1 D'): sma200 = None  <- el problema que se resuelve")
check(v_2d["sma200"] is not None,
      f"con 442 barras ('2 D'): sma200 = {v_2d['sma200']:.4f}  <- disponible desde el minuto 1")
check(v_2d["sma50"] is not None and v_2d["sma20"] is not None,
      "sma20 y sma50 tambien disponibles")

# ============================================================ 3
print()
print("=" * 78)
print("3) EL COSTE, medido: que indicadores CAMBIAN al ampliar la serie")
print("=" * 78)
# misma cola de 52 velas en ambos casos: lo unico que cambia es cuanta historia hay ANTES
larga = barras(442)
corta = larga.iloc[-52:].reset_index(drop=True)
vl, vc = ta.compute(larga), ta.compute(corta)


def dif(campo):
    a, b = vl.get(campo), vc.get(campo)
    if a is None or b is None:
        return None
    return abs(a - b)


print("   (mismas 52 velas finales; solo cambia la historia previa)")
# Se REPORTA la magnitud real en notacion cientifica. Un check que da OK diciendo "CAMBIA" con
# dif=0.000000 (por el formato %.6f) es engañoso: la ema8 converge tan rapido que la diferencia
# es de ~1e-9, o sea NADA. Lo unico que cambia de forma apreciable es ema50 y obv.
UMBRAL_APRECIABLE = 1e-4
for campo in ("ema8", "ema21", "ema50"):
    d = dif(campo)
    apreciable = d is not None and d > UMBRAL_APRECIABLE
    check(d is not None,
          f"{campo:>6} {'CAMBIA' if apreciable else 'igual '} -> {vc[campo]:.6f} (1D) vs "
          f"{vl[campo]:.6f} (2D)  dif={d:.3e}"
          f"{'  <-- coste real' if apreciable else '  (despreciable)'}")
check(dif("ema50") > UMBRAL_APRECIABLE,
      f"ema50 es la que de verdad se ve afectada -> dif={dif('ema50'):.3e}")
check(vl["obv_trend"] is not None and vc["obv_trend"] is not None,
      f"obv_trend: '{vc['obv_trend']}' (1D) vs '{vl['obv_trend']}' (2D) -> es acumulado, puede cambiar")
for campo in ("rsi", "atr", "bb_up", "bb_low", "vwap", "sma20", "sma50"):
    d = dif(campo)
    check(d is not None and d < 1e-9,
          f"{campo:>6} NO cambia (ventana fija) -> {vl[campo]:.6f} en ambos")

# ============================================================ 4
print()
print("=" * 78)
print("4) La duracion queda REGISTRADA en sesion_config")
print("=" * 78)
app = S.SpyDirection(demo=True)
app.demo = False
app.db.close()
app.db = sqlite3.connect(":memory:")
app._init_db()
cols = [d[1] for d in app.db.execute("PRAGMA table_info(sesion_config)")]
for c in ("bars_duration", "start_trade_hhmm", "open_hhmm"):
    check(c in cols, f"columna {c} en sesion_config")
app.trading = True
app._sellar_sesion()                      # <-- METODO REAL que escribe sesion_config
r = app.db.execute("SELECT bars_duration,start_trade_hhmm,open_hhmm,gaps_activos "
                   "FROM sesion_config").fetchone()
check(r is not None, "se escribio la fila de sesion_config")
if r:
    check(r[0] == "2 D", f"bars_duration guardado -> {r[0]!r}")
    check(r[1] == S.START_TRADE_HHMM, f"start_trade_hhmm -> {r[1]!r}")
    check(r[2] == S.OPEN_HHMM, f"open_hhmm -> {r[2]!r}")
    check("BARS2D" in (r[3] or "") and "SMA20-50-200" in (r[3] or ""),
          f"gaps_activos incluye los arreglos nuevos")

# ============================================================ 5
print()
print("=" * 78)
print("5) CONTRA IBKR REAL: '2 D' devuelve >=200 barras ahora mismo")
print("=" * 78)
S.CLIENT_ID = 22                     # temporal, no toca el 7 de la app en produccion
probe = S.SpyDirection(demo=True)
probe.demo = False
try:
    probe.connect()
    spy = S.Stock(S.SYMBOL, "SMART", "USD")
    probe.ib.qualifyContracts(spy)
    b = probe.ib.reqHistoricalData(spy, "", S.BARS_DURATION, "1 min", "TRADES",
                                   useRTH=True, keepUpToDate=True)
    n = len(b) if b else 0
    check(n >= 200, f"'{S.BARS_DURATION}' -> {n} barras (>=200 necesarias para la SMA200)")
    if n:
        print(f"      de {b[0].date} a {b[-1].date}")
        df = pd.DataFrame([{"high": x.high, "low": x.low, "close": x.close,
                            "volume": x.volume, "date": x.date} for x in b])
        vr = ta.compute(df)
        check(vr["sma200"] is not None,
              f"SMA200 REAL calculada con datos de IBKR -> {vr['sma200']:.4f}")
        check(vr["sma20"] is not None and vr["sma50"] is not None,
              f"SMA20={vr['sma20']:.4f} SMA50={vr['sma50']:.4f}")
        probe.ib.cancelHistoricalData(b)
except Exception as e:
    check(False, f"error contra IBKR: {type(e).__name__}: {e}")
finally:
    try:
        probe.ib.disconnect()
    except Exception:
        pass

print()
print("=" * 78)
print(("TODO VERDE" if not FAILS else f"{len(FAILS)} FALLOS: " + " | ".join(FAILS)))
print("=" * 78)
sys.exit(1 if FAILS else 0)
