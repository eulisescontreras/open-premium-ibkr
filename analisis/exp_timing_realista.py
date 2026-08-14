# -*- coding: utf-8 -*-
"""EXPERIMENTO CRITICO: look-ahead del timing de entrada.
   Hallazgo (usuario, 2026-08-14): la señal del ST 2-min etiquetada "HH:MM" sale de un
   bucket de 2-min [HH:MM, HH:MM+1] cuyo cierre ocurre al FINAL de HH:MM+1. En tiempo real
   la señal recien se conoce a HH:MM+2. PERO el backtest entra en la etiqueta HH:MM usando
   el precio de esa vela 1-min -> entra 2 min ANTES de que el flip se confirme = LOOK-AHEAD.

   Mide cuanto del edge es real vs inflado: compara el timing actual contra entrar en el
   momento REALISTA (etiqueta + shift min). shift=2 es el correcto (vela 2-min ya cerrada,
   se actua en la apertura de la siguiente). shift=1 como bracket intermedio.
   Reutiliza sen_2min/build_tmp/stats y simular() REALES (R3/R8/R9). skip 09:45, bid/ask.
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra
from year_backtest import sen_2min
from reverifica_dias_malos import stats
from exp_trail_2min import build_tmp, TMP
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
def mm(h): return int(h[:2])*60+int(h[3:5])
def hhmm(m): return f"{m//60:02d}:{m%60:02d}"

SIZE_CAP=400.0; SKIP="09:45"; TRAIL=0.04
SHIFTS=[0,1,2]   # 0 = actual (look-ahead); 2 = realista (bucket 2-min ya cerrado)

def shift_sen(sen, n):
    return [(hhmm(mm(h)+n), lado) for h,lado in sen]

def corre_year(modelo, db, etiqueta):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dias = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    por={n:[] for n in SHIFTS}
    for fk in dias:
        dk = fk.replace("-","")
        bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rth = [(h, cl, hi, lo, cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rth) < 300: continue
        sen = sen_2min(bars)
        if not sen: continue
        build_tmp(modelo, fk, dk, rth)   # velas 1-min (baseline de grilla)
        for n in SHIFTS:
            s = shift_sen(sen, n)
            _,c = simular(fk, senales=s, trail=TRAIL, db_velas=TMP, db_tape=None, expiry=dk,
                          mid=False, mag_umbral=None, size_cap=SIZE_CAP, hora_min=SKIP)
            por[n].append(c-CAPITAL_0)
    con.close()
    if os.path.exists(TMP): os.remove(TMP)
    print(f"\n=== {etiqueta} · skip {SKIP} · trail {TRAIL}% · bid/ask ===")
    print(f"{'timing':>22} | {'TOTAL':>11} {'%verde':>7} {'suma_malos':>11} {'peor':>9} {'ratio':>6}")
    res={}
    for n in SHIFTS:
        s=stats(por[n]); res[n]=s
        et = "ACTUAL (look-ahead)" if n==0 else f"realista +{n}min"
        print(f"{et:>22} | {s['tot']:>+10.2f}$ {s['verde']:>6.1f}% {s['suma_malos']:>+10.2f}$ {s['peor']:>+8.2f}$ {s['ratio']:>6.2f}")
    return res

if __name__ == "__main__":
    modelo = calibra(["2026-08-11","2026-08-12","2026-08-13"])
    print(f"modelo calibrado ({len(modelo)} buckets). Midiendo look-ahead del timing...", flush=True)
    r1 = corre_year(modelo, R("spy_bars_year.db"),  "AÑO1 (tune)")
    r2 = corre_year(modelo, R("spy_bars_year2.db"), "AÑO2 (OOS)")
    print("\n=== VEREDICTO: cuanto del edge se pierde con timing REALISTA (+2min) ===")
    for et,rY in (("AÑO1",r1),("AÑO2",r2)):
        b=rY[0]; rr=rY[2]
        dtot=rr['tot']-b['tot']; dv=rr['verde']-b['verde']
        print(f"  {et}: total {b['tot']:+.0f} -> {rr['tot']:+.0f}  (Δ {dtot:+.0f}$, {100*dtot/abs(b['tot']) if b['tot'] else 0:+.1f}%) | "
              f"%verde {b['verde']:.1f}% -> {rr['verde']:.1f}% (Δ {dv:+.1f})")
    print("\n(Si el edge se derrumba con +2min, gran parte era look-ahead. Si aguanta, es robusto.)")
