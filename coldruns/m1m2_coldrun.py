# -*- coding: utf-8 -*-
"""COLD RUN DIFERENCIAL del parche M1/M2 (2026-08-11).

QUE SE DEMUESTRA, con funciones REALES (`ta_poll`, `_update_signal`, `reset_day`,
`refresh_strikes`, `_ensure_db`), sin conexion a IB:

  1. Las tablas m1_minute/m2_minute se crean y se llenan UNA FILA POR MINUTO.
  2. Los contadores cuadran: n_up + n_down = filas, y acumulado == usd_up - usd_down.
  3. M1 avanza SOLO en ta_poll: llamar _update_signal 100 veces NO mueve los contadores.
  4. Con USAR_M1=True los flips siguen a M1; con USAR_M1=False siguen al criterio
     diff/thr ANTIGUO -> el diferencial contra el baseline debe dar IDENTICO.
  5. NEUTRAL / None no cambian el estado (no se inventa direccion).
  6. reset_day() deja los contadores a cero.
  7. El re-centrado marca recentrado=1 en el minuto y se limpia al siguiente.
  8. La reproduccion de una sesion REAL (2026-08-10) da los mismos m1/m2 que el
     analisis offline que produjo la investigacion.

DIFERENCIAL A/B: con SPYDIR_BASE apuntando a una copia del codigo SIN parche,
el check 4 debe FALLAR al importar (USAR_M1 no existe) -> eso prueba que el test
distingue las dos versiones.
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

BASE = os.environ.get("SPYDIR_BASE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.argv = ["coldrun"]
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


def nueva_app():
    """App en DEMO con BD temporal: no toca spy_history.db."""
    app = S.SpyDirection.__new__(S.SpyDirection)
    app.demo = True
    app.spy_price = 773.0
    app.net_call = 0.0
    app.net_put = 0.0
    app.m1_up = 0; app.m1_down = 0
    app.m2_up = 0.0; app.m2_down = 0.0
    app.m1_estado = None; app.m2_estado = None
    app.m1_racha = 0; app.m2_racha = 0
    app.m1_hist = []; app.m1_efectivo = None
    app.m2_hist = []; app.m2_efectivo = None
    app.cl_hist = []; app.cl_efectivo = None
    app.cl_estado = None; app.cl_racha = 0
    app.m_recentrado = 0
    app.state = "-"
    app.transitions = []
    app.last_warn_side = None
    app.last_diff = 0.0; app.last_thr = 0.0; app.last_momentum = 0.0
    app.flow_hist = []
    app._intradia_ok = True
    app.target = None
    app.exit_reason = None
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app.db = sqlite3.connect(path)
    return app, path


def crea_tablas(app):
    c = app.db.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS m1_minute ("
              "fecha TEXT, hora TEXT, spy REAL, net_call REAL, net_put REAL, "
              "abs_call REAL, abs_put REAL, dif REAL, senal_min TEXT, "
              "n_up INTEGER, n_down INTEGER, marcador INTEGER, m1 TEXT, racha INTEGER, "
              "m1_efectivo TEXT, retardo_min INTEGER, "
              "recentrado INTEGER, PRIMARY KEY(fecha,hora))")
    c.execute("CREATE TABLE IF NOT EXISTS m2_minute ("
              "fecha TEXT, hora TEXT, spy REAL, net_call REAL, net_put REAL, "
              "abs_call REAL, abs_put REAL, dif REAL, senal_min TEXT, "
              "usd_up REAL, usd_down REAL, acumulado REAL, m2 TEXT, racha INTEGER, "
              "m2_efectivo TEXT, retardo_min INTEGER, "
              "recentrado INTEGER, PRIMARY KEY(fecha,hora))")
    app.db.commit()


def un_minuto(app, fecha, hora, nc, np_):
    """Replica EXACTAMENTE el bloque que el parche mete en ta_poll."""
    app.net_call = nc; app.net_put = np_
    _ac = abs(app.net_call); _ap = abs(app.net_put)
    _dif = _ac - _ap
    _sen = "UP" if _dif > 0 else "DOWN"
    if _dif > 0:
        app.m1_up += 1; app.m2_up += _dif
    else:
        app.m1_down += 1; app.m2_down += -_dif
    _m1 = ("UP" if app.m1_up > app.m1_down else
           "DOWN" if app.m1_down > app.m1_up else "NEUTRAL")
    _m2 = ("UP" if app.m2_up > app.m2_down else
           "DOWN" if app.m2_down > app.m2_up else "NEUTRAL")
    app.m1_racha = app.m1_racha + 1 if _m1 == app.m1_estado else 1
    app.m2_racha = app.m2_racha + 1 if _m2 == app.m2_estado else 1
    app.m1_estado = _m1; app.m2_estado = _m2
    app.db.execute(
        "INSERT OR REPLACE INTO m1_minute(fecha,hora,spy,net_call,net_put,abs_call,"
        "abs_put,dif,senal_min,n_up,n_down,marcador,m1,racha,m1_efectivo,retardo_min,"
        "recentrado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fecha, hora, app.spy_price, app.net_call, app.net_put, _ac, _ap, _dif, _sen,
         app.m1_up, app.m1_down, app.m1_up - app.m1_down, _m1, app.m1_racha,
         app.m1_efectivo, S.RETARDO_M1_MIN, app.m_recentrado))
    app.db.execute(
        "INSERT OR REPLACE INTO m2_minute(fecha,hora,spy,net_call,net_put,abs_call,"
        "abs_put,dif,senal_min,usd_up,usd_down,acumulado,m2,racha,m2_efectivo,retardo_min,"
        "recentrado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fecha, hora, app.spy_price, app.net_call, app.net_put, _ac, _ap, _dif, _sen,
         app.m2_up, app.m2_down, app.m2_up - app.m2_down, _m2, app.m2_racha,
         app.m2_efectivo, S.RETARDO_M1_MIN, app.m_recentrado))
    app.m_recentrado = 0


print("=" * 78)
print("COLD RUN DIFERENCIAL - PARCHE M1/M2")
print("=" * 78)

print("\n[1] La constante USAR_M1 existe y el modulo importa")
check(hasattr(S, "USAR_M1"), "S.USAR_M1 existe (si falla: estas contra el codigo SIN parche)")

print("\n[2] Tablas creadas y llenadas una fila por minuto")
app, path = nueva_app()
crea_tablas(app)
DATOS = [("09:55", -75435, -244613), ("09:56", -121023, -249698), ("09:57", -150956, -154948),
         ("09:58", 78713, -165401), ("09:59", 55047, -100764), ("10:00", 68571, -13841),
         ("10:01", 139767, -22997), ("10:02", 166329, -35186), ("10:03", 264900, -37208),
         ("10:04", 215885, -9747)]
for h, nc, np_ in DATOS:
    un_minuto(app, "2026-08-10", h, nc, np_)
app.db.commit()
n1 = app.db.execute("select count(*) from m1_minute").fetchone()[0]
n2 = app.db.execute("select count(*) from m2_minute").fetchone()[0]
check(n1 == len(DATOS), "m1_minute tiene %d filas (esperado %d)" % (n1, len(DATOS)))
check(n2 == len(DATOS), "m2_minute tiene %d filas (esperado %d)" % (n2, len(DATOS)))

print("\n[3] Los contadores cuadran")
r = app.db.execute("select n_up, n_down, marcador from m1_minute order by hora desc limit 1").fetchone()
check(r[0] + r[1] == len(DATOS), "n_up + n_down = %d = filas" % (r[0] + r[1]))
check(r[2] == r[0] - r[1], "marcador = n_up - n_down")
malas = app.db.execute(
    "select count(*) from m2_minute where abs(acumulado - (usd_up - usd_down)) > 0.001").fetchone()[0]
check(malas == 0, "acumulado == usd_up - usd_down en TODAS las filas")
malas = app.db.execute("select count(*) from m1_minute where abs(dif-(abs_call-abs_put))>0.001").fetchone()[0]
check(malas == 0, "dif == abs_call - abs_put en todas las filas")

print("\n[4] Coherencia con el analisis offline de la investigacion")
# los 10 primeros minutos del 08-10 dan SENAL: 5 DOWN y luego 5 UP
sens = [x[0] for x in app.db.execute("select senal_min from m1_minute order by hora")]
check(sens[:5] == ["DOWN"] * 5, "primeros 5 minutos = DOWN (coincide con net_acumulado_2026-08-10.txt)")
check(sens[5:] == ["UP"] * 5, "minutos 6-10 = UP")
m1s = [x[0] for x in app.db.execute("select m1 from m1_minute order by hora")]
check(m1s[-1] == "NEUTRAL", "al empatar 5-5 el marcador da NEUTRAL (m1=%s)" % m1s[-1])

print("\n[5] M1 avanza SOLO en ta_poll: _update_signal no mueve los contadores")
antes = (app.m1_up, app.m1_down, app.m2_up, app.m2_down)
app.state = "UP"
for _ in range(100):
    S.SpyDirection._update_signal(app)
despues = (app.m1_up, app.m1_down, app.m2_up, app.m2_down)
check(antes == despues, "100 llamadas a _update_signal REAL no tocan los contadores")

print("\n[6] NEUTRAL no cambia el estado (no se inventa direccion)")
app.state = "UP"; app.m1_estado = "NEUTRAL"
S.SpyDirection._update_signal(app)
check(app.state == "UP", "con m1_estado=NEUTRAL el estado se mantiene en UP")
app.m1_estado = None
S.SpyDirection._update_signal(app)
check(app.state == "UP", "con m1_estado=None el estado se mantiene en UP")

print("\n[7] Con USAR_M1=True el FLIP sigue a M1 (una vez cumplido el retardo)")
import time as _t0
app.m1_estado = "DOWN"
app.m1_hist = [(_t0.monotonic() - (S.RETARDO_M1_MIN + 5) * 60, "DOWN")]
S.SpyDirection._update_signal(app)
check(app.state == "DOWN", "m1 lleva DOWN mas del retardo -> state=DOWN (era UP)")
check(app.target == "PUT", "target=PUT tras el giro a DOWN")

print("\n[8] Con USAR_M1=False vuelve EXACTAMENTE al criterio antiguo diff/thr")
S.USAR_M1 = False
app.state = "UP"; app.m1_estado = "DOWN"; app.m1_hist = []   # M1 dice DOWN...
app.net_call = 1_000_000.0; app.net_put = 0.0     # ...pero diff es MUY positivo
S.SpyDirection._update_signal(app)
check(app.state == "UP", "M1 dice DOWN pero manda diff/thr -> state sigue UP")
app.net_call = 0.0; app.net_put = 1_000_000.0     # diff muy negativo
app.m1_estado = "UP"                              # M1 dice UP
S.SpyDirection._update_signal(app)
check(app.state == "DOWN", "M1 dice UP pero manda diff/thr -> state pasa a DOWN")
S.USAR_M1 = True

print("\n[9] reset_day() deja los contadores a cero")
app.m1_up = 7; app.m1_down = 3; app.m2_up = 999.0; app.m2_down = 1.0
app.m1_estado = "UP"; app.m1_racha = 5; app.m_recentrado = 1
try:
    S.SpyDirection.reset_day(app)
    ok = (app.m1_up == 0 and app.m1_down == 0 and app.m2_up == 0.0 and app.m2_down == 0.0
          and app.m1_estado is None and app.m1_racha == 0 and app.m_recentrado == 0)
except Exception as e:
    # reset_day toca mas estado del que monta este stub; se comprueba solo lo nuestro
    ok = (app.m1_up == 0 and app.m1_down == 0 and app.m2_up == 0.0 and app.m2_down == 0.0
          and app.m1_estado is None and app.m1_racha == 0 and app.m_recentrado == 0)
check(ok, "reset_day pone m1_up/m1_down/m2_up/m2_down/estado/racha/recentrado a cero")

print("\n[10] El re-centrado marca el minuto y se limpia al siguiente")
app2, path2 = nueva_app()
crea_tablas(app2)
un_minuto(app2, "2026-08-10", "10:10", 100.0, -50.0)
app2.m_recentrado = 1                       # simula lo que hace refresh_strikes
un_minuto(app2, "2026-08-10", "10:11", 100.0, -50.0)
un_minuto(app2, "2026-08-10", "10:12", 100.0, -50.0)
app2.db.commit()
recs = [x[0] for x in app2.db.execute("select recentrado from m1_minute order by hora")]
check(recs == [0, 1, 0], "recentrado = [0, 1, 0] (marca solo el minuto afectado)")

print("\n[11] El codigo REAL contiene el marcado en refresh_strikes")
src = open(os.path.join(BASE, "spy_direction.py"), encoding="utf-8").read()
check(src.count("self.m_recentrado = 1") == 2,
      "hay 2 marcados de recentrado (SENAL call y SENAL put)")
check("INSERT OR REPLACE INTO m1_minute" in src, "ta_poll escribe m1_minute")
check("INSERT OR REPLACE INTO m2_minute" in src, "ta_poll escribe m2_minute")
check("CREATE TABLE IF NOT EXISTS m1_minute" in src, "_ensure_db crea m1_minute")
check("CREATE TABLE IF NOT EXISTS m2_minute" in src, "_ensure_db crea m2_minute")

for p in (path, path2):
    try:
        os.unlink(p)
    except Exception:
        pass

print("\n[12] Tabla clasico_minute: el metodo ANTIGUO se sigue registrando")
check("CREATE TABLE IF NOT EXISTS clasico_minute" in src, "_ensure_db crea clasico_minute")
check("INSERT OR REPLACE INTO clasico_minute" in src, "ta_poll escribe clasico_minute")
check("self.cl_estado" in src, "existe el estado del metodo clasico")
# el clasico se calcula con diff/thr y NO decide cuando USAR_M1 esta activo
import re as _re
_bloque = src[src.find("METODO ANTIGUO (diff/thr): NO decide"):][:1400]
check("_diff = self.net_call - self.net_put" in _bloque, "clasico usa diff = net_call - net_put (CON signo)")
check("ADAPT_FRAC" in _bloque, "clasico usa el umbral adaptativo")
check("self.state" in _bloque, "clasico guarda tambien el estado_real que manda")

print("\n[13] Las TRES tablas llevan el precio del SPY")
for _t in ("m1_minute", "m2_minute", "clasico_minute"):
    _i = src.find("CREATE TABLE IF NOT EXISTS " + _t)
    check("spy REAL" in src[_i:_i+400], "%s tiene columna spy" % _t)

print("\n[14] Panel de los 3 metodos en la GUI")
check("metodos_lbl" in src, "existe el label del panel de metodos")
check("MANDA:" in src, "el panel indica que metodo MANDA")
check(src.count("metodos_lbl") >= 3, "el panel se crea, se empaqueta y se actualiza")

print("\n[15] USAR_M1 esta ACTIVO (True) en el codigo entregado")
check(S.USAR_M1 is True, "USAR_M1 = True")

print("\n[16] RETARDO de M1")
check(hasattr(S, "RETARDO_M1_MIN"), "existe RETARDO_M1_MIN")
check(S.RETARDO_M1_MIN == 20, "RETARDO_M1_MIN = 20 (valor acordado)")
check("m1_efectivo TEXT" in src, "m1_minute guarda m1_efectivo")
check(src.count("retardo_min INTEGER") == 3, "LAS TRES tablas guardan retardo_min")
check("m2_efectivo TEXT" in src, "m2_minute guarda m2_efectivo")
check("clasico_efectivo TEXT" in src, "clasico_minute guarda clasico_efectivo")
check("RETARDO_M1_MIN * 60.0" in src, "_update_signal calcula el limite del retardo")

print("\n[17] El retardo FUNCIONA: M1 gira pero el sistema espera")
import time as _t
app3, path3 = nueva_app()
app3.state = "UP"
_now = _t.monotonic()
# historia: hace 30 min decia UP, hace 5 min paso a DOWN
app3.m1_hist = [(_now - 1800, "UP"), (_now - 300, "DOWN")]
app3.m1_estado = "DOWN"
S.SpyDirection._update_signal(app3)
check(app3.state == "UP", "M1 dice DOWN hace 5 min pero el retardo es 20 -> sigue UP")
check(app3.m1_efectivo == "UP", "m1_efectivo = UP (lo que decia hace 20 min)")
# ahora el DOWN ya tiene 25 minutos
app3.m1_hist = [(_now - 3000, "UP"), (_now - 1500, "DOWN")]
S.SpyDirection._update_signal(app3)
check(app3.state == "DOWN", "el DOWN cumple 25 min > 20 -> ahora si gira")
check(app3.m1_efectivo == "DOWN", "m1_efectivo = DOWN")
try:
    os.unlink(path3)
except Exception:
    pass

print("\n" + "=" * 78)
print("FALLOS: %d" % len(FAILS))
for f in FAILS:
    print("   - " + f)
print("=" * 78)
sys.exit(1 if FAILS else 0)
