# -*- coding: utf-8 -*-
"""COLD RUN: los 4 metodos ESCRIBEN EN EL LOG (2026-08-12, peticion del usuario).

POR QUE EXISTE: hasta hoy M1/M2/CLASICO/CONFIRMACION solo escribian en sus tablas y en
el panel de la GUI. `grep -c 'ACT.info' con m1|m2|clasico|confirma` daba **0**. Como M1
es el que DECIDE (USAR_M1=True), un fallo suyo era invisible en spy_activity.log y solo
se podia diagnosticar consultando la BD.

Y hay un modo de fallo que NO revienta: si una linea de `ACT.info` tiene mal el numero
de argumentos de formato, `logging` NO lanza — se traga la linea y sigue. Un cold run
que solo mire "no hay excepcion" daria verde con el log mudo. Por eso aqui se CAPTURA
la salida real del logger y se comprueba el TEXTO.

LO QUE HAY QUE DEMOSTRAR:
  1. `_log_minute` REAL emite la linea METODOS con los 4 estados.
  2. Emite la linea de contadores de M1.
  3. Ninguna de las dos sale con error de formato (logging lo registraria como error).
  4. Marca cual MANDA segun USAR_M1.
  5. Muestra el efectivo con retardo y el tamaño de m1_hist (lo que hay que mirar si M1
     no gira cuando deberia).
  6. La linea de GIRO dice POR QUE giro (antes imprimia `thr`, que con USAR_M1 no decide).
"""
import logging as _lg
import os
import sqlite3
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import spy_direction as S

# NO se importa m1m2_coldrun: ese script llama a sys.exit() al final y mataria este
# proceso antes de llegar a los checks. Las tablas se crean con el `_init_db` REAL de
# produccion, que ademas es mejor que duplicar el DDL en el test (regla 9).

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


class Captura(_lg.Handler):
    """Guarda el texto YA FORMATEADO. Si el formato esta mal, logging marca el record
    con exc_info y el mensaje no sale: por eso se captura `record.getMessage()`."""
    def __init__(self):
        super().__init__()
        self.lineas = []
        self.errores = 0

    def emit(self, record):
        try:
            self.lineas.append(record.getMessage())
        except Exception:
            self.errores += 1

    def handleError(self, record):
        self.errores += 1


cap = Captura()
S.ACT.handlers = [cap]
S.ACT.setLevel(_lg.DEBUG)
S.LOG.handlers = [_lg.NullHandler()]
S.ENABLE_TOAST = False

app = S.SpyDirection.__new__(S.SpyDirection)
fd, path = tempfile.mkstemp(suffix=".db")
os.close(fd)
app.db = sqlite3.connect(path)
S.SpyDirection._init_db(app)          # el REAL: crea las 4 tablas nuevas tambien
app.demo = True
app.m1_up = 0; app.m1_down = 0
app.m2_up = 0.0; app.m2_down = 0.0
app.m1_estado = None; app.m2_estado = None
app.m1_racha = 0; app.m2_racha = 0
app.m1_hist = []; app.m1_efectivo = None
app.m2_hist = []; app.m2_efectivo = None
app.cl_hist = []; app.cl_efectivo = None
app.cl_estado = None; app.cl_racha = 0
app.sen_estado = None; app.sen_racha = 0
app.conf_estado = None; app.conf_hist = []; app.conf_efectivo = None
app.m_recentrado = 0
app.state = "-"
app.transitions = []
app.last_warn_side = None
app.last_diff = 0.0; app.last_thr = 0.0; app.last_momentum = 0.0
app.flow_hist = []
app._intradia_ok = True
app.target = None
app.exit_reason = None
# lo que _log_minute necesita ademas de los contadores
app.accum = {}
app.today_prem = {}
app.today_net = {}
app.net_prem = {}
app.today_vol = {}
app.band_contracts = []
app.info_base = {}
app.call = None
app.put = None
app.pos = "FLAT"
app.pos_qty = 0
app.entry_price = None
app.trade_id = None
app._tape_buf = []
app._tape_n = 0
app._prem_snap = None
app.last_bar_time = None
app.spy_price = 773.0
app.acct_net = None
app.acct_avail = None
app.acct_net_open = None
app.pnl_realizado = 0.0
app.pnl_ibkr = None
app.pnl_ibkr_unreal = None
app.n_trades = 0
app.n_wins = 0
app.walls = None
app.gex = None

print("=" * 78)
print("1) `_log_minute` REAL emite las dos lineas nuevas")
print("=" * 78)
app.net_call, app.net_put = -75435.0, -244613.0
try:
    S.SpyDirection._log_minute(app, None, None)
    exploto = False
except Exception as e:
    exploto = True
    print("   EXCEPCION:", type(e).__name__, e)
check(not exploto, "_log_minute no lanza")

met = [l for l in cap.lineas if "METODOS" in l]
cnt = [l for l in cap.lineas if "M1 contadores" in l]
check(len(met) == 1, "sale UNA linea METODOS -> %d" % len(met))
check(len(cnt) == 1, "sale UNA linea de contadores de M1 -> %d" % len(cnt))
check(cap.errores == 0, "logging NO registro errores de formato -> %d" % cap.errores)

if met:
    L = met[0]
    print("   >> %s" % L[:150])
    check("M1=" in L and "M2=" in L and "CLASICO=" in L and "CONFIRMA=" in L,
          "la linea lleva los CUATRO metodos")
    check("efectivos(-%dmin)" % S.RETARDO_M1_MIN in L,
          "declara el retardo aplicado -> %d min" % S.RETARDO_M1_MIN)
    check(("MANDA M1" in L) == bool(S.USAR_M1),
          "marca quien MANDA coherente con USAR_M1=%s" % S.USAR_M1)
if cnt:
    L = cnt[0]
    print("   >> %s" % L[:150])
    check("up=" in L and "down=" in L and "marcador=" in L, "lleva los contadores crudos")
    check("hist m1=" in L, "lleva el tamaño de m1_hist (lo que hay que mirar si M1 no gira)")

print()
print("=" * 78)
print("2) Los valores del log CUADRAN con lo que se guardo en la BD")
print("=" * 78)
app.db.commit()
r = app.db.execute("select m1, racha, n_up, n_down, marcador from m1_minute").fetchone()
check(r is not None, "se escribio la fila en m1_minute")
if r and met:
    check("M1=%s(r%d)" % (r[0], r[1]) in met[0],
          "el estado y la racha del LOG coinciden con la BD -> M1=%s(r%d)" % (r[0], r[1]))
    check("up=%d down=%d marcador=%+d" % (r[2], r[3], r[4]) in cnt[0],
          "los contadores del LOG coinciden con la BD -> up=%d down=%d" % (r[2], r[3]))

print()
print("=" * 78)
print("3) La linea de GIRO dice POR QUE giro")
print("=" * 78)
cap.lineas.clear()
app.state = "DOWN"
app._intradia_ok = True
# m1_hist con una entrada lo bastante vieja para que el efectivo sea UP
import time as _t
app.m1_hist = [(_t.monotonic() - (S.RETARDO_M1_MIN * 60.0 + 5.0), "UP")]
S.SpyDirection._update_signal(app)
gir = [l for l in cap.lineas if l.startswith("GIRO ->")]
check(len(gir) == 1, "hubo giro y se logueo -> %d" % len(gir))
if gir:
    print("   >> %s" % gir[0][:150])
    if S.USAR_M1:
        check("por M1" in gir[0], "dice que lo disparo M1")
        check("thr=" in gir[0] and "NO decide" in gir[0],
              "y aclara que el umbral NO decide (antes solo imprimia thr)")
    else:
        check("por CLASICO" in gir[0], "dice que lo disparo el CLASICO")

print()
print("=" * 78)
print("4) `_persist_accum` deja constancia: al guardar Y al fallar")
print("=" * 78)
cap.lineas.clear()
cap.errores = 0
app.accum = {("20260812", 773.0, "C"): 1000.0, ("20260812", 773.0, "P"): 2000.0}
app.accum_net = {}
app.today_prem = dict(app.accum)
app.today_net = {}
app._intradia_ok = True
app.n_trades = 2
app.n_wins = 1
app.pnl_realizado = -3.5
S.SpyDirection._persist_accum(app)
per = [l for l in cap.lineas if l.startswith("PERSIST")]
check(len(per) == 1, "al guardar deja UNA linea PERSIST -> %d" % len(per))
if per:
    print("   >> %s" % per[0][:150])
    check("accum=2" in per[0] and "daily=2" in per[0],
          "cuenta los strikes guardados -> accum=2 daily=2")
    check("intradia=SI" in per[0], "dice si escribio el estado intradia")
n = app.db.execute("select count(*) from strike_accum").fetchone()[0]
check(n == 2, "y de verdad escribio en strike_accum -> %d filas" % n)
n = app.db.execute("select count(*) from estado_intradia").fetchone()[0]
check(n == 1, "y en estado_intradia -> %d fila" % n)

# EL CASO QUE IMPORTA: antes el `except` era `pass` y un fallo era INVISIBLE
cap.lineas.clear()
_warn = []
S.LOG.handlers = [_lg.NullHandler()]
_real_exc = S.LOG.exception
S.LOG.exception = lambda *a, **k: _warn.append("LOG.exception")


class CapWarn(_lg.Handler):
    def emit(self, record):
        _warn.append(record.getMessage())


S.ACT.handlers = [cap, CapWarn()]
app.db.close()          # fuerza el fallo: la conexion esta cerrada
S.SpyDirection._persist_accum(app)
check(any("PERSIST FALLO" in w for w in _warn),
      "si falla, AVISA en el log (antes era `except: pass`, invisible) -> %s"
      % [w[:40] for w in _warn][:2])
check("LOG.exception" in _warn, "y deja el traceback en spy_direction.log")
S.LOG.exception = _real_exc

try:
    os.unlink(path)
except Exception:
    pass

print()
print("=" * 78)
if FAILS:
    print("FALLOS: %d" % len(FAILS))
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("LOGS DE LOS METODOS OK: todos los checks pasaron")
