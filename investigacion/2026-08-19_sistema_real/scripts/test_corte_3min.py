# -*- coding: utf-8 -*-
# CORTES DE ALTA PRECISION CON LA INFORMACION DISPONIBLE A LOS 3 MINUTOS.
#
# POR QUE 3 MIN: medido en el motor, esperar 3 min NO cuesta (+600$ sobre la base honesta),
# mientras que 12 min cuesta -3.912$ y 15 min -4.356$. Todo filtro que exija mas espera ya
# empieza perdiendo. A los 3 min ya cerro la 1a vela post-flip -> es la unica ventana barata.
#
# OBJETIVO DEL USUARIO: no empeorar NINGUNA metrica. Eso exige tocar MUY POCAS operaciones y
# que sean las peores -> aqui se buscan cortes por COBERTURA (%) y PRECISION (%malos), no por
# separacion global.
# Objetivo honesto: recorrido favorable real desde h+3 (< 1.0 ATR = malo).
import sqlite3, sys

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
        if i is None or i < 11 or i + 12 > len(ks) - 1:
            continue
        lado = 1 if d == 'C' else -1
        atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
        if atr <= 0:
            continue
        fin = flips[n_ + 1][0] if n_ + 1 < len(flips) else "15:59"
        seg = [cl_[z] for z in horas if hhmm(ks[i] + 3) <= z <= fin]
        if len(seg) < 3:
            continue
        mov = max((y - seg[0]) * lado for y in seg) / atr
        V, P = L[ks[i - 1]], L[ks[i]]            # vela del flip / 1a vela post-flip
        D.append(dict(
            f=f, mov=mov, malo=1 if mov < 1.0 else 0,
            av=(P['cl'] - V['cl']) * lado / atr,               # avance del cierre
            avx=(P['cl'] - (V['hi'] if lado > 0 else V['lo'])) * lado / atr,   # vs extremo
            dl=abs((P['lo'] if lado > 0 else P['hi']) - P['linea']) / atr,     # mecha a la linea
            dcl=abs(P['cl'] - P['linea']) / atr,               # cierre a la linea
            cuerpo=(P['cl'] - P['o']) * lado / atr,            # cuerpo de la 1a vela
            rango=(P['hi'] - P['lo']) / atr))

n = len(D)
base_malo = 100.0 * sum(x['malo'] for x in D) / n
base_mov = sum(x['mov'] for x in D) / n
print("n=%d flips  |  BASE a h+3: %.1f%% malos, recorrido medio %.2f ATR  |  corte %s"
      % (n, base_malo, base_mov, CORTE))
print("\nBuscando cortes que quiten POCO y MALO (cobertura baja + %malos alto en los DOS años)")
print("%-26s %6s %7s %8s %8s %8s %8s"
      % ("corte (se DESCARTA si...)", "n", "cobert", "%malos", "movATR", "%malA1", "%malA2"))

CAND = []
for camp, nom, ops in (("av", "avance cierre", (-1.0, -0.75, -0.5, -0.35, -0.25, -0.15, 0.0)),
                       ("avx", "avance vs extremo", (-1.5, -1.2, -1.0, -0.8, -0.6)),
                       ("cuerpo", "cuerpo 1a vela", (-1.0, -0.75, -0.5, -0.35, -0.25)),
                       ("dl", "mecha a la linea", (0.15, 0.25, 0.4, 0.5, 0.75)),
                       ("dcl", "cierre a la linea", (0.15, 0.25, 0.4, 0.5, 0.75))):
    for u in ops:
        if camp in ("dl", "dcl"):
            sub = [x for x in D if x[camp] <= u]
        else:
            sub = [x for x in D if x[camp] <= u]
        if len(sub) < 25:
            continue
        a1 = [x for x in sub if x['f'] < CORTE]
        a2 = [x for x in sub if x['f'] >= CORTE]
        if len(a1) < 8 or len(a2) < 8:
            continue
        pm = 100.0 * sum(x['malo'] for x in sub) / len(sub)
        p1 = 100.0 * sum(x['malo'] for x in a1) / len(a1)
        p2 = 100.0 * sum(x['malo'] for x in a2) / len(a2)
        mv = sum(x['mov'] for x in sub) / len(sub)
        print("%-26s %6d %6.1f%% %8.1f %8.2f %8.1f %8.1f"
              % ("%s <= %.2f" % (nom, u), len(sub), 100.0 * len(sub) / n, pm, mv, p1, p2))
        if pm > base_malo + 12 and min(p1, p2) > base_malo + 5 and len(sub) / n < 0.25:
            CAND.append((camp, u, nom, len(sub), pm, mv, p1, p2))

print("\n== CANDIDATOS (cobertura <25%, %malos > base+12, y peor año > base+5) ==")
if not CAND:
    print("  ninguno")
for camp, u, nom, ns, pm, mv, p1, p2 in sorted(CAND, key=lambda x: -min(x[6], x[7])):
    print("  %-22s <= %5.2f   n=%3d (%.1f%%)  malos %.1f%%  mov %.2f  A1 %.1f / A2 %.1f"
          % (nom, u, ns, 100.0 * ns / n, pm, mv, p1, p2))
