# -*- coding: utf-8 -*-
"""ORDER-FLOW IMBALANCE del SPY (tape TRADES, regla del tick) vs direccion futura.
Lee spy_tape.db (dias completos). Clasifica agresor: uptick=compra, downtick=venta, zero=arrastra.
Agrega por minuto: buy_vol, sell_vol, OFI=buy-sell. close=ultimo precio. Mide lead-lag:
corr(OFI(t), retorno t->t+H) y vs pasado (reactivo). + acierto direccional. HIPOTESIS (pocos dias).
"""
import sqlite3, sys, statistics as st
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
DB = "spy_tape.db"
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
listos = [r[0] for r in c.execute("select fecha from dias_listos order by fecha")]
print(f"dias completos en tape: {listos}")

# construir por-minuto por dia
def corr(xs, ys):
    n=len(xs)
    if n<5: return 0.0
    mx=sum(xs)/n; my=sum(ys)/n
    num=sum((a-mx)*(b-my) for a,b in zip(xs,ys)); dx=(sum((a-mx)**2 for a in xs))**.5; dy=(sum((b-my)**2 for b in ys))**.5
    return num/(dx*dy) if dx and dy else 0.0

OFI={}; CLOSE={}   # (fecha,minuto)-> valor
for f in listos:
    rows=c.execute("select ts,price,size from trades where fecha=? order by ts",(f,)).fetchall()
    prevp=None; d=0
    perm={}
    for ts,price,size in rows:
        if prevp is not None:
            if price>prevp: d=1
            elif price<prevp: d=-1
        prevp=price
        m=ts[:16]   # YYYY-MM-DD HH:MM
        bs=perm.setdefault(m,[0.0,0.0,price])
        if d>=0: bs[0]+=size
        else: bs[1]+=size
        bs[2]=price
    for m,(bv,sv,cl) in perm.items():
        OFI[(f,m)]=bv-sv; CLOSE[(f,m)]=cl

# lead-lag por dia (no cruzar dias)
print("="*80)
print("ORDER-FLOW IMBALANCE SPY (tick rule) vs retorno futuro — HIPOTESIS (pocos dias)")
print("="*80)
print(f"{'H (min)':>8} | {'corr(OFI, ret futuro)':>22} | {'acierto signo':>14}")
for H in (-5,-1,1,3,5,8):
    xs=[]; ys=[]; ok=tot=0
    for f in listos:
        ms=sorted(m for (ff,m) in OFI if ff==f)
        idx={m:k for k,m in enumerate(ms)}
        for k in range(len(ms)):
            kf=k+H
            if 0<=kf<len(ms):
                of=OFI[(f,ms[k])]; ret=CLOSE[(f,ms[kf])]-CLOSE[(f,ms[k])]
                xs.append(of); ys.append(ret)
                if H>0 and of!=0:
                    ok+= (1 if (of>0)==(ret>0) else 0); tot+=1
    acc = f"{100*ok/tot:.1f}% (n={tot})" if (H>0 and tot) else "-"
    print(f"  t->t{H:+d} | {corr(xs,ys):>22.3f} | {acc:>14}")
print("\n(H>0 corr>0 => OFI ADELANTA al precio [util]. H<0 => precio adelanta a OFI [reactivo].)")
print("="*80)
