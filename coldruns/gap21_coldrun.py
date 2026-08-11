# -*- coding: utf-8 -*-
"""COLD RUN del GAP 21 (2026-08-11): el premium por minuto debe guardarse AUNQUE no haya TA.

Problema REAL medido hoy en vivo: a las 09:56 `ta_minute` tenia 2 filas mientras `_on_ticks`
llevaba acumulando desde las 09:30 (el acumulado ya valia -2,6 M). El premium por vela y las
ventanas moviles viven en `ta_minute`, y esa tabla no se escribia hasta tener 26 barras de TA
(09:30 + 26 = 09:56). Se perdia el flujo por minuto de la media hora MAS activa del dia, tanto
en la BD como en el log.

Se ejercitan las FUNCIONES REALES `_log_minute` y `ta_poll`.
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

# capturar lo que se ESCRIBE en el log (el usuario lo quiere en BD *y* en logs)
LINEAS = []


class Captura(_lg.Handler):
    def emit(self, record):
        # getMessage() YA aplica record.args. Volver a hacer "% record.args" revienta con los
        # '%' literales del propio mensaje (p.ej. "atr=0.32(0.04%)") y acabaria guardando el
        # texto SIN formatear -> el test daria un falso FAIL. Solo getMessage().
        LINEAS.append(record.getMessage())


for _l in (S.ACT, S.LOG):
    _l.handlers = []
S.ACT.addHandler(Captura())
S.LOG.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def nueva():
    a = S.SpyDirection(demo=True)
    a.demo = False
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.spy_price = 773.50
    a.expiry = "20260811"
    a.state = "UP"
    a.net_call, a.net_put = 150000.0, 40000.0
    a.last_diff, a.last_thr, a.last_momentum = 110000.0, 22000.0, 5000.0
    # premium REAL acumulado por strike (lo que _on_ticks habria dejado)
    a.accum = {("20260811", 773.0, "C"): 900000.0, ("20260811", 773.0, "P"): 400000.0}
    a.today_prem = {("20260811", 773.0, "C"): 500000.0, ("20260811", 773.0, "P"): 220000.0}
    a.today_net = {("20260811", 773.0, "C"): 120000.0, ("20260811", 773.0, "P"): -30000.0}
    a.accum_net = dict(a.today_net)
    a.net_prem = {}
    return a


# =============================================================== 1
print("=" * 78)
print("1) _log_minute SIN TA (vals=None): debe guardar el PREMIUM, no salirse")
print("=" * 78)
app = nueva()
LINEAS.clear()
app._log_minute(None, "2026-08-11 09:35:00")          # <-- FUNCION REAL, sin TA

ta = app.db.execute("SELECT * FROM ta_minute WHERE hora='09:35'").fetchone()
check(ta is not None, "SE ESCRIBE la fila en ta_minute sin TA  <-- ESTO ES EL GAP 21")
if ta:
    cols = [d[0] for d in app.db.execute("SELECT * FROM ta_minute WHERE hora='09:35'").description]
    f = dict(zip(cols, ta))
    check(f["spy"] == 773.50, f"spy guardado desde self.spy_price -> {f['spy']}")
    check(f["net_call"] == 150000.0 and f["net_put"] == 40000.0,
          f"acumulado de senal guardado -> netC={f['net_call']} netP={f['net_put']}")
    check(f["diff"] == 110000.0 and f["thr"] == 22000.0,
          f"diff/thr guardados -> {f['diff']}/{f['thr']}")
    check(f["prem_state"] == "UP", f"estado guardado -> {f['prem_state']}")
    check(f["rsi"] is None and f["ema8"] is None and f["macd_line"] is None,
          "las columnas de TA quedan en NULL (la verdad, no un 0 inventado)")
n = app.db.execute("SELECT COUNT(*) FROM premium_minute WHERE hora='09:35'").fetchone()[0]
check(n == 2, f"premium_minute recibe sus filas por strike -> {n}")
r = app.db.execute("SELECT cum_prem,day_prem FROM premium_minute "
                   "WHERE hora='09:35' AND strike=773 AND right='C'").fetchone()
check(r == (900000.0, 500000.0), f"valores correctos del strike 773C -> {r}")

print()
print("  -- y en el LOG (el usuario lo quiere en BD *y* en logs) --")
hay_min = [l for l in LINEAS if l.startswith("MIN 09:35")]
check(len(hay_min) >= 3, f"se escriben lineas MIN en el log sin TA -> {len(hay_min)}")
check(any("TA todavia sin 26 barras" in l for l in hay_min),
      "el log DICE por que faltan los indicadores (no parece que este caido)")
check(any("VELA" in l for l in hay_min), "el log trae el premium DE LA VELA")
check(any("VENTANAS" in l for l in hay_min), "el log trae las ventanas moviles")
check(any("PREM 20260811 773C" in l for l in hay_min),
      "el log trae el premium POR STRIKE")
check(not any("TA dir=" in l for l in hay_min),
      "no se imprime una linea de TA falsa")

# =============================================================== 2
print()
print("=" * 78)
print("2) _log_minute CON TA: sigue funcionando EXACTAMENTE igual que antes")
print("=" * 78)
app2 = nueva()
LINEAS.clear()
vals = {"close": 774.10, "rsi": 55.5, "ema8": 773.9, "ema21": 773.5, "ema50": 773.1,
        "macd_line": 0.12, "macd_signal": 0.10, "macd_hist": 0.02, "bb_up": 774.9,
        "bb_mid": 773.8, "bb_low": 772.7, "atr": 0.31, "atr_pct": 0.04, "vwap": 773.7,
        "obv_trend": "bullish", "score": 2, "dir": "BULL"}
app2._log_minute(vals, "2026-08-11 10:20:00")
cols = [d[0] for d in app2.db.execute("SELECT * FROM ta_minute WHERE hora='10:20'").description]
f2 = dict(zip(cols, app2.db.execute("SELECT * FROM ta_minute WHERE hora='10:20'").fetchone()))
check(f2["spy"] == 774.10, f"spy del TA (no self.spy_price) -> {f2['spy']}")
check(f2["rsi"] == 55.5 and f2["ema8"] == 773.9 and f2["ta_dir"] == "BULL",
      f"TA completo guardado -> rsi={f2['rsi']} ema8={f2['ema8']} dir={f2['ta_dir']}")
check(any("TA dir=BULL" in l for l in LINEAS if l.startswith("MIN 10:20")),
      "el log imprime la linea de TA como siempre")

# =============================================================== 3
print()
print("=" * 78)
print("3) ta_poll REAL con MENOS de 26 barras: dispara el registro al cerrar un minuto")
print("=" * 78)


class FakeBar:
    def __init__(self, d, c):
        self.date, self.close, self.high, self.low, self.volume = d, c, c + .1, c - .1, 100


app3 = nueva()
app3.bars = [FakeBar("2026-08-11 09:31:00", 773.2), FakeBar("2026-08-11 09:32:00", 773.4)]
app3.last_bar_time = None
app3.ta_poll()                                   # <-- FUNCION REAL
check(app3.last_bar_time == "2026-08-11 09:32:00",
      f"1a pasada: solo toma referencia, no escribe -> last_bar_time={app3.last_bar_time}")
check(app3.db.execute("SELECT COUNT(*) FROM ta_minute").fetchone()[0] == 0,
      "1a pasada: no escribe (no hay minuto cerrado todavia)")
check(app3.spy_price == 773.4, f"el precio SI se actualiza sin TA -> {app3.spy_price}")

app3.bars.append(FakeBar("2026-08-11 09:33:00", 773.9))
app3.ta_poll()
filas = app3.db.execute("SELECT hora,spy,rsi,net_call FROM ta_minute").fetchall()
check(len(filas) == 1, f"2a pasada: se cerro un minuto -> se registra ({len(filas)} fila)")
if filas:
    check(filas[0][0] == "09:32", f"registra la barra YA CERRADA (09:32) -> {filas[0][0]}")
    check(filas[0][2] is None, "sin TA -> rsi NULL")
    check(filas[0][3] == 150000.0, f"pero CON el premium acumulado -> netC={filas[0][3]}")
check(app3.db.execute("SELECT COUNT(*) FROM premium_minute").fetchone()[0] == 2,
      "y con el premium por strike en premium_minute")

# =============================================================== 4
print()
print("=" * 78)
print("4) al llegar a 26 barras el TA entra sin perder el minuto de transicion")
print("=" * 78)
app4 = nueva()
app4.bars = [FakeBar("2026-08-11 09:%02d:00" % (31 + i), 773 + i * 0.01) for i in range(25)]
app4.last_bar_time = None
app4.ta_poll()
check(app4.last_bar_time is not None,
      f"con 25 barras ya hay referencia -> {app4.last_bar_time}")
n_antes = app4.db.execute("SELECT COUNT(*) FROM ta_minute").fetchone()[0]
app4.bars.append(FakeBar("2026-08-11 09:56:00", 773.5))     # la 26
app4.ta_poll()
n_desp = app4.db.execute("SELECT COUNT(*) FROM ta_minute").fetchone()[0]
check(n_desp > n_antes,
      f"al cruzar las 26 barras NO se pierde el minuto de transicion ({n_antes} -> {n_desp})")

print()
print("=" * 78)
print(("TODO VERDE" if not FAILS else f"{len(FAILS)} FALLOS: " + " | ".join(FAILS)))
print("=" * 78)
sys.exit(1 if FAILS else 0)
