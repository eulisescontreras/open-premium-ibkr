# -*- coding: utf-8 -*-
# MEDIR EL COSTE REAL DE EJECUCION (idea del usuario): hacer varias compras y ventas SIN
# estrategia, solo para ver el spread real y a que precio llenan las ordenes.
#
# POR QUE ES LA MEDICION MAS IMPORTANTE: medido hoy sobre 485 sesiones, el sistema pasa de
# 149x (coste 0%) a 129x (2%), 100x (5%) y MUERE (10%). Todo depende de esto y solo teniamos
# 2 fills reales.
#
# METODO: para cada vertical se registra bid/ask REAL de las dos patas ANTES de enviar nada,
# se compra al MID (lo que asume el backtest) y se mide QUE PRECIO se consigue y en cuanto
# tiempo. Luego se cierra y se mide igual. Todo con las FUNCIONES REALES del sistema.
# Se usa clientId 34 (el vivo esta PARADO).
import sys, json, time, datetime, os
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C
C.IBKR_CLIENT_ID = 34
from sys2.data.ibkr import IBKR

EXP = datetime.date.today().strftime("%Y%m%d")
ANCHO = 2.0
ESPERA = 12          # segundos de espera por fill antes de cancelar
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spreads_reales.json")

SECO = "--seco" in sys.argv        # solo LEE la cadena y muestra spreads, NO envia ordenes

k = IBKR()
k.conectar()
# spot: ultima barra de SPY en sys2.db (fiable, no depende de la API de mercado)
import sqlite3
_c = sqlite3.connect(r"C:\Users\eulis\proyectos\open-premium-ibkr\sys2.db")
_r = _c.execute("select close from bars where fecha=? order by hora desc limit 1",
                (datetime.date.today().strftime("%Y-%m-%d"),)).fetchone()
_c.close()
spot = float(_r[0]) if _r else None
if spot is None:
    raise SystemExit("no hay barras de hoy en sys2.db para sacar el spot")
print("spot=%.2f  expiry=%s  saldo=%.2f  %s"
      % (spot, EXP, k.saldo(), "[MODO SECO: no se envian ordenes]" if SECO else "[ORDENES REALES]"))

cad = k.cadena(EXP, spot, n=4)
base = round(spot)
# verticales a probar: ATM y desplazados, calls y puts (largo ITM, corto a ANCHO de distancia)
PRUEBAS = []
for off in (-1, 0, 1):
    PRUEBAS.append(("C", base + off, base + off + ANCHO))
    PRUEBAS.append(("P", base + off, base + off - ANCHO))

res = []
for right, kl, ks in PRUEBAS:
    dl = cad.get((right, float(kl)))
    ds = cad.get((right, float(ks)))
    if not dl or not ds or dl["bid"] is None or dl["ask"] is None or ds["bid"] is None or ds["ask"] is None:
        print("  %s %s/%s -> sin bid/ask, se salta" % (right, kl, ks))
        continue
    # precio del vertical: comprar largo al ASK y vender corto al BID = peor caso (cruzar spread)
    mid_v = (dl["mid"] or 0) - (ds["mid"] or 0)
    peor_v = dl["ask"] - ds["bid"]
    mejor_v = dl["bid"] - ds["ask"]
    if mid_v <= 0.02:
        print("  %s %s/%s -> mid %.2f demasiado bajo, se salta" % (right, kl, ks, mid_v))
        continue
    print("\n%s L=%.0f/S=%.0f | largo bid/ask %.2f/%.2f | corto bid/ask %.2f/%.2f"
          % (right, kl, ks, dl["bid"], dl["ask"], ds["bid"], ds["ask"]))
    print("   vertical: MID %.3f | cruzando spread %.3f | favorable %.3f | spread total %.3f (%.1f%% del mid)"
          % (mid_v, peor_v, mejor_v, peor_v - mejor_v,
             100.0 * (peor_v - mejor_v) / mid_v if mid_v else 0))

    r = {"hora": datetime.datetime.now().strftime("%H:%M:%S"), "right": right,
         "k_long": kl, "k_short": ks, "spot": spot,
         "largo_bid": dl["bid"], "largo_ask": dl["ask"], "corto_bid": ds["bid"], "corto_ask": ds["ask"],
         "mid_vert": mid_v, "peor_vert": peor_v, "mejor_vert": mejor_v}

    if SECO:
        res.append(r)
        continue

    # ── COMPRA al MID (lo que asume el backtest) ──
    t0 = time.time()
    tr = k.comprar_vertical(EXP, kl, ks, right, mid_v / 1.01, qty=1)   # comprar_vertical mete *1.01
    llenado = 0.0
    for _ in range(ESPERA * 2):
        k.ib.sleep(0.5)
        if tr.orderStatus.status == "Filled":
            break
    dt = time.time() - t0
    llenado = float(tr.orderStatus.avgFillPrice or 0)
    r.update(compra_estado=tr.orderStatus.status, compra_precio=llenado,
             compra_seg=round(dt, 1), compra_limite=round(mid_v, 2))
    print("   COMPRA: %s  precio %.3f  (limite %.3f)  en %.1fs" % (tr.orderStatus.status, llenado, mid_v, dt))
    if tr.orderStatus.status != "Filled":
        try:
            k.ib.cancelOrder(tr.order)
        except Exception:
            pass
        k.ib.sleep(1)
        res.append(r)
        continue
    r["slippage_compra_pct"] = 100.0 * (llenado - mid_v) / mid_v if mid_v else None

    # ── VENTA (cierre) y medicion ──
    k.ib.sleep(2)
    cad2 = k.cadena(EXP, spot, n=2)
    dl2 = cad2.get((right, float(kl))) or dl
    ds2 = cad2.get((right, float(ks))) or ds
    mid2 = (dl2["mid"] or 0) - (ds2["mid"] or 0)
    t1 = time.time()
    plana, precios = k.cerrar_todo(EXP, right=right, qty=1)
    dt2 = time.time() - t1
    cobrado = None
    if precios:
        pl = precios.get(float(kl)); ps = precios.get(float(ks))
        if pl is not None and ps is not None:
            cobrado = pl - ps
    r.update(venta_plana=plana, venta_precios=precios, venta_seg=round(dt2, 1),
             mid_al_vender=mid2, venta_cobrado=cobrado)
    if cobrado is not None and mid2:
        r["slippage_venta_pct"] = 100.0 * (cobrado - mid2) / abs(mid2)
    print("   VENTA:  plana=%s  cobrado %s  (mid %.3f)  en %.1fs" % (plana, cobrado, mid2, dt2))
    res.append(r)
    k.ib.sleep(1)

json.dump(res, open(SALIDA, "w"), indent=1)
print("\n=== RESUMEN (%d pruebas) ===" % len(res))
for r in res:
    print(" %s %s/%s: spread %.1f%% del mid | compra %s %s | venta %s"
          % (r["right"], r["k_long"], r["k_short"],
             100.0 * (r["peor_vert"] - r["mejor_vert"]) / r["mid_vert"] if r["mid_vert"] else 0,
             r.get("compra_estado"), ("%.3f" % r["compra_precio"]) if r.get("compra_precio") else "",
             ("%.3f" % r["venta_cobrado"]) if r.get("venta_cobrado") is not None else "--"))
print("\nsaldo final:", k.saldo(), "| abiertas:", k.abiertas(EXP))
print("guardado en", SALIDA)
k.desconectar()
