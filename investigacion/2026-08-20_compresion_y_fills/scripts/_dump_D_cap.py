import json, sys, os
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2.backtest import motor
from sys2.db import repo
con = repo.abrir(); SES, PREM, ETFB = motor.cargar(con); con.close()
_h = os.environ.get("RL_HASTA") or None
D = motor.SIS70(SES, PREM, ETFB, capital=600, hasta=_h)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
s = 600.0
for f in sorted(D):
    s += D[f]
print("OK %d dias  saldo %.0f" % (len(D), s))
