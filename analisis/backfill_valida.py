"""VALIDA el backfill: reconstruye el 08-12 con LA MISMA LOGICA y lo compara con lo vivo.

Si no cuadra al 100% en el 08-12 -que si tiene datos reales-, no se escribe nada en los otros
dias. Es la unica forma de saber que la reconstruccion es fiable y no una invencion.
"""
import sqlite3

DB = ('file:C:/Users/eulis/AppData/Local/Temp/claude/C--Users-eulis/'
      '8150f2ad-141b-4a8f-b160-c4d910900269/scratchpad/snap_spy_history.db?mode=ro')
c = sqlite3.connect(DB, uri=True)
F = '2026-08-12'
RETARDO, CONFIRMACION_MIN = 20, 5


def mins(h):
    return int(h[:2]) * 60 + int(h[3:5])


ta = list(c.execute("select hora,spy,net_call,net_put from ta_minute where fecha=? "
                    "and net_call is not null and net_put is not null and spy is not null "
                    "order by hora", (F,)))

real_m1 = {h: (nu, nd, mar, m1, sen, ra) for h, nu, nd, mar, m1, sen, ra in c.execute(
    "select hora,n_up,n_down,marcador,m1,senal_min,racha from m1_minute where fecha=?", (F,))}
real_m2 = {h: (uu, ud, ac, m2, ra) for h, uu, ud, ac, m2, ra in c.execute(
    "select hora,usd_up,usd_down,acumulado,m2,racha from m2_minute where fecha=?", (F,))}
real_cf = {h: (ra, cf) for h, ra, cf in c.execute(
    "select hora,racha,confirmado from confirmacion_minute where fecha=?", (F,))}

up = dn = 0
u_up = u_dn = 0.0
m1_est = m2_est = sen_est = conf = None
m1_r = m2_r = sen_r = 0
ok = {"senal": 0, "m1": 0, "m2": 0, "conf": 0}
tot = 0
fallos = []

for h, s, nc, np_ in ta:
    ac, ap = abs(nc), abs(np_)
    dif = ac - ap
    sen = "UP" if dif > 0 else "DOWN"
    if dif > 0:
        up += 1
        u_up += dif
    else:
        dn += 1
        u_dn += -dif
    m1 = "UP" if up > dn else ("DOWN" if dn > up else "NEUTRAL")
    m2 = "UP" if u_up > u_dn else ("DOWN" if u_dn > u_up else "NEUTRAL")
    m1_r = m1_r + 1 if m1 == m1_est else 1
    m2_r = m2_r + 1 if m2 == m2_est else 1
    m1_est, m2_est = m1, m2
    sen_r = sen_r + 1 if sen == sen_est else 1
    sen_est = sen
    if sen_r >= CONFIRMACION_MIN:
        conf = sen

    if h in real_m1:
        tot += 1
        r = real_m1[h]
        if r[4] == sen:
            ok["senal"] += 1
        if r[0] == up and r[1] == dn and r[3] == m1 and r[5] == m1_r:
            ok["m1"] += 1
        elif len(fallos) < 3:
            fallos.append(("m1", h, (up, dn, m1, m1_r), (r[0], r[1], r[3], r[5])))
        if h in real_m2:
            r2 = real_m2[h]
            if (abs((r2[0] or 0) - u_up) < 1 and abs((r2[1] or 0) - u_dn) < 1
                    and r2[3] == m2 and r2[4] == m2_r):
                ok["m2"] += 1
            elif len(fallos) < 6:
                fallos.append(("m2", h, (round(u_up), round(u_dn), m2, m2_r),
                               (round(r2[0] or 0), round(r2[1] or 0), r2[3], r2[4])))
        if h in real_cf:
            rc = real_cf[h]
            if rc[0] == sen_r and rc[1] == conf:
                ok["conf"] += 1
            elif len(fallos) < 9:
                fallos.append(("conf", h, (sen_r, conf), (rc[0], rc[1])))

print("=" * 84)
print(f"VALIDACION DEL BACKFILL contra los datos VIVOS del {F}")
print("=" * 84)
print(f"  minutos comparados: {tot}")
for k, et in (("senal", "senal_min"), ("m1", "M1: n_up,n_down,estado,racha"),
              ("m2", "M2: usd_up,usd_down,estado,racha"),
              ("conf", "CONFIRMACION: racha,confirmado")):
    p = 100.0 * ok[k] / tot if tot else 0
    print(f"  {et:38s} {ok[k]:4d}/{tot}  ({p:5.1f}%)  {'OK' if p == 100 else '*** NO CUADRA ***'}")
if fallos:
    print("\n  primeros desajustes (reconstruido vs real):")
    for f in fallos:
        print(f"    {f[0]} {f[1]}: {f[2]}  vs  {f[3]}")
print()
print("  VEREDICTO: " + ("se puede escribir en los otros dias"
                         if all(ok[k] == tot for k in ok) else
                         "NO escribir: la reconstruccion no reproduce lo vivo"))
