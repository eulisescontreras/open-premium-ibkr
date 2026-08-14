# FIDELIDAD del ORB implementado vs la spec congelada v2.
# Ejecuta la FUNCION REAL _orb_check sobre los 511 dias de spy_bars_year(+2).db y compara
# los agregados con los que declara el documento:
#     dias con señal de apertura .... 214 de 512
#     dias sin señal ................ 298
#     horas de disparo .............. 09:40..09:44
import os, sys, sqlite3, logging as _lg
from datetime import datetime
REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, REPO)
import spy_direction as S
for _l in (S.ACT, S.LOG):
    _l.handlers = []; _l.addHandler(_lg.NullHandler())


def nueva_app():
    a = S.SpyDirection.__new__(S.SpyDirection)
    a.demo = False
    a.orb_hi = a.orb_lo = None
    a.orb_hecho = False
    a.orb_senal = None
    a.orb_modulo = None
    return a


# cargar barras 09:30..09:45 de todos los dias de las dos BDs
dias = {}
for db in ("spy_bars_year.db", "spy_bars_year2.db"):
    p = os.path.join(REPO, db)
    if not os.path.exists(p):
        continue
    con = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    for fecha, hora, hi, lo, cl in con.execute(
            "select fecha,hora,high,low,close from bars "
            "where hora>='09:30' and hora<='09:50' order by fecha,hora"):
        dias.setdefault(fecha, []).append((hora, hi, lo, cl))
    con.close()

print("dias cargados: %d" % len(dias))
n_total = n_senal = n_estrecho = n_no_sale = n_incompleto = 0
horas = {}
dirs = {"UP": 0, "DOWN": 0}

for fecha in sorted(dias):
    filas = dias[fecha]
    if len(filas) < 12:
        n_incompleto += 1
        continue
    y, m, d = map(int, fecha.split("-"))
    bars = [dict(date=datetime(y, m, d, int(h[:2]), int(h[3:5])), high=hi, low=lo, close=cl)
            for h, hi, lo, cl in filas]
    n_total += 1
    app = nueva_app()
    disparo = None
    for i in range(2, len(bars) + 1):
        S.SpyDirection._orb_check(app, bars[:i])
        if app.orb_senal:
            disparo = (bars[i - 2]["date"].strftime("%H:%M"), app.orb_senal)
            app.orb_senal = None
            break
    if disparo:
        n_senal += 1
        horas[disparo[0]] = horas.get(disparo[0], 0) + 1
        dirs[disparo[1]] += 1
    elif app.orb_hi is not None and (app.orb_hi - app.orb_lo) < S.ORB_RANGO_MIN:
        n_estrecho += 1
    else:
        n_no_sale += 1

print("\n" + "=" * 66)
print("FIDELIDAD DEL ORB IMPLEMENTADO  (funcion real _orb_check)")
print("=" * 66)
print("  dias evaluados ................ %d   (spec: 512)" % n_total)
print("  dias CON señal de apertura .... %d   (spec: 214)" % n_senal)
print("  dias SIN señal ................ %d   (spec: 298)" % (n_estrecho + n_no_sale))
print("       por rango < %.2f .......... %d" % (S.ORB_RANGO_MIN, n_estrecho))
print("       por no salir del rango ... %d" % n_no_sale)
print("  dias descartados por datos .... %d" % n_incompleto)
print("\n  horas de disparo (spec: 09:40..09:44):")
for h in sorted(horas):
    print("      %s  %3d" % (h, horas[h]))
print("\n  direccion: UP/CALL %d  |  DOWN/PUT %d" % (dirs["UP"], dirs["DOWN"]))

print("\n" + "=" * 66)
ok_h = all("09:40" <= h < "09:45" for h in horas)
dif = abs(n_senal - 214)
print("  ventana 09:40..09:44 respetada : %s" % ("SI" if ok_h else "NO"))
print("  desviacion vs spec (214 dias)  : %+d dias (%.1f%%)" % (n_senal - 214, 100.0 * dif / 214))
print("=" * 66)
