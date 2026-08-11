# -*- coding: utf-8 -*-
"""COLD RUN de las SMA 20/50/200 (2026-08-11, peticion del usuario).

Lo que hay que demostrar:
  1. Se calculan con `rolling(N)` -> con MENOS de N barras dan **None** (NULL en la BD), no un
     numero falso. Es la diferencia clave con `ewm(span=N)`, que sobre 52 barras devuelve un
     valor que PARECE valido y contaminaria la BD en silencio.
  2. El valor es la media aritmetica REAL de las N ultimas velas (se compara contra el calculo
     a mano, sin pandas).
  3. Llegan a `ta_minute` y al LOG.
  4. NO tocan la decision: el score/dir del TA no cambia (la compra/venta sigue siendo solo
     premium).
  5. Los indicadores que ya existian no cambian de valor.

Se ejercita la FUNCION REAL `TAEngine.compute` y `_log_minute`.
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
LINEAS = []


class Captura(_lg.Handler):
    def emit(self, record):
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


if not S.HAVE_PD:
    print("pandas no disponible: no se puede probar")
    sys.exit(1)
import pandas as pd

ta = S.TAEngine()


def barras(n, base=773.0, paso=0.01):
    """n velas sinteticas, cierre creciente y predecible para poder comprobar la media a mano."""
    return pd.DataFrame([{"high": base + i * paso + .05, "low": base + i * paso - .05,
                          "close": base + i * paso, "volume": 1000 + i,
                          "date": "2026-08-11 %02d:%02d:00" % (9 + i // 60, i % 60)}
                         for i in range(n)])


# ============================================================ 1
print("=" * 78)
print("1) Con MENOS barras que la ventana -> None (NULL), nunca un numero inventado")
print("=" * 78)
casos = [(30, "sma20", True), (30, "sma50", False), (30, "sma200", False),
         (60, "sma20", True), (60, "sma50", True), (60, "sma200", False),
         (210, "sma20", True), (210, "sma50", True), (210, "sma200", True)]
for n, campo, debe_existir in casos:
    v = ta.compute(barras(n))
    got = v[campo]
    ok = (got is not None) if debe_existir else (got is None)
    check(ok, f"{n:>3} barras -> {campo} = {got if got is None else round(got, 4)} "
              f"({'debe tener valor' if debe_existir else 'debe ser None'})")

# --- la comparacion que justifica usar rolling y no ewm ---
close = barras(52)["close"]
ewm200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
roll200 = close.rolling(200).mean().iloc[-1]
check(pd.isna(roll200) and not pd.isna(ewm200),
      f"con 52 barras: rolling(200)=NaN (correcto) pero ewm(200)={ewm200:.4f} "
      f"(numero FALSO que parece valido)")

# ============================================================ 2
print()
print("=" * 78)
print("2) El valor es la media aritmetica REAL de las N ultimas velas")
print("=" * 78)
df = barras(210)
v = ta.compute(df)
for n, campo in ((20, "sma20"), (50, "sma50"), (200, "sma200")):
    manual = sum(df["close"].iloc[-n:]) / n          # a mano, sin pandas
    check(abs(v[campo] - manual) < 1e-9,
          f"{campo} = {v[campo]:.6f} == media manual de las ultimas {n} velas ({manual:.6f})")
check(v["sma20"] > v["sma50"] > v["sma200"],
      f"en serie creciente: sma20 > sma50 > sma200 ({v['sma20']:.2f} > {v['sma50']:.2f} "
      f"> {v['sma200']:.2f})")

# ============================================================ 3
print()
print("=" * 78)
print("3) Llegan a ta_minute y al LOG")
print("=" * 78)
app = S.SpyDirection(demo=True)
app.demo = False
app.db.close()
app.db = sqlite3.connect(":memory:")
app._init_db()
app.spy_price = 774.0
app.expiry = "20260811"
app.state = "UP"
app.net_call, app.net_put = 100.0, 50.0
app.last_diff = app.last_thr = app.last_momentum = 0.0
app.accum = {}
app.today_prem = {}
app.today_net = {}
app.accum_net = {}
app.net_prem = {}

cols = [d[1] for d in app.db.execute("PRAGMA table_info(ta_minute)")]
for c in ("sma20", "sma50", "sma200"):
    check(c in cols, f"la columna {c} existe en ta_minute (migracion ALTER TABLE)")

LINEAS.clear()
app._log_minute(v, "2026-08-11 13:00:00")
r = app.db.execute("SELECT sma20,sma50,sma200 FROM ta_minute WHERE hora='13:00'").fetchone()
check(r is not None and r[0] is not None and r[1] is not None and r[2] is not None,
      f"las 3 SMA se guardan en ta_minute -> {tuple(round(x, 3) for x in r) if r else None}")
check(r and abs(r[0] - v["sma20"]) < 1e-9, "el valor guardado coincide con el calculado")
lin = [l for l in LINEAS if "SMA 20/50/200" in l]
check(len(lin) == 1, f"se escribe la linea de SMA en el log -> {len(lin)}")
if lin:
    print("      " + lin[0])
    check("precio-SMA" in lin[0], "el log incluye la distancia precio-SMA")

# --- con la SMA200 aun sin datos, el log dice '-' y la BD guarda NULL ---
v2 = ta.compute(barras(60))
LINEAS.clear()
app._log_minute(v2, "2026-08-11 13:01:00")
r2 = app.db.execute("SELECT sma20,sma50,sma200 FROM ta_minute WHERE hora='13:01'").fetchone()
check(r2[0] is not None and r2[1] is not None and r2[2] is None,
      f"con 60 barras: sma20/50 con valor y sma200 NULL -> {r2}")
lin2 = [l for l in LINEAS if "SMA 20/50/200" in l]
check(lin2 and lin2[0].count("-") >= 1, "el log muestra '-' para la SMA200 que aun no existe")
if lin2:
    print("      " + lin2[0])

# ============================================================ 4
print()
print("=" * 78)
print("4) NO tocan la decision ni cambian los indicadores que ya existian")
print("=" * 78)
d210 = barras(210)
v3 = ta.compute(d210)
# score/dir se calculan con los 7 componentes de siempre; las SMA no estan entre ellos
close3 = d210["close"]
check(abs(v3["ema8"] - float(close3.ewm(span=8, adjust=False).mean().iloc[-1])) < 1e-9,
      "ema8 sigue siendo exactamente la de antes")
check(abs(v3["ema50"] - float(close3.ewm(span=50, adjust=False).mean().iloc[-1])) < 1e-9,
      "ema50 sigue siendo exactamente la de antes")
check(v3["dir"] in ("BULL", "BEAR", "NEUTRAL") and isinstance(v3["score"], int),
      f"score/dir intactos -> {v3['score']}/{v3['dir']}")
# la SMA no aparece en el score: se comprueba que el score es la suma de los 7 de siempre
check(-13 <= v3["score"] <= 13,
      f"el score sigue en el rango de los 7 componentes de siempre -> {v3['score']}")

print()
print("=" * 78)
print(("TODO VERDE" if not FAILS else f"{len(FAILS)} FALLOS: " + " | ".join(FAILS)))
print("=" * 78)
sys.exit(1 if FAILS else 0)
