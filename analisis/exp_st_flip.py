# -*- coding: utf-8 -*-
"""SISTEMA ST PURO (flip-exit, sin trail) — timing EJECUTABLE.
   Idea (usuario, 2026-08-14): sin trail; entrar en el flip del ST y DAR VUELTA la posicion
   en el flip opuesto (obedecer la señal). Usa simular(salir_en_flip=True, trail=99=off).
   Señal: ST N-min. Entrada REALISTA: label + N (confirmacion del bucket), sin look-ahead.
   Reutiliza st_dir/shift_sen/build_tmp/stats/simular REALES (R3/R9). skip 09:45, bid/ask.

   Corrida verificada 2026-08-14 (premium sintetico):
     ST-1min -> DESASTRE (whipsaw, muere por costos): A1 -17350 / A2 -4555
     ST-2min -> ~breakeven
     ST-3min skip09:45 -> A1 +7195 / A2 +7654  (POSITIVO ambos, OOS robusto)  <-- mejor
   Caso 2026-03-10 (peor dia del combo trail-ancho, -593): con flip-exit da +483
     (obedece el flip UP de 10:33 que antes ignoraba).
   CAVEAT: premium SINTETICO con holds largos (theta) -> pendiente validar premium real.
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra
from year_backtest import st_dir
from reverifica_dias_malos import stats
from exp_trail_2min import build_tmp, TMP
from exp_timing_realista import shift_sen
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
def mm(h): return int(h[:2])*60+int(h[3:5])
def hhmm(m): return f"{m//60:02d}:{m%60:02d}"

def sen_Nmin(bars, N):
    """ST en velas de N-min (premarket calienta el ATR). Flips RTH. Label = inicio del bucket."""
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

def corre(modelo, db):
    con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
    dias=[r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    acc={(n,sk):[] for n in (1,2,3) for sk in (None,"09:45")}
    for fk in dias:
        dk=fk.replace("-","")
        bars=con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rth=[(h,cl,hi,lo,cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rth)<300: continue
        build_tmp(modelo,fk,dk,rth)   # velas 1-min
        for n in (1,2,3):
            sen=sen_Nmin(bars,n)
            if not sen: continue
            senr=shift_sen(sen,n)     # timing realista: confirmacion = label + n
            for sk in (None,"09:45"):
                _,c=simular(fk,senales=senr,trail=99.0,db_velas=TMP,db_tape=None,expiry=dk,
                            mid=False,mag_umbral=None,size_cap=400.0,hora_min=sk,salir_en_flip=True)
                acc[(n,sk)].append(c-CAPITAL_0)
    con.close()
    if os.path.exists(TMP): os.remove(TMP)
    return {k:stats(v) for k,v in acc.items() if v}

if __name__=="__main__":
    modelo=calibra(["2026-08-11","2026-08-12","2026-08-13"])
    print("ST PURO · sin trail · flip en cada senal · timing realista", flush=True)
    r1=corre(modelo,R("spy_bars_year.db")); r2=corre(modelo,R("spy_bars_year2.db"))
    print(f'{"ST":>3} {"skip":>6} | {"A1 tot":>8} {"A1 verde":>8} | {"A2 tot":>8} {"A2 verde":>8} | ambos+')
    for n in (1,2,3):
        for sk in (None,"09:45"):
            k=(n,sk); s1=r1[k]; s2=r2[k]; ok=s1["tot"]>0 and s2["tot"]>0
            print(f'{n}m {str(sk):>6} | {s1["tot"]:>+7.0f} {s1["verde"]:>7.1f}% | {s2["tot"]:>+7.0f} {s2["verde"]:>7.1f}% | {"** SI **" if ok else ""}')
