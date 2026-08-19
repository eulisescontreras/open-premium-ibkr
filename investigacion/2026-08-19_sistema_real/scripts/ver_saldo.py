# corrida en frio: ejecuta la FUNCION REAL IBKR.saldo() con clientId alterno
import sys
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C
C.IBKR_CLIENT_ID = 33            # no chocar con el vivo (17)
from sys2.data.ibkr import IBKR

k = IBKR()
k.conectar()
print("CUENTAS:", k.ib.managedAccounts())
print("SALDO() ->", k.saldo())
print("--- accountSummary crudo ---")
for v in k.ib.accountSummary():
    if v.tag in ("NetLiquidation", "TotalCashValue", "AvailableFunds", "BuyingPower",
                 "GrossPositionValue", "UnrealizedPnL", "RealizedPnL"):
        print("%-20s %-12s %-10s cuenta=%s" % (v.tag, v.value, v.currency, v.account))
print("--- posiciones ---")
for p in k.posiciones():
    print(p.account, p.contract.localSymbol, p.position, p.avgCost)
k.desconectar()
