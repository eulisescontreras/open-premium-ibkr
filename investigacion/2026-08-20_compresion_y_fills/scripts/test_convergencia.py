# -*- coding: utf-8 -*-
# ¿LA LÍNEA SE MUEVE HACIA EL PRECIO EN VEZ DE ALEJARSE?  (idea del usuario 2026-08-20)
#
# LA OBSERVACIÓN: "a veces la línea sí se mueve y resulta que es mentira ese movimiento...
# en esos casos parece que la línea se mueve HACIA el precio en lugar de alejarse".
#
# POR QUÉ ES DISTINTO DE LO YA MEDIDO: ayer se midió que el PRECIO baja hacia la línea
# (aproximación). Esto es lo contrario: la LÍNEA sube hacia el precio. Mecánicamente significa
# que el precio NO avanza mientras la línea le come el colchón -> COMPRESIÓN. En una tendencia
# sana el precio avanza MÁS rápido que la línea y la distancia se mantiene o crece.
#
# VARIABLES (todas de buckets YA FORMADOS -> sin look-ahead):
#   d_linea   cuánto se movió la LÍNEA en los últimos k buckets (en ATR, con signo a favor)
#   d_precio  cuánto se movió el PRECIO en los mismos buckets (en ATR, a favor)
#   dist0/dist1  distancia precio-línea al principio y al final del tramo
#   conver    (dist0 - dist1) / dist0  -> >0 se ESTRECHA (línea alcanza al precio), <0 se abre
#
# OBJETIVO HONESTO: recorrido favorable REAL del precio DESDE el bucket de decisión
# (< 1.0 ATR = malo). NO se usa el veredicto de reb2 (sería fuga de objetivo).
import sqlite3, sys, statistics as stt

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import st_lin_p
from sys2.core.supertrend import mm, hhmm

K = 4                      # buckets hacia atrás para medir el movimiento (12 min)
con = sqlite3.connect(RAIZ + r"\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
CORTE = FECHAS[len(FECHAS) // 2]

D = []
for f in FECHAS:
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                       (f,)).fetchall()
    if len(bars) < 100:
        continue
    try:
        L, ks, Dd = st_lin_p(bars, C.ST_PER, C.ST_MULT)
    except Exception:
        continue
    for i in range(12, len(ks) - 13):
        h = hhmm(ks[i])
        if not ("09:45" <= h <= "15:20"):
            continue
        atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
        if atr <= 0:
            continue
        d = L[ks[i]]['d']
        if L[ks[i - K]]['d'] != d:          # el tramo debe ser de la MISMA dirección
            continue
        lado = 1 if d > 0 else -1
        lin0, lin1 = L[ks[i - K]]['linea'], L[ks[i]]['linea']
        cl0, cl1 = L[ks[i - K]]['cl'], L[ks[i]]['cl']
        d_linea = (lin1 - lin0) * lado / atr        # >0 = la línea avanza a favor
        d_precio = (cl1 - cl0) * lado / atr         # >0 = el precio avanza a favor
        dist0 = abs(cl0 - lin0) / atr
        dist1 = abs(cl1 - lin1) / atr
        if dist0 <= 0.05:
            continue
        conver = (dist0 - dist1) / dist0             # >0 se estrecha

        # objetivo: recorrido favorable en los siguientes 12 buckets desde AQUÍ
        cls = [L[ks[j]]['cl'] for j in range(i, i + 13)]
        mov = max((y - cls[0]) * lado for y in cls) / atr
        D.append(dict(f=f, d_linea=d_linea, d_precio=d_precio, dist0=dist0, dist1=dist1,
                      conver=conver, mov=mov, malo=1 if mov < 1.0 else 0))

n = len(D)
base = 100.0 * sum(x['malo'] for x in D) / n
print("buckets: %d | corte %s" % (n, CORTE))
print("BASE: %.1f%% malos, recorrido medio %.2f ATR\n" % (base, stt.mean(x['mov'] for x in D)))


def bloque(sub, etiq):
    if len(sub) < 150:
        return
    a1 = [x for x in sub if x['f'] < CORTE]
    a2 = [x for x in sub if x['f'] >= CORTE]
    print("%-40s %6d %7.1f%% %8.2f %8s %8s"
          % (etiq, len(sub), 100.0 * sum(x['malo'] for x in sub) / len(sub),
             stt.mean(x['mov'] for x in sub),
             ("%.1f%%" % (100.0 * sum(x['malo'] for x in a1) / len(a1))) if len(a1) >= 60 else "-",
             ("%.1f%%" % (100.0 * sum(x['malo'] for x in a2) / len(a2))) if len(a2) >= 60 else "-"))


CAB = "%-40s %6s %8s %8s %8s %8s" % ("grupo", "n", "%malos", "movATR", "A1", "A2")

print("=== 1) ¿LA DISTANCIA PRECIO-LÍNEA SE ESTRECHA O SE ABRE? ===")
print(CAB)
for lo, hi, et in ((-99, -0.3, "se ABRE fuerte (conver < -0.3)"),
                   (-0.3, -0.05, "se abre poco"),
                   (-0.05, 0.05, "estable"),
                   (0.05, 0.3, "se estrecha poco"),
                   (0.3, 0.6, "se ESTRECHA (0.3-0.6)"),
                   (0.6, 99, "se ESTRECHA MUCHO (>0.6)")):
    bloque([x for x in D if lo <= x['conver'] < hi], "  " + et)
print()

print("=== 2) LA CLAVE: ¿QUIÉN SE MUEVE, LA LÍNEA O EL PRECIO? ===")
print(CAB)
bloque([x for x in D if x['d_linea'] > 0.15 and x['d_precio'] <= 0.05],
       "  LÍNEA avanza y PRECIO NO  <- la idea")
bloque([x for x in D if x['d_linea'] > 0.15 and x['d_precio'] > 0.15],
       "  ambos avanzan (tendencia sana)")
bloque([x for x in D if x['d_linea'] <= 0.05 and x['d_precio'] > 0.15],
       "  PRECIO avanza y LÍNEA no")
bloque([x for x in D if x['d_linea'] <= 0.05 and x['d_precio'] <= 0.05],
       "  ninguno se mueve (lateral)")
print()

print("=== 3) RATIO línea/precio (cuánto come la línea por unidad de avance) ===")
print(CAB)
sub = [x for x in D if x['d_precio'] > 0.05]
for lo, hi in ((0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 3.0), (3.0, 99)):
    bloque([x for x in sub if lo <= x['d_linea'] / x['d_precio'] < hi],
           "  linea/precio %.1f-%.1f" % (lo, hi))
print()

print("=== 4) DISTANCIA ACTUAL A LA LÍNEA (colchón restante) ===")
print(CAB)
for lo, hi in ((0, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 99)):
    bloque([x for x in D if lo <= x['dist1'] < hi], "  dist %.1f-%.1f ATR" % (lo, hi))
print()

print("=== 5) COMBINADO: colchón pequeño Y estrechándose ===")
print(CAB)
bloque([x for x in D if x['dist1'] < 1.0 and x['conver'] > 0.3],
       "  dist<1.0 Y se estrecha >0.3")
bloque([x for x in D if x['dist1'] < 1.0 and x['conver'] <= 0],
       "  dist<1.0 pero se abre")
bloque([x for x in D if x['dist1'] >= 2.0 and x['conver'] <= 0],
       "  dist>=2.0 y se abre (lo mejor?)")
