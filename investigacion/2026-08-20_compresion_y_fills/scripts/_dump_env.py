# -*- coding: utf-8 -*-
import json, sys, os, sqlite3
RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2.backtest import motor
from sys2.db import repo
from sys2.core.supertrend import mm

PCT = os.environ.get("RL_PCT", "")
E = json.load(open(r"C:\Users\eulis\proyectos\open-premium-ibkr\investigacion\2026-08-19_sistema_real\resultados\envolvente.json"))
TAB, RANGOS = E["tabla"], E["rangos"]

def celda(mny, minutos):
    m = max(-10, min(10, int(round(mny))))
    t = min(6, int(minutos // 60))
    return (m, t)

con = repo.abrir()
SES, PREM, ETFB = motor.cargar(con)
SP = {}
for f, h, cl in con.execute("select fecha,hora,close from bars where hora>=? and hora<=?",
                            ("09:30", "16:00")):
    SP[(f, h)] = cl
con.close()

if PCT:
    n_cambiadas = n_total = 0
    for fk, dias in PREM.items():
        rango = RANGOS.get(fk)
        if not rango:
            continue
        for hora, cad in dias.items():
            S = SP.get((fk, hora))
            if S is None:
                continue
            minutos = max(0, 960 - mm(hora))
            for (right, k), v in list(cad.items()):
                n_total += 1
                intr = max(0.0, (S - k) if right == "C" else (k - S))
                mny = (S - k) if right == "C" else (k - S)
                c = TAB.get("%s|%d|%d" % ((right,) + celda(mny, minutos)))
                if not c:
                    continue
                cad[(right, k)] = (max(intr + c[PCT] * rango, 0.01), v[1])
                n_cambiadas += 1
    print("precios sustituidos: %d de %d" % (n_cambiadas, n_total), file=sys.stderr)

D = motor.SIS70(SES, PREM, ETFB, capital=600)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
s = 600.0
for f in sorted(D):
    s += D[f]
print("OK saldo %.0f" % s)
