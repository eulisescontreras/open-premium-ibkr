# -*- coding: utf-8 -*-
# ESPERA CONDICIONAL (idea del usuario 2026-08-19 tarde):
#   "si la vela siguiente supera a la del flip -> se entra de una vez, no hay que esperar.
#    si retrocede, queda por debajo o la diferencia es minima -> se espera (y ahi se mira la linea)"
#
# POR QUE IMPORTA: medido hoy, la señal de aproximacion vale +2.494$ pero exige esperar 15 min,
# y ese retraso cuesta -4.356$ (control `hn_esp_k4`). La espera condicional paga el peaje SOLO
# en los flips dudosos.
#
# ARITMETICA VERIFICADA contra rebote.sen_p (emite en el bucket del flip y aplica shift +3):
#   i = ik[(mm(h)//3)*3]  ->  i-1 = vela QUE GENERO el flip ; i = 1a post ; i+1 = 2a post
# Objetivo HONESTO: recorrido favorable real desde el minuto en que se entra (<1.0 ATR = malo).
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

        def mov(desde):
            seg = [cl_[z] for z in horas if desde <= z <= fin]
            if len(seg) < 3:
                return None
            return max((y - seg[0]) * lado for y in seg) / atr

        V = L[ks[i - 1]]                      # la vela QUE GENERO el flip
        ref_cl = V['cl']
        ref_ext = V['hi'] if lado > 0 else V['lo']    # su extremo a favor
        p1, p2 = L[ks[i]], L[ks[i + 1]]               # 1a y 2a vela despues del flip
        # avance de cada vela post-flip respecto a la del flip, en ATR
        av1 = (p1['cl'] - ref_cl) * lado / atr
        av2 = (p2['cl'] - ref_cl) * lado / atr
        ex2 = (p2['cl'] - ref_ext) * lado / atr       # criterio duro: supera su extremo
        # distancia a la linea en la 2a vela (para el caso "hay que esperar")
        dl2 = abs((p2['lo'] if lado > 0 else p2['hi']) - p2['linea']) / atr
        m0 = mov(h)                                   # entrar YA (lo que hace el sistema)
        m1 = mov(hhmm(ks[i] + 3))                     # entrar tras la 1a vela  (h+3)
        m2 = mov(hhmm(ks[i + 1] + 3))                 # entrar tras la 2a vela  (h+6)
        if None in (m0, m1, m2):
            continue
        D.append(dict(f=f, av1=av1, av2=av2, ex2=ex2, dl2=dl2,
                      m0=m0, m1=m1, m2=m2))

print("n flips=%d   corte A1/A2=%s" % (len(D), CORTE))
base_malo = 100.0 * sum(1 for x in D if x['m0'] < 1.0) / len(D)
print("BASE (entrar YA en el flip): %.1f%% malos, recorrido medio %.2f ATR\n"
      % (base_malo, sum(x['m0'] for x in D) / len(D)))


def grupo(sub, campo_mov, etiq):
    if len(sub) < 40:
        return None
    pm = 100.0 * sum(1 for x in sub if x[campo_mov] < 1.0) / len(sub)
    mv = sum(x[campo_mov] for x in sub) / len(sub)
    a1 = [x for x in sub if x['f'] < CORTE]
    a2 = [x for x in sub if x['f'] >= CORTE]
    p1 = 100.0 * sum(1 for x in a1 if x[campo_mov] < 1.0) / len(a1) if len(a1) >= 15 else float('nan')
    p2 = 100.0 * sum(1 for x in a2 if x[campo_mov] < 1.0) / len(a2) if len(a2) >= 15 else float('nan')
    return (etiq, len(sub), pm, mv, p1, p2)


print("== ¿'la vela post-flip supera a la del flip' SELECCIONA BIEN? ==")
print("   (entrar tras esa vela; %malos y recorrido medidos DESDE ahi)")
print("%-42s %5s %8s %7s %7s %7s" % ("grupo", "n", "%malos", "movATR", "%malA1", "%malA2"))
for U in (0.0, 0.15, 0.25, 0.4, 0.6):
    for campo, mv_, nom, cuando in (("av1", "m1", "1a vela cl", "h+3"),
                                    ("av2", "m2", "2a vela cl", "h+6")):
        r = grupo([x for x in D if x[campo] >= U], mv_, "%s avanza >=%.2f ATR -> entra %s"
                  % (nom, U, cuando))
        if r:
            print("%-42s %5d %8.1f %7.2f %7.1f %7.1f" % r)
print()
r = grupo([x for x in D if x['ex2'] >= 0], "m2", "2a vela SUPERA el extremo del flip -> h+6")
if r:
    print("%-42s %5d %8.1f %7.2f %7.1f %7.1f" % r)

print("\n== EL RESTO (no avanza) : ¿ahi funciona el filtro de la linea? ==")
print("%-42s %5s %8s %7s %7s %7s" % ("grupo", "n", "%malos", "movATR", "%malA1", "%malA2"))
for U in (0.0, 0.15, 0.25):
    resto = [x for x in D if x['av2'] < U]
    for etiq, sub in (("resto completo", resto),
                      ("resto Y pegado a la linea (dl2<=1.0)",
                       [x for x in resto if x['dl2'] <= 1.0]),
                      ("resto y NO pegado (dl2>1.0)",
                       [x for x in resto if x['dl2'] > 1.0])):
        r = grupo(sub, "m2", "av2<%.2f | %s" % (U, etiq))
        if r:
            print("%-42s %5d %8.1f %7.2f %7.1f %7.1f" % r)
