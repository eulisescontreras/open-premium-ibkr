# -*- coding: utf-8 -*-
# Cierra TODO lo abierto del 0DTE de hoy y deja la cuenta plana. Usa las FUNCIONES REALES
# (ibkr.abiertas / ibkr.cerrar_todo), con clientId alterno para no chocar con el vivo (17).
# El sistema vivo YA ESTA PARADO (se detuvo antes de ejecutar esto).
import sys, datetime
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C
C.IBKR_CLIENT_ID = 34
from sys2.data.ibkr import IBKR

EXP = datetime.date.today().strftime("%Y%m%d")
k = IBKR()
k.conectar()
print("cuenta:", k.ib.managedAccounts(), "| expiry 0DTE:", EXP)
print("saldo:", k.saldo())

ab = k.abiertas(EXP)
print("\nPOSICIONES ABIERTAS (%d):" % len(ab))
for s, r, q in ab:
    print("   strike %.0f %s  cantidad %+.0f" % (s, r, q))

if ab:
    print("\ncerrando todo...")
    plana, precios = k.cerrar_todo(EXP)
    print("plana=%s  precios ejecutados=%s" % (plana, precios))
    k.ib.sleep(2)
    ab2 = k.abiertas(EXP)
    print("\nVERIFICACION tras el cierre: %d posiciones" % len(ab2))
    for s, r, q in ab2:
        print("   QUEDA strike %.0f %s  %+.0f" % (s, r, q))
else:
    print("\nya estaba plana")

print("\nsaldo final:", k.saldo())
for v in k.ib.accountSummary():
    if v.tag in ("NetLiquidation", "TotalCashValue", "AvailableFunds", "GrossPositionValue"):
        print("  %-20s %s" % (v.tag, v.value))
k.desconectar()
