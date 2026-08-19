# Hijo con soporte de RL_DESDE (para medir riesgo de ruina empezando en distintas fechas).
import json, os, sys
RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2.backtest import motor
from sys2.db import repo

con = repo.abrir()
SES, PREM, ETFB = motor.cargar(con)
con.close()
desde = os.environ.get("RL_DESDE") or None
D = motor.SIS70(SES, PREM, ETFB, desde=desde)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
print("OK %d dias%s" % (len(D), (" desde %s" % desde) if desde else ""))
