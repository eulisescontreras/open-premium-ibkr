# -*- coding: utf-8 -*-
"""PAISAJE COMPLETO (timing REALISTA, sin look-ahead):
   barre (ST timeframe) x (trail grid timeframe) x (trail %) y reporta positivo-ambos-años.
   Señal: ST en N_st-min (confirmada en label+N_st). Entrada: primera vela del grid de trail
   >= confirmacion (ejecutable). Trail: sobre cierres del grid de N_tr-min. skip 09:45, bid/ask.
   Reutiliza st_dir/simular/synth_premium/build_tmp REALES (R3/R9).
"""
import os, sys, sqlite3
REPO=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra
from year_backtest import st_dir
from reverifica_dias_malos import stats
from exp_trail_2min import build_tmp, TMP
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
def R(p): return os.path.join(REPO,p)
def mm(h): return int(h[:2])*60+int(h[3:5])
def hhmm(m): return f"{m//60:02d}:{m%60:02d}"

def agrega(rth, N):
    buck={}
    for h,o,hi,lo,cl in rth:
        s=(mm(h)//N)*N; a=buck.get(s)
        if a is None: buck[s]={"o":o,"hi":hi,"lo":lo,"cl":cl}
        else: a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    return [(hhmm(s),buck[s]["o"],buck[s]["hi"],buck[s]["lo"],buck[s]["cl"]) for s in sorted(buck)]

def sen_Nmin(bars, N):
    """ST en velas de N-min (con premarket para calentar), flips en horario RTH. Label=inicio bucket."""
    buck={}
    for h,hi,lo,cl in bars:
        s=(mm(h)//N)*N; a=buck.setdefault(s,{"hi":hi,"lo":lo,"cl":cl})
        a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    st=sorted(buck); HI=[buck[s]["hi"] for s in st]; LO=[buck[s]["lo"] for s in st]; CL=[buck[s]["cl"] for s in st]; HO=[hhmm(s) for s in st]
    D=st_dir(HI,LO,CL); out=[]; prev=None
    for i in range(len(st)):
        if HO[i]<"09:30" or HO[i]>"16:00": continue
        if D[i]==0: continue
        if prev is None or D[i]!=prev: out.append((HO[i],"C" if D[i]>0 else "P"))
        prev=D[i]
    return out

def snap_sen(sen, N_st, grid):
    gl=sorted(grid, key=mm); out={}
    for h,lado in sen:
        tr=mm(h)+N_st                                   # confirmacion = fin del bucket del ST
        g=next((x for x in gl if mm(x)>=tr), None)
        if g is not None: out[g]=lado
    return [(g,out[g]) for g in sorted(out, key=mm)]

def snap_hora(h, grid):
    gl=sorted(grid,key=mm); return next((x for x in gl if mm(x)>=mm(h)), gl[-1])

STS=[2,3]; GRIDS=[1,2,3]; TRAILS=[0.04,0.10,0.30,1.00]

def corre(modelo, db):
    con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
    dias=[r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    acc={(a,b,t):[] for a in STS for b in GRIDS for t in TRAILS}
    for fk in dias:
        dk=fk.replace("-","")
        bars=con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rth=[(h,cl,hi,lo,cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rth)<300: continue
        sens={a:sen_Nmin(bars,a) for a in STS}
        for b in GRIDS:
            velas=agrega(rth,b); grid=[v[0] for v in velas]
            build_tmp(modelo,fk,dk,velas)
            skipG=snap_hora("09:45",grid)
            for a in STS:
                senA=snap_sen(sens[a],a,grid)
                if not senA: continue
                for t in TRAILS:
                    _,c=simular(fk,senales=senA,trail=t,db_velas=TMP,db_tape=None,expiry=dk,mid=False,mag_umbral=None,size_cap=400.0,hora_min=skipG)
                    acc[(a,b,t)].append(c-CAPITAL_0)
    con.close()
    if os.path.exists(TMP): os.remove(TMP)
    return {k:stats(v) for k,v in acc.items() if v}

if __name__=="__main__":
    modelo=calibra(["2026-08-11","2026-08-12","2026-08-13"])
    print("corriendo AÑO1...",flush=True); r1=corre(modelo,R("spy_bars_year.db"))
    print("corriendo AÑO2...",flush=True); r2=corre(modelo,R("spy_bars_year2.db"))
    print(f"\n{'ST':>3} {'trailTF':>7} {'trail%':>7} | {'A1 total':>9} {'A1 verde':>8} | {'A2 total':>9} {'A2 verde':>8} | ambos+")
    for a in STS:
     for b in GRIDS:
      for t in TRAILS:
        k=(a,b,t)
        if k not in r1 or k not in r2: continue
        s1=r1[k]; s2=r2[k]; ok = s1['tot']>0 and s2['tot']>0
        print(f"{a:>2}m {b:>6}m {t:>6.2f}% | {s1['tot']:>+8.0f} {s1['verde']:>7.1f}% | {s2['tot']:>+8.0f} {s2['verde']:>7.1f}% | {'** SI **' if ok else ''}")
