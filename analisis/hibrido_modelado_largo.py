# -*- coding: utf-8 -*-
"""Metodo VWAP sobre 255 sesiones, contrato ITM MODELADO con griegas EMPIRICAS (calibra_itm.py).
Barrido por CAPITAL: mas capital -> ITM mas profundo (mas delta, pero mas spread). ¿Cruza a positivo?

P&L_op = delta*fav*100 - (theta_min*8 + comision + spread*100).  fav = mov SPY a favor (8min, señal VWAP).
Griegas de 2 dias reales; profundidad >+5 pts NO es confiable (ITM 0DTE ilíquida, quotes anchos).
"""
import sqlite3, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
DB = "historico_spy.db"; MEDIA_DIST = 0.20; HORIZ = 8; COMISION = 1.72
def mm(h): return int(h[:2]) * 60 + int(h[3:5])
# calibracion empirica (calibra_itm.py): pts ITM -> (delta, theta$/min, spread$, costo_contrato$)
CAL = {0:(0.42,0.31,0.010,73), 1:(0.59,0.28,0.019,136), 2:(0.69,0.28,0.036,219),
       3:(0.75,0.29,0.071,311), 4:(0.77,0.14,0.109,407), 5:(0.78,0.17,0.145,504),
       6:(0.77,0.37,0.174,603), 7:(0.74,0.61,0.184,703), 8:(0.73,0.34,0.197,801),
       9:(0.67,0.30,0.220,902), 10:(0.68,0.30,0.247,995)}   # theta +9/+10 saneado (positivos = ruido)

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); d = {}
    for f, h, close, vwap in c.execute("select fecha,hora,close,vwap from ta_historico order by fecha,hora"):
        d.setdefault(f, []).append((h, close, vwap))
    c.close(); return sorted(d), d

def favs(orden, dias):
    """movimientos a favor (puntos) de las entradas VWAP — INDEPENDIENTE del contrato."""
    out = []
    for f in orden:
        s = dias[f]; H = [x[0] for x in s]; P = [x[1] for x in s]; V = [x[2] for x in s]
        i = 0; n = len(s)
        while i < n:
            if H[i] >= "15:40": break
            if V[i] is None: i += 1; continue
            dd = P[i] - V[i]
            if dd >= MEDIA_DIST: lado = "P"
            elif dd <= -MEDIA_DIST: lado = "C"
            else: i += 1; continue
            fin = [k for k in range(i, n) if mm(H[k]) >= mm(H[i]) + HORIZ]
            if not fin: break
            k = fin[0]; ds = P[k] - P[i]
            out.append(ds if lado == "C" else -ds); i = k
    return out

def depth_for(cap):
    tope = cap * 0.80
    ok = [b for b, (d, t, sp, cost) in CAL.items() if cost <= tope]
    return max(ok) if ok else 0

def main():
    orden, dias = carga()
    fv = favs(orden, dias)
    n = len(fv); media_fav = sum(fv) / n
    print("=" * 92)
    print(f"METODO VWAP, 255 sesiones, {n} operaciones. media_fav = {media_fav:+.4f} puntos (INDEP del contrato)")
    print("  Barrido por CAPITAL -> ITM mas profundo. EV_op = delta*fav*100 - theta*8 - comision - spread*100")
    print("=" * 92)
    print(f"{'capital$':>9} {'ITM pts':>8} {'delta':>6} {'costo_fijo$':>11} {'EV/op$':>8} {'P&L 255d$':>11} {'win%':>6}  fiab.")
    for cap in (400, 600, 800, 1000, 1500, 3000):
        b = depth_for(cap); delta, theta, spr, cost = CAL[b]
        fijo = theta * HORIZ + COMISION + spr * 100
        pnls = [delta * x * 100 - fijo for x in fv]
        ev = sum(pnls) / n; win = 100 * sum(1 for p in pnls if p > 0) / n
        fiab = "OK" if b <= 5 else "NO CONFIABLE (iliquida)"
        print(f"  {cap:>7} {b:>8} {delta:>6.2f} {fijo:>11.2f} {ev:>+8.2f} {sum(pnls):>+11.0f} {win:>6.1f}  {fiab}")
    print("-" * 92)
    print("TECHO TEORICO (delta=1.0, theta=0, spread deep ~0.20): EV = 100*media_fav - comision - 20")
    ev_ideal = 100 * media_fav - COMISION - 20
    print(f"  = 100*{media_fav:+.4f} - 1.72 - 20 = {ev_ideal:+.2f}$/op  (aun NEGATIVO: sin ventaja direccional, nada lo salva)")
    print("=" * 92)

if __name__ == "__main__":
    main()
