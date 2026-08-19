# -*- coding: utf-8 -*-
# APROXIMACION A LA LINEA MEDIDA MINUTO A MINUTO (no cada 4 velas de 3 min).
#
# POR QUE: con velas de 3 min hay que esperar k=4 (15 min) para ver la señal, y ese retraso
# cuesta -4.356$ en el motor (control `hn_esp_k4`), mas de lo que el filtro salva (+2.494$).
# La LINEA del ST solo necesita el bucket CERRADO; el PRECIO se puede mirar cada minuto.
# -> se puede decidir a los 1-6 minutos del flip en vez de a los 15.
#
# HONESTO: en el minuto t se usa la linea del ultimo bucket CERRADO ((mm(t)//3)*3 - 3) y las
# barras de 1 min hasta t. Objetivo = recorrido favorable real DESDE t (< 1.0 ATR = malo).
import sqlite3, sys

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import sen_p
from sys2.core.supertrend import mm, hhmm

MINS = [1, 2, 3, 4, 5, 6, 9, 12]          # minutos de observacion tras el flip
UMBR = [0.25, 0.4, 0.5, 0.6, 0.75, 1.0, 1.25]

con = sqlite3.connect(RAIZ + r"\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
CORTE = FECHAS[len(FECHAS) // 2]

D = []
for f in FECHAS:
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                       (f,)).fetchall()
    if len(bars) < 100:
        continue
    B = {h: (hi, lo, cl) for h, hi, lo, cl in bars}
    cl_ = {h: v[2] for h, v in B.items() if "09:30" <= h <= "16:00"}
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
        dmin = None                       # distancia minima vista hasta el minuto t
        for m in range(1, max(MINS) + 1):
            t = hhmm(mm(h) + m)
            if t not in B:
                continue
            kv = (mm(t) // 3) * 3 - 3     # ultimo bucket CERRADO en el minuto t
            x = L.get(kv)
            if x is None:
                continue
            punta = B[t][1] if lado > 0 else B[t][0]      # low si CALL, high si PUT
            dis = abs(punta - x['linea']) / atr
            dmin = dis if dmin is None else min(dmin, dis)
            if m not in MINS:
                continue
            seg = [cl_[z] for z in horas if t <= z <= fin]
            if len(seg) < 3:
                continue
            mov = max((y - seg[0]) * lado for y in seg) / atr
            D.append(dict(f=f, m=m, dmin=dmin, dult=dis, mov=mov,
                          malo=1 if mov < 1.0 else 0))

print("n=%d  corte A1/A2=%s  |  objetivo: recorrido<1.0 ATR desde el minuto de decision"
      % (len(D), CORTE))


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
for m in MINS:
    S = [x for x in D if x['m'] == m]
    if not S:
        continue
    for u in UMBR:
        res.append(evalua(S, lambda x, u=u: x['dmin'] <= u, "%2d min  dmin<=%.2f" % (m, u)))
        res.append(evalua(S, lambda x, u=u: x['dult'] <= u, "%2d min  dult<=%.2f" % (m, u)))
res = [x for x in res if x]
res.sort(key=lambda x: -min(x['a1'], x['a2']))
print("\n== ordenados por ROBUSTEZ (peor año primero) ==")
print("%-22s %5s %7s %7s %7s %6s %6s %7s %7s"
      % ("filtro", "n", "%maloSI", "%maloNO", "brecha", "movSI", "movNO", "brA1", "brA2"))
for x in res[:20]:
    print("%-22s %5d %7.1f %7.1f %+7.1f %6.2f %6.2f %+7.1f %+7.1f"
          % (x['etiq'], x['n'], x['pa'], x['pb'], x['br'], x['ma'], x['mb'], x['a1'], x['a2']))
