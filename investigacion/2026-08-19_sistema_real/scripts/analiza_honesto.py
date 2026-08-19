# -*- coding: utf-8 -*-
# Analiza las variantes contra la base HONESTA con el CRITERIO DEL USUARIO (2026-08-19):
#   una señal solo es buena si NO EMPEORA NINGUNA metrica y MEJORA AL MENOS UNA.
#   metricas: TOTAL, drawdown, racha, verdes, rojos, peor dia.  ("si sube el profit y lo demas
#   se mantiene igual tambien es valido; la cosa es que siempre mejore").
# Ademas se corren los 4 tests §2.1 con la funcion REAL sys2.backtest.validacion.valida_regla.
import json, os, sys

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2.backtest.validacion import valida_regla

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dh")
BASE = "hn_base"


def met(d):
    F = sorted(d)
    racha = mx = 0
    for f in F:
        racha = racha + 1 if d[f] < 0 else 0
        mx = max(mx, racha)
    eq = pico = dd = 0.0
    for f in F:
        eq += d[f]
        pico = max(pico, eq)
        dd = min(dd, eq - pico)
    return dict(tot=sum(d.values()),
                verdes=sum(1 for f in F if d[f] > 0),
                rojos=sum(1 for f in F if d[f] < 0),
                racha=mx, dd=dd, peor=min(d.values()))


# sentido de cada metrica: +1 = cuanto mas alto mejor, -1 = cuanto mas bajo mejor
SENT = {"tot": +1, "verdes": +1, "rojos": -1, "racha": -1, "dd": +1, "peor": +1}
NOM = {"tot": "profit", "verdes": "verdes", "rojos": "rojos", "racha": "racha",
       "dd": "drawdown", "peor": "peor dia"}


def veredicto(b, n):
    """Devuelve (domina, mejora[], empeora[])."""
    mej, emp = [], []
    for k, s in SENT.items():
        d = (n[k] - b[k]) * s
        if d > 1e-9:
            mej.append(NOM[k])
        elif d < -1e-9:
            emp.append(NOM[k])
    return (not emp and bool(mej)), mej, emp


b = json.load(open(os.path.join(D, BASE + ".json")))
B = met(b)
F = sorted(b)
CORTE = F[len(F) // 2]
print("BASE %s: profit %+.0f | verdes %d | rojos %d | racha %d | drawdown %.0f | peor dia %.0f"
      % (BASE, B["tot"], B["verdes"], B["rojos"], B["racha"], B["dd"], B["peor"]))
print("        A1 %+.0f   A2 %+.0f   (corte %s)"
      % (sum(v for k, v in b.items() if k < CORTE),
         sum(v for k, v in b.items() if k >= CORTE), CORTE))
print()
print("%-16s %8s %8s %8s %8s %5s %5s %4s %8s %7s %5s %6s  %s"
      % ("variante", "profit", "vs base", "A1", "A2", "verd", "rojo", "rch",
         "drawdwn", "peor", "T1", "p", "veredicto"))

filas = []
for n in os.listdir(D):
    if not n.endswith(".json") or n[:-5] == BASE:
        continue
    d = json.load(open(os.path.join(D, n)))
    M = met(d)
    dom, mej, emp = veredicto(B, M)
    R = valida_regla(b, d, n[:-5])
    filas.append((M["tot"], n[:-5], M, dom, mej, emp, R, d))

for tot, nom, M, dom, mej, emp, R, d in sorted(filas, key=lambda x: -x[0]):
    a1 = sum(x for k, x in d.items() if k < CORTE) - sum(x for k, x in b.items() if k < CORTE)
    a2 = sum(x for k, x in d.items() if k >= CORTE) - sum(x for k, x in b.items() if k >= CORTE)
    ver = "DOMINA" if dom else ("empeora: " + ",".join(emp) if emp else "igual")
    print("%-16s %8.0f %+8.0f %+8.0f %+8.0f %5d %5d %4d %8.0f %7.0f %3d/4 %6.3f  %s"
          % (nom, M["tot"], M["tot"] - B["tot"], a1, a2, M["verdes"], M["rojos"],
             M["racha"], M["dd"], M["peor"], R["test1"][1], R["test3"][1], ver))
    if mej and not dom:
        print("%-16s %s" % ("", "   (mejora: " + ",".join(mej) + ")"))
