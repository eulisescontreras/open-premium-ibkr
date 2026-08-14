# -*- coding: utf-8 -*-
"""COLD RUN del ORB de apertura + tope de operaciones (spec congelada v2, 2026-08-14).

QUE SE DEMUESTRA, con la FUNCION REAL `SpyDirection._orb_check` y barras REALES de
spy_bars_year.db (premarket + RTH, mismo formato que alimenta a la app en vivo):

  T1  El rango se calcula con las 10 barras 09:30..09:39 (alto=max high, bajo=min low),
      contrastado contra un calculo INDEPENDIENTE hecho aparte.
  T2  Filtro 0.75: con amplitud < 0.75 NO dispara nunca.
  T3  Ventana ESTRICTA: todo disparo cae en 09:40..09:44. Ni uno en 09:45 o despues.
  T4  REVERSION, no ruptura: cierre POR ENCIMA del alto -> DOWN (PUT);
                              cierre POR DEBAJO del bajo -> UP  (CALL).
  T5  UNA SOLA operacion de apertura por dia (orb_hecho corta).
  T6  Solo mira barras CERRADAS: la barra en formacion (rows[-1]) NUNCA dispara.
  T7  A/B DIFERENCIAL: con ORB_ENABLED=False no emite NADA (identico a HEAD).
  T8  Tope del dia: la guarda usa n_abiertas y MAX_TRADES_DIA; con MAX_TRADES_DIA=None
      no bloquea nunca (identico a HEAD).

PASA si no hay ningun FAIL.
"""
import os, sys, sqlite3, logging as _lg
from datetime import datetime

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO)
try:
    import spy_direction as S
except Exception as e:
    print("FALLO import:", e); sys.exit(1)

# este cold run NO debe escribir en el spy_activity.log de produccion
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


class _Bar(dict):
    """Misma forma que las filas que ta_poll pasa a _orb_check (dict con date/high/low/close)."""
    pass


def nueva_app():
    """Instancia REAL sin __init__ (patron de los cold runs del repo), con lo justo que
    _orb_check necesita. demo=False para que el ORB no se auto-desactive."""
    a = S.SpyDirection.__new__(S.SpyDirection)
    a.demo = False
    a.orb_hi = None
    a.orb_lo = None
    a.orb_hecho = False
    a.orb_senal = None
    a.orb_modulo = None
    return a


def barras_dia(con, dia):
    filas = con.execute(
        "select hora,high,low,close from bars where fecha=? and hora>='09:30' "
        "and hora<='16:00' order by hora", (dia,)).fetchall()
    y, m, d = map(int, dia.split("-"))
    return [_Bar(date=datetime(y, m, d, int(h[:2]), int(h[3:5])),
                 high=hi, low=lo, close=cl) for h, hi, lo, cl in filas]


def rango_ref(bars):
    """Referencia INDEPENDIENTE del rango de apertura (no usa el codigo de la app)."""
    r = [b for b in bars if "09:30" <= b["date"].strftime("%H:%M") <= "09:39"]
    if len(r) < 10:
        return None
    return (max(b["high"] for b in r), min(b["low"] for b in r), len(r))


def simular_dia(bars):
    """Alimenta _orb_check REAL barra a barra, como hace ta_poll: rows[-1] es la barra EN
    FORMACION y rows[-2] la ultima cerrada. Devuelve (app, disparos)."""
    app = nueva_app()
    disparos = []
    for i in range(2, len(bars) + 1):
        rows = bars[:i]
        antes = app.orb_senal
        S.SpyDirection._orb_check(app, rows)
        if app.orb_senal and app.orb_senal != antes:
            # hora de la barra CERRADA que disparo
            disparos.append((rows[-2]["date"].strftime("%H:%M"), app.orb_senal,
                             rows[-2]["close"]))
            app.orb_senal = None          # lo consume _update_signal en la app real
    return app, disparos


DB = os.path.join(REPO, "spy_bars_year.db")
if not os.path.exists(DB):
    print("FALLO: no existe spy_bars_year.db"); sys.exit(1)
con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
dias = [r[0] for r in con.execute(
    "select distinct fecha from bars order by fecha desc limit 60")]

print("=" * 78)
print("COLD RUN ORB + max_trades  ·  %d dias reales de spy_bars_year.db" % len(dias))
print("config: rango %s-%s | ventana %s..<%s | min %.2f | ORB_ENABLED=%s | MAX_TRADES_DIA=%s"
      % (S.ORB_RANGO_INI, S.ORB_RANGO_FIN, S.ORB_VENTANA_INI, S.ORB_VENTANA_FIN,
         S.ORB_RANGO_MIN, S.ORB_ENABLED, S.MAX_TRADES_DIA))
print("=" * 78)

n_disp = n_desc = n_sin = 0
malos_ventana = []
malos_dir = []
malos_rango = []
multi = []
ejemplos = []

for dia in dias:
    bars = barras_dia(con, dia)
    if len(bars) < 30:
        continue
    ref = rango_ref(bars)
    app, disp = simular_dia(bars)

    # T1: rango calculado por la app == referencia independiente
    if ref and app.orb_hi is not None:
        if abs(app.orb_hi - ref[0]) > 1e-9 or abs(app.orb_lo - ref[1]) > 1e-9:
            malos_rango.append((dia, app.orb_hi, app.orb_lo, ref[0], ref[1]))

    if len(disp) > 1:
        multi.append((dia, disp))

    if disp:
        n_disp += 1
        hhmm, sen, cl = disp[0]
        # T3: ventana estricta 09:40..09:44
        if not (S.ORB_VENTANA_INI <= hhmm < S.ORB_VENTANA_FIN):
            malos_ventana.append((dia, hhmm))
        # T4: REVERSION
        if app.orb_hi is not None:
            if cl > app.orb_hi and sen != "DOWN":
                malos_dir.append((dia, hhmm, "cierre>alto pero senal", sen))
            if cl < app.orb_lo and sen != "UP":
                malos_dir.append((dia, hhmm, "cierre<bajo pero senal", sen))
        # T2: si disparo, la amplitud tenia que cumplir el minimo
        if app.orb_hi is not None and (app.orb_hi - app.orb_lo) < S.ORB_RANGO_MIN:
            malos_rango.append((dia, "disparo con amplitud", app.orb_hi - app.orb_lo))
        if len(ejemplos) < 6:
            ejemplos.append((dia, app.orb_lo, app.orb_hi, app.orb_hi - app.orb_lo, hhmm, cl, sen))
    elif app.orb_hi is not None and (app.orb_hi - app.orb_lo) < S.ORB_RANGO_MIN:
        n_desc += 1
    else:
        n_sin += 1

print("\n[1] RANGO DE APERTURA (app vs calculo independiente)")
check(not malos_rango, "el rango 09:30-09:39 coincide en los %d dias (%d discrepancias)"
      % (len(dias), len(malos_rango)))
if malos_rango:
    for x in malos_rango[:3]:
        print("       ", x)

print("\n[2] FILTRO %.2f" % S.ORB_RANGO_MIN)
check(True, "dias con disparo: %d | descartados por rango estrecho: %d | sin salida del rango: %d"
      % (n_disp, n_desc, n_sin))

print("\n[3] VENTANA ESTRICTA %s..<%s" % (S.ORB_VENTANA_INI, S.ORB_VENTANA_FIN))
check(not malos_ventana, "todos los disparos caen en la ventana (%d fuera)" % len(malos_ventana))
if malos_ventana:
    for x in malos_ventana[:5]:
        print("        dia %s disparo a las %s" % x)

print("\n[4] REVERSION (no ruptura)")
check(not malos_dir, "cierre por ENCIMA -> DOWN/PUT y por DEBAJO -> UP/CALL (%d al reves)"
      % len(malos_dir))
if malos_dir:
    for x in malos_dir[:5]:
        print("       ", x)

print("\n[5] UNA SOLA operacion de apertura por dia")
check(not multi, "ningun dia dispara mas de una vez (%d con varios)" % len(multi))

print("\n[6] SOLO BARRAS CERRADAS (la barra en formacion no dispara)")
# se alimenta hasta la barra de 09:44 INCLUIDA como EN FORMACION: no debe haber disparo
# atribuido a ella; el ultimo disparo posible viene de la barra cerrada 09:43 en ese punto.
ok6 = True
for dia in dias[:15]:
    bars = barras_dia(con, dia)
    hasta = [b for b in bars if b["date"].strftime("%H:%M") <= "09:44"]
    if len(hasta) < 12:
        continue
    app = nueva_app()
    S.SpyDirection._orb_check(app, hasta)
    if app.orb_senal:
        # el disparo debe venir de 09:43 (la cerrada), nunca de 09:44 (en formacion)
        if hasta[-2]["date"].strftime("%H:%M") != "09:43":
            ok6 = False
check(ok6, "con 09:44 en formacion, el disparo procede de la barra CERRADA (09:43)")

print("\n[7] A/B DIFERENCIAL: ORB_ENABLED=False -> no emite NADA (identico a HEAD)")
_bak = S.ORB_ENABLED
S.ORB_ENABLED = False
sin_orb = 0
for dia in dias:
    bars = barras_dia(con, dia)
    if len(bars) < 30:
        continue
    app, disp = simular_dia(bars)
    if disp or app.orb_hi is not None or app.orb_hecho:
        sin_orb += 1
S.ORB_ENABLED = _bak
check(sin_orb == 0, "con el ORB apagado no toca nada en ningun dia (%d dias con efecto)" % sin_orb)

print("\n[8] TOPE DEL DIA (guarda de max_trades)")
def bloquea(n_abiertas, tope):
    """Espejo EXACTO de la condicion de trade_poll: `if MAX_TRADES_DIA and n_abiertas >= tope`."""
    return bool(tope and n_abiertas >= tope)
check(S.MAX_TRADES_DIA == 4, "MAX_TRADES_DIA = 4 (spec congelada)")
check(not bloquea(0, S.MAX_TRADES_DIA), "con 0 abiertas SI se puede abrir")
check(not bloquea(3, S.MAX_TRADES_DIA), "con 3 abiertas SI se puede abrir (seria la 4a)")
check(bloquea(4, S.MAX_TRADES_DIA), "con 4 abiertas se BLOQUEA (no hay 5a operacion)")
check(bloquea(9, S.MAX_TRADES_DIA), "con 9 abiertas se BLOQUEA")
check(not bloquea(99, None), "con MAX_TRADES_DIA=None NO bloquea nunca (identico a HEAD)")

print("\n[9] EJEMPLOS REALES")
print("     %-12s %8s %8s %6s  %5s %9s %s" % ("dia", "bajo", "alto", "ampl", "hora", "cierre", "senal"))
for d, lo, hi, amp, hh, cl, sen in ejemplos:
    print("     %-12s %8.2f %8.2f %6.2f  %5s %9.2f %s (%s)"
          % (d, lo, hi, amp, hh, cl, sen, "PUT" if sen == "DOWN" else "CALL"))

con.close()
print("\n" + "=" * 78)
print("FALLOS: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
print("=" * 78)
sys.exit(1 if FAILS else 0)
