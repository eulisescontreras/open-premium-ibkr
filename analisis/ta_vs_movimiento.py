# -*- coding: utf-8 -*-
"""READ-ONLY. El TA tiene relacion con los movimientos grandes? Anticipa o acompana?
El TA es INDEPENDIENTE del premium: si el premium va detras del precio, quiza el TA no."""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _fecha import fecha_analisis   # fecha por argumento; por defecto, la ultima con datos

F = fecha_analisis()
rows = c.execute("SELECT hora,spy,ta_score,ta_dir,rsi,macd_hist,atr_pct,vwap,bb_up,bb_low,"
                 "bb_mid,obv_trend FROM ta_minute WHERE fecha=? AND spy IS NOT NULL "
                 "ORDER BY hora", (F,)).fetchall()


def m(h):
    a = h.split(":")
    return int(a[0]) * 60 + int(a[1])


# tramos continuos (sin huecos)
tr = []
cur = []
for i in range(1, len(rows)):
    if m(rows[i][0]) - m(rows[i - 1][0]) == 1:
        cur.append((rows[i - 1], rows[i]))
    else:
        if len(cur) > 10:
            tr.append(cur)
        cur = []
if len(cur) > 10:
    tr.append(cur)


def corr(xs, ys):
    n = len(xs)
    if n < 10:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


print("=" * 72)
print("1) EL ta_score ANTICIPA el movimiento del SPY? (correlacion cruzada)")
print("=" * 72)
serie = [x for t in tr for x in t]
print("  pares de minutos consecutivos: %d" % len(serie))
print("  lag   que significa                          corr")
for lag in range(0, 6):
    xs = []
    ys = []
    for t in tr:
        for i in range(len(t)):
            j = i + lag
            if j < len(t):
                xs.append(t[i][0][2] or 0)          # ta_score en el minuto i
                ys.append(t[j][1][1] - t[j][0][1])  # movimiento del SPY en i+lag
    r = corr(xs, ys)
    if r is None:
        continue
    et = "TA y precio mismo minuto" if lag == 0 else "TA %d min ANTES del movimiento" % lag
    print("  %+2d    %-38s %+.3f" % (lag, et, r))

print("\n" + "=" * 72)
print("2) QUE DECIA EL TA en los 10 mayores movimientos de 3 minutos")
print("=" * 72)
movs = []
for i in range(len(rows) - 3):
    if m(rows[i + 3][0]) - m(rows[i][0]) == 3:
        movs.append((rows[i + 3][1] - rows[i][1], rows[i], rows[i + 3]))
movs.sort(key=lambda x: -abs(x[0]))
print("  mov     desde  ->  hasta    ta_dir(inicio) score rsi   macd_h    acierta?")
ac = 0
for d, a, b in movs[:10]:
    dirok = (a[3] == "BULL" and d > 0) or (a[3] == "BEAR" and d < 0)
    if a[3] in ("BULL", "BEAR"):
        ac += 1 if dirok else 0
    print("  %+.2f   %s -> %s   %-8s %+3d  %4.1f  %+7.4f   %s"
          % (d, a[0], b[0], a[3], a[2] or 0, a[4] or 0, a[5] or 0,
             "SI" if dirok else ("no" if a[3] in ("BULL", "BEAR") else "-")))
print("  aciertos direccionales del TA en los 10 mayores: %d" % ac)

print("\n" + "=" * 72)
print("3) TA vs PREMIUM: cual acierta mas la direccion del minuto siguiente?")
print("=" * 72)
ta_ok = ta_tot = pr_ok = pr_tot = 0
for t in tr:
    for a, b in t:
        d = b[1] - a[1]
        if abs(d) < 0.005:
            continue
        if a[3] == "BULL":
            ta_tot += 1
            ta_ok += 1 if d > 0 else 0
        elif a[3] == "BEAR":
            ta_tot += 1
            ta_ok += 1 if d < 0 else 0
pm = c.execute("SELECT hora,spy,prem_state FROM ta_minute WHERE fecha=? AND spy IS NOT NULL "
               "ORDER BY hora", (F,)).fetchall()
for i in range(1, len(pm)):
    if m(pm[i][0]) - m(pm[i - 1][0]) != 1:
        continue
    d = pm[i][1] - pm[i - 1][1]
    if abs(d) < 0.005:
        continue
    st = pm[i - 1][2]
    if st == "UP":
        pr_tot += 1
        pr_ok += 1 if d > 0 else 0
    elif st == "DOWN":
        pr_tot += 1
        pr_ok += 1 if d < 0 else 0
print("  TA      (ta_dir BULL/BEAR): %d de %d  = %.1f%%"
      % (ta_ok, ta_tot, (ta_ok / ta_tot * 100) if ta_tot else 0))
print("  PREMIUM (estado UP/DOWN)  : %d de %d  = %.1f%%"
      % (pr_ok, pr_tot, (pr_ok / pr_tot * 100) if pr_tot else 0))
print("  (50%% = moneda al aire)")

print("\n" + "=" * 72)
print("4) LA SUBIDA DE AHORA (14:30 en adelante): que dice el TA")
print("=" * 72)
print("  hora   SPY     dSPY   ta_dir  score  rsi   macd_h    dist_vwap  bb_ancho%")
for h, spy, sc, dr, rsi, mh, atr, vwap, bu, bl, bm, obv in rows:
    if h >= "14:30":
        anch = ((bu - bl) / bm * 100.0) if (bu and bl and bm) else 0
        prev = [r for r in rows if r[0] < h]
        d = (spy - prev[-1][1]) if prev else 0
        print("  %s %7.2f %+6.2f  %-6s %+3d  %4.1f  %+7.4f   %+6.2f     %.3f"
              % (h, spy, d, dr, sc or 0, rsi or 0, mh or 0, spy - (vwap or spy), anch))
