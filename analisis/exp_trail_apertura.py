# -*- coding: utf-8 -*-
"""EXPERIMENTO: en vez de SKIPEAR la apertura, OPERARLA con trail 2-min SOLO en ese tramo
   (1-min el resto del dia). Idea del usuario: quiza los trades de apertura no son malos por
   direccion sino porque el trail ceñido de 1-min los sacude con el ruido del open; un trail
   2-min solo ahi los dejaria respirar y capturariamos los movimientos buenos de apertura.

   Comparacion (R8/R16) con control para separar efectos:
     - BASE     : skip 09:45   + trail 1-min           (sistema actual)
     - CONTROL  : sin skip     + trail 1-min           (opera apertura, trail normal)
     - VARIANTE : sin skip     + trail 2-min < LIM, 1-min despues  (grilla hibrida)
   Solo cambia la GRILLA de velas (R11/R15, no toca simular()). MISMO ST 2-min, misma config.
   REGLA OOS: mejora solo cuenta si se sostiene en AMBOS años.
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulador_st import simular, CAPITAL_0
from synth_premium import calibra
from year_backtest import sen_2min
from reverifica_dias_malos import stats
from exp_trail_2min import agrega_2min, build_tmp, TMP     # R9: reutilizar
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)

SIZE_CAP = 400.0
LIMS = ["09:45", "10:00"]   # frontera hasta donde se usa trail 2-min

def hibrida(rth, lim):
    """2-min para h<lim, 1-min para h>=lim. rth=[(h,o,hi,lo,cl)] 1-min."""
    a=[r for r in rth if r[0] < lim]
    b=[r for r in rth if r[0] >= lim]
    return sorted(agrega_2min(a) + b, key=lambda r: r[0])

def corre_year(modelo, db, etiqueta):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dias = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    base=[]; ctrl=[]; var={l:[] for l in LIMS}
    for fk in dias:
        dk = fk.replace("-","")
        bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",(fk,)).fetchall()
        rth = [(h, cl, hi, lo, cl) for (h,hi,lo,cl) in bars if "09:30"<=h<="16:00"]
        if len(rth) < 300: continue
        sen = sen_2min(bars)
        if not sen: continue
        # BASE y CONTROL comparten velas 1-min
        build_tmp(modelo, fk, dk, rth)
        _,c = simular(fk, senales=sen, trail=0.04, db_velas=TMP, db_tape=None, expiry=dk,
                      mid=False, mag_umbral=None, size_cap=SIZE_CAP, hora_min="09:45")
        base.append(c-CAPITAL_0)
        _,c = simular(fk, senales=sen, trail=0.04, db_velas=TMP, db_tape=None, expiry=dk,
                      mid=False, mag_umbral=None, size_cap=SIZE_CAP, hora_min=None)
        ctrl.append(c-CAPITAL_0)
        # VARIANTE: grilla hibrida por cada LIM
        for l in LIMS:
            build_tmp(modelo, fk, dk, hibrida(rth, l))
            _,c = simular(fk, senales=sen, trail=0.04, db_velas=TMP, db_tape=None, expiry=dk,
                          mid=False, mag_umbral=None, size_cap=SIZE_CAP, hora_min=None)
            var[l].append(c-CAPITAL_0)
    con.close()
    if os.path.exists(TMP): os.remove(TMP)
    print(f"\n=== {etiqueta} · trail 0.04% · size_cap ${SIZE_CAP:.0f} · bid/ask ===")
    print(f"{'variante':>26} | {'TOTAL':>11} {'%verde':>7} {'suma_malos':>11} {'peor':>9} {'ratio':>6}")
    def linea(et, arr):
        s=stats(arr)
        print(f"{et:>26} | {s['tot']:>+10.2f}$ {s['verde']:>6.1f}% {s['suma_malos']:>+10.2f}$ {s['peor']:>+8.2f}$ {s['ratio']:>6.2f}")
        return s
    res={}
    res['base']=linea("BASE skip09:45 1min", base)
    res['ctrl']=linea("CTRL sin-skip 1min", ctrl)
    for l in LIMS:
        res[l]=linea(f"VAR sin-skip 2min<{l}", var[l])
    return res

if __name__ == "__main__":
    modelo = calibra(["2026-08-11","2026-08-12","2026-08-13"])
    print(f"modelo calibrado ({len(modelo)} buckets). Trail 2-min solo en apertura...", flush=True)
    r1 = corre_year(modelo, R("spy_bars_year.db"),  "AÑO1 (tune)")
    r2 = corre_year(modelo, R("spy_bars_year2.db"), "AÑO2 (OOS)")
    print("\n=== VEREDICTO OOS (Δ vs BASE skip09:45 — debe sostenerse en AMBOS años) ===")
    print(f"{'variante':>26} | {'Δtot A1':>10} {'Δtot A2':>10} {'Δmalos A1':>11} {'Δmalos A2':>11} {'Δ%verde A1':>11} {'Δ%verde A2':>11}")
    b1=r1['base']; b2=r2['base']
    for k in ['ctrl']+LIMS:
        et = "CTRL sin-skip 1min" if k=='ctrl' else f"VAR sin-skip 2min<{k}"
        s1=r1[k]; s2=r2[k]
        print(f"{et:>26} | {s1['tot']-b1['tot']:>+9.2f}$ {s2['tot']-b2['tot']:>+9.2f}$ "
              f"{s1['suma_malos']-b1['suma_malos']:>+10.2f}$ {s2['suma_malos']-b2['suma_malos']:>+10.2f}$ "
              f"{s1['verde']-b1['verde']:>+10.1f}% {s2['verde']-b2['verde']:>+10.1f}%")
    print("\n(Δ>0 = mejor que el baseline skip 09:45. Mejora real = positiva en AMBOS años.)")
