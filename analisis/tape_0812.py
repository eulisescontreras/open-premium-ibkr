# -*- coding: utf-8 -*-
"""EXPLORACION del tape 0DTE del 2026-08-12 (unico dia completo). 1 dia = HIPOTESIS, no validacion.
Objetivo: ¿el flujo AGRESOR de opciones anticipa los giros del precio del SPY?

Presion direccional por trade (agresor):
  CALL COMPRA -> +  (alcista) | CALL VENTA -> -  (bajista)
  PUT  COMPRA -> -  (bajista) | PUT  VENTA -> +  (alcista)
Peso: size (contratos) y size*last (prima $). Se agrega por minuto.
Se cruza con el precio del SPY (m1_minute) y se mide LEAD-LAG: corr(flujo(t), retorno futuro(t->t+H)).
Tambien: en los GIROS reales del dia, ¿que hizo el flujo justo antes? Read-only.
"""
import sqlite3, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
DB = "spy_history.db"; DIA = "2026-08-12"
def mmhh(h): return h[:5]   # HH:MM
def mm(h): return int(h[:2])*60+int(h[3:5])

c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
# flujo por minuto
flow_size = {}; flow_prem = {}; gross = {}
for hora, strike, right, last, size, agresor in c.execute(
        "select hora,strike,right,last,size,agresor from tape where fecha=?", (DIA,)):
    m = mmhh(hora)
    signo = 0
    if right == "C": signo = 1 if agresor == "COMPRA" else -1
    else:            signo = -1 if agresor == "COMPRA" else 1
    flow_size[m] = flow_size.get(m, 0) + signo * (size or 0)
    flow_prem[m] = flow_prem.get(m, 0) + signo * (size or 0) * (last or 0) * 100
    gross[m] = gross.get(m, 0) + (size or 0)

# precio SPY por minuto
spy = {}
for hora, s in c.execute("select hora,spy from m1_minute where fecha=?", (DIA,)):
    spy[mmhh(hora)] = s

mins = sorted(set(flow_size) & set(spy))
def corr(xs, ys):
    n = len(xs)
    if n < 5: return 0.0
    mx = sum(xs)/n; my = sum(ys)/n
    num = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
    dx = (sum((a-mx)**2 for a in xs))**0.5; dy = (sum((b-my)**2 for b in ys))**0.5
    return num/(dx*dy) if dx and dy else 0.0

print("=" * 84)
print(f"TAPE {DIA} (unico dia completo) — ¿el flujo agresor ANTICIPA el precio? 1 dia = HIPOTESIS")
print(f"  minutos con flujo y precio: {len(mins)}")
print("=" * 84)

# LEAD-LAG: corr(flujo(t), retorno futuro t->t+H) y contemporaneo/pasado
idx = {m: k for k, m in enumerate(mins)}
px = [spy[m] for m in mins]
fs = [flow_size[m] for m in mins]; fp = [flow_prem[m] for m in mins]
print(f"{'H (min)':>8} | {'corr(flujo_size, ret futuro)':>28} | {'corr(flujo_prima, ret futuro)':>30}")
for H in (-5, -1, 0, 1, 3, 5, 8, 15):   # H<0 = pasado (precio LIDERA flujo); H>0 = futuro (flujo LIDERA precio)
    xs = []; ys = []; zs = []
    for k in range(len(mins)):
        kf = k + H
        if 0 <= kf < len(mins):
            ret = px[kf] - px[k]
            xs.append(fs[k]); ys.append(ret); zs.append(fp[k])
    etiqueta = f"t->t{H:+d}"
    print(f"  {etiqueta:>6} | {corr(xs, ys):>28.3f} | {corr(zs, ys):>30.3f}")

print("\n  (H>0 y corr>0  => el flujo ADELANTA al precio [util]. H<0 => el precio adelanta al flujo [inutil, reactivo].)")

# acierto direccional: signo del flujo(t) vs signo del retorno t->t+8
for H in (5, 8, 15):
    ok = tot = 0
    for k in range(len(mins)-H):
        if fs[k] == 0: continue
        pred = 1 if fs[k] > 0 else -1
        real = 1 if px[k+H] > px[k] else -1
        ok += (pred == real); tot += 1
    print(f"  acierto signo(flujo_size) -> mov {H}min: {100*ok/tot:.1f}%  (n={tot})")
print("=" * 84)
