# -*- coding: utf-8 -*-
"""MODELO de prima 0DTE = intrinseco + extrinseco calibrado (metodo A, autorizado por usuario).
  prima_mid(K,right,S,ttc) = max(intrinseco,0) + extrinseco[bucket(itm_depth, ttc)]
extrinseco se calibra con contratos REALES guardados (08-11pm, 08-12, 08-13).

Este script SOLO calibra y VALIDA (predice mid real vs grabado) -> mide el error.
NO genera datos sinteticos todavia: primero hay que ver si la premisa se sostiene.
"""
import os, sys, sqlite3, statistics as st
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
PMDB = R("spy_bars_pm.db")

CAL = {"2026-08-11": "20260811", "2026-08-12": "20260812", "2026-08-13": "20260813"}

def spy_por_min(fkey):
    con = sqlite3.connect(f"file:{PMDB}?mode=ro", uri=True)
    d = {h: c for h, c in con.execute(
        "select hora,close from bars_pm where fecha=? and hora>='09:30' and hora<='16:00'", (fkey,))}
    con.close()
    return d

def ttc(hora):
    return 960 - (int(hora[:2]) * 60 + int(hora[3:5]))   # min al cierre 16:00

def bucket(depth, t):
    return (round(depth * 2) / 2.0, round(t / 30.0) * 30)  # depth a $0.5, ttc a 30min

# ---- calibracion: junta extrinsecos reales por bucket ----
tabla = {}
muestras = []   # (fkey, hora, K, right, S, intrinsic, mid_real, depth, ttc)
for fkey, dk in CAL.items():
    S = spy_por_min(fkey)
    db = R(f"spy_history_{dk}.db")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("select hora,strike,right,bid,ask from premium_minute "
                       "where fecha=? and expiry=? and bid is not null and ask is not null",
                       (fkey, dk)).fetchall()
    con.close()
    for hora, K, right, bid, ask in rows:
        if hora not in S:
            continue
        s = S[hora]; midr = (bid + ask) / 2.0
        intr = max(s - K, 0.0) if right == "C" else max(K - s, 0.0)
        depth = (s - K) if right == "C" else (K - s)   # ITM>0, OTM<0
        t = ttc(hora)
        extr = midr - intr
        tabla.setdefault(bucket(depth, t), []).append(extr)
        muestras.append((fkey, hora, K, right, s, intr, midr, depth, t))

modelo = {k: st.mean(v) for k, v in tabla.items()}
print(f"buckets calibrados: {len(modelo)}   muestras reales: {len(muestras)}")

# ---- validacion: predecir mid real vs grabado ----
def predice(depth, t, intr):
    b = bucket(depth, t)
    if b in modelo:
        return intr + modelo[b]
    # vecino en ttc si falta el bucket exacto
    cand = [kk for kk in modelo if kk[0] == b[0]]
    if cand:
        kk = min(cand, key=lambda x: abs(x[1] - b[1]))
        return intr + modelo[kk]
    return None

err_all = []; err_atm = []   # atm = los que el simulador compra: ITM poco profundo, mid 1.5-3.5
for fkey, hora, K, right, s, intr, midr, depth, t in muestras:
    p = predice(depth, t, intr)
    if p is None:
        continue
    e = abs(p - midr)
    err_all.append(e)
    if -0.5 <= depth <= 3.0 and 1.5 <= midr <= 3.5:
        err_atm.append((e, midr))

def resumen(nombre, errs):
    if not errs:
        print(f"  {nombre}: sin muestras"); return
    vals = [e if isinstance(e, float) else e[0] for e in errs]
    print(f"  {nombre}: n={len(vals)}  MAE=${st.mean(vals):.3f}  mediana=${st.median(vals):.3f}  p90=${sorted(vals)[int(len(vals)*0.9)]:.3f}")

print("\nERROR de prediccion (|pred - mid_real|):")
resumen("TODOS los contratos", err_all)
resumen("Cerca-ATM (lo que compra el sim)", err_atm)
if err_atm:
    mae = st.mean([e for e, _ in err_atm]); midm = st.mean([m for _, m in err_atm])
    print(f"  -> error relativo cerca-ATM: {100*mae/midm:.1f}% del precio medio (${midm:.2f})")
