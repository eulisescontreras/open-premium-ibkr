# -*- coding: utf-8 -*-
"""
COLD RUN GAP 15 - el REINICIO a media sesion borraba el acumulado del dia.

Detectado por el usuario 2026-08-10 11:50. Mecanismo verificado en codigo:
  sesion = {"fecha": None}                       <- variable local de run_gui
  try_connect(nuevo_dia=(sesion["fecha"] != hoy))
  if nuevo_dia: reset_day() -> net_call = net_put = 0
En un proceso NUEVO sesion["fecha"] siempre es None, asi que SIEMPRE se trata como dia
nuevo aunque sea un reinicio a media sesion.

Consecuencia real (log de las 11:50, umbral maduro previo ~138.000):
   thr = max(5000, 0.15 * 0) = 5000   <- el piso, 27 veces menor
   11:50:48 GIRO UP | 11:50:55 DOWN | 11:51:06 UP | 11:51:22 DOWN  = 4 giros en 34 s
Y en medio cerro una CALL que la senal madura habria mantenido, mientras el SPY subia.

Funciones REALES (_persist_accum, _load_accum, _load_intradia, reset_day), BD en fichero
temporal para que sobreviva entre "procesos" simulados.
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime

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


class FakeC:
    """Contrato minimo para los tests del GAP 16."""
    def __init__(self, strike, right, conId, expiry="20260810"):
        self.strike = strike
        self.right = right
        self.conId = conId
        self.symbol = "SPY"
        self.secType = "OPT"
        self.exchange = "SMART"
        self.localSymbol = "SPY %g%s" % (strike, right)
        self.lastTradeDateOrContractMonth = expiry


RUTA = os.path.join(tempfile.gettempdir(), "gap15_test.db")
if os.path.exists(RUTA):
    os.remove(RUTA)


def proceso():
    """Simula un ARRANQUE de la app: objeto nuevo sobre la MISMA base de datos."""
    a = S.SpyDirection(demo=True)
    a.db.close()
    a.db = sqlite3.connect(RUTA)
    a._init_db()
    a.demo = False
    return a


print("=" * 76)
print("COLD RUN GAP 15 - el reinicio no debe borrar el acumulado del dia")
print("=" * 76)

print("\n== T1: sesion en marcha, se acumula flujo y se persiste ==")
a = proceso()
a.reset_day()                                  # arranque del dia: todo a 0
a._load_accum()                                # incluye _load_intradia
check(a.net_call == 0 and a.net_put == 0, "primer arranque del dia: senal en 0 (correcto)")
check(a._intradia_ok, "la bandera se activa: a partir de aqui SI se persiste")
a.net_call = 920000.0
a.net_put = -180000.0
a.pnl_realizado = -54.0
a.n_trades = 9
a.n_wins = 3
thr_maduro = max(S.SIGNAL_THRESHOLD, S.ADAPT_FRAC * (abs(a.net_call) + abs(a.net_put)))
print("     umbral con la senal madura: %.0f" % thr_maduro)
a._persist_accum()                             # metodo REAL

print("\n== T2: REINICIO a media sesion (proceso nuevo, misma BD) ==")
b = proceso()
b.reset_day()                                  # esto es lo que hace try_connect en un proceso nuevo
check(b.net_call == 0 and b.net_put == 0, "reset_day pone la senal a 0 (comportamiento actual)")
b._load_accum()                                # metodo REAL -> llama _load_intradia
check(abs(b.net_call - 920000.0) < 1e-6 and abs(b.net_put - (-180000.0)) < 1e-6,
      "RESTAURADO: netC=%.0f netP=%.0f (antes se perdian)" % (b.net_call, b.net_put))
thr_rest = max(S.SIGNAL_THRESHOLD, S.ADAPT_FRAC * (abs(b.net_call) + abs(b.net_put)))
check(abs(thr_rest - thr_maduro) < 1e-6,
      "el UMBRAL vuelve a su valor maduro %.0f (sin el arreglo seria %.0f, %.0fx mas sensible)"
      % (thr_rest, S.SIGNAL_THRESHOLD, thr_rest / S.SIGNAL_THRESHOLD))
check(b.pnl_realizado == -54.0 and b.n_trades == 9 and b.n_wins == 3,
      "contadores del panel restaurados: realizado %.2f, ops %d (%d ganadoras)"
      % (b.pnl_realizado, b.n_trades, b.n_wins))

print("\n== T3: el giro artificial YA NO se dispara ==")
# diff pequeno que con thr=5000 habria disparado un giro, y con el umbral maduro no
b.state = "UP"
b.net_call = 920000.0 + 30000.0
b.net_put = -180000.0
b._update_signal()                             # metodo REAL
check(b.state == "UP",
      "con umbral %.0f un diff de %.0f NO cambia el estado (sigue %s)"
      % (b.last_thr, b.last_diff, b.state))
c = proceso()
c.reset_day()
c._intradia_ok = True                          # simular SIN restaurar (comportamiento viejo)
c.state = "UP"
c.net_call = 30000.0
c.net_put = 0.0
c._update_signal()
check(c.state == "UP" or c.last_thr == S.SIGNAL_THRESHOLD,
      "sin restaurar, el umbral es el piso %.0f -> cualquier ruido cruza" % c.last_thr)

print("\n== T4: DIA NUEVO -> no debe restaurar nada ==")
d = proceso()
d.db.execute("UPDATE estado_intradia SET fecha='2020-01-01'")
d.db.commit()
d.reset_day()
d._load_accum()
check(d.net_call == 0 and d.net_put == 0,
      "con el estado guardado de otra fecha, arranca en 0 (netC=%.0f netP=%.0f)"
      % (d.net_call, d.net_put))

print("\n== T5: GUARDA - si setup falla antes de restaurar, NO se escriben ceros ==")
e = proceso()
e.db.execute("DELETE FROM estado_intradia")
e.db.execute("INSERT INTO estado_intradia(fecha,hora,net_call,net_put,pnl_realizado,"
             "n_trades,n_wins) VALUES(?,?,?,?,?,?,?)",
             (datetime.now().strftime("%Y-%m-%d"), "12:00:00", 500000.0, -100000.0, -10.0, 5, 2))
e.db.commit()
e.reset_day()                                  # setup_contracts fallo -> _load_accum NUNCA corrio
check(not e._intradia_ok, "la bandera sigue en False (no se intento restaurar)")
e._persist_accum()                             # metodo REAL: no debe pisar el estado bueno
r = e.db.execute("SELECT net_call,net_put FROM estado_intradia").fetchone()
check(abs(r[0] - 500000.0) < 1e-6 and abs(r[1] - (-100000.0)) < 1e-6,
      "el estado guardado SOBREVIVE (%.0f/%.0f) - no se sobrescribio con ceros" % r)

print("\n== T6: ciclo completo guardar -> reiniciar -> seguir acumulando ==")
f = proceso()
f.reset_day(); f._load_accum()
base_c, base_p = f.net_call, f.net_put
f.net_call += 50000.0
f._persist_accum()
g = proceso()
g.reset_day(); g._load_accum()
check(abs(g.net_call - (base_c + 50000.0)) < 1e-6,
      "tras 2 reinicios el acumulado sigue creciendo correctamente (%.0f)" % g.net_call)

# ================================================================ GAP 16
print("\n" + "=" * 76)
print("GAP 16 - restauracion COMPLETA: la pantalla debe quedar como estaba")
print("=" * 76)

HOY = datetime.now().strftime("%Y-%m-%d")


class IBcuenta:
    def __init__(self, net):
        self.net = net
    def accountSummary(self):
        class R:
            def __init__(s, t, v):
                s.tag = t; s.value = v; s.currency = "USD"
        return [R("NetLiquidation", str(self.net)), R("AvailableFunds", str(self.net))]


print("\n== T7: acct_net_open sobrevive -> el DIA +/- se mide desde la APERTURA ==")
h = proceso()
h.reset_day(); h._load_accum()
h.ib = IBcuenta(400.0)
h._read_account()                                   # 1a lectura del dia: fija la base
h.ib = IBcuenta(360.0)                              # la cuenta baja durante el dia
h._read_account()
antes = h.resumen_cuenta()                          # metodo REAL
print("     antes del reinicio -> %s" % antes)
h._persist_accum()
i = proceso()
i.reset_day(); i._load_accum()
i.ib = IBcuenta(360.0)
i._read_account()
despues = i.resumen_cuenta()
print("     tras el reinicio   -> %s" % despues)
check(abs((i.acct_net_open or 0) - 400.0) < 1e-6,
      "T7 base del dia restaurada: %.2f (sin el arreglo seria 360.00)" % (i.acct_net_open or 0))
check("-40.00" in despues and "-10.0%" in despues,
      "T7 el DIA sigue midiendo desde la apertura (-40.00, -10.0%)")

print("\n== T8/T9: estado UP/DOWN restaurado y SIN alertas espurias ==")
j = proceso()
j.reset_day(); j._load_accum()
j.state = "UP"
j.net_call = 900000.0; j.net_put = -100000.0
j._intradia_ok = True
j._persist_accum()
k = proceso()
k.reset_day()
check(k.state == "-", "tras reset_day el estado arranca en '-'")
k._load_accum()
check(k.state == "UP", "T8 estado restaurado a UP (antes arrancaba en '-')")
# ACTUALIZADO 2026-08-10 (GAP 5): antes se comprobaba `diff_hist == []`. Esa lista contaba
# EVENTOS y se elimino al pasar el momentum a medirse por TIEMPO; la historia con sello de
# tiempo es ahora flow_hist. Lo que se verifica es lo mismo de siempre: tras restaurar el
# estado NO hay historia de flujo, asi que el momentum vale 0 y no se dispara alerta espuria.
check(k.flow_hist == [], "T9 flow_hist queda VACIO a proposito (momentum neutro)")
alertas_antes = k.alert_text
k._update_signal()                                  # metodo REAL
check(k.alert_kind != "FLIP" or k.state == "UP",
      "T9 no se dispara un giro espurio en el primer tick (estado=%s alerta='%s')"
      % (k.state, k.alert_kind))

print("\n== T10/T11: today_prem, net_prem y today_vol repuestos ==")
m = proceso()
m.reset_day(); m._load_accum()
m.expiry = "20260810"
m.spy_price = 774.0
k1 = ("20260810", 774.0, "C")
k2 = ("20260810", 773.0, "P")
m.today_prem = {k1: 250000.0, k2: 180000.0}
m.net_prem = {k1: 90000.0}
m.today_vol = {k1: 4200.0}
m.accum = {k1: 900000.0}
m.walls = {"put_wall": 772.0, "call_wall": 776.0, "max_pain_static": 773.0,
           "max_pain_dyn": 774.0, "prem_center": 774.1, "spot": 774.0}
m.gex = {"gex_total": 2.0e11, "regime": "LONG", "gamma_flip": 772.9}
m.band_contracts = [FakeC(774.0, "C", 1), FakeC(773.0, "P", 2)]
m._persist_accum()
m._persist_walls({774.0: 5000.0}, {773.0: 4000.0}, {774.0: 0.12}, {773.0: 0.11})
n = proceso()
n.reset_day()
check(n.today_prem == {}, "tras reset_day, today_prem vacio (Ladder en blanco)")
n._load_accum()
check(n.today_prem.get(k1) == 250000.0 and n.today_prem.get(k2) == 180000.0,
      "T10 today_prem repuesto (%d strikes) -> la Ladder sale poblada" % len(n.today_prem))
n.expiry = "20260810"
n.spy_price = 774.0
n.band_contracts = [FakeC(774.0, "C", 1), FakeC(773.0, "P", 2)]
lr = n.ladder_rows()                                # metodo REAL
check(lr["max_prem"] > 0, "T10 ladder_rows devuelve barras de inmediato (max_prem=%.0f)"
      % lr["max_prem"])
check(n.net_prem.get(k1) == 90000.0, "T11 net_prem repuesto (%s)" % n.net_prem.get(k1))
check(n.today_vol.get(k1) == 4200.0, "T11 today_vol repuesto (%s) -> magneto dinamico vivo"
      % n.today_vol.get(k1))

print("\n== T12: lista de giros repoblada desde la BD ==")
p = proceso()
p.reset_day(); p._load_accum()
for est in ("UP", "DOWN", "UP"):
    p.state = est
    p._save(est, "FLIP")                            # metodo REAL
q = proceso()
q.reset_day()
check(q.transitions == [], "tras reset_day la lista esta vacia")
q._load_accum()
check(len(q.transitions) == 3, "T12 %d giros repoblados desde transitions" % len(q.transitions))

print("\n== T13/T14 (CRITICO): lo que NO se debe restaurar sigue VACIO ==")
r2 = proceso()
r2.reset_day(); r2._load_accum()
check(r2.prev_vol == {}, "T13 prev_vol VACIO (si se restaurara -> premium fantasma)")
check(r2.band_prev_vol == {}, "T13 band_prev_vol VACIO")
check(r2.buys_pend == 0, "T13 buys_pend en 0 (las ordenes del proceso muerto no existen)")
check(r2.last_buy_ts == 0.0, "T13 last_buy_ts en 0")
# premium fantasma: primera lectura con volumen alto solo debe fijar la base
r2.expiry = "20260810"
r2.call = FakeC(774.0, "C", 55)
r2.put = FakeC(773.0, "P", 56)
prem_antes = r2.today_prem.get(("20260810", 774.0, "C"), 0.0)


class Tk2:
    def __init__(self, c, vol, last):
        self.contract = c; self.volume = vol; self.last = last
        self.bid = last - 0.02; self.ask = last + 0.02


r2._on_ticks([Tk2(r2.call, 250000.0, 1.10)])        # metodo REAL, volumen ENORME
prem_desp = r2.today_prem.get(("20260810", 774.0, "C"), 0.0)
check(abs(prem_desp - prem_antes) < 1e-6,
      "T14 sin premium fantasma: la 1a lectura solo fija la base (%.0f -> %.0f)"
      % (prem_antes, prem_desp))

print("\n== T15: DIA NUEVO -> no se restaura NADA, ni la base de cuenta ==")
s2 = proceso()
s2.db.execute("UPDATE estado_intradia SET fecha='2020-01-01'")
s2.db.execute("UPDATE strike_daily SET fecha='2020-01-01'")
s2.db.execute("UPDATE premium_minute SET fecha='2020-01-01'")
s2.db.execute("UPDATE transitions SET fecha='2020-01-01'")
s2.db.commit()
s2.reset_day(); s2._load_accum()
check(s2.net_call == 0 and s2.acct_net_open is None and s2.state == "-"
      and s2.today_prem == {} and s2.transitions == [],
      "T15 dia nuevo: todo limpio (netC=%.0f base=%s estado=%s prem=%d giros=%d)"
      % (s2.net_call, s2.acct_net_open, s2.state, len(s2.today_prem), len(s2.transitions)))

try:
    os.remove(RUTA)
except Exception:
    pass

print()
if FAILS:
    print("GAP 15 NO CERRADO: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("GAP 15 CERRADO: todos los checks pasaron")
sys.exit(0)
