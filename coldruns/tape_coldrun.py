# -*- coding: utf-8 -*-
"""COLD RUN del TAPE: una fila por operacion (2026-08-11, peticion del usuario).

POR QUE EXISTE: el flujo se agregaba al minuto, asi que un print institucional de 3.038
contratos y 50 operaciones de retail de 60 quedaban IDENTICOS (mismo dvol, mismo premium). Y
cualquier señal mas rapida que 1 minuto se promediaba hasta borrarla: el resultado "lag 0" del
10-ago es compatible tanto con "no anticipa" como con "anticipa 30 segundos".

tk.lastSize SI trae el tamaño de la operacion. Verificado en vivo contra IBKR el 2026-08-11:
    last=0.9  lastSize=2.0  volume=153529  rtVolume=153559

LO QUE HAY QUE DEMOSTRAR:
  1. Cada operacion deja su fila, con su TAMAÑO.
  2. Un print grande y muchos pequeños con el MISMO dvol total quedan DISTINGUIBLES  <-- el punto
  3. El agresor (COMPRA/VENTA/MID) se clasifica igual que en la señal.
  4. La SEÑAL no cambia ni un decimal con el tape activado (es solo registro).
  5. El buffer vuelca por lotes y al cerrar sesion no se pierde nada.
  6. Si el tape falla, la señal sigue.
  7. TAPE_ENABLED=False lo desactiva por completo.
  8. Coste en tiempo de _on_ticks.
"""
import math
import sqlite3
import sys
import time

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


class TK:
    """Ticker: lo que llega en pendingTickersEvent."""
    def __init__(self, contract, last, volume, bid, ask, lastSize=None):
        self.contract, self.last, self.volume = contract, last, volume
        self.bid, self.ask, self.lastSize = bid, ask, lastSize


def opt(strike, right, expiry="20260811", conId=None):
    o = S.Option(S.SYMBOL, expiry, strike, right, "SMART", tradingClass=S.SYMBOL)
    o.conId = conId or int(strike * 10 + (1 if right == "C" else 2))
    return o


def nueva(tape=True):
    S.TAPE_ENABLED = tape
    a = S.SpyDirection(demo=True)
    a.demo = False
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.call, a.put = opt(773, "C"), opt(773, "P")
    a.info_base = {}
    a._update_signal = lambda: None      # aislar: la señal se comprueba por net_call/net_put
    a.accum = {}
    a.today_prem = {}
    a.accum_net = {}
    a.today_net = {}
    a.prev_vol = {}
    a.net_call = a.net_put = 0.0
    a._tape_buf = []
    a._tape_n = 0
    return a


# ============================================================ 1
print("=" * 78)
print("1) Cada operacion deja su fila CON SU TAMAÑO")
print("=" * 78)
app = nueva()
c = app.call
app._on_ticks([TK(c, 1.00, 1000, 0.99, 1.00)])          # 1a: solo fija prev_vol
app._on_ticks([TK(c, 0.75, 4038, 0.74, 0.75, lastSize=3038)])   # print de 3.038 al ASK
app._flush_tape(forzar=True)
rs = app.db.execute("SELECT strike,right,last,size,dvol,bid,ask,agresor,premium,premium_dvol,"
                    "grupo FROM tape").fetchall()
check(len(rs) == 1, f"se registro 1 operacion -> {len(rs)}")
if rs:
    r = rs[0]
    check(r[3] == 3038.0, f"TAMAÑO de la operacion guardado -> size={r[3]}")
    check(r[4] == 3038.0, f"dvol del mismo tick -> {r[4]}")
    check(r[7] == "COMPRA", f"agresor (last>=ask) -> {r[7]}")
    check(abs(r[8] - 0.75 * 3038 * 100) < 1e-6,
          f"premium de ESTA operacion = last*size*100 -> {r[8]:,.0f}")
    check(r[10] == "SENAL", f"grupo -> {r[10]}")

# ============================================================ 2  (EL PUNTO)
print()
print("=" * 78)
print("2) EL PUNTO: mismo dvol total, un print grande vs muchos pequeños -> DISTINGUIBLES")
print("=" * 78)
# caso A: UN print de 3.000
a1 = nueva()
a1._on_ticks([TK(a1.call, 1.00, 1000, 0.99, 1.00)])
a1._on_ticks([TK(a1.call, 0.75, 4000, 0.74, 0.75, lastSize=3000)])
a1._flush_tape(forzar=True)
# caso B: 50 operaciones de 60 (mismo total: 3.000)
a2 = nueva()
a2._on_ticks([TK(a2.call, 1.00, 1000, 0.99, 1.00)])
v = 1000
for _ in range(50):
    v += 60
    a2._on_ticks([TK(a2.call, 0.75, v, 0.74, 0.75, lastSize=60)])
a2._flush_tape(forzar=True)

g1 = a1.db.execute("SELECT COUNT(*), SUM(dvol), MAX(size), ROUND(AVG(size),1) FROM tape").fetchone()
g2 = a2.db.execute("SELECT COUNT(*), SUM(dvol), MAX(size), ROUND(AVG(size),1) FROM tape").fetchone()
print(f"     A (1 print grande): filas={g1[0]:>2}  dvol_total={g1[1]:.0f}  size_max={g1[2]:.0f}  size_medio={g1[3]}")
print(f"     B (50 pequeñas)   : filas={g2[0]:>2}  dvol_total={g2[1]:.0f}  size_max={g2[2]:.0f}  size_medio={g2[3]}")
check(g1[1] == g2[1], f"el VOLUMEN TOTAL es el mismo en ambos ({g1[1]:.0f}) -> antes eran indistinguibles")
check(g1[2] != g2[2], f"pero el TAMAÑO MAXIMO los separa: {g1[2]:.0f} vs {g2[2]:.0f}  <-- ESTO ES LO NUEVO")
check(g1[0] != g2[0], f"y el numero de operaciones: {g1[0]} vs {g2[0]}")
# el premium agregado tambien coincide: la senal no puede distinguirlos
p1 = a1.db.execute("SELECT SUM(premium_dvol) FROM tape").fetchone()[0]
p2 = a2.db.execute("SELECT SUM(premium_dvol) FROM tape").fetchone()[0]
check(abs(p1 - p2) < 1e-6,
      f"el premium que ve la SEÑAL es identico en ambos ({p1:,.0f}) -> por eso hacia falta el tape")

# ============================================================ 3
print()
print("=" * 78)
print("3) Agresor: mismo criterio que la señal")
print("=" * 78)
a3 = nueva()
a3._on_ticks([TK(a3.call, 1.00, 1000, 0.99, 1.00)])
a3._on_ticks([TK(a3.call, 1.10, 1100, 1.05, 1.10, lastSize=100)])   # last>=ask -> COMPRA
a3._on_ticks([TK(a3.call, 1.05, 1200, 1.05, 1.09, lastSize=100)])   # last<=bid -> VENTA
a3._on_ticks([TK(a3.call, 1.07, 1300, 1.05, 1.09, lastSize=100)])   # dentro    -> MID
a3._flush_tape(forzar=True)
ags = [r[0] for r in a3.db.execute("SELECT agresor FROM tape ORDER BY id")]
check(ags == ["COMPRA", "VENTA", "MID"], f"COMPRA/VENTA/MID -> {ags}")

# ============================================================ 4
print()
print("=" * 78)
print("4) La SEÑAL no cambia con el tape activado")
print("=" * 78)
SEC = [(1.00, 1000, 0.99, 1.00, None), (1.10, 1100, 1.05, 1.10, 100),
       (1.05, 1200, 1.05, 1.09, 40), (1.20, 1500, 1.15, 1.20, 300)]
res = {}
for tape in (True, False):
    ap = nueva(tape=tape)
    for last, vol, bid, ask, ls in SEC:
        ap._on_ticks([TK(ap.call, last, vol, bid, ask, lastSize=ls)])
    res[tape] = (ap.net_call, ap.net_put,
                 ap.accum.get(("20260811", 773.0, "C"), 0.0),
                 ap.accum_net.get(("20260811", 773.0, "C"), 0.0))
check(res[True] == res[False],
      f"net_call/net_put/accum/accum_net IDENTICOS con y sin tape -> {res[True]}")

# ============================================================ 5
print()
print("=" * 78)
print("5) Volcado por lotes y cierre de sesion")
print("=" * 78)
a5 = nueva()
a5._on_ticks([TK(a5.call, 1.00, 1000, 0.99, 1.00)])
v = 1000
for i in range(S.TAPE_FLUSH_N + 20):
    v += 10
    a5._on_ticks([TK(a5.call, 1.00, v, 0.99, 1.00, lastSize=10)])
n_bd = a5.db.execute("SELECT COUNT(*) FROM tape").fetchone()[0]
check(n_bd >= S.TAPE_FLUSH_N,
      f"al pasar de TAPE_FLUSH_N={S.TAPE_FLUSH_N} volco solo -> {n_bd} en BD, "
      f"{len(a5._tape_buf)} en buffer")
check(len(a5._tape_buf) > 0, "y queda un resto pendiente en el buffer")
pend = len(a5._tape_buf)
a5._flush_tape(forzar=True)
n2 = a5.db.execute("SELECT COUNT(*) FROM tape").fetchone()[0]
check(n2 == n_bd + pend and not a5._tape_buf,
      f"forzar=True vuelca el resto -> {n2} filas, buffer vacio")

# ============================================================ 6
print()
print("=" * 78)
print("6) Si el TAPE falla, la señal SIGUE")
print("=" * 78)
a6 = nueva()
a6._on_ticks([TK(a6.call, 1.00, 1000, 0.99, 1.00)])
a6.db.close()          # romper la BD a proposito
try:
    a6._on_ticks([TK(a6.call, 1.10, 1100, 1.05, 1.10, lastSize=100)])
    a6._flush_tape(forzar=True)
    vivo = True
except Exception as e:
    vivo = False
    print("      excepcion:", type(e).__name__, e)
check(vivo, "con la BD rota, _on_ticks y _flush_tape NO propagan excepcion")
check(a6.net_call > 0, f"y la señal se siguio actualizando -> net_call={a6.net_call:,.0f}")

# ============================================================ 7
print()
print("=" * 78)
print("7) TAPE_ENABLED=False desactiva la escritura")
print("=" * 78)
a7 = nueva(tape=False)
a7._on_ticks([TK(a7.call, 1.00, 1000, 0.99, 1.00)])
a7._on_ticks([TK(a7.call, 1.10, 1100, 1.05, 1.10, lastSize=100)])
a7._flush_tape(forzar=True)
check(a7.db.execute("SELECT COUNT(*) FROM tape").fetchone()[0] == 0,
      "con TAPE_ENABLED=False no se escribe ni una fila")
check(a7.net_call > 0, f"pero la señal funciona igual -> net_call={a7.net_call:,.0f}")
S.TAPE_ENABLED = True

# ============================================================ 8
print()
print("=" * 78)
print("8) Coste en tiempo de _on_ticks")
print("=" * 78)
for tape in (False, True):
    ap = nueva(tape=tape)
    ap._on_ticks([TK(ap.call, 1.00, 1000, 0.99, 1.00)])
    v = 1000
    t0 = time.perf_counter()
    for i in range(2000):
        v += 10
        ap._on_ticks([TK(ap.call, 1.00, v, 0.99, 1.00, lastSize=10)])
    ap._flush_tape(forzar=True)
    us = (time.perf_counter() - t0) / 2000 * 1e6
    print(f"     tape={'ON ' if tape else 'OFF'} -> {us:8.1f} us por tick")
    if tape:
        check(us < 300, f"con tape: {us:.1f} us/tick (2000 ticks)")
S.TAPE_ENABLED = True

print()
print("=" * 78)
print(("TODO VERDE" if not FAILS else f"{len(FAILS)} FALLOS: " + " | ".join(FAILS)))
print("=" * 78)
sys.exit(1 if FAILS else 0)
