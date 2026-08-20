# -*- coding: utf-8 -*-
# ¿LA LÍNEA PLANA DEL ST-3 MARCA "TIEMPO MUERTO"?  (idea del usuario 2026-08-20, viendo el gráfico)
#
# LA OBSERVACIÓN: "cuando la línea del supertrend se mantiene estable en el mismo valor vela por
# vela, el precio se lateraliza; cuando se mueve, es cuando se dan los movimientos tendenciales.
# Eso es tiempo muerto que no se debería tradear."
#
# POR QUÉ TIENE SENTIDO MECÁNICO (verificado en rebote.st_lin_p:68-69): la línea solo se
# actualiza cuando el precio hace un EXTREMO NUEVO (`lb > fl` o `CL[i-1] < fl`). Si se queda
# congelada, es que el precio NO está haciendo extremos = está en rango. No es una correlación
# casual: es la definición del indicador.
#
# NO ES LOOK-AHEAD: la línea de los buckets ANTERIORES al flip ya está formada cuando se decide.
#
# SEGUNDA IDEA DEL USUARIO (también se mide): el rango genera un TECHO, y cuando se rompe es
# cuando el precio reacciona de verdad -> `rompe_techo`.
#
# OBJETIVO HONESTO (el mismo de toda la investigación): recorrido favorable REAL del precio
# desde el minuto en que se decide, malo = < 1.0 ATR (criterio de rebote.clasificar_dia:177).
# NO se usa el veredicto de reb2 como objetivo: sería fuga (reb2 define "malo" con el mismo
# criterio que el predictor).
import sqlite3, sys, statistics as stt

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import sen_p
from sys2.core.supertrend import mm, hhmm

con = sqlite3.connect(RAIZ + r"\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
CORTE = FECHAS[len(FECHAS) // 2]

D = []
for f in FECHAS:
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                       (f,)).fetchall()
    if len(bars) < 100:
        continue
    cl_ = {h: cl for h, hi, lo, cl in bars if "09:30" <= h <= "16:00"}
    if len(cl_) < 100:
        continue
    try:
        sp, L, ks = sen_p(bars, C.ST_PER, C.ST_MULT)
    except Exception:
        continue
    ik = {kk: i for i, kk in enumerate(ks)}
    flips = [(h, d) for h, d in sp if h >= "09:45"]
    horas = sorted(cl_)
    for n_, (h, d) in enumerate(flips):
        i = ik.get((mm(h) // 3) * 3)
        if i is None or i < 12 or i + 12 > len(ks) - 1:
            continue
        lado = 1 if d == 'C' else -1
        atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
        if atr <= 0:
            continue

        # ── cuántos buckets CONSECUTIVOS lleva la línea SIN MOVERSE antes del flip ──
        # (se mira hacia atrás desde i-1: todo eso ya está formado cuando se decide)
        # ⚠️ EMPEZAR EN i-2, NO EN i-1: `sen_p` aplica shift_sen(+3), así que i-1 es el bucket
        # donde la línea SALTA de lado (de fu a fl). Empezar ahí daba plana=0 en los 1.505 flips.
        plana = 0
        for j in range(i - 2, max(0, i - 14), -1):
            if abs(L[ks[j]]['linea'] - L[ks[j - 1]]['linea']) < 1e-9:
                plana += 1
            else:
                break
        # MATIZ DEL USUARIO: la línea se queda quieta cuando el precio va EN CONTRA de la
        # tendencia del ST-3 o cuando está lateral (fl solo sube si hay mínimos más altos).
        # Se separan los dos casos: durante el tramo plano, ¿el precio iba en contra o de lado?
        _d_prev = L[ks[i - 2]]['d'] if i >= 2 else 0
        _ini_p = max(0, i - 1 - max(plana, 1))
        _cl0, _cl1 = L[ks[_ini_p]]['cl'], L[ks[i - 2]]['cl']
        _dir_precio = (_cl1 - _cl0) * _d_prev / atr        # >0 a favor del ST, <0 en contra
        contra = 1 if _dir_precio < -0.3 else 0
        lateral = 1 if abs(_dir_precio) <= 0.3 else 0

        # ── el RANGO durante el tramo plano y si el precio lo ROMPIÓ (idea 2 del usuario) ──
        ini = max(0, i - max(plana, 1))
        seg_hi = max(L[ks[j]]['hi'] for j in range(ini, i))
        seg_lo = min(L[ks[j]]['lo'] for j in range(ini, i))
        rango = (seg_hi - seg_lo) / atr
        cl_flip = L[ks[i - 1]]['cl']
        rompe = 1 if (cl_flip > seg_hi if lado > 0 else cl_flip < seg_lo) else 0

        # ── objetivo: recorrido real desde la DECISIÓN (h) hasta el siguiente flip ──
        fin = flips[n_ + 1][0] if n_ + 1 < len(flips) else "15:59"
        seg = [cl_[z] for z in horas if h <= z <= fin]
        if len(seg) < 3:
            continue
        mov = max((y - seg[0]) * lado for y in seg) / atr
        D.append(dict(f=f, plana=plana, rango=round(rango, 2), rompe=rompe,
                      contra=contra, lateral=lateral, dir_precio=round(_dir_precio, 2),
                      mov=mov, malo=1 if mov < 1.0 else 0))

n = len(D)
base = 100.0 * sum(x['malo'] for x in D) / n
print("flips analizados: %d   |   corte A1/A2: %s" % (n, CORTE))
print("BASE: %.1f%% malos, recorrido medio %.2f ATR\n" % (base, sum(x['mov'] for x in D) / n))


def bloque(sub, etiq):
    if len(sub) < 25:
        return
    a1 = [x for x in sub if x['f'] < CORTE]
    a2 = [x for x in sub if x['f'] >= CORTE]
    print("%-34s %5d %7.1f%% %8.2f %8s %8s"
          % (etiq, len(sub), 100.0 * sum(x['malo'] for x in sub) / len(sub),
             sum(x['mov'] for x in sub) / len(sub),
             ("%.1f%%" % (100.0 * sum(x['malo'] for x in a1) / len(a1))) if len(a1) >= 10 else "-",
             ("%.1f%%" % (100.0 * sum(x['malo'] for x in a2) / len(a2))) if len(a2) >= 10 else "-"))


print("=== 1) VELAS CON LA LÍNEA PLANA ANTES DEL FLIP ===")
print("%-34s %5s %8s %8s %8s %8s" % ("grupo", "n", "%malos", "movATR", "A1", "A2"))
for p in range(0, 9):
    bloque([x for x in D if x['plana'] == p], "  linea plana %d bucket(s)" % p)
print()
for u in (2, 3, 4, 5, 6):
    bloque([x for x in D if x['plana'] >= u], "  plana >= %d  (NO ENTRAR)" % u)
    bloque([x for x in D if x['plana'] < u], "  plana <  %d  (sí entrar)" % u)
    print()

print("=== 2) ¿EL PRECIO ROMPIÓ EL TECHO DEL RANGO? (idea 2) ===")
print("%-34s %5s %8s %8s %8s %8s" % ("grupo", "n", "%malos", "movATR", "A1", "A2"))
bloque([x for x in D if x['rompe'] == 1], "  ROMPE el techo del rango")
bloque([x for x in D if x['rompe'] == 0], "  NO rompe")
print()
bloque([x for x in D if x['plana'] >= 3 and x['rompe'] == 1], "  plana>=3 Y rompe (lo mejor?)")
bloque([x for x in D if x['plana'] >= 3 and x['rompe'] == 0], "  plana>=3 y NO rompe (peor?)")
print()

print("=== 2b) LÍNEA PLANA: ¿precio EN CONTRA o LATERAL? (matiz del usuario) ===")
print("%-34s %5s %8s %8s %8s %8s" % ("grupo", "n", "%malos", "movATR", "A1", "A2"))
bloque([x for x in D if x['plana'] >= 2 and x['contra']], "  plana>=2 y precio EN CONTRA")
bloque([x for x in D if x['plana'] >= 2 and x['lateral']], "  plana>=2 y precio LATERAL")
bloque([x for x in D if x['plana'] >= 2 and not x['contra'] and not x['lateral']],
       "  plana>=2 y precio A FAVOR")
bloque([x for x in D if x['contra']], "  precio EN CONTRA (sin filtro plana)")
bloque([x for x in D if x['lateral']], "  precio LATERAL (sin filtro plana)")
print()

print("=== 3) AMPLITUD DEL RANGO PREVIO (en ATR) ===")
print("%-34s %5s %8s %8s %8s %8s" % ("grupo", "n", "%malos", "movATR", "A1", "A2"))
for lo, hi in ((0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.5), (2.5, 99)):
    bloque([x for x in D if lo <= x['rango'] < hi], "  rango %.1f-%.1f ATR" % (lo, hi))
