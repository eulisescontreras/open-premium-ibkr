# -*- coding: utf-8 -*-
# BUSQUEDA AMPLIA del mejor predictor de "flip que no va a rendir", con objetivo HONESTO:
# recorrido favorable real del precio DESDE EL MINUTO DE LA DECISION (< 1.0 ATR = malo).
# 485 sesiones, desglose A1/A2. Predictores que describen lo que se VE en el grafico:
#   dmin/dult/d2   : distancia de la mecha a la linea (minima / ultima / mejor de las 2 ultimas)
#   pend           : pendiente de esa distancia (negativa = acercandose)
#   cruce          : el CIERRE quedo al otro lado de la linea (la rompio)
#   contra         : velas contrarias a la direccion del flip
#   compresion     : dult / dd[0]  (se esta comiendo la distancia inicial)
import sqlite3, sys, statistics as stt

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import sen_p
from sys2.core.supertrend import mm, hhmm

KS = [2, 3, 4, 6]
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
        for k in KS:
            V = [L[ks[j]] for j in range(i + 1, i + 1 + k)]
            if len(V) < k:
                continue
            dd = [abs((x['lo'] if lado > 0 else x['hi']) - x['linea']) / atr for x in V]
            hd = hhmm(ks[i + k] + 3)
            seg = [cl_[t] for t in horas if hd <= t <= fin]
            if len(seg) < 3:
                continue
            mov = max((y - seg[0]) * lado for y in seg) / atr
            mx = stt.mean(range(len(dd))); my = stt.mean(dd)
            den = sum((q - mx) ** 2 for q in range(len(dd))) or 1
            pend = sum((q - mx) * (dd[q] - my) for q in range(len(dd))) / den
            D.append(dict(f=f, k=k, mov=mov, malo=1 if mov < 1.0 else 0,
                          dmin=min(dd), dult=dd[-1], d2=min(dd[-2:]),
                          pend=pend,
                          cruce=1 if any((x['cl'] - x['linea']) * lado < 0 for x in V) else 0,
                          contra=sum(1 for x in V if (x['cl'] - x['o']) * lado < 0),
                          comp=dd[-1] / dd[0] if dd[0] > 0 else 9.9))

print("n=%d  corte A1/A2=%s  objetivo: recorrido<1.0 ATR desde la DECISION" % (len(D), CORTE))


def evalua(sub, cond, etiq):
    a = [x for x in sub if cond(x)]
    b = [x for x in sub if not cond(x)]
    if len(a) < 60 or len(b) < 60:
        return None
    pa = 100.0 * sum(x['malo'] for x in a) / len(a)
    pb = 100.0 * sum(x['malo'] for x in b) / len(b)

    def por(y):
        aa = [x for x in a if (x['f'] < CORTE) == y]
        bb = [x for x in b if (x['f'] < CORTE) == y]
        if len(aa) < 20 or len(bb) < 20:
            return float('nan')
        return (100.0 * sum(x['malo'] for x in aa) / len(aa)
                - 100.0 * sum(x['malo'] for x in bb) / len(bb))
    return dict(etiq=etiq, n=len(a), pa=pa, pb=pb, br=pa - pb,
                ma=sum(x['mov'] for x in a) / len(a), mb=sum(x['mov'] for x in b) / len(b),
                a1=por(True), a2=por(False))


res = []
for k in KS:
    S = [x for x in D if x['k'] == k]
    if not S:
        continue
    for u in (0.4, 0.5, 0.6, 0.75, 0.9, 1.0, 1.25, 1.5):
        for v in ("dmin", "dult", "d2"):
            res.append(evalua(S, lambda x, u=u, v=v: x[v] <= u, "k=%d %s<=%.2f" % (k, v, u)))
    res.append(evalua(S, lambda x: x['cruce'] == 1, "k=%d cierre CRUZA la linea" % k))
    res.append(evalua(S, lambda x: x['comp'] <= 0.5, "k=%d compresion<=0.5" % k))
    res.append(evalua(S, lambda x: x['contra'] >= 2, "k=%d 2+ velas contrarias" % k))
    for u in (0.75, 1.0):
        res.append(evalua(S, lambda x, u=u: x['dult'] <= u and x['pend'] < 0,
                          "k=%d dult<=%.2f Y acercandose" % (k, u)))
        res.append(evalua(S, lambda x, u=u: x['dult'] <= u or x['cruce'] == 1,
                          "k=%d dult<=%.2f O cruza" % (k, u)))

res = [x for x in res if x]
# ordenar por robustez: la MENOR de las dos brechas anuales (que funcione en los dos años)
res.sort(key=lambda x: -min(x['a1'], x['a2']))
print("\n== ordenados por ROBUSTEZ (peor de los dos años primero) ==")
print("%-30s %5s %7s %7s %7s %6s %6s %7s %7s"
      % ("filtro", "n", "%maloSI", "%maloNO", "brecha", "movSI", "movNO", "brA1", "brA2"))
for x in res[:20]:
    print("%-30s %5d %7.1f %7.1f %+7.1f %6.2f %6.2f %+7.1f %+7.1f"
          % (x['etiq'], x['n'], x['pa'], x['pb'], x['br'], x['ma'], x['mb'], x['a1'], x['a2']))
