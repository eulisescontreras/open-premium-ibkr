# -*- coding: utf-8 -*-
"""VERIFICACION del JUEZ OOS (reproduce los numeros TITULARES de INVESTIGACION_0DTE_SISTEMA.md).
   Config titular: bid/ask (mid=False) + skip apertura 09:45 (hora_min) + sizing fijo $400 (size_cap)
   + magnitud OFF + trail 0.04%. Reutiliza simular() y synth_premium REALES (R3/R9).
   Corrida verificada 2026-08-14:
       AÑO1 (tune, 261 dias): +16074.60$  ·  63.2% verde   (doc: +15.761 / 63%)
       AÑO2 (OOS,  251 dias): +11574.90$  ·  60.2% verde   (doc: +11.273 / 61%)
   -> el edge base SE REPLICA en el año2 independiente. Delta ~2-3% vs doc (config inline
      original no quedo guardada bit-exact); direccion y conclusion se sostienen.
   Premium SINTETICO (candado #1): calibrado en 08-11/12/13. NO valida contra premium real.
"""
import os, sys, sqlite3, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra, extr, ttc
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
TMP = R("_tmp_verif.db")
def mm(h): return int(h[:2])*60+int(h[3:5])
def hhmm(m): return f"{m//60:02d}:{m%60:02d}"

def st_dir(hi,lo,cl,per=7,mult=3.0):
    n=len(cl); tr=[0.0]*n
    for i in range(1,n): tr[i]=max(hi[i]-lo[i],abs(hi[i]-cl[i-1]),abs(lo[i]-cl[i-1]))
    atr=[None]*n
    if n>per:
        atr[per]=sum(tr[1:per+1])/per
        for i in range(per+1,n): atr[i]=(atr[i-1]*(per-1)+tr[i])/per
    tend=[0]*n; fu=fl=None; d=1
    for i in range(n):
        if atr[i] is None: continue
        med=(hi[i]+lo[i])/2; bu=med+mult*atr[i]; bl=med-mult*atr[i]
        fu=bu if (fu is None or bu<fu or cl[i-1]>fu) else fu
        fl=bl if (fl is None or bl>fl or cl[i-1]<fl) else fl
        if d==1 and cl[i]<fl: d=-1
        elif d==-1 and cl[i]>fu: d=1
        tend[i]=d
    return tend

def sen_2min(bars):
    B=2; buck={}
    for h,hi,lo,cl in bars:
        s=(mm(h)//B)*B
        a=buck.setdefault(s,{"hi":hi,"lo":lo,"cl":cl,"h":hhmm(s)})
        a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    st=sorted(buck); HI=[buck[s]["hi"] for s in st]; LO=[buck[s]["lo"] for s in st]
    CL=[buck[s]["cl"] for s in st]; HO=[buck[s]["h"] for s in st]
    D=st_dir(HI,LO,CL); out=[]; prev=None
    for i in range(len(st)):
        if HO[i]<"09:30" or HO[i]>"16:00": continue
        if D[i]==0: continue
        if prev is None or D[i]!=prev: out.append((HO[i],"C" if D[i]>0 else "P"))
        prev=D[i]
    return out

def corre_year(modelo, db, etiqueta, trail=0.04, hora_min="09:45", size_cap=400.0, mid=False):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dias = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    pnl=0.0; win=0; ndays=0; peor=1e9; mejor=-1e9; suma_malos=0.0
    for fk in dias:
        dk = fk.replace("-","")
        bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rth = [(h, cl, hi, lo, cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rth) < 300: continue
        S = {h:cl for h,o,hi,lo,cl in rth}
        sen = sen_2min(bars)
        if not sen: continue
        smin=min(S.values()); smax=max(S.values())
        k0=int(math.floor(smin))-3; k1=int(math.ceil(smax))+3
        if os.path.exists(TMP): os.remove(TMP)
        d=sqlite3.connect(TMP)
        d.execute("CREATE TABLE bars_minute (fecha TEXT,hora TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
        d.executemany("insert into bars_minute values (?,?,?,?,?,?,0)", [(fk,h,o,hi,lo,cl) for h,o,hi,lo,cl in rth])
        d.execute("CREATE TABLE premium_minute (fecha TEXT,hora TEXT,expiry TEXT,strike REAL,right TEXT,bid REAL,ask REAL)")
        filas=[]
        for h,s in S.items():
            t=ttc(h)
            for K in range(k0,k1+1):
                for r in ("C","P"):
                    intr=max(s-K,0.0) if r=="C" else max(K-s,0.0)
                    dep=(s-K) if r=="C" else (K-s)
                    mid_v=max(intr+extr(modelo,dep,t),0.01)
                    bid=mid_v*0.99; ask=mid_v*1.01   # spread 2% realista (medido en contratos reales)
                    filas.append((fk,h,dk,float(K),r,bid,ask))
        d.executemany("insert into premium_minute values (?,?,?,?,?,?,?)", filas)
        d.commit(); d.close()
        _,c = simular(fk, senales=sen, trail=trail, db_velas=TMP, db_tape=None, expiry=dk,
                      mid=mid, mag_umbral=None, size_cap=size_cap, hora_min=hora_min)
        g=c-CAPITAL_0
        pnl+=g; ndays+=1; win+=(1 if g>0 else 0)
        peor=min(peor,g); mejor=max(mejor,g)
        if g<0: suma_malos+=g
    con.close()
    if os.path.exists(TMP): os.remove(TMP)
    print(f"\n=== {etiqueta} · trail {trail}% · skip {hora_min} · size_cap ${size_cap:.0f} · bid/ask ===")
    print(f"  dias operados : {ndays}")
    print(f"  TOTAL         : {pnl:+.2f}$")
    print(f"  %dias verdes  : {100*win/ndays:.1f}%")
    print(f"  suma malos    : {suma_malos:+.2f}$")
    print(f"  peor / mejor  : {peor:+.2f}$ / {mejor:+.2f}$")
    return pnl

if __name__ == "__main__":
    modelo = calibra(["2026-08-11","2026-08-12","2026-08-13"])
    print(f"modelo sintetico calibrado ({len(modelo)} buckets). Corriendo juez OOS...", flush=True)
    corre_year(modelo, R("spy_bars_year.db"),  "AÑO1 (tune)")
    corre_year(modelo, R("spy_bars_year2.db"), "AÑO2 (OOS)")
