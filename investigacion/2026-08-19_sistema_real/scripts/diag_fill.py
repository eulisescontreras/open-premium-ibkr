# -*- coding: utf-8 -*-
# ¿POR QUE las ordenes al MID quedan "Inactive"? 5 de 6 no llenaron. Hay que saber si es
# el MERCADO (nadie cruza a ese precio) o la CONFIGURACION de la orden (TIF/preset).
# Se prueba el MISMO vertical a 3 precios: MID, MID+medio spread, y CRUZANDO el spread.
# Se vuelca el log COMPLETO de cada orden (motivo del rechazo si lo hay).
import sys, time, datetime, sqlite3
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C
C.IBKR_CLIENT_ID = 34
from sys2.data.ibkr import IBKR

EXP = datetime.date.today().strftime("%Y%m%d")
k = IBKR()
k.conectar()
_c = sqlite3.connect(r"C:\Users\eulis\proyectos\open-premium-ibkr\sys2.db")
_r = _c.execute("select close from bars where fecha=? order by hora desc limit 1",
                (datetime.date.today().strftime("%Y-%m-%d"),)).fetchone()
_c.close()
spot = float(_r[0])
base = round(spot)
cad = k.cadena(EXP, spot, n=3)

# vertical PUT ITM (el que mas se parece a lo que opera el sistema)
KL, KS, R = base + 1, base - 1, "P"
dl, ds = cad[(R, float(KL))], cad[(R, float(KS))]
mid = (dl["mid"] or 0) - (ds["mid"] or 0)
cruza = dl["ask"] - ds["bid"]          # comprar largo al ask, vender corto al bid
print("spot %.2f | %s L=%.0f/S=%.0f" % (spot, R, KL, KS))
print("  largo bid/ask %.2f/%.2f | corto bid/ask %.2f/%.2f" % (dl["bid"], dl["ask"], ds["bid"], ds["ask"]))
print("  MID %.3f | CRUZANDO %.3f | spread %.3f" % (mid, cruza, cruza - mid))

for etiq, precio in (("MID", mid), ("MID+50%spread", (mid + cruza) / 2), ("CRUZANDO", cruza)):
    print("\n--- %s: limite %.2f ---" % (etiq, precio))
    tr = k.comprar_vertical(EXP, KL, KS, R, precio / 1.01, qty=1)
    for _ in range(24):
        k.ib.sleep(0.5)
        if tr.orderStatus.status in ("Filled", "Cancelled", "Inactive", "ApiCancelled"):
            if tr.orderStatus.status == "Filled":
                break
    print("  estado=%s  filled=%s  avgPrice=%s" %
          (tr.orderStatus.status, tr.orderStatus.filled, tr.orderStatus.avgFillPrice))
    for e in tr.log:
        print("    [%s] %s %s" % (e.time.strftime("%H:%M:%S"), e.status,
                                  (e.message or "")[:110]))
    if tr.orderStatus.status == "Filled":
        print("  -> LLENO. cerrando...")
        plana, precios = k.cerrar_todo(EXP, right=R, qty=1)
        print("  cierre: plana=%s precios=%s" % (plana, precios))
        break
    try:
        k.ib.cancelOrder(tr.order)
    except Exception:
        pass
    k.ib.sleep(1)

print("\nabiertas:", k.abiertas(EXP), "| saldo:", k.saldo())
k.desconectar()
