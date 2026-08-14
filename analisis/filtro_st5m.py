# -*- coding: utf-8 -*-
"""EXPERIMENTO: filtro de regimen con Supertrend de 5-min (causal).
Agrega 1-min -> 5-min (con premarket), ST(7,3) en 5-min = regimen.
Solo se toma la señal 1-min si va alineada con el regimen de la ultima vela 5-min CERRADA.
Diferencial baseline vs filtrado en 08-11/12/13. Premium = mezcla ya construida.
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from simulador_st import simular, CAPITAL_0
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)

DIAS = {"2026-08-11":("20260811",R("spy_tape_20260811_denso.db")),
        "2026-08-12":("20260812",R("spy_tape_ayer.db")),
        "2026-08-13":("20260813",R("spy_tape_20260813_denso.db"))}

def mm(h): return int(h[:2])*60+int(h[3:5])

def bars1(fk):
    con=sqlite3.connect(f"file:{R('spy_bars_pm.db')}?mode=ro",uri=True)
    b=con.execute("select hora,high,low,close from bars_pm where fecha=? order by hora",(fk,)).fetchall()
    con.close(); return b

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

BUCKET = int(sys.argv[1]) if len(sys.argv) > 1 else 5

def regimen_5m(fk, B=BUCKET):
    """Devuelve funcion regimen(minuto_hhmm)-> +1/-1 de la ultima vela de B-min cerrada."""
    b=bars1(fk)
    buck={}
    for h,hi,lo,cl in b:
        s=(mm(h)//B)*B
        a=buck.setdefault(s,{"hi":hi,"lo":lo,"cl":cl})
        a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    starts=sorted(buck)
    HI=[buck[s]["hi"] for s in starts]; LO=[buck[s]["lo"] for s in starts]; CL=[buck[s]["cl"] for s in starts]
    D=st_dir(HI,LO,CL)
    reg={s:D[i] for i,s in enumerate(starts)}
    def regimen(h):
        m=mm(h); s=((m-B)//B)*B   # inicio de la vela B-min anterior (ya cerrada) -> causal
        while s>=starts[0] and s not in reg: s-=B
        return reg.get(s,0)
    return regimen

def senales_pm(fk):
    b=bars1(fk)
    hi=[x[1] for x in b]; lo=[x[2] for x in b]; cl=[x[3] for x in b]; ho=[x[0] for x in b]
    tend=st_dir(hi,lo,cl)
    out=[]; prev=None
    for i in range(len(b)):
        if ho[i]<"09:30" or ho[i]>"16:00": continue
        if tend[i]==0: continue
        if prev is None or tend[i]!=prev: out.append((ho[i],"C" if tend[i]>0 else "P"))
        prev=tend[i]
    return out

print(f"{'dia':>12} {'baseline':>10} {'ST5m-filtro':>12} {'delta':>9}   quitadas")
tb=tf=0.0
for fk,(dk,tape) in DIAS.items():
    reg=regimen_5m(fk); sen=senales_pm(fk)
    sen_f=[]; quit=[]
    for h,r in sen:
        g=reg(h)
        ok=(r=="C" and g>0) or (r=="P" and g<0) or g==0
        (sen_f if ok else quit).append((h,r))
    mix=R(f"spy_prem_mix_{dk}.db")
    _,cb=simular(fk,senales=sen,   db_velas=mix,db_tape=tape,expiry=dk,mid=True)
    _,cf=simular(fk,senales=sen_f, db_velas=mix,db_tape=tape,expiry=dk,mid=True)
    gb=cb-CAPITAL_0; gf=cf-CAPITAL_0; tb+=gb; tf+=gf
    print(f"{fk:>12} {gb:>+9.2f}$ {gf:>+11.2f}$ {gf-gb:>+8.2f}$   {' '.join(f'{h}{r}' for h,r in quit) or '(ninguna)'}")
print(f"{'TOTAL':>12} {tb:>+9.2f}$ {tf:>+11.2f}$ {tf-tb:>+8.2f}$")
