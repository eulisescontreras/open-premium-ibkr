# Hijo de PRUEBA: corre el motor REAL solo sobre los ultimos N dias (argv[2]) para validar que
# un parche COMPILA y PRODUCE datos antes de lanzar la corrida de 485 sesiones (~4 min cada una).
import json, sys
RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2.backtest import motor
from sys2.db import repo

N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
con = repo.abrir()
SES, PREM, ETFB = motor.cargar(con)
con.close()
fechas = sorted(PREM)
desde = fechas[-N] if len(fechas) > N else fechas[0]
D = motor.SIS70(SES, PREM, ETFB, desde=desde)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
print("OK %d dias (desde %s) total %+.0f" % (len(D), desde, sum(D.values())))
