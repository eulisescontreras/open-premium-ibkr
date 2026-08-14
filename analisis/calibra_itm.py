# -*- coding: utf-8 -*-
"""Calibra delta/theta/spread EMPIRICOS de opciones 0DTE ITM del SPY con los 2 dias reales
(premium_minute, 08-11/08-12). Objetivo: ver si se pueden MODELAR los contratos para backtestear
el metodo VWAP sobre las 255 sesiones sin descargar opciones. Read-only.
"""
import sqlite3, statistics as st
from collections import defaultdict
DB = "spy_history.db"; DIAS = ("2026-08-11", "2026-08-12")
def mm(h): return int(h[:2]) * 60 + int(h[3:5])
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

px = {}
for f, h, exp, s, r, mid, spr in c.execute(
        "select fecha,hora,expiry,strike,right,mid,spread from premium_minute "
        "where mid is not null and mid>0 and fecha in (?,?)", DIAS):
    if str(exp) != f.replace("-", ""):
        continue
    k = (f, h, s, r)
    if k not in px or (spr if spr is not None else 9e9) < px[k][1]:
        px[k] = (mid, spr if spr is not None else 9e9)

spy = {}
for f, h, v in c.execute("select fecha,hora,spy from m1_minute where fecha in (?,?)", DIAS):
    spy[(f, h)] = v

def pts_itm(f, h, s, r):
    sp = spy.get((f, h))
    if sp is None:
        return None
    return round((sp - s) if r == "C" else (s - sp))   # + = ITM

# DELTA y THETA por bucket de pts ITM
dpairs = defaultdict(list)   # bucket -> [(dmid, dspy)]
flat = defaultdict(list)     # bucket -> [dmid con spy casi quieto] (proxy de theta/min)
for f in DIAS:
    hs = sorted({hh for (ff, hh, s, r) in px if ff == f})
    rights_strikes = defaultdict(list)
    for (ff, hh, s, r) in px:
        if ff == f:
            rights_strikes[r].append(s)
    for r in ("C", "P"):
        for s in sorted(set(rights_strikes[r])):
            serie = [(h, px[(f, h, s, r)][0]) for h in hs if (f, h, s, r) in px and (f, h) in spy]
            for i in range(1, len(serie)):
                h0, m0 = serie[i-1]; h1, m1 = serie[i]
                if mm(h1) - mm(h0) != 1:
                    continue
                dsp = spy[(f, h1)] - spy[(f, h0)]
                dfav = dsp if r == "C" else -dsp   # movimiento a FAVOR del contrato (call sube, put baja)
                b = pts_itm(f, h0, s, r)
                if b is None:
                    continue
                if abs(dsp) >= 0.02:
                    dpairs[b].append((m1 - m0, dfav))
                if abs(dsp) < 0.02:
                    flat[b].append(m1 - m0)   # spy casi quieto: el cambio de mid ~ theta/min

precio = defaultdict(list)   # bucket -> [mid]  (precio tipico del contrato a esa profundidad)
sb = defaultdict(list)       # bucket -> [spread]
for (f, h, s, r), (mid, spr) in px.items():
    b = pts_itm(f, h, s, r)
    if b is not None:
        precio[b].append(mid); sb[b].append(spr)

print("=" * 88)
print("CALIBRACION EMPIRICA opciones 0DTE ITM SPY (2 dias reales) — con PROFUNDIDAD y PRECIO")
print("=" * 88)
print(f"{'ptsITM':>7} | {'delta':>6} | {'theta$/min':>10} | {'spread$':>8} | {'precio_medio$':>13} | {'costo_contrato$':>15}")
for b in sorted(set(list(dpairs) + list(flat) + list(precio))):
    if b < 0 or b > 12:
        continue
    delta = theta = None; nd = len(dpairs.get(b, []))
    if nd >= 20:
        num = sum(dm*ds for dm, ds in dpairs[b]); den = sum(ds*ds for dm, ds in dpairs[b])
        delta = num/den if den else None
    if len(flat.get(b, [])) >= 20:
        theta = st.mean(flat[b])
    pm = st.mean(precio[b]) if precio.get(b) else None
    ds = f"{delta:+.2f}" if delta is not None else "  -"
    ts = f"{theta*100:+.2f}" if theta is not None else "  -"
    ss = f"{st.mean(sb[b]):.3f}" if sb.get(b) else "  -"
    ps = f"{pm:.2f}" if pm else "  -"
    cs = f"{pm*100:.0f}" if pm else "  -"
    print(f"  {b:+d}    | {ds:>6} | {ts:>10} | {ss:>8} | {ps:>13} | {cs:>15}")
print("\nNOTA: costo_contrato = precio_medio x100 = capital necesario para comprar 1 contrato a esa profundidad.")
