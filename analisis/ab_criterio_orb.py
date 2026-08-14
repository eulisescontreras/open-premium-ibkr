# A/B del CRITERIO DE DISPARO del ORB, para acotar por que salen 182 y la spec dice 214.
# A) CIERRE fuera del rango  (lo que dice el doc literalmente, y lo implementado)
# B) TOQUE: high por encima del alto o low por debajo del bajo
# C) CIERRE, pero rango calculado con CLOSES en vez de high/low
# D) CIERRE, sin el filtro de amplitud 0.75
import os, sqlite3
from datetime import datetime
REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MIN_AMP = 0.75

dias = {}
for db in ("spy_bars_year.db", "spy_bars_year2.db"):
    p = os.path.join(REPO, db)
    if not os.path.exists(p):
        continue
    con = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    for fecha, hora, hi, lo, cl in con.execute(
            "select fecha,hora,high,low,close from bars "
            "where hora>='09:30' and hora<='09:44' order by fecha,hora"):
        dias.setdefault(fecha, []).append((hora, hi, lo, cl))
    con.close()

res = {k: 0 for k in "ABCD"}
tot = 0
for fecha, filas in dias.items():
    ran = [f for f in filas if "09:30" <= f[0] <= "09:39"]
    ven = [f for f in filas if "09:40" <= f[0] < "09:45"]
    if len(ran) < 10 or not ven:
        continue
    tot += 1
    hi_hl = max(f[1] for f in ran); lo_hl = min(f[2] for f in ran)
    hi_cl = max(f[3] for f in ran); lo_cl = min(f[3] for f in ran)
    amp = hi_hl - lo_hl

    # A) cierre fuera, con filtro (IMPLEMENTADO)
    if amp >= MIN_AMP and any(f[3] > hi_hl or f[3] < lo_hl for f in ven):
        res["A"] += 1
    # B) toque fuera, con filtro
    if amp >= MIN_AMP and any(f[1] > hi_hl or f[2] < lo_hl for f in ven):
        res["B"] += 1
    # C) cierre fuera de un rango hecho con closes, con filtro
    if (hi_cl - lo_cl) >= MIN_AMP and any(f[3] > hi_cl or f[3] < lo_cl for f in ven):
        res["C"] += 1
    # D) cierre fuera, SIN filtro de amplitud
    if any(f[3] > hi_hl or f[3] < lo_hl for f in ven):
        res["D"] += 1

print("dias evaluados: %d   (spec: 512)" % tot)
print("\n%-70s %5s  %s" % ("CRITERIO", "dias", "vs 214"))
print("-" * 84)
et = {
    "A": "CIERRE fuera del rango high/low + filtro 0.75  << IMPLEMENTADO (dice el doc)",
    "B": "TOQUE (high/low) fuera del rango + filtro 0.75",
    "C": "CIERRE fuera de un rango de CLOSES + filtro 0.75",
    "D": "CIERRE fuera del rango high/low, SIN filtro de amplitud",
}
for k in "ABCD":
    print("%-70s %5d  %+d" % (et[k], res[k], res[k] - 214))
print("-" * 84)
print("\nEl que se acerque a 214 indica que criterio uso el backtest.")
