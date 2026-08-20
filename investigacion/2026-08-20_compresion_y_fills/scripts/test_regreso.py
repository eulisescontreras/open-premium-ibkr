# -*- coding: utf-8 -*-
# ¿APLANARSE = FIN DE TENDENCIA Y EL PRECIO REGRESA HACIA EL SUPERTREND? (idea del usuario)
# Distinto de lo ya medido: no es "el precio va a favor o en contra", es si la DISTANCIA
# precio-línea se REDUCE. El precio puede ir a favor y aun así acercarse si la línea corre más.
# Y se mide tambien si el ST FLIPEA (fin de tendencia de verdad).
import sqlite3, sys, statistics as stt
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C
from sys2.core.rebote import st_lin_p
from sys2.core.supertrend import mm, hhmm

con = sqlite3.connect(r"C:\Users\eulis\proyectos\open-premium-ibkr\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
CORTE = FECHAS[len(FECHAS)//2]
D = []
for f in FECHAS:
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",(f,)).fetchall()
    if len(bars) < 100: continue
    try: L, ks, Dd = st_lin_p(bars, C.ST_PER, C.ST_MULT)
    except Exception: continue
    for i in range(12, len(ks)-13):
        h = hhmm(ks[i])
        if not ("09:45" <= h <= "15:30"): continue
        atr = sum(L[ks[j]]['hi']-L[ks[j]]['lo'] for j in range(i-10,i+1))/11.0
        if atr <= 0: continue
        plana = 0
        for j in range(i, max(0,i-60), -1):
            if abs(L[ks[j]]['linea']-L[ks[j-1]]['linea']) < 1e-9: plana += 1
            else: break
        d = L[ks[i]]['d']
        dist0 = abs(L[ks[i]]['cl'] - L[ks[i]]['linea'])/atr
        # ¿se ACERCA a la línea en los siguientes 12 buckets? (lo que describe el usuario)
        dmin = min(abs(L[ks[j]]['cl'] - L[ks[j]]['linea'])/atr for j in range(i, i+13))
        dfin = abs(L[ks[i+12]]['cl'] - L[ks[i+12]]['linea'])/atr
        # ¿FLIPEA el ST? (fin de tendencia de verdad)
        flipea = 1 if any(L[ks[j]]['d'] != d for j in range(i+1, i+13)) else 0
        D.append(dict(f=f, plana=plana, dist0=dist0, dmin=dmin, dfin=dfin,
                      acerca=1 if dmin < dist0*0.5 else 0, flipea=flipea))

n=len(D)
b_fl = 100.0*sum(x['flipea'] for x in D)/n
b_ac = 100.0*sum(x['acerca'] for x in D)/n
print("buckets: %d"%n)
print("BASE: %.1f%% flipean en 36 min | %.1f%% se acercan a la linea (dist se parte por 2)"%(b_fl,b_ac))
print()
print("%-18s %7s %10s %10s %9s %9s"%("linea plana","n","%FLIPEA","%acerca","dist0","dist final"))
for lo,hi,et in ((0,1,"0"),(1,3,"1-2"),(3,6,"3-5"),(6,11,"6-10"),(11,16,"11-15"),(16,21,"16-20"),(21,999,"21+")):
    s=[x for x in D if lo<=x['plana']<hi]
    if len(s)<200: continue
    print("%-18s %7d %9.1f%% %9.1f%% %9.2f %9.2f"%("  plana "+et,len(s),
        100.0*sum(x['flipea'] for x in s)/len(s), 100.0*sum(x['acerca'] for x in s)/len(s),
        stt.mean(x['dist0'] for x in s), stt.mean(x['dfin'] for x in s)))
print()
for u in (6,8,16,21):
    pl=[x for x in D if x['plana']>=u]; no=[x for x in D if x['plana']<u]
    if len(pl)<200: continue
    print("  plana>=%2d: FLIPEA %.1f%% vs %.1f%% (%+.1f pts) | se acerca %.1f%% vs %.1f%% (%+.1f pts)"%(
        u, 100.0*sum(x['flipea'] for x in pl)/len(pl), 100.0*sum(x['flipea'] for x in no)/len(no),
        100.0*sum(x['flipea'] for x in pl)/len(pl)-100.0*sum(x['flipea'] for x in no)/len(no),
        100.0*sum(x['acerca'] for x in pl)/len(pl), 100.0*sum(x['acerca'] for x in no)/len(no),
        100.0*sum(x['acerca'] for x in pl)/len(pl)-100.0*sum(x['acerca'] for x in no)/len(no)))
