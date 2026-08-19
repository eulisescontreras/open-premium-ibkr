# -*- coding: utf-8 -*-
# FASE 1 — ¿DONDE ESTA EL DINERO DEL LOOK-AHEAD?  (485 sesiones)
#
# reb2 con vision de 12 buckets no hace UNA cosa, hace CUATRO:
#   NORMAL   -> entra en h, direccion d           (lo mismo que hace el vivo)
#   RETRASA  -> entra en hh>h, misma direccion    (mueve la entrada)
#   INVIERTE -> entra en hh, direccion CONTRARIA  (le da la vuelta)
#   DESCARTA -> no entra
# El vivo (1 bucket) devuelve NORMAL SIEMPRE -> las otras 3 son la brecha de -28.864$.
# Sin saber cuanto aporta CADA UNA no se puede buscar el sustituto honesto correcto.
#
# Se mide el recorrido favorable real (en ATR) que habria capturado cada decision:
#   vivo  = entrar en h en direccion d               (lo que hace hoy el sistema)
#   reb2  = lo que decide reb2 con vision completa
# `malo` = recorrido < 1.0 ATR (criterio de rebote.clasificar_dia:177).
import sqlite3, sys

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import sen_p, reb2, _grupo
from sys2.core.supertrend import mm

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
        if i is None or i < 11 or i + 12 > len(ks) - 1:
            continue
        lado = 1 if d == 'C' else -1
        atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
        if atr <= 0:
            continue
        fin = flips[n_ + 1][0] if n_ + 1 < len(flips) else "15:59"

        def rec(desde, lad):
            seg = [cl_[z] for z in horas if desde <= z <= fin]
            if len(seg) < 3:
                return None
            return max((y - seg[0]) * lad for y in seg) / atr

        r = reb2(L, ks, ik, h, d)
        g = _grupo(r, h, d)
        mv_vivo = rec(h, lado)                       # lo que hace el sistema hoy
        if mv_vivo is None:
            continue
        mv_reb = None
        if r:
            he, df = r[0]
            lad2 = 1 if df == 'C' else -1
            mv_reb = rec(he, lad2)
        D.append(dict(f=f, g=g, vivo=mv_vivo, reb=mv_reb,
                      dur=len([z for z in horas if h <= z <= fin])))

n = len(D)
print("FLIPS analizados: %d   |   corte A1/A2 = %s\n" % (n, CORTE))

print("== REPARTO DE FLIPS Y QUE CAPTURA CADA DECISION (recorrido favorable, ATR) ==")
print("%-10s %6s %6s %10s %10s %10s %10s"
      % ("grupo", "n", "%", "vivo mov", "reb2 mov", "vivo %mal", "reb2 %mal"))
tot_v = tot_r = 0.0
for g in ("NORMAL", "RETRASA", "INVIERTE", "DESCARTA"):
    S = [x for x in D if x['g'] == g]
    if not S:
        continue
    mv = sum(x['vivo'] for x in S) / len(S)
    pv = 100.0 * sum(1 for x in S if x['vivo'] < 1.0) / len(S)
    con_reb = [x for x in S if x['reb'] is not None]
    mr = sum(x['reb'] for x in con_reb) / len(con_reb) if con_reb else 0.0
    pr = (100.0 * sum(1 for x in con_reb if x['reb'] < 1.0) / len(con_reb)) if con_reb else 0.0
    print("%-10s %6d %5.1f%% %10.2f %10s %9.1f%% %10s"
          % (g, len(S), 100.0 * len(S) / n, mv,
             ("%.2f" % mr) if con_reb else "-- (no entra)",
             pv, ("%.1f%%" % pr) if con_reb else "--"))
    tot_v += mv * len(S)
    tot_r += (mr * len(con_reb)) if con_reb else 0.0

print("\nTOTAL recorrido capturado (suma ATR sobre los %d flips):" % n)
print("  vivo (entra SIEMPRE en h)          %10.1f" % tot_v)
print("  reb2 (con vision de 12 buckets)    %10.1f   dif %+.1f" % (tot_r, tot_r - tot_v))

print("\n== VALOR DE CADA DECISION vs EL VIVO (ATR acumulados; + = reb2 gana) ==")
print("%-10s %6s %12s %12s %12s %10s %10s"
      % ("decision", "n", "vivo suma", "reb2 suma", "diferencia", "difA1", "difA2"))
for g in ("RETRASA", "INVIERTE", "DESCARTA"):
    S = [x for x in D if x['g'] == g]
    if not S:
        continue
    sv = sum(x['vivo'] for x in S)
    sr = sum((x['reb'] or 0.0) for x in S)
    d1 = sum((x['reb'] or 0.0) - x['vivo'] for x in S if x['f'] < CORTE)
    d2 = sum((x['reb'] or 0.0) - x['vivo'] for x in S if x['f'] >= CORTE)
    print("%-10s %6d %12.1f %12.1f %+12.1f %+10.1f %+10.1f"
          % (g, len(S), sv, sr, sr - sv, d1, d2))

print("\n== DETALLE INVIERTE: ¿de verdad gana al darle la vuelta? ==")
S = [x for x in D if x['g'] == 'INVIERTE' and x['reb'] is not None]
if S:
    gana = sum(1 for x in S if x['reb'] > x['vivo'])
    print("  n=%d   reb2 captura mas en %d casos (%.1f%%)   media vivo %.2f -> reb2 %.2f"
          % (len(S), gana, 100.0 * gana / len(S),
             sum(x['vivo'] for x in S) / len(S), sum(x['reb'] for x in S) / len(S)))

print("\n== DETALLE DESCARTA: ¿cuanto se ahorra por no entrar? ==")
S = [x for x in D if x['g'] == 'DESCARTA']
if S:
    base_mv = sum(x['vivo'] for x in D) / n
    print("  n=%d   el vivo habria capturado %.2f ATR de media (media global %.2f)"
          % (len(S), sum(x['vivo'] for x in S) / len(S), base_mv))
    print("  %% malos de los descartados: %.1f%%   (global %.1f%%)"
          % (100.0 * sum(1 for x in S if x['vivo'] < 1.0) / len(S),
             100.0 * sum(1 for x in D if x['vivo'] < 1.0) / n))
