# -*- coding: utf-8 -*-
"""RE-VERIFICACION de DIAS MALOS — objetivo: reducir/eliminar dias malos SIN sacrificar
   dias buenos, manteniendo o subiendo el %verde que dio el skip de apertura.
   Corre los 2 años (año1 tune + año2 OOS) con la config titular y BARRE el umbral de skip.
   Reutiliza sen_2min/st_dir (year_backtest), synth_premium y simular() REALES (R3/R9).

   Metrica por año: TOTAL, %verde, suma de malos, peor dia, ratio (prom_ganador/|prom_perdedor|).
   REGLA OOS (R8, caveat #5 del doc): una mejora SOLO cuenta si se sostiene en AMBOS años.
   Cualquier ganancia que aparezca en año1 pero no en año2 = overfit, se descarta.

   Premium SINTETICO (candado #1): calibrado en 08-11/12/13. NO valida contra premium real.
"""
import os, sys, sqlite3, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra, extr, ttc
from year_backtest import sen_2min      # ST(7,3.0) 2-min con premarket (codigo real, R9)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
TMP = R("_tmp_reverif.db")

# Config titular (fija). Lo unico que barremos aca es SKIP.
TRAIL = 0.04
SIZE_CAP = 400.0
MID = False          # bid/ask realista
SKIPS = [None, "09:45", "09:50", "10:00", "10:15", "10:30"]  # None = sin skip

def build_day_tmp(modelo, fk, dk, rth, S):
    """Construye la tmp db (bars_minute + premium_minute sintetico bid/ask) para un dia."""
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
                mid=max(intr+extr(modelo,dep,t),0.01)
                filas.append((fk,h,dk,float(K),r,mid*0.99,mid*1.01))
    d.executemany("insert into premium_minute values (?,?,?,?,?,?,?)", filas)
    d.commit(); d.close()

def stats(por_dia):
    n=len(por_dia); tot=sum(por_dia); win=[g for g in por_dia if g>0]; los=[g for g in por_dia if g<=0]
    verde=100*len(win)/n if n else 0
    suma_malos=sum(los)
    pw=sum(win)/len(win) if win else 0.0
    pl=sum(los)/len(los) if los else 0.0
    ratio=(pw/abs(pl)) if pl<0 else float('inf')
    return dict(n=n,tot=tot,verde=verde,suma_malos=suma_malos,peor=min(por_dia) if por_dia else 0,
                mejor=max(por_dia) if por_dia else 0, ratio=ratio)

def corre_year(modelo, db, etiqueta):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dias = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    por_skip = {sk:[] for sk in SKIPS}
    for fk in dias:
        dk = fk.replace("-","")
        bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rth = [(h, cl, hi, lo, cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rth) < 300: continue
        S = {h:cl for h,o,hi,lo,cl in rth}
        sen = sen_2min(bars)
        if not sen: continue
        build_day_tmp(modelo, fk, dk, rth, S)   # premium 1 sola vez por dia
        for sk in SKIPS:
            _,c = simular(fk, senales=sen, trail=TRAIL, db_velas=TMP, db_tape=None, expiry=dk,
                          mid=MID, mag_umbral=None, size_cap=SIZE_CAP, hora_min=sk)
            por_skip[sk].append(c-CAPITAL_0)
    con.close()
    if os.path.exists(TMP): os.remove(TMP)
    print(f"\n=== {etiqueta} · trail {TRAIL}% · size_cap ${SIZE_CAP:.0f} · bid/ask ===")
    print(f"{'skip':>7} | {'TOTAL':>11} {'%verde':>7} {'suma_malos':>11} {'peor':>9} {'mejor':>9} {'ratio':>6}")
    res={}
    for sk in SKIPS:
        s=stats(por_skip[sk]); res[sk]=s
        et="sin" if sk is None else sk
        print(f"{et:>7} | {s['tot']:>+10.2f}$ {s['verde']:>6.1f}% {s['suma_malos']:>+10.2f}$ "
              f"{s['peor']:>+8.2f}$ {s['mejor']:>+8.2f}$ {s['ratio']:>6.2f}")
    return res

if __name__ == "__main__":
    modelo = calibra(["2026-08-11","2026-08-12","2026-08-13"])
    print(f"modelo sintetico calibrado ({len(modelo)} buckets). Barriendo skip en 2 años...", flush=True)
    r1 = corre_year(modelo, R("spy_bars_year.db"),  "AÑO1 (tune)")
    r2 = corre_year(modelo, R("spy_bars_year2.db"), "AÑO2 (OOS)")
    print("\n=== VEREDICTO OOS (mejora solo cuenta si se sostiene en AMBOS años) ===")
    base = "09:45"
    print(f"{'skip':>7} | {'Δtot A1':>10} {'Δtot A2':>10} {'Δmalos A1':>11} {'Δmalos A2':>11} {'Δ%verde A1':>11} {'Δ%verde A2':>11}")
    for sk in SKIPS:
        et="sin" if sk is None else sk
        dt1=r1[sk]['tot']-r1[base]['tot']; dt2=r2[sk]['tot']-r2[base]['tot']
        dm1=r1[sk]['suma_malos']-r1[base]['suma_malos']; dm2=r2[sk]['suma_malos']-r2[base]['suma_malos']
        dv1=r1[sk]['verde']-r1[base]['verde']; dv2=r2[sk]['verde']-r2[base]['verde']
        print(f"{et:>7} | {dt1:>+9.2f}$ {dt2:>+9.2f}$ {dm1:>+10.2f}$ {dm2:>+10.2f}$ {dv1:>+10.1f}% {dv2:>+10.1f}%")
    print("\n(baseline = skip 09:45. Δmalos>0 = menos perdida en dias malos. Δ%verde>0 = mas dias verdes.)")
