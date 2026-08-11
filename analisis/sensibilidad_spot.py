"""
sensibilidad_spot.py — READ-ONLY

Objecion del usuario, y es correcta: un strike se clasifica ITM/ATM/OTM con el
spot de AHORA, pero el premium se negocio ANTES, cuando el SPY podia estar en
otro sitio. Si el hallazgo depende de que referencia de precio se use, no es un
hallazgo: es un artefacto del etiquetado.

Recalcula las variables con las 3 referencias (cierre / inicio / media del
intervalo) y compara el lift. Solo sobrevive lo que aguanta las tres.
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from direccion_premium import DB
from direccion_foco import recoger, evalua

VARS = ["atm_ratio", "atm_C_menos_P", "cerca_menos_lejos_norm",
        "z_sup0a1_ratio", "bruto_ratio_CP"]
HOR = [1, 3, 5, 10, 15]

db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
c = db.cursor()
fechas = [f for (f,) in c.execute(
    "SELECT DISTINCT fecha FROM premium_minute ORDER BY fecha")]

cache = {}
for ref in ("actual", "previo", "medio"):
    for f in fechas:
        cache[(ref, f)] = recoger(c, f, spot_ref=ref)

# cuanto se movio el SPY dentro del intervalo (magnitud del problema)
print("=" * 88)
print("MAGNITUD DEL PROBLEMA: cuanto se mueve el SPY entre dos lecturas de premium")
print("=" * 88)
for f in fechas:
    m_act, precio = cache[("actual", f)]
    mins = sorted(m for m, _ in m_act)
    difs = []
    for i in range(1, len(mins)):
        if mins[i] in precio and mins[i - 1] in precio:
            difs.append(abs(precio[mins[i]] - precio[mins[i - 1]]))
    difs.sort()
    if difs:
        print("[%s] intervalos=%d | movimiento |dSPY| mediana=%.3f  p90=%.3f  max=%.3f"
              % (f, len(difs), difs[len(difs) // 2], difs[int(len(difs) * .9)], difs[-1]))
        print("      -> %.1f%% de los intervalos mueven MENOS de 0.5 (medio strike): "
              "el etiquetado casi no cambia"
              % (100.0 * sum(1 for d in difs if d < 0.5) / len(difs)))

for var in VARS:
    print("\n" + "=" * 88)
    print("VARIABLE:", var, " — lift medio (up+dn)/2 segun la referencia de spot")
    print("=" * 88)
    print("%-12s %6s | %10s %10s %10s | %6s" %
          ("fecha", "horiz", "cierre", "inicio", "media", "n"))
    print("-" * 88)
    for f in fechas:
        for h in HOR:
            fila = []
            n = 0
            for ref in ("actual", "previo", "medio"):
                muestras, precio = cache[(ref, f)]
                r = evalua(muestras, precio, var, h)
                if r is None:
                    fila.append(None)
                else:
                    fila.append((r["lift_up"] + r["lift_dn"]) / 2)
                    n = r["n"]
            if all(x is None for x in fila):
                continue
            print("%-12s %6d | %s | %6d" %
                  (f, h, " ".join("%+10.1f" % x if x is not None else "%10s" % "-"
                                  for x in fila), n))
        print("-" * 88)
db.close()
