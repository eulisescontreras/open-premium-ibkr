# -*- coding: utf-8 -*-
# ¿EL PRECIO SE DEVUELVE HACIA LA LINEA DEL ST? — con umbral ABSOLUTO, no relativo.
# CORRECCION: el test anterior definia "se acerca" como dist_min < dist0/2, y eso PENALIZABA
# los tramos planos porque ahi el precio YA esta cerca (dist0 1,67 vs 3,16). Metrica sesgada.
# Aqui se mide en ATR absolutos: ¿llega a TOCAR (<=1.0 ATR, el mismo criterio de reb2)?
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
        d = L[ks[i]]['d']; lado = 1 if d > 0 else -1
        dist0 = abs(L[ks[i]]['cl'] - L[ks[i]]['linea'])/atr
        # ¿la MECHA toca la linea? (criterio de reb2: punta a <=1.0 ATR)
        toca = 0; dmin_abs = 99.0
        for j in range(i+1, i+13):
            x = L[ks[j]]
            punta = x['lo'] if lado > 0 else x['hi']
            dd = abs(punta - x['linea'])/atr
            dmin_abs = min(dmin_abs, dd)
            if dd <= 1.0: toca = 1
        # y el movimiento NETO del precio: ¿va hacia la linea o se aleja?
        neto = (L[ks[i+12]]['cl'] - L[ks[i]]['cl']) * lado / atr   # >0 se aleja, <0 va hacia ella
        D.append(dict(f=f, plana=plana, dist0=dist0, toca=toca, dmin=dmin_abs, neto=neto,
                      vuelve=1 if neto < -0.3 else 0))

n=len(D)
print("buckets: %d"%n)
print("BASE: %.1f%% TOCAN la linea en 36 min | %.1f%% el precio VUELVE hacia ella | dist media %.2f"%(
    100.0*sum(x['toca'] for x in D)/n, 100.0*sum(x['vuelve'] for x in D)/n, stt.mean(x['dist0'] for x in D)))
print()
print("%-16s %7s %10s %10s %9s %9s %8s"%("linea plana","n","%TOCA","%VUELVE","dist0","dist min","A1/A2 toca"))
for lo,hi,et in ((0,1,"0"),(1,3,"1-2"),(3,6,"3-5"),(6,11,"6-10"),(11,16,"11-15"),(16,21,"16-20"),(21,999,"21+")):
    s=[x for x in D if lo<=x['plana']<hi]
    if len(s)<200: continue
    a1=[x for x in s if x['f']<CORTE]; a2=[x for x in s if x['f']>=CORTE]
    print("%-16s %7d %9.1f%% %9.1f%% %9.2f %9.2f  %.0f/%.0f"%("  plana "+et,len(s),
        100.0*sum(x['toca'] for x in s)/len(s), 100.0*sum(x['vuelve'] for x in s)/len(s),
        stt.mean(x['dist0'] for x in s), stt.mean(x['dmin'] for x in s),
        100.0*sum(x['toca'] for x in a1)/max(1,len(a1)), 100.0*sum(x['toca'] for x in a2)/max(1,len(a2))))
print()
for u in (6,8,16):
    pl=[x for x in D if x['plana']>=u]; no=[x for x in D if x['plana']<u]
    print("  plana>=%2d: TOCA %.1f%% vs %.1f%% (%+.1f pts) | VUELVE %.1f%% vs %.1f%% (%+.1f pts)"%(
        u, 100.0*sum(x['toca'] for x in pl)/len(pl), 100.0*sum(x['toca'] for x in no)/len(no),
        100.0*sum(x['toca'] for x in pl)/len(pl)-100.0*sum(x['toca'] for x in no)/len(no),
        100.0*sum(x['vuelve'] for x in pl)/len(pl), 100.0*sum(x['vuelve'] for x in no)/len(no),
        100.0*sum(x['vuelve'] for x in pl)/len(pl)-100.0*sum(x['vuelve'] for x in no)/len(no)))
