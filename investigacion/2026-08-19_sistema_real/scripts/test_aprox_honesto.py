# -*- coding: utf-8 -*-
# APROXIMACION A LA LINEA DEL ST -> ¿PREDICE EL MERCADO?  485 sesiones, desglose A1/A2.
# Objetivo INDEPENDIENTE (no el veredicto de reb2): recorrido favorable real del precio medido
# DESDE EL MINUTO EN QUE SE DECIDE. Criterio `falso` = recorrido < 1.0 ATR (rebote.py:177).
# Barrido de predictores x k velas x umbral. Se reporta separacion y desglose por año.
import sqlite3, sys, statistics as stt

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import sen_p, reb2
from sys2.core.supertrend import mm, hhmm

KS = [2, 3, 4, 6]
UMBRALES = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

con = sqlite3.connect(RAIZ + r"\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
CORTE = FECHAS[len(FECHAS) // 2]

D = []          # un registro por (flip, k)
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
        r = reb2(L, ks, ik, h, d)
        malo_reb2 = 1 if ((not r) or (r[0][1] != d)) else 0
        fin = flips[n_ + 1][0] if n_ + 1 < len(flips) else "15:59"

        def recorrido(desde):
            seg = [cl_[t] for t in horas if desde <= t <= fin]
            if len(seg) < 3:
                return None
            return max((y - seg[0]) * lado for y in seg) / atr

        for k in KS:
            dd = []
            for j in range(i + 1, i + 1 + k):
                x = L[ks[j]]
                dd.append(abs((x['lo'] if lado > 0 else x['hi']) - x['linea']) / atr)
            if len(dd) < k:
                continue
            hd = hhmm(ks[i + k] + 3)               # la vela i+k ya cerro (convencion shift_sen +3)
            mv = recorrido(hd)
            if mv is None:
                continue
            nac = 0
            for q in range(1, len(dd)):
                nac = nac + 1 if dd[q] < dd[q - 1] else 0
            mx = stt.mean(range(len(dd))); my = stt.mean(dd)
            den = sum((q - mx) ** 2 for q in range(len(dd))) or 1
            pend = sum((q - mx) * (dd[q] - my) for q in range(len(dd))) / den
            D.append(dict(f=f, k=k, dmin=min(dd), dult=dd[-1], pend=pend, nac=nac,
                          mov=mv, malo=1 if mv < 1.0 else 0, malo_reb2=malo_reb2))

print("n registros=%d  |  corte A1/A2 = %s  |  objetivo: recorrido<1.0 ATR desde la DECISION"
      % (len(D), CORTE))

# ── 0) demostracion de la fuga: mismo predictor, objetivo reb2 vs objetivo mercado ──
print("\n== FUGA DE OBJETIVO (k=4, dmin<=1.0) ==")
S = [x for x in D if x['k'] == 4]
a = [x for x in S if x['dmin'] <= 1.0]; b = [x for x in S if x['dmin'] > 1.0]
for nom, key in (("objetivo reb2 (el del test de ayer)", 'malo_reb2'),
                 ("objetivo MERCADO desde la decision", 'malo')):
    pa = 100.0 * sum(x[key] for x in a) / len(a)
    pb = 100.0 * sum(x[key] for x in b) / len(b)
    print("  %-38s se acerco %.1f%%  |  no %.1f%%  |  brecha %+.1f pts"
          % (nom, pa, pb, pa - pb))

# ── 1) barrido de predictores ──
def evalua(sub, cond, etiq):
    a = [x for x in sub if cond(x)]
    b = [x for x in sub if not cond(x)]
    if len(a) < 60 or len(b) < 60:
        return None
    pa = 100.0 * sum(x['malo'] for x in a) / len(a)
    pb = 100.0 * sum(x['malo'] for x in b) / len(b)
    ma = sum(x['mov'] for x in a) / len(a)
    mb = sum(x['mov'] for x in b) / len(b)
    # mismo corte, por año
    def por(anio):
        aa = [x for x in a if (x['f'] < CORTE) == anio]
        bb = [x for x in b if (x['f'] < CORTE) == anio]
        if len(aa) < 20 or len(bb) < 20:
            return float('nan')
        return (100.0 * sum(x['malo'] for x in aa) / len(aa)
                - 100.0 * sum(x['malo'] for x in bb) / len(bb))
    return dict(etiq=etiq, n=len(a), pa=pa, pb=pb, br=pa - pb, ma=ma, mb=mb,
                a1=por(True), a2=por(False))

res = []
for k in KS:
    S = [x for x in D if x['k'] == k]
    if not S:
        continue
    for u in UMBRALES:
        res.append(evalua(S, lambda x, u=u: x['dmin'] <= u, "k=%d  dmin<=%.2f" % (k, u)))
        res.append(evalua(S, lambda x, u=u: x['dult'] <= u, "k=%d  dult<=%.2f" % (k, u)))
    res.append(evalua(S, lambda x: x['pend'] < 0, "k=%d  pendiente<0 (se acerca)" % k))
    res.append(evalua(S, lambda x: x['nac'] >= 2, "k=%d  2+ velas acercandose" % k))
    res.append(evalua(S, lambda x: x['dmin'] <= 1.0 and x['pend'] < 0,
                      "k=%d  dmin<=1.0 Y pendiente<0" % k))

res = [x for x in res if x]
res.sort(key=lambda x: -x['br'])
print("\n== PREDICTORES ordenados por brecha (%malos si dispara - %malos si no) ==")
print("%-30s %6s %8s %8s %8s %8s %8s %7s %7s"
      % ("filtro", "n", "%malos", "%malos", "brecha", "movSI", "movNO", "brA1", "brA2"))
print("%-30s %6s %8s %8s %8s %8s %8s %7s %7s"
      % ("", "", "SI", "NO", "pts", "ATR", "ATR", "pts", "pts"))
for x in res[:18]:
    print("%-30s %6d %8.1f %8.1f %+8.1f %8.2f %8.2f %+7.1f %+7.1f"
          % (x['etiq'], x['n'], x['pa'], x['pb'], x['br'], x['ma'], x['mb'], x['a1'], x['a2']))
print("\n(brecha POSITIVA = el filtro identifica flips peores -> sirve para NO entrar)")
