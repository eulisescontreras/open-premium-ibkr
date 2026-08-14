# -*- coding: utf-8 -*-
"""4 combinaciones dual-timeframe en el MISMO motor (read-only, en memoria). Timing ejecutable.
   Motor generico sim(entry_events, exit_dir_by_h):
     - ENTRA/ROTA en un evento de entry_events (flip del TF de entrada, direccion del evento).
     - SALE A PLANO si exit_dir_by_h[h] (dir del TF lento) esta EN CONTRA (None = desactivado).
     - CIERRE 15:59 aplana. skip 09:45, STOP_NEW 15:40. Compra deepest-ITM (elegir_contrato REAL).
   Variantes:
     A) pura ST-3 flip-exit  = entry3, exit=None   (baseline conocido: +7195 / +7654)
     B) pura ST-1 flip-exit  = entry1, exit=None   (conocido: -17350 / -4555)  [cross-check]
     C) entra ST-3 / sale ST-1 = entry3, exit=d1   (ya medido: -1415 / -2813)
     D) entra ST-1 / sale ST-3 = entry1, exit=d3   <-- LO PEDIDO
   Reutiliza elegir_contrato/COMISION/FRAC_TOPE/CAPITAL_0, st_dir, sen_Nmin, synth, stats (R9).
"""
import os, sys, sqlite3, math
REPO=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import elegir_contrato, COMISION, FRAC_TOPE, CAPITAL_0
from year_backtest import st_dir
from exp_st_flip import sen_Nmin
from synth_premium import calibra, extr, ttc
from reverifica_dias_malos import stats
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
def mm(h): return int(h[:2])*60+int(h[3:5])
def hhmm(m): return f"{m//60:02d}:{m%60:02d}"
SKIP="09:45"; STOP_NEW="15:40"; CIERRE="15:59"; TOPE=CAPITAL_0*FRAC_TOPE

def build_P(modelo,S):
    smin=min(S.values()); smax=max(S.values()); k0=int(math.floor(smin))-3; k1=int(math.ceil(smax))+3
    P={}
    for h,s in S.items():
        t=ttc(h)
        for K in range(k0,k1+1):
            for r in ("C","P"):
                intr=max(s-K,0.0) if r=="C" else max(K-s,0.0); dep=(s-K) if r=="C" else (K-s)
                mid=max(intr+extr(modelo,dep,t),0.01); P[(float(K),r,h)]=(mid*0.99,mid*1.01)
    return P

def entradas_N(bars, N):
    """flips del ST-N -> {hora_realista (label+N): dir}."""
    out={}
    for h,lado in sen_Nmin(bars,N):
        out[hhmm(mm(h)+N)] = (1 if lado=="C" else -1)
    return out

def dirN_realista(bars, N):
    """dir del ST-N conocida en cada minuto RTH (ultimo bucket N-min cerrado: label+N <= minuto)."""
    buck={}
    for h,hi,lo,cl in bars:
        s=(mm(h)//N)*N; a=buck.setdefault(s,{"hi":hi,"lo":lo,"cl":cl})
        a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    labs=sorted(buck); HI=[buck[s]["hi"] for s in labs]; LO=[buck[s]["lo"] for s in labs]; CL=[buck[s]["cl"] for s in labs]
    D=st_dir(HI,LO,CL)
    # (label, dir_conocido_a_label+N)
    conf=[(labs[i]+N, D[i]) for i in range(len(labs))]   # dir del bucket i se conoce a label+N
    return conf   # lista (minuto_conf, dir), ordenada

def dir_en(conf, minuto):
    d=None
    for mc,dd in conf:
        if mc<=minuto: d=dd
        else: break
    return d

def sim(horas, entry_events, exit_conf, P):
    cap=CAPITAL_0; pos=None
    for h in horas:
        if h>CIERRE: break
        if pos is not None:
            exit_now=False; rota=None
            if exit_conf is not None:
                de=dir_en(exit_conf, mm(h))
                if de is not None and de!=pos["lado"]: exit_now=True
            if h in entry_events and entry_events[h]!=pos["lado"]:
                exit_now=True; rota=entry_events[h]
            if h>=CIERRE: exit_now=True; rota=None
            if exit_now:
                q=P.get((pos["k"],pos["rt"],h)); venta=q[0] if q else pos["px_in"]
                cap+=(venta-pos["px_in"])*100.0-COMISION; pos=None
                if rota is not None and SKIP<=h<STOP_NEW:
                    rt="C" if rota==1 else "P"; el=elegir_contrato(P,h,rt,TOPE,False)
                    if el: k,(bid,ask)=el; pos={"lado":rota,"k":k,"rt":rt,"px_in":ask}
                continue
        if pos is None and h in entry_events and SKIP<=h<STOP_NEW:
            lado=entry_events[h]; rt="C" if lado==1 else "P"; el=elegir_contrato(P,h,rt,TOPE,False)
            if el: k,(bid,ask)=el; pos={"lado":lado,"k":k,"rt":rt,"px_in":ask}
    return cap-CAPITAL_0

def corre(modelo, db):
    con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
    dias=[r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    acc={k:[] for k in ("A","B","C","D")}
    for fk in dias:
        bars=con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rthb=[(h,hi,lo,cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rthb)<300: continue
        S={h:cl for h,hi,lo,cl in rthb}; horas=sorted(S,key=mm)
        e3=entradas_N(bars,3); e1=entradas_N(bars,1)
        if not e3 or not e1: continue
        c1=dirN_realista(bars,1); c3=dirN_realista(bars,3)
        P=build_P(modelo,S)
        acc["A"].append(sim(horas,e3,None,P))
        acc["B"].append(sim(horas,e1,None,P))
        acc["C"].append(sim(horas,e3,c1,P))
        acc["D"].append(sim(horas,e1,c3,P))
    con.close()
    return {k:stats(v) for k,v in acc.items()}

if __name__=="__main__":
    modelo=calibra(["2026-08-11","2026-08-12","2026-08-13"])
    nom={"A":"pura ST-3 flip-exit","B":"pura ST-1 flip-exit","C":"entra ST-3 / sale ST-1","D":"entra ST-1 / sale ST-3  <-- pedido"}
    for et,db in (("AÑO1","spy_bars_year.db"),("AÑO2 OOS","spy_bars_year2.db")):
        r=corre(modelo,os.path.join(REPO,db))
        print(f"\n{et} (skip 09:45, timing realista):")
        for k in ("A","B","C","D"):
            s=r[k]; print(f"  {nom[k]:<34} total {s['tot']:>+8.0f}$  verde {s['verde']:.1f}%  ratio {s['ratio']:.2f}")
