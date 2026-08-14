# -*- coding: utf-8 -*-
"""EXPERIMENTO: adaptar el TRAIL al timeframe del ST (2-min).
   Contexto: el ST se pasó de 1-min a 2-min porque mejoraba, PERO el trail siguió
   corriendo sobre velas de 1-min (simulador_st.py:164-165,184 -> loop en B de 1-min).
   Hipótesis del usuario: alinear el trail a 2-min (misma resolución que el ST) puede
   dejar de cortar entradas de dirección correcta por dips de ruido de 1-min.

   Differential (R8): MISMAS señales (ST 2-min), MISMA config (skip 09:45, size_cap 400,
   bid/ask). Lo ÚNICO que cambia es la GRILLA de las velas que ve simular():
     - BASELINE : velas 1-min  -> trail vigila retroceso minuto a minuto (sistema actual)
     - VARIANTE : velas 2-min  -> trail vigila retroceso cada 2 min (+ fills a cierre 2-min)
   OJO honesto (R2/R7): pasar las velas a 2-min cambia también el precio de fill de
   entrada/salida al cierre de 2-min (no solo el trail). Es la versión "todo 2-min".
   No toca simular() (R11/R15): se logra alimentando velas+premium agregados a 2-min.

   REGLA OOS (R8): una mejora SOLO cuenta si se sostiene en AMBOS años.
"""
import os, sys, sqlite3, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra, extr, ttc
from year_backtest import sen_2min
from reverifica_dias_malos import stats     # R9: reutilizar metrica
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
TMP = R("_tmp_trail2m.db")
def mm(h): return int(h[:2])*60+int(h[3:5])
def hhmm(m): return f"{m//60:02d}:{m%60:02d}"

TRAIL_BASE = 0.04
SIZE_CAP = 400.0
SKIP = "09:45"

def agrega_2min(rth):
    """rth = [(h,o,hi,lo,cl)] 1-min -> velas 2-min [(h,o,hi,lo,cl)] con label = inicio del bucket."""
    buck = {}
    for h,o,hi,lo,cl in rth:
        s = (mm(h)//2)*2
        a = buck.get(s)
        if a is None: buck[s] = {"o":o,"hi":hi,"lo":lo,"cl":cl}
        else:
            a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl  # o = primer open del bucket
    out=[]
    for s in sorted(buck):
        a=buck[s]; out.append((hhmm(s), a["o"], a["hi"], a["lo"], a["cl"]))
    return out

def build_tmp(modelo, fk, dk, velas):
    """velas = [(h,o,hi,lo,cl)] (1-min o 2-min). Construye bars_minute + premium_minute a esa grilla."""
    S = {h:cl for h,o,hi,lo,cl in velas}
    smin=min(S.values()); smax=max(S.values())
    k0=int(math.floor(smin))-3; k1=int(math.ceil(smax))+3
    if os.path.exists(TMP): os.remove(TMP)
    d=sqlite3.connect(TMP)
    d.execute("CREATE TABLE bars_minute (fecha TEXT,hora TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    d.executemany("insert into bars_minute values (?,?,?,?,?,?,0)", [(fk,h,o,hi,lo,cl) for h,o,hi,lo,cl in velas])
    d.execute("CREATE TABLE premium_minute (fecha TEXT,hora TEXT,expiry TEXT,strike REAL,right TEXT,bid REAL,ask REAL)")
    filas=[]
    for h,s in S.items():
        t=ttc(h)
        for K in range(k0,k1+1):
            for r in ("C","P"):
                intr=max(s-K,0.0) if r=="C" else max(K-s,0.0)
                dep=(s-K) if r=="C" else (K-s)
                mid=max(intr+extr(modelo,dep,t),0.01)
                filas.append((fk,h,dk,float(K),r,mid*0.99,mid*1.01))
    d.executemany("insert into premium_minute values (?,?,?,?,?,?,?)", filas)
    d.commit(); d.close()

def corre_year(modelo, db, etiqueta, trails_2m=(0.04,0.06,0.08)):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dias = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    base=[]; var={t:[] for t in trails_2m}
    for fk in dias:
        dk = fk.replace("-","")
        bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rth = [(h, cl, hi, lo, cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rth) < 300: continue
        sen = sen_2min(bars)
        if not sen: continue
        # BASELINE: velas 1-min
        build_tmp(modelo, fk, dk, rth)
        _,c = simular(fk, senales=sen, trail=TRAIL_BASE, db_velas=TMP, db_tape=None, expiry=dk,
                      mid=False, mag_umbral=None, size_cap=SIZE_CAP, hora_min=SKIP)
        base.append(c-CAPITAL_0)
        # VARIANTE: velas 2-min
        v2 = agrega_2min(rth)
        build_tmp(modelo, fk, dk, v2)
        for t in trails_2m:
            _,c = simular(fk, senales=sen, trail=t, db_velas=TMP, db_tape=None, expiry=dk,
                          mid=False, mag_umbral=None, size_cap=SIZE_CAP, hora_min=SKIP)
            var[t].append(c-CAPITAL_0)
    con.close()
    if os.path.exists(TMP): os.remove(TMP)
    print(f"\n=== {etiqueta} · skip {SKIP} · size_cap ${SIZE_CAP:.0f} · bid/ask ===")
    print(f"{'variante':>16} | {'TOTAL':>11} {'%verde':>7} {'suma_malos':>11} {'peor':>9} {'ratio':>6}")
    def linea(et, arr):
        s=stats(arr)
        print(f"{et:>16} | {s['tot']:>+10.2f}$ {s['verde']:>6.1f}% {s['suma_malos']:>+10.2f}$ {s['peor']:>+8.2f}$ {s['ratio']:>6.2f}")
        return s
    res={"base":linea("trail 1min 0.04", base)}
    for t in trails_2m:
        res[t]=linea(f"trail 2min {t:.2f}", var[t])
    return res

if __name__ == "__main__":
    modelo = calibra(["2026-08-11","2026-08-12","2026-08-13"])
    print(f"modelo sintetico calibrado ({len(modelo)} buckets). Comparando trail 1min vs 2min...", flush=True)
    r1 = corre_year(modelo, R("spy_bars_year.db"),  "AÑO1 (tune)")
    r2 = corre_year(modelo, R("spy_bars_year2.db"), "AÑO2 (OOS)")
    print("\n=== VEREDICTO OOS (Δ vs baseline trail 1min 0.04 — debe sostenerse en AMBOS años) ===")
    print(f"{'variante':>16} | {'Δtot A1':>10} {'Δtot A2':>10} {'Δmalos A1':>11} {'Δmalos A2':>11} {'Δ%verde A1':>11} {'Δ%verde A2':>11}")
    b1=r1['base']; b2=r2['base']
    for t in (0.04,0.06,0.08):
        s1=r1[t]; s2=r2[t]
        print(f"{'trail 2min '+f'{t:.2f}':>16} | {s1['tot']-b1['tot']:>+9.2f}$ {s2['tot']-b2['tot']:>+9.2f}$ "
              f"{s1['suma_malos']-b1['suma_malos']:>+10.2f}$ {s2['suma_malos']-b2['suma_malos']:>+10.2f}$ "
              f"{s1['verde']-b1['verde']:>+10.1f}% {s2['verde']-b2['verde']:>+10.1f}%")
    print("\n(Δmalos>0 = menos perdida en dias malos. Δ%verde>0 = mas dias verdes. Mejora real = positiva en AMBOS años.)")
