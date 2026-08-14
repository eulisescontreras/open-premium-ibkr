# SOLO LECTURA. Distribucion de la amplitud del rango de apertura (09:30-09:39) en TODO el
# histórico disponible, para contrastar el filtro 0.75 contra lo que dice la spec (298/512).
import sqlite3, os
REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"
res = {}
for db in ("spy_bars_year.db", "spy_bars_year2.db"):
    p = os.path.join(REPO, db)
    if not os.path.exists(p):
        continue
    con = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    for fecha, hi, lo, n in con.execute(
            "select fecha, max(high), min(low), count(*) from bars "
            "where hora>='09:30' and hora<='09:39' group by fecha"):
        if n >= 10 and fecha not in res:
            res[fecha] = hi - lo
    con.close()

amp = sorted(res.items())
print("dias con rango de apertura completo: %d" % len(amp))
print("periodo: %s .. %s" % (amp[0][0], amp[-1][0]))
v = sorted(x[1] for x in amp)
n = len(v)
print("\n=== DISTRIBUCION DE LA AMPLITUD (puntos de SPY) ===")
for q, et in ((0.05, "p5"), (0.25, "p25"), (0.50, "mediana"), (0.75, "p75"), (0.95, "p95")):
    print("  %-8s %.2f" % (et, v[int(q * (n - 1))]))
print("  min      %.2f" % v[0])
print("  max      %.2f" % v[-1])

bajo = [x for x in amp if x[1] < 0.75]
print("\n=== FILTRO 0.75 ===")
print("  dias por DEBAJO de 0.75 (descartados): %d de %d  (%.0f%%)"
      % (len(bajo), n, 100.0 * len(bajo) / n))
print("  la spec dice: 298 de 512 (58%)")

print("\n=== POR AÑO ===")
por = {}
for f, a in amp:
    y = f[:4]
    por.setdefault(y, []).append(a)
for y in sorted(por):
    lst = por[y]
    nb = sum(1 for x in lst if x < 0.75)
    print("  %s: %3d dias | mediana %.2f | por debajo de 0.75: %3d (%.0f%%)"
          % (y, len(lst), sorted(lst)[len(lst) // 2], nb, 100.0 * nb / len(lst)))

print("\n=== ULTIMOS 60 DIAS (los del cold run) ===")
ult = amp[-60:]
nb = sum(1 for _, a in ult if a < 0.75)
print("  mediana %.2f | minimo %.2f | por debajo de 0.75: %d"
      % (sorted(a for _, a in ult)[30], min(a for _, a in ult), nb))
