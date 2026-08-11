"""
control_reloj.py — READ-ONLY

Control anti-trampa. Los dos dias con datos fueron BAJISTAS, asi que cualquier
variable que crezca o decrezca monotonamente con la hora correlaciona con el
retorno futuro sin contener NINGUNA informacion. Es la "correlacion con el reloj"
que ya esta listada como trampa en ANALISIS_ENTRADA_SALIDA.md.

Mide, por cada variable de `direccion_premium.py`:
    rho(variable, minuto del dia)
y lo compara con la referencia:
    rho(minuto del dia, retorno futuro)   <- lo que acierta un reloj parado

|rho_reloj| alto  =>  la variable es un cronometro disfrazado. Descartar.
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from direccion_premium import DB, spearman
from direccion_foco import recoger

db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
c = db.cursor()
fechas = [f for (f,) in c.execute(
    "SELECT DISTINCT fecha FROM premium_minute ORDER BY fecha")]

print("=" * 74)
print("CONTROL DEL RELOJ")
print("=" * 74)

acc = {}
for f in fechas:
    muestras, precio = recoger(c, f)
    xs = [m for m, _ in muestras if m in precio and (m + 30) in precio]
    ys = [precio[m + 30] - precio[m] for m in xs]
    print("[%s] rho(RELOJ, retorno 30m) = %+.2f   <- lo que acierta un reloj parado"
          % (f, spearman(xs, ys)))
    nombres = set(k for _, ff in muestras for k in ff if not k.startswith("_"))
    for nombre in nombres:
        pares = [(ff[nombre], float(m)) for m, ff in muestras if ff.get(nombre) is not None]
        if len(pares) < 30:
            continue
        r = spearman([p[0] for p in pares], [p[1] for p in pares])
        if r is not None:
            acc.setdefault(nombre, {})[f] = r

print("\n%-28s %12s %12s   %s" % ("variable", fechas[0], fechas[1], "veredicto"))
print("-" * 74)
for nombre, d in sorted(acc.items(), key=lambda kv: -max(abs(v) for v in kv[1].values())):
    if len(d) != len(fechas):
        continue
    peor = max(abs(v) for v in d.values())
    ver = "CRONOMETRO" if peor >= 0.50 else ("sospechosa" if peor >= 0.30 else "limpia")
    print("%-28s %+12.2f %+12.2f   %s" % (nombre, d[fechas[0]], d[fechas[1]], ver))
db.close()
