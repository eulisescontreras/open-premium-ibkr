# -*- coding: utf-8 -*-
"""¿Saltarse mas minutos / la primera hora RESCATA el sistema con timing REALISTA?
   Con timing realista (+2min, sin look-ahead) el edge era negativo. Aca barremos el skip
   (09:45..11:00) bajo timing realista, para ver si evitar la manana lo vuelve positivo en
   AMBOS años. Reutiliza sen_2min/build_tmp/stats/shift_sen y simular() REALES (R3/R8/R9).
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra
from year_backtest import sen_2min
from reverifica_dias_malos import stats
from exp_trail_2min import build_tmp, TMP
from exp_timing_realista import shift_sen
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)

SIZE_CAP=400.0; TRAIL=0.04; SHIFT=2   # timing realista
SKIPS=["09:45","10:00","10:30","11:00"]

def corre_year(modelo, db, etiqueta):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dias = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    por={sk:[] for sk in SKIPS}; look=[]   # look = baseline look-ahead skip 09:45 (referencia)
    for fk in dias:
        dk = fk.replace("-","")
        bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rth = [(h, cl, hi, lo, cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rth) < 300: continue
        sen = sen_2min(bars)
        if not sen: continue
        build_tmp(modelo, fk, dk, rth)
        # referencia look-ahead (shift 0, skip 09:45)
        _,c = simular(fk, senales=sen, trail=TRAIL, db_velas=TMP, db_tape=None, expiry=dk,
                      mid=False, mag_umbral=None, size_cap=SIZE_CAP, hora_min="09:45")
        look.append(c-CAPITAL_0)
        # realista (+2) barriendo skip
        s2 = shift_sen(sen, SHIFT)
        for sk in SKIPS:
            _,c = simular(fk, senales=s2, trail=TRAIL, db_velas=TMP, db_tape=None, expiry=dk,
                          mid=False, mag_umbral=None, size_cap=SIZE_CAP, hora_min=sk)
            por[sk].append(c-CAPITAL_0)
    con.close()
    if os.path.exists(TMP): os.remove(TMP)
    print(f"\n=== {etiqueta} · trail {TRAIL}% · bid/ask ===")
    print(f"{'config':>28} | {'TOTAL':>11} {'%verde':>7} {'suma_malos':>11} {'peor':>9} {'ratio':>6}")
    s=stats(look); print(f"{'look-ahead skip09:45 (ref)':>28} | {s['tot']:>+10.2f}$ {s['verde']:>6.1f}% {s['suma_malos']:>+10.2f}$ {s['peor']:>+8.2f}$ {s['ratio']:>6.2f}")
    res={}
    for sk in SKIPS:
        s=stats(por[sk]); res[sk]=s
        print(f"{'realista +2 skip '+sk:>28} | {s['tot']:>+10.2f}$ {s['verde']:>6.1f}% {s['suma_malos']:>+10.2f}$ {s['peor']:>+8.2f}$ {s['ratio']:>6.2f}")
    return res

if __name__ == "__main__":
    modelo = calibra(["2026-08-11","2026-08-12","2026-08-13"])
    print(f"modelo calibrado ({len(modelo)} buckets). Timing realista + barrido de skip...", flush=True)
    r1=corre_year(modelo, R("spy_bars_year.db"),  "AÑO1 (tune)")
    r2=corre_year(modelo, R("spy_bars_year2.db"), "AÑO2 (OOS)")
    print("\n=== VEREDICTO: ¿algun skip vuelve POSITIVO el timing realista en AMBOS años? ===")
    for sk in SKIPS:
        pos = (r1[sk]['tot']>0 and r2[sk]['tot']>0)
        print(f"  skip {sk}: A1 {r1[sk]['tot']:+.0f}$  A2 {r2[sk]['tot']:+.0f}$  -> {'POSITIVO AMBOS' if pos else 'NO'}")
