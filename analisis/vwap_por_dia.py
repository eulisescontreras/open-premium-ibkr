# -*- coding: utf-8 -*-
"""P&L DIA POR DIA del metodo VWAP sobre 255 sesiones (contrato ITM 3pts modelado).
Responde: ¿hay dias positivos? ¿cuantos? ¿los 2 dias que testeamos (08-11/08-12) salen positivos
tambien en el modelo (consistencia)? Muestra que 'negativo en promedio' != 'negativo todos los dias'.
"""
import sqlite3, sys, statistics as st
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
DB = "historico_spy.db"; MEDIA_DIST = 0.20; H = 8
DELTA = 0.75; THETA_MIN = 0.29; SPREAD = 0.071; COMISION = 1.72
FIJO_MID = THETA_MIN * H + COMISION            # fill al mid (optimista, ~como la prueba de 2 dias)
FIJO_CRUCE = FIJO_MID + SPREAD * 100           # cruzando spread (realista)
def mm(h): return int(h[:2]) * 60 + int(h[3:5])

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); d = {}
    for f, h, close, vwap in c.execute("select fecha,hora,close,vwap from ta_historico order by fecha,hora"):
        d.setdefault(f, []).append((h, close, vwap))
    c.close(); return sorted(d), d

def pnl_dia(barras, fijo):
    horas = [x[0] for x in barras]; P = [x[1] for x in barras]; V = [x[2] for x in barras]
    i = 0; n = len(barras); tot = 0.0; nops = 0
    while i < n:
        if horas[i] >= "15:40": break
        if V[i] is None: i += 1; continue
        d = P[i] - V[i]
        if d >= MEDIA_DIST: lado = "P"
        elif d <= -MEDIA_DIST: lado = "C"
        else: i += 1; continue
        fin = [k for k in range(i, n) if mm(horas[k]) >= mm(horas[i]) + H]
        if not fin: break
        k = fin[0]; ds = P[k] - P[i]; fav = ds if lado == "C" else -ds
        tot += DELTA * fav * 100 - fijo; nops += 1; i = k
    return tot, nops

def main():
    orden, dias = carga()
    for etq, fijo in (("FILL AL MID (optimista, ~como prueba 2 dias)", FIJO_MID),
                      ("CRUZANDO SPREAD (realista)", FIJO_CRUCE)):
        pnls = {f: pnl_dia(dias[f], fijo)[0] for f in orden}
        vals = list(pnls.values())
        pos = [v for v in vals if v > 0]; neg = [v for v in vals if v <= 0]
        print("=" * 84)
        print(f"VWAP dia por dia — {etq}")
        print("=" * 84)
        print(f"  dias POSITIVOS: {len(pos)}/{len(vals)} ({100*len(pos)/len(vals):.0f}%)  |  dias negativos: {len(neg)}")
        print(f"  suma dias+ = {sum(pos):+.0f}$   suma dias- = {sum(neg):+.0f}$   TOTAL = {sum(vals):+.0f}$")
        print(f"  mejor dia {max(vals):+.0f}$   peor dia {min(vals):+.0f}$   mediana {st.median(vals):+.1f}$")
        for d in ("2026-08-11", "2026-08-12"):
            if d in pnls:
                print(f"  >> dia testeado {d}: {pnls[d]:+.0f}$  ({'POSITIVO' if pnls[d]>0 else 'negativo'})")
        # top 5 mejores y peores
        top = sorted(pnls.items(), key=lambda kv: kv[1], reverse=True)
        print("  5 mejores dias:", ", ".join(f"{d[5:]}:{v:+.0f}" for d, v in top[:5]))
        print("  5 peores dias :", ", ".join(f"{d[5:]}:{v:+.0f}" for d, v in top[-5:]))
        print()

if __name__ == "__main__":
    main()
