# -*- coding: utf-8 -*-
"""READ-ONLY. LA PREGUNTA: el flujo de premium ANTICIPA el movimiento del SPY, o lo SIGUE?

Metodo: correlacion cruzada entre el flujo NETO por minuto (delta de net_call - net_put) y el
movimiento del SPY por minuto, desplazando la serie del flujo entre -5 y +5 minutos.
  lag NEGATIVO con correlacion alta -> el flujo va DELANTE (predice)
  lag 0                             -> ocurren a la vez (no sirve para anticipar)
  lag POSITIVO                      -> el flujo va DETRAS (solo reacciona)

Se excluyen los tramos con reinicio (net_call se restaura y da saltos artificiales).
"""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)
F = "2026-08-10"

rows = c.execute("SELECT hora,spy,net_call,net_put FROM ta_minute WHERE fecha=? "
                 "AND spy IS NOT NULL AND net_call IS NOT NULL ORDER BY hora", (F,)).fetchall()


def m(h):
    a = h.split(":")
    return int(a[0]) * 60 + int(a[1])


# --- construir series de DELTAS por minuto, cortando en huecos y reinicios ---
tramos = []
cur = []
for i in range(1, len(rows)):
    h0, s0, c0, p0 = rows[i - 1]
    h1, s1, c1, p1 = rows[i]
    if m(h1) - m(h0) != 1:                 # hueco temporal -> cortar tramo
        if len(cur) > 10:
            tramos.append(cur)
        cur = []
        continue
    d_flujo = (c1 - c0) - (p1 - p0)        # flujo NETO que entro en ese minuto
    d_spy = s1 - s0
    # reinicio: el acumulado se restaura y produce saltos imposibles para 1 minuto
    if abs(d_flujo) > 3_000_000:
        if len(cur) > 10:
            tramos.append(cur)
        cur = []
        continue
    cur.append((h1, d_flujo, d_spy))
if len(cur) > 10:
    tramos.append(cur)

datos = [x for t in tramos for x in t]
print("tramos limpios: %d | minutos utilizables: %d" % (len(tramos), len(datos)))
print("(se descartan huecos y los saltos por reinicio)")


def corr(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


print("\n" + "=" * 74)
print("CORRELACION CRUZADA: flujo del minuto  vs  movimiento del SPY")
print("=" * 74)
print("  lag   interpretacion                       corr     n")
mejor = (0, 0.0, 0)
for lag in range(-5, 6):
    xs = []
    ys = []
    for t in tramos:
        for i in range(len(t)):
            j = i + lag
            if 0 <= j < len(t):
                xs.append(t[i][1])       # flujo en el minuto i
                ys.append(t[j][2])       # movimiento del SPY en el minuto i+lag
    r = corr(xs, ys)
    if r is None:
        continue
    if lag < 0:
        et = "flujo va %d min DETRAS del precio" % (-lag)
    elif lag == 0:
        et = "flujo y precio, MISMO minuto"
    else:
        et = "flujo va %d min DELANTE (predice)" % lag
    marca = ""
    if abs(r) > abs(mejor[1]):
        mejor = (lag, r, len(xs))
        marca = ""
    print("  %+2d    %-36s %+.3f   %d" % (lag, et, r, len(xs)))

print("\n  MAXIMO en lag %+d  (corr %+.3f, n=%d)" % mejor)
if mejor[0] > 0:
    print("  -> el flujo iria DELANTE del precio: la senal PREDICE")
elif mejor[0] == 0:
    print("  -> flujo y precio se mueven A LA VEZ: la senal NO anticipa, coincide")
else:
    print("  -> el flujo va DETRAS: la senal REACCIONA al precio, no lo predice")

print("\n" + "=" * 74)
print("EL EPISODIO DE LAS 12:36 (la entrada de ~1,1 M en calls)")
print("=" * 74)
print("  minuto  SPY      d_SPY    flujo_neto_del_minuto")
for h, s, cc, pp in rows:
    if "12:30" <= h <= "12:42":
        prev = [r for r in rows if r[0] < h]
        if not prev:
            continue
        p = prev[-1]
        if m(h) - m(p[0]) != 1:
            print("  %s %7.2f   (hueco)" % (h, s))
            continue
        df = (cc - p[2]) - (pp - p[3])
        print("  %s %7.2f  %+.2f   %+12.0f" % (h, s, s - p[1], df))

print("\n" + "=" * 74)
print("FALSOS FLIPS: que distingue un giro que RECORRE de uno que no")
print("=" * 74)
ta = {r[0]: r for r in c.execute(
    "SELECT hora,spy,rsi,atr_pct,bb_up,bb_low,bb_mid,vwap FROM ta_minute WHERE fecha=?",
    (F,)).fetchall()}
flips = c.execute("SELECT hora,estado FROM transitions WHERE fecha=? AND tipo='FLIP' "
                  "ORDER BY id", (F,)).fetchall()
buenos = []
malos = []
for hora, estado in flips:
    hm = hora[:5]
    if hm not in ta:
        continue
    t0 = m(hm)
    p0 = ta[hm][1]
    sig = 1.0 if estado == "UP" else -1.0
    # maximo recorrido A FAVOR en los 10 minutos siguientes
    favs = [(ta[k][1] - p0) * sig for k in ta if 0 < m(k) - t0 <= 10]
    if not favs:
        continue
    mfe = max(favs)
    r = ta[hm]
    anch = ((r[4] - r[5]) / r[6] * 100.0) if (r[4] and r[5] and r[6]) else None
    dv = (p0 - r[7]) if r[7] else None
    reg = {"mfe": mfe, "bb": anch, "atr": r[3], "rsi": r[2], "dvwap": dv,
           "min": t0 - m("09:30"), "hora": hora, "estado": estado}
    (buenos if mfe >= 0.20 else malos).append(reg)


def med(lst, k):
    v = sorted(x[k] for x in lst if x[k] is not None)
    return v[len(v) // 2] if v else None


print("  flips que recorrieron >=0.20 a favor en 10 min: %d" % len(buenos))
print("  flips que NO:                                   %d" % len(malos))
print()
print("  variable            RECORRIERON   NO RECORRIERON   separacion")
for k, nom in (("bb", "ancho Bollinger %"), ("atr", "ATR %"), ("rsi", "RSI"),
               ("dvwap", "dist a VWAP"), ("min", "minuto de sesion")):
    a = med(buenos, k)
    b = med(malos, k)
    if a is None or b is None:
        continue
    print("  %-18s  %12.4f   %14.4f   %+.4f" % (nom, a, b, a - b))
print("\n  (mediana. n pequeno: son indicios para vigilar, NO reglas)")
