# -*- coding: utf-8 -*-
"""BACKTEST del AÑO (261 dias) CON MAGNITUD FICTICIA derivada del volumen.
Mapeo cuantil volumen->|NET| calibrado en los 4 dias con tape (08-10..13), aplicado a
todo el año. Inyecta esa magnitud via simular(net_ext=...). Barre el trail, compara ON vs OFF.

  Señales: ST 2-min (spy_bars_year.db, con premarket)
  Premium: sintetico (modelo intrinseco+extrinseco)
  Trail:   sobre la vela (db_tape=None)
  Magnitud: FICTICIA (volumen->|NET| cuantil)  vs  OFF
$ absolutos aproximados; lo robusto es la comparacion relativa (trails, ON vs OFF).
"""
import os, sys, sqlite3, math, bisect
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
YEAR = R("spy_bars_year.db"); TMP = R("_tmp_day_mag.db")
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
        s=(mm(h)//B)*B; a=buck.setdefault(s,{"hi":hi,"lo":lo,"cl":cl,"h":hhmm(s)})
        a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    st=sorted(buck); HI=[buck[s]["hi"] for s in st]; LO=[buck[s]["lo"] for s in st]; CL=[buck[s]["cl"] for s in st]; HO=[buck[s]["h"] for s in st]
    D=st_dir(HI,LO,CL); out=[]; prev=None
    for i in range(len(st)):
        if HO[i]<"09:30" or HO[i]>"16:00": continue
        if D[i]==0: continue
        if prev is None or D[i]!=prev: out.append((HO[i],"C" if D[i]>0 else "P"))
        prev=D[i]
    return out

# ---- mapeo volumen->|NET| con los 4 dias con tape ----
def net_real(tape):
    con=sqlite3.connect(f"file:{tape}?mode=ro",uri=True); NET={}; prev=None
    for m,p,s in con.execute("select minuto,price,size from trades_raw order by ts_et"):
        h=m[-5:] if len(m)>5 else m
        sg=0 if prev is None else (1 if p>prev else (-1 if p<prev else 0)); prev=p
        NET[h]=NET.get(h,0.0)+sg*s*p
    con.close(); return {h:abs(v) for h,v in NET.items() if "09:30"<=h<="16:00"}
def vol_year(fk):
    con=sqlite3.connect(f"file:{YEAR}?mode=ro",uri=True)
    d={h:v for h,v in con.execute("select hora,volume from bars where fecha=? and hora>='09:30' and hora<='16:00'",(fk,))}
    con.close(); return d
TAPEDIAS={"2026-08-10":"spy_tape_20260810_denso.db","2026-08-11":"spy_tape_20260811_denso.db",
          "2026-08-12":"spy_tape_20260812_denso.db","2026-08-13":"spy_tape_20260813_denso.db"}
pv=[]; pn=[]
for fk,tp in TAPEDIAS.items():
    NR=net_real(R(tp)); VO=vol_year(fk)
    for h in sorted(set(NR)&set(VO)):
        pv.append(VO[h]); pn.append(NR[h])
pv_s=sorted(pv); pn_s=sorted(pn); L=len(pn_s)
def mapv(v):
    pct=bisect.bisect_right(pv_s,v)/max(1,len(pv_s))
    return pn_s[min(L-1,int(pct*(L-1)))]
print(f"mapeo volumen->|NET| calibrado con {L} minutos de 4 dias con tape", flush=True)

modelo = calibra(["2026-08-11","2026-08-12","2026-08-13"])
conY = sqlite3.connect(f"file:{YEAR}?mode=ro", uri=True)
dias = [r[0] for r in conY.execute("select distinct fecha from bars order by fecha")]
TRAILS=[0.04,0.05,0.06,0.08,0.10]
res={("ON",t):{"pnl":0.0,"win":0,"n":0,"pd":[]} for t in TRAILS}
res.update({("OFF",t):{"pnl":0.0,"win":0,"n":0,"pd":[]} for t in TRAILS})

for fk in dias:
    dk=fk.replace("-","")
    bars=conY.execute("select hora,high,low,close,volume from bars where fecha=? order by hora",(fk,)).fetchall()
    rth=[(h,cl,hi,lo,cl) for (h,hi,lo,cl,v) in bars if "09:30"<=h<="16:00"]
    if len(rth)<300: continue
    S={h:cl for h,o,hi,lo,cl in rth}
    vold={h:v for (h,hi,lo,cl,v) in bars if "09:30"<=h<="16:00"}
    sen=sen_2min([(h,hi,lo,cl) for (h,hi,lo,cl,v) in bars])
    if not sen: continue
    fict={h:mapv(vold.get(h,0.0)) for h in S}
    smin=min(S.values()); smax=max(S.values()); k0=int(math.floor(smin))-3; k1=int(math.ceil(smax))+3
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
                filas.append((fk,h,dk,float(K),r,max(intr+extr(modelo,dep,t),0.01),max(intr+extr(modelo,dep,t),0.01)))
    d.executemany("insert into premium_minute values (?,?,?,?,?,?,?)", filas); d.commit(); d.close()
    for t in TRAILS:
        _,con_=simular(fk,senales=sen,trail=t,db_velas=TMP,db_tape=None,expiry=dk,mid=True,mag_umbral=0.8,net_ext=fict)
        _,cof=simular(fk,senales=sen,trail=t,db_velas=TMP,db_tape=None,expiry=dk,mid=True,mag_umbral=None)
        for tag,c in (("ON",con_),("OFF",cof)):
            g=c-CAPITAL_0; r=res[(tag,t)]; r["pnl"]+=g; r["n"]+=1; r["win"]+=(1 if g>0 else 0); r["pd"].append(g)
conY.close()
if os.path.exists(TMP): os.remove(TMP)

print(f"\nBACKTEST AÑO ({res[('ON',0.04)]['n']} dias) · 2-min · premium sintetico")
print(f"{'trail':>6} | {'MAG FICTICIA':>13} {'%d+':>5} | {'MAG OFF':>11} {'%d+':>5} | {'gana mag':>9}")
for t in TRAILS:
    a=res[("ON",t)]; b=res[("OFF",t)]
    print(f"{t:>5.2f}% | {a['pnl']:>+12.2f}$ {100*a['win']/a['n']:>4.0f}% | {b['pnl']:>+10.2f}$ {100*b['win']/b['n']:>4.0f}% | {a['pnl']-b['pnl']:>+8.2f}$")
