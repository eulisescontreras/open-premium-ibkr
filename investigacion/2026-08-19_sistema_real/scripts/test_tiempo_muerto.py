# -*- coding: utf-8 -*-
# ¿LA LÍNEA PLANA = TIEMPO MUERTO?  — LA PRUEBA CORRECTA de la hipótesis del usuario.
#
# EL TEST ANTERIOR (`test_linea_plana.py`) MEDÍA OTRA COSA: solo miraba los flips del ST-3, o sea
# lo que pasa DESPUÉS del tramo plano. Pero un flip implica, por definición, que la línea acaba
# de saltar de lado — así que medía un caso raro, no el que describe el usuario.
#
# LO QUE DICE EL USUARIO: "cuando la línea se mantiene estable vela por vela el precio se
# lateraliza; eso es TIEMPO MUERTO QUE NO SE DEBERÍA TRADEAR". Eso es sobre lo que ocurre
# DURANTE el tramo plano, no sobre el flip que lo cierra.
#
# PRUEBA CORRECTA: para CADA bucket del día (no solo los flips), contar cuántos buckets lleva la
# línea sin moverse EN ESE MOMENTO (solo pasado) y medir qué hace el precio DESPUÉS:
#   - recorrido absoluto en los siguientes 4 y 12 buckets (12 y 36 min)  -> ¿hay movimiento?
#   - |desplazamiento neto| / recorrido  = EFICIENCIA -> ¿va a algún sitio o solo oscila?
# Si la hipótesis es cierta: a más buckets planos, MENOS recorrido y MENOS eficiencia después.
#
# Y se mide sobre TODAS LAS SEÑALES del sistema (no solo ST-3): ORB y aperturas también caen
# dentro de tramos planos y son las que el usuario querría filtrar.
import sqlite3, sys, statistics as stt

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import st_lin_p, sen_p
from sys2.core.supertrend import mm, hhmm

con = sqlite3.connect(RAIZ + r"\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
CORTE = FECHAS[len(FECHAS) // 2]

B = []          # un registro por BUCKET (todos, no solo flips)
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
        if not ("09:45" <= h <= "15:30"):
            continue
        atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
        if atr <= 0:
            continue
        # cuántos buckets lleva la línea SIN MOVERSE hasta AHORA (solo pasado)
        plana = 0
        for j in range(i, max(0, i - 60), -1):
            if abs(L[ks[j]]['linea'] - L[ks[j - 1]]['linea']) < 1e-9:
                plana += 1
            else:
                break
        # qué hace el precio DESPUÉS (esto es el objetivo, no el predictor)
        for k_, etiq in ((4, "4b"), (12, "12b")):
            cls = [L[ks[j]]['cl'] for j in range(i, i + k_ + 1)]
            his = [L[ks[j]]['hi'] for j in range(i, i + k_ + 1)]
            los = [L[ks[j]]['lo'] for j in range(i, i + k_ + 1)]
            recorrido = (max(his) - min(los)) / atr           # cuánto se movió (rango)
            neto = abs(cls[-1] - cls[0]) / atr                # cuánto avanzó de verdad
            camino = sum(abs(cls[j] - cls[j - 1]) for j in range(1, len(cls))) / atr
            efic = neto / camino if camino > 0 else 0         # 1 = recto, 0 = puro ruido
            B.append(dict(f=f, plana=plana, k=etiq, recorrido=recorrido, neto=neto, efic=efic,
                          d=L[ks[i]]['d']))

n4 = [x for x in B if x['k'] == "4b"]
n12 = [x for x in B if x['k'] == "12b"]
print("buckets analizados: %d   |   corte A1/A2: %s\n" % (len(n4), CORTE))


def tabla(datos, titulo):
    print("=== %s ===" % titulo)
    print("%-26s %7s %9s %9s %9s %8s %8s"
          % ("línea plana", "n", "recorrido", "neto", "eficiencia", "recA1", "recA2"))
    base_r = stt.mean(x['recorrido'] for x in datos)
    base_e = stt.mean(x['efic'] for x in datos)
    print("%-26s %7d %9.3f %9.3f %9.3f" % ("TODOS (base)", len(datos), base_r,
                                           stt.mean(x['neto'] for x in datos), base_e))
    for lo, hi in ((0, 1), (1, 3), (3, 6), (6, 11), (11, 16), (16, 21), (21, 31), (31, 999)):
        sub = [x for x in datos if lo <= x['plana'] < hi]
        p = "%d-%d" % (lo, hi - 1)
        if len(sub) < 40:
            continue
        a1 = [x for x in sub if x['f'] < CORTE]
        a2 = [x for x in sub if x['f'] >= CORTE]
        print("%-26s %7d %9.3f %9.3f %9.3f %8s %8s"
              % ("  plana %s" % p, len(sub), stt.mean(x['recorrido'] for x in sub),
                 stt.mean(x['neto'] for x in sub), stt.mean(x['efic'] for x in sub),
                 ("%.3f" % stt.mean(x['recorrido'] for x in a1)) if len(a1) >= 20 else "-",
                 ("%.3f" % stt.mean(x['recorrido'] for x in a2)) if len(a2) >= 20 else "-"))
    print()
    for u in (3, 6, 11, 16, 21, 26):
        pl = [x for x in datos if x['plana'] >= u]
        no = [x for x in datos if x['plana'] < u]
        if len(pl) < 40 or len(no) < 40:
            continue
        rp, rn = stt.mean(x['recorrido'] for x in pl), stt.mean(x['recorrido'] for x in no)
        ep, en = stt.mean(x['efic'] for x in pl), stt.mean(x['efic'] for x in no)
        print("  plana>=%d: recorrido %.3f vs %.3f (%+.1f%%) | eficiencia %.3f vs %.3f (%+.1f%%)"
              % (u, rp, rn, 100.0 * (rp - rn) / rn, ep, en, 100.0 * (ep - en) / en))
    print()


tabla(n4, "SIGUIENTES 4 BUCKETS (12 min)")
tabla(n12, "SIGUIENTES 12 BUCKETS (36 min)")

# ── y sobre las SEÑALES REALES del sistema (ST-3), que es donde se decide operar ──
print("=== ¿CUÁNTAS SEÑALES CAEN EN TRAMO PLANO? ===")
S = []
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
        if i is None or i < 14 or i + 12 > len(ks) - 1:
            continue
        lado = 1 if d == 'C' else -1
        atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
        if atr <= 0:
            continue
        # planitud EN EL TRAMO PREVIO (saltando los 2 buckets del cambio de lado)
        plana = 0
        for j in range(i - 3, max(0, i - 60), -1):
            if abs(L[ks[j]]['linea'] - L[ks[j - 1]]['linea']) < 1e-9:
                plana += 1
            else:
                break
        fin = flips[n_ + 1][0] if n_ + 1 < len(flips) else "15:59"
        seg = [cl_[z] for z in horas if h <= z <= fin]
        if len(seg) < 3:
            continue
        mov = max((y - seg[0]) * lado for y in seg) / atr
        S.append(dict(f=f, plana=plana, mov=mov, malo=1 if mov < 1.0 else 0))

if S:
    bs = 100.0 * sum(x['malo'] for x in S) / len(S)
    print("señales: %d | base %.1f%% malos, recorrido %.2f ATR" % (len(S), bs, stt.mean(x['mov'] for x in S)))
    print("%-26s %7s %9s %9s %8s %8s" % ("línea plana previa", "n", "%malos", "movATR", "A1", "A2"))
    for u in (3, 6, 11, 16, 21):
        for et, sub in (("plana>=%d" % u, [x for x in S if x['plana'] >= u]),
                        ("plana<%d" % u, [x for x in S if x['plana'] < u])):
            if len(sub) < 30:
                continue
            a1 = [x for x in sub if x['f'] < CORTE]
            a2 = [x for x in sub if x['f'] >= CORTE]
            print("%-26s %7d %8.1f%% %9.2f %8s %8s"
                  % ("  " + et, len(sub), 100.0 * sum(x['malo'] for x in sub) / len(sub),
                     stt.mean(x['mov'] for x in sub),
                     ("%.1f%%" % (100.0 * sum(x['malo'] for x in a1) / len(a1))) if len(a1) >= 15 else "-",
                     ("%.1f%%" % (100.0 * sum(x['malo'] for x in a2) / len(a2))) if len(a2) >= 15 else "-"))
        print()
