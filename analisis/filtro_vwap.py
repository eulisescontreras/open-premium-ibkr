# -*- coding: utf-8 -*-
"""EXPERIMENTO: filtro de tendencia por VWAP (causal, sin lookahead).
Solo se toma la señal si va del lado del VWAP: CALL si precio>=VWAP, PUT si precio<=VWAP.
Diferencial baseline (sin filtro) vs filtrado, en 08-11/12/13.

VWAP = acumulado del tape (sum price*size / sum size) por minuto.
Señales ST premarket; premium = mezcla real+sintetica ya construida (spy_prem_mix_*.db).
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

DIAS = {
    "2026-08-11": ("20260811", R("spy_tape_20260811_denso.db")),
    "2026-08-12": ("20260812", R("spy_tape_ayer.db")),
    "2026-08-13": ("20260813", R("spy_tape_20260813_denso.db")),
}

def spy_min(fk):
    con = sqlite3.connect(f"file:{R('spy_bars_pm.db')}?mode=ro", uri=True)
    d = {h: c for h, c in con.execute("select hora,close from bars_pm where fecha=? and hora>='09:30' and hora<='16:00'", (fk,))}
    con.close(); return d

def vwap_min(tape):
    """VWAP acumulado por minuto desde el tape (trades_raw)."""
    con = sqlite3.connect(f"file:{tape}?mode=ro", uri=True)
    rows = con.execute("select minuto, price, size from trades_raw order by ts_et").fetchall()
    con.close()
    out = {}; cum_pv = 0.0; cum_v = 0.0
    for m, p, s in rows:
        h = m[-5:] if len(m) > 5 else m
        cum_pv += p * s; cum_v += s
        out[h] = cum_pv / cum_v if cum_v else p
    return out

def senales_pm(fk):
    con = sqlite3.connect(f"file:{R('spy_bars_pm.db')}?mode=ro", uri=True)
    b = con.execute("select hora,high,low,close from bars_pm where fecha=? order by hora", (fk,)).fetchall()
    con.close()
    hi=[x[1] for x in b]; lo=[x[2] for x in b]; cl=[x[3] for x in b]; ho=[x[0] for x in b]
    n=len(cl); tr=[0.0]*n
    for i in range(1,n): tr[i]=max(hi[i]-lo[i],abs(hi[i]-cl[i-1]),abs(lo[i]-cl[i-1]))
    atr=[None]*n
    if n>7:
        atr[7]=sum(tr[1:8])/7
        for i in range(8,n): atr[i]=(atr[i-1]*6+tr[i])/7
    tend=[0]*n; fu=fl=None; d=1
    for i in range(n):
        if atr[i] is None: continue
        med=(hi[i]+lo[i])/2; bu=med+3.0*atr[i]; bl=med-3.0*atr[i]
        fu=bu if (fu is None or bu<fu or cl[i-1]>fu) else fu
        fl=bl if (fl is None or bl>fl or cl[i-1]<fl) else fl
        if d==1 and cl[i]<fl: d=-1
        elif d==-1 and cl[i]>fu: d=1
        tend[i]=d
    out=[]; prev=None
    for i in range(n):
        if ho[i]<"09:30" or ho[i]>"16:00": continue
        if tend[i]==0: continue
        if prev is None or tend[i]!=prev: out.append((ho[i],"C" if tend[i]>0 else "P"))
        prev=tend[i]
    return out

print(f"{'dia':>12} {'baseline':>10} {'VWAP-filtro':>12} {'delta':>9}   señales quitadas")
tot_b=tot_f=0.0
for fk,(dk,tape) in DIAS.items():
    S=spy_min(fk); V=vwap_min(tape)
    sen=senales_pm(fk)
    # filtro: CALL solo si precio>=VWAP ; PUT solo si precio<=VWAP
    sen_f=[]; quit=[]
    for h,r in sen:
        s=S.get(h); v=V.get(h)
        if s is None or v is None: sen_f.append((h,r)); continue
        ok = (r=="C" and s>=v) or (r=="P" and s<=v)
        (sen_f if ok else quit).append((h,r))
    mix=R(f"spy_prem_mix_{dk}.db")
    _,cb=simular(fk,senales=sen,   db_velas=mix,db_tape=tape,expiry=dk,mid=True)
    _,cf=simular(fk,senales=sen_f, db_velas=mix,db_tape=tape,expiry=dk,mid=True)
    gb=cb-CAPITAL_0; gf=cf-CAPITAL_0; tot_b+=gb; tot_f+=gf
    print(f"{fk:>12} {gb:>+9.2f}$ {gf:>+11.2f}$ {gf-gb:>+8.2f}$   quitadas: {' '.join(f'{h}{r}' for h,r in quit) or '(ninguna)'}")
print(f"{'TOTAL':>12} {tot_b:>+9.2f}$ {tot_f:>+11.2f}$ {tot_f-tot_b:>+8.2f}$")
