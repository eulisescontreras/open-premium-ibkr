# Hijo: corre el MOTOR REAL y vuelca D = {fecha: pnl_dia} al JSON indicado en argv[1].
import json, sys
RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2.backtest import motor
from sys2.db import repo

con = repo.abrir()
SES, PREM, ETFB = motor.cargar(con)
con.close()
D = motor.SIS70(SES, PREM, ETFB)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
print("OK %d dias" % len(D))
