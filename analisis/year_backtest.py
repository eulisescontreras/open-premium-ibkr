# -*- coding: utf-8 -*-
"""BACKTEST del AÑO (261 dias) bars-only, magnitud OFF.
  - Señales: ST 2-min desde spy_bars_year.db (con premarket)
  - Premium: SINTETICO (modelo intrinseco+extrinseco calibrado en 08-11/12/13)
  - Trail: sobre el cierre de la vela (db_tape=None)
  - mid=True, mag_umbral=None
Barre el trail (0.04-0.10%) para validar el 0.05% sobre el año completo.
Reutiliza simular() real y el modelo de synth_premium (R9). $ absolutos aproximados
(premium sintetico); lo que importa es la COMPARACION relativa entre trails.
"""
import os, sys, sqlite3, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra, extr, ttc
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
YEAR = R("spy_bars_year.db")
TMP = R("_tmp_day.db")
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

def sen_2min(bars):  # bars = [(hora,hi,lo,cl)] con premarket
    B=2; buck={}
    for h,hi,lo,cl in bars:
        s=(mm(h)//B)*B
        a=buck.setdefault(s,{"hi":hi,"lo":lo,"cl":cl,"h":hhmm(s)})
        a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    st=sorted(buck); HI=[buck[s]["hi"] for s in st]; LO=[buck[s]["lo"] for s in st]; CL=[buck[s]["cl"] for s in st]; HO=[buck[s]["h"] for s in st]
    D=st_dir(HI,LO,CL); out=[]; prev=None
    for i in range(len(st)):
        if HO[i]<"09:30" or HO[i]>"16:00": continue
        if D[i]==0: continue
        if prev is None or D[i]!=prev: out.append((HO[i],"C" if D[i]>0 else "P"))
        prev=D[i]
    return out

def _main():
  modelo = calibra(["2026-08-11","2026-08-12","2026-08-13"])
  print(f"modelo calibrado ({len(modelo)} buckets). Cargando dias del año...", flush=True)

  conY = sqlite3.connect(f"file:{YEAR}?mode=ro", uri=True)
  dias = [r[0] for r in conY.execute("select distinct fecha from bars order by fecha")]
  TRAILS = [0.04,0.05,0.06,0.08,0.10]
  agg = {t:{"pnl":0.0,"win":0,"days":0} for t in TRAILS}
  por_dia = {t:[] for t in TRAILS}

  for fk in dias:
    dk = fk.replace("-","")
    bars = conY.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
    # (h, open~=close, hi, lo, cl) para RTH; no tenemos open real, usamos close como open (no afecta trail)
    rth = [(h, cl, hi, lo, cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
    if len(rth) < 300:   # dia incompleto/medio dia
        continue
    S = {h:cl for h,o,hi,lo,cl in rth}
    sen = sen_2min(bars)
    if not sen:
        continue
    # rango de strikes del dia
    smin=min(S.values()); smax=max(S.values())
    k0=int(math.floor(smin))-3; k1=int(math.ceil(smax))+3
    # construir tmp db: bars_minute (RTH) + premium_minute sintetico
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
                mid=max(intr+extr(modelo,dep,t),0.01)
                filas.append((fk,h,dk,float(K),r,mid,mid))
    d.executemany("insert into premium_minute values (?,?,?,?,?,?,?)", filas)
    d.commit(); d.close()
    for t in TRAILS:
        _,c = simular(fk, senales=sen, trail=t, db_velas=TMP, db_tape=None, expiry=dk, mid=True, mag_umbral=None)
        g=c-CAPITAL_0
        agg[t]["pnl"]+=g; agg[t]["days"]+=1; agg[t]["win"]+= (1 if g>0 else 0); por_dia[t].append(g)
  conY.close()
  if os.path.exists(TMP): os.remove(TMP)

  print(f"\nBACKTEST AÑO ({agg[TRAILS[0]]['days']} dias) · 2-min · premium sintetico · magnitud OFF")
  print(f"{'trail':>6} | {'TOTAL':>12} {'prom/dia':>9} {'%dias+':>7} {'mejor':>9} {'peor':>9}")
  for t in TRAILS:
    a=agg[t]; pd=por_dia[t]
    prom=a["pnl"]/a["days"]; wr=100*a["win"]/a["days"]
    print(f"{t:>5.2f}% | {a['pnl']:>+11.2f}$ {prom:>+8.2f}$ {wr:>6.1f}% {max(pd):>+8.2f}$ {min(pd):>+8.2f}$")

if __name__ == "__main__":
  _main()
