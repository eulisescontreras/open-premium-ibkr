# -*- coding: utf-8 -*-
"""MATRIZ de ACIERTO DIRECCIONAL (% fav>0) de cada TA en cada REGIMEN por separado. 255 sesiones.
Regimen del dia: DIRECCION (alcista/bajista/neutra por close-open) y TENDENCIA (efficiency ratio: lateral/mixto/tendencial).
Objetivo: ver si algun TA supera claramente el 50% en algun regimen concreto (pista real).
Reusa generadores de barrido_ta (R9). ta_historico byte-fiel.
"""
import os, sqlite3, sys
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from barrido_ta import make_rsi, make_macd, make_macd_cross, make_ema_cross, make_bb
DB = "historico_spy.db"; H = 8; MEDIA_DIST = 0.20
def mm(h): return int(h[:2]) * 60 + int(h[3:5])

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); d = {}
    for row in c.execute("select fecha,hora,close,rsi,macd_hist,ema8,ema21,bb_up,bb_low,vwap from ta_historico order by fecha,hora"):
        d.setdefault(row[0], []).append(row[1:])
    c.close(); return sorted(d), d

def lado_media(prev, cur):
    c, v = cur[1], cur[8]
    if v is None: return None
    dd = c - v
    return "C" if dd <= -MEDIA_DIST else ("P" if dd >= MEDIA_DIST else None)

def favs_por_dia(orden, dias, fn):
    res = {}
    for f in orden:
        b = dias[f]; hs = [x[0] for x in b]; cl = [x[1] for x in b]; mn = [mm(x[0]) for x in b]
        out = []; i = 1; n = len(b)
        while i < n:
            if hs[i] >= "15:40": break
            if i-1 < 1: i += 1; continue
            lado = fn(b[i-2], b[i-1])
            if lado is None: i += 1; continue
            fin = [k for k in range(i, n) if mn[k] >= mn[i] + H]
            if not fin: break
            k = fin[0]; ds = cl[k] - cl[i]
            out.append(ds if lado == "C" else -ds); i = k
        res[f] = out
    return res

def main():
    orden, dias = carga()
    # regimen
    dird = {}; erd = {}
    for f in orden:
        cl = [x[1] for x in dias[f]]
        neto = cl[-1] - cl[0]; camino = sum(abs(cl[i]-cl[i-1]) for i in range(1, len(cl))) or 1e-9
        dird[f] = "alcista" if neto > 0.5 else ("bajista" if neto < -0.5 else "neutra")
        erd[f] = abs(neto)/camino
    ev = sorted(erd.values()); q1 = ev[len(ev)//3]; q2 = ev[2*len(ev)//3]
    trend = {f: ("lateral" if erd[f] <= q1 else "mixto" if erd[f] <= q2 else "tendencial") for f in orden}
    print("=" * 108)
    print("% ACIERTO DIRECCIONAL por TA y REGIMEN (255 sesiones). n ops entre parentesis. >=54% marcado con *")
    print(f"  dias: {dict(Counter(dird.values()))} | tendencia: {dict(Counter(trend.values()))}")
    print("=" * 108)
    fams = [("VWAP/media", lado_media), ("RSI rev 30/70", make_rsi(30,70,"rev")),
            ("MACD trend", make_macd("trend")), ("MACD cruce rev", make_macd_cross("rev")),
            ("EMA cross trend", make_ema_cross("trend")), ("EMA cross rev", make_ema_cross("rev")),
            ("Bollinger rev", make_bb("rev")), ("Bollinger breakout", make_bb("breakout"))]
    regs = ["alcista","bajista","neutra","lateral","mixto","tendencial"]
    regmap = {**{r:dird for r in ("alcista","bajista","neutra")}, **{r:trend for r in ("lateral","mixto","tendencial")}}
    print(f"{'TA':>19} |" + "".join(f"{r:>14}" for r in regs) + f"{'GLOBAL':>12}")
    for etq, fn in fams:
        pd = favs_por_dia(orden, dias, fn)
        cols = []
        allf = []
        for r in regs:
            fv = [x for f in orden if regmap[r][f]==r for x in pd.get(f,[])]
            if fv:
                acc = 100*sum(1 for x in fv if x>0)/len(fv)
                mark = "*" if acc>=54 else " "
                cols.append(f"{acc:.1f}{mark}({len(fv)})")
            else: cols.append("-")
        gv = [x for f in orden for x in pd.get(f,[])]
        gacc = 100*sum(1 for x in gv if x>0)/len(gv) if gv else 0
        print(f"  {etq:>17} |" + "".join(f"{c:>14}" for c in cols) + f"{gacc:>11.1f}%")
    print("=" * 108)
    print("LECTURA: buscar celdas con * (>=54%). El liston para GANAR con opcion es ~56.7%.")
    print("  OJO: el regimen se conoce al CERRAR el dia; usarlo requiere predecirlo temprano.")

if __name__ == "__main__":
    main()
