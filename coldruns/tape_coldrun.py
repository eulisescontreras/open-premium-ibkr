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

# ============================================================ 9  (2026-08-12)
print()
print("=" * 78)
print("9) LA BANDA ENTRA EN EL TAPE")
print("=" * 78)
# POR QUE: hasta el 2026-08-12 `_on_ticks` descartaba todo lo que no fuera SENAL o BASELINE,
# asi que el tape veia 290.319 de 1.916.463 contratos del 0DTE (15,1%) y 32 de 40 strikes
# quedaban a CERO operaciones. La direccion (net_call/net_put -> M1) se decidia sobre 2 strikes
# rotatorios que no son donde esta el volumen.
# Lo que hay que demostrar aqui:
#   9.1 una operacion de la BANDA deja su fila, etiquetada BANDA (no BASELINE).
#   9.2 la SENAL no cambia: solo `is_signal` toca net_call/net_put.
#   9.3 lo que no es senal/baseline/banda se SIGUE descartando (el filtro sigue filtrando).
#   9.4 no hay DOBLE CONTEO con la ruta de walls (seria el GAP 2 sobre 40 strikes).
#   9.5 CONTROL: si _on_ticks nunca cuenta un contrato, walls SI lo cuenta -> el dato no se
#       pierde en silencio. Este caso lo detecto la cold run diferencial: una exclusion
#       ESTATICA dejaba `prem_center` en '-' y el premium de la banda a cero.


class WTicker:
    """Ticker para compute_walls: necesita OI y greeks, que TK no trae."""
    def __init__(self, volume, last=1.0, bid=0.99, ask=1.00, right="C", oi=100.0, gamma=0.05):
        self.callOpenInterest = oi if right == "C" else float("nan")
        self.putOpenInterest = oi if right == "P" else float("nan")
        self.modelGreeks = type("G", (), {"gamma": gamma})()
        self.volume = volume
        self.last, self.bid, self.ask = last, bid, ask
        self.time = "2026-08-11 10:00:00"


class WIB:
    def __init__(self):
        self._tk = {}

    def isConnected(self):
        return True

    def ticker(self, c):
        return self._tk[c.conId]


EXPB = "20260811"
KEY = (EXPB, 776.0, "C")


def con_banda():
    a = nueva()
    a.expiry = EXPB
    a.spy_price = 772.0
    a.ib = WIB()
    a.band_contracts = [opt(776, "C", expiry=EXPB, conId=7761),
                        opt(770, "P", expiry=EXPB, conId=7702)]
    for c in a.band_contracts:
        a.ib._tk[c.conId] = WTicker(1000.0, right=c.right)
    return a


a9 = con_banda()
b9 = a9.band_contracts[0]
a9._on_ticks([TK(b9, 1.00, 1000, 0.99, 1.00)])                    # siembra prev_vol
a9._on_ticks([TK(b9, 0.80, 1500, 0.79, 0.80, lastSize=500)])
a9._flush_tape(forzar=True)
rs9 = a9.db.execute("SELECT strike,right,grupo,size FROM tape").fetchall()
check(len(rs9) == 1, f"9.1 una operacion de la BANDA deja su fila -> {len(rs9)}")
check(bool(rs9) and rs9[0][2] == "BANDA",
      f"9.1 etiquetada BANDA, no BASELINE -> {rs9[0][2] if rs9 else '-'}")
check(a9.net_call == 0.0 and a9.net_put == 0.0,
      f"9.2 la BANDA NO altera la senal -> net_call={a9.net_call} net_put={a9.net_put}")

a9b = con_banda()
x9 = opt(790, "C", expiry=EXPB, conId=7901)      # ni senal, ni baseline, ni banda
a9b._on_ticks([TK(x9, 1.00, 1000, 0.99, 1.00)])
a9b._on_ticks([TK(x9, 0.80, 1500, 0.79, 0.80, lastSize=500)])
a9b._flush_tape(forzar=True)
check(a9b.db.execute("SELECT COUNT(*) FROM tape").fetchone()[0] == 0,
      "9.3 un contrato ajeno a senal/baseline/banda SIGUE descartandose")

a94 = con_banda()
b94 = a94.band_contracts[0]
a94.compute_walls()                               # 1a: siembra band_prev_vol (prev None)
a94.ib._tk[b94.conId].volume = 1500.0             # el mismo volumen que vera _on_ticks
a94._on_ticks([TK(b94, 1.00, 1000, 0.99, 1.00)])
a94._on_ticks([TK(b94, 0.80, 1500, 0.79, 0.80, lastSize=500)])
p_tick = a94.today_prem.get(KEY, 0.0)
check(p_tick > 0, f"9.4 _on_ticks conto el premium de la banda -> {p_tick:,.0f}")
check(b94.conId in a94._tick_prem_ids, "9.4 y lo marco en _tick_prem_ids")
a94.compute_walls()                               # 2a: NO debe volver a sumarlo
check(abs(a94.today_prem.get(KEY, 0.0) - p_tick) < 1e-6,
      f"9.4 compute_walls NO lo vuelve a sumar (GAP 2) -> {a94.today_prem.get(KEY, 0.0):,.0f}")

a95 = con_banda()
b95 = a95.band_contracts[0]
a95.compute_walls()                               # siembra
a95.ib._tk[b95.conId].volume = 1500.0
a95.compute_walls()                               # sin _on_ticks de por medio
check(a95.today_prem.get(KEY, 0.0) > 0,
      f"9.5 CONTROL: sin _on_ticks, walls SIGUE contando (el dato no se pierde) -> "
      f"{a95.today_prem.get(KEY, 0.0):,.0f}")

# ============================================================ 9.6
# LA BANDA SE SUSCRIBE EN DOS SITIOS. Si uno pide 233 y el otro no, el tape se queda ciego
# EN SILENCIO en cuanto el precio deriva >3 strikes y `refresh_strikes` re-suscribe la banda.
# No hay error, no hay log: simplemente dejan de llegar `last`/`lastSize`.
# Ocurrio de verdad el 2026-08-12: se arreglo `setup_contracts` (:1259) y se dejo el espejo de
# `refresh_strikes` con la lista vieja. Esta prueba ejercita el re-centrado REAL.
print()
print("=" * 78)
print("9.6) LA BANDA SIGUE PIDIENDO RTVolume TRAS UN RE-CENTRADO")
print("=" * 78)


class IBRec:
    """FakeIB que APUNTA cada reqMktData con su lista de ticks genericos."""
    def __init__(self):
        self.subs = []          # [(strike, right, genericTickList)]
        self._n = 5000

    def qualifyContracts(self, *cs):
        for c in cs:
            if not getattr(c, "conId", None):
                self._n += 1
                c.conId = self._n
        return list(cs)

    def reqMktData(self, c, gen, *a, **k):
        self.subs.append((getattr(c, "strike", None), getattr(c, "right", None), gen))

    def cancelMktData(self, c):
        pass

    def isConnected(self):
        return True

    def ticker(self, c):
        return None


a96 = nueva()
a96.ib = IBRec()
a96.expiry = "20260811"
a96.strikes = [765.0 + i for i in range(21)]          # 765..785
# banda centrada en 770 y precio en 780 -> deriva > 3 strikes => obliga a re-centrar
a96.band_contracts = [opt(s, r, expiry="20260811", conId=int(s * 10 + (1 if r == "C" else 2)))
                      for s in (768.0, 769.0, 770.0, 771.0, 772.0) for r in ("C", "P")]
a96.spy_price = 780.0
a96.pos_qty = 0
a96.order = None
_ban_antes = sorted({c.strike for c in a96.band_contracts})
a96.refresh_strikes()                                  # <-- FUNCION REAL
_ban_despues = sorted({c.strike for c in a96.band_contracts})
check(_ban_antes != _ban_despues,
      f"9.6 el re-centrado REAL ocurrio: {_ban_antes[0]:g}-{_ban_antes[-1]:g} -> "
      f"{_ban_despues[0]:g}-{_ban_despues[-1]:g}")

_band_str = set(_ban_despues)
_subs_banda = [(s, r, g) for (s, r, g) in a96.ib.subs if s in _band_str and "100" in (g or "")]
check(len(_subs_banda) > 0, f"9.6 se re-suscribio la banda -> {len(_subs_banda)} contratos")
_sin_233 = [(s, r, g) for (s, r, g) in _subs_banda if "233" not in (g or "")]
check(not _sin_233,
      f"9.6 TODAS las suscripciones de la banda piden 233 -> "
      f"{len(_subs_banda) - len(_sin_233)}/{len(_subs_banda)}"
      + (f"  *** SIN 233: {_sin_233[:3]} ***" if _sin_233 else ""))

# ============================================================ 10: TAPE DEL SUBYACENTE
print()
print("=" * 78)
print("10) TAPE DEL SPY (2026-08-13): se captura el subyacente SIN tocar la señal")
print("=" * 78)


def stk(conId=756733):
    s = S.Stock(S.SYMBOL, "SMART", "USD")
    s.conId = conId
    return s


# 10.1 EL CHECK CLAVE: el SPY no puede contaminar NADA de la ruta de opciones.
S.TAPE_SPY = True
a10 = nueva()
sp = stk()
a10._on_ticks([TK(sp, 640.00, 1_000_000, 639.99, 640.00)])          # 1o: solo fija prev_vol
a10._on_ticks([TK(sp, 640.05, 1_005_000, 640.04, 640.05, lastSize=500)])
check(a10.net_call == 0.0 and a10.net_put == 0.0,
      "10.1 el SPY NO mueve la señal -> net_call=%s net_put=%s" % (a10.net_call, a10.net_put))
check(not a10.accum and not a10.today_prem and not a10.accum_net and not a10.today_net,
      "10.1 el SPY NO entra en los acumuladores de premium -> accum=%d today_prem=%d "
      "accum_net=%d today_net=%d"
      % (len(a10.accum), len(a10.today_prem), len(a10.accum_net), len(a10.today_net)))

# 10.2 pero SI deja su fila, con el formato correcto
a10._flush_tape(forzar=True)
rs = a10.db.execute("SELECT expiry,strike,right,last,size,dvol,agresor,premium,premium_dvol,"
                    "grupo FROM tape ORDER BY id").fetchall()
check(len(rs) == 1, "10.2 se registro 1 operacion del SPY -> %d" % len(rs))
if rs:
    r = rs[0]
    check(r[0] is None and r[1] is None and r[2] is None,
          "10.2 expiry/strike/right van NULL (una accion no los tiene) -> %s" % (r[:3],))
    check(r[9] == "SPY", "10.2 grupo='SPY' -> %s" % r[9])
    check(r[4] == 500.0 and r[5] == 5000.0,
          "10.2 size=%s (la operacion) y dvol=%s (el delta de volumen)" % (r[4], r[5]))
    check(r[6] == "COMPRA", "10.2 agresor por la MISMA regla que en opciones -> %s" % r[6])
    # EL x100 ES DE OPCIONES: en acciones el premium son dolares a secas
    check(abs(r[8] - 640.05 * 5000) < 1e-6,
          "10.2 premium SIN el x100 del multiplicador -> %s (esperado %.0f)"
          % (r[8], 640.05 * 5000))
    check(abs(r[7] - 640.05 * 500) < 1e-6,
          "10.2 premium de ESTA operacion = last*lastSize -> %s" % r[7])

# 10.3 REINICIO: con prev_vol vacio, el PRIMER tick no puede inventarse un dvol gigante.
#      tk.volume de IBKR es el ACUMULADO del dia: sin el guard entraria una operacion de
#      millones de acciones cada vez que se reinicia la app.
a103 = nueva()
a103._on_ticks([TK(stk(), 640.00, 12_000_000, 639.99, 640.00)])     # como tras un reinicio
a103._flush_tape(forzar=True)
n103 = a103.db.execute("SELECT COUNT(*) FROM tape WHERE grupo='SPY'").fetchone()[0]
check(n103 == 0,
      "10.3 tras un reinicio (prev_vol vacio) el 1er tick NO genera fila -> %d "
      "(si fuera 1, seria una operacion falsa de 12M de acciones)" % n103)

# 10.4 DIA NUEVO: el volumen de IBKR vuelve a 0 -> dvol negativo -> descartado
a104 = nueva()
a104._on_ticks([TK(stk(), 640.00, 12_000_000, 639.99, 640.00)])
a104._on_ticks([TK(stk(), 640.00, 5_000, 639.99, 640.00)])          # dia nuevo: contador a 0
a104._flush_tape(forzar=True)
n104 = a104.db.execute("SELECT COUNT(*) FROM tape WHERE grupo='SPY'").fetchone()[0]
check(n104 == 0, "10.4 dia nuevo (volumen reseteado) -> dvol<=0, no se registra -> %d" % n104)

# 10.5 INTERRUPTOR: con TAPE_SPY=False no se captura nada, y las opciones siguen igual
S.TAPE_SPY = False
a105 = nueva()
a105._on_ticks([TK(stk(), 640.00, 1_000_000, 639.99, 640.00)])
a105._on_ticks([TK(stk(), 640.05, 1_005_000, 640.04, 640.05, lastSize=500)])
c105 = opt(773, "C")
a105.call = c105
a105._on_ticks([TK(c105, 1.00, 1000, 0.99, 1.00)])
a105._on_ticks([TK(c105, 0.75, 1100, 0.74, 0.75, lastSize=100)])
a105._flush_tape(forzar=True)
_spy = a105.db.execute("SELECT COUNT(*) FROM tape WHERE grupo='SPY'").fetchone()[0]
_opt = a105.db.execute("SELECT COUNT(*) FROM tape WHERE grupo<>'SPY'").fetchone()[0]
check(_spy == 0, "10.5 con TAPE_SPY=False no se captura el subyacente -> %d" % _spy)
check(_opt == 1, "10.5 y las OPCIONES se siguen capturando igual -> %d" % _opt)
S.TAPE_SPY = True

# 10.6 la suscripcion del SPY pide 233: sin el, no llegan las operaciones (el bug de la banda)
_src = open(S.__file__, encoding="utf-8").read()
check('reqMktData(self.spy_stock, "233"' in _src,
      "10.6 el subyacente se suscribe con RTVolume(233), no con '' (mismo bug que la banda)")

print()
print("=" * 78)
print(("TODO VERDE" if not FAILS else f"{len(FAILS)} FALLOS: " + " | ".join(FAILS)))
print("=" * 78)
sys.exit(1 if FAILS else 0)
