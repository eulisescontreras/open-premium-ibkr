# -*- coding: utf-8 -*-
"""MISMO contrato ITM modelado (griegas reales), pero variando el TA de ENTRADA (no solo VWAP).
Sobre 255 sesiones. Responde: ¿algun OTRO TA, con el contrato real, saca profit donde el VWAP no?

Reusa los generadores de señal de barrido_ta.py (R9) y el contrato modelado de calibra_itm.
P&L_op = delta*fav*100 - (theta*8 + comision + spread*100). fav=mov SPY a favor (8min, no solapado).
Contrato: 3pts ITM (lo que ~$400 compra): delta 0.75, fijo ~$11.14 (cruzando spread) / $4.04 (fill al mid).
"""
import os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from barrido_ta import make_rsi, make_macd, make_macd_cross, make_ema_cross, make_bb

DB = "historico_spy.db"; H = 8; MEDIA_DIST = 0.20
DELTA = 0.75; THETA_MIN = 0.29; SPREAD = 0.071; COMISION = 1.72   # 3pts ITM (calibra_itm)
FIJO_CRUCE = THETA_MIN * H + COMISION + SPREAD * 100     # cruzando spread (realista) ~11.14
FIJO_MID = THETA_MIN * H + COMISION                       # fill perfecto al mid (optimista) ~4.04
def mm(h): return int(h[:2]) * 60 + int(h[3:5])

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); d = {}
    for row in c.execute("select fecha,hora,close,rsi,macd_hist,ema8,ema21,bb_up,bb_low,vwap "
                         "from ta_historico order by fecha,hora"):
        d.setdefault(row[0], []).append(row[1:])   # (hora,close,rsi,macd_hist,ema8,ema21,bb_up,bb_low,vwap)
    c.close(); return sorted(d), d

def favs(orden, dias, lado_fn):
    return [x for _f, lst in favs_por_dia(orden, dias, lado_fn).items() for x in lst]

def favs_por_dia(orden, dias, lado_fn):
    """{fecha: [fav,...]} por operacion, no solapada, retraso 1."""
    res = {}
    for f in orden:
        b = dias[f]; horas = [x[0] for x in b]; close = [x[1] for x in b]; mins = [mm(x[0]) for x in b]
        out = []; i = 1; n = len(b)
        while i < n:
            if horas[i] >= "15:40": break
            j = i - 1
            if j < 1: i += 1; continue
            lado = lado_fn(b[j-1], b[j])
            if lado is None: i += 1; continue
            fin = [k for k in range(i, n) if mins[k] >= mins[i] + H]
            if not fin: break
            k = fin[0]; ds = close[k] - close[i]
            out.append(ds if lado == "C" else -ds); i = k
        res[f] = out
    return res

def lado_media(prev, cur):
    """VWAP/media real: idx 8 = vwap. d=close-vwap; d<=-0.20->CALL, d>=0.20->PUT (hacia la media)."""
    c, v = cur[1], cur[8]
    if v is None: return None
    d = c - v
    if d <= -MEDIA_DIST: return "C"
    if d >= MEDIA_DIST: return "P"
    return None

def ev(fv, fijo):
    n = len(fv)
    if not n: return (0, 0.0, 0.0, 0.0, 0.0)
    mf = sum(fv) / n
    diracc = 100 * sum(1 for x in fv if x > 0) / n          # acierto direccional CRUDO (fav>0)
    pnls = [DELTA * x * 100 - fijo for x in fv]
    return (n, mf, sum(pnls) / n, 100 * sum(1 for p in pnls if p > 0) / n, diracc)

def main():
    orden, dias = carga()
    fams = [
        ("VWAP/media", lado_media), ("RSI rev 30/70", make_rsi(30, 70, "rev")),
        ("MACD trend", make_macd("trend")), ("MACD rev", make_macd("rev")),
        ("MACD cruce rev", make_macd_cross("rev")),
        ("EMA cross trend", make_ema_cross("trend")), ("EMA cross rev", make_ema_cross("rev")),
        ("Bollinger rev", make_bb("rev")), ("Bollinger breakout", make_bb("breakout")),
    ]
    # --- regimen por dia: DIRECCION (alcista/bajista/neutra) y TENDENCIA (efficiency ratio) ---
    def regd(b):
        cl = [x[1] for x in b]
        neto = cl[-1] - cl[0]
        camino = sum(abs(cl[i]-cl[i-1]) for i in range(1, len(cl))) or 1e-9
        return neto, abs(neto)/camino
    dird = {}; erd = {}
    for f in orden:
        neto, er = regd(dias[f])
        dird[f] = "alcista" if neto > 0.5 else ("bajista" if neto < -0.5 else "neutra")
        erd[f] = er
    ev_ord = sorted(erd.values()); q1 = ev_ord[len(ev_ord)//3]; q2 = ev_ord[2*len(ev_ord)//3]
    erbucket = {f: ("lateral" if erd[f] <= q1 else "mixto" if erd[f] <= q2 else "tendencial") for f in orden}
    from collections import Counter
    print("=" * 104)
    print("QUE TA FUNCIONA SEGUN EL REGIMEN DEL DIA — EV/op ($) por regimen. Contrato ITM 3pts, costo cruce.")
    print(f"  dias: {dict(Counter(dird.values()))} | tendencia: {dict(Counter(erbucket.values()))}")
    print(f"  (verde = EV>0). breakeven media_fav ~0.148 pts. n ops entre parentesis.")
    print("=" * 104)

    def evbucket(pd, cond):
        fv = [x for f in orden if cond(f) for x in pd.get(f, [])]
        if not fv: return None, 0
        return DELTA * (sum(fv)/len(fv)) * 100 - FIJO_CRUCE, len(fv)

    hdr = f"{'TA':>20} |" + "".join(f"{c:>16}" for c in ("alcista", "bajista", "neutra", "lateral", "mixto", "tendencial"))
    print(hdr)
    for etq, fn in fams:
        pd = favs_por_dia(orden, dias, fn)
        cols = []
        for reg, campo in (("alcista", dird), ("bajista", dird), ("neutra", dird),
                           ("lateral", erbucket), ("mixto", erbucket), ("tendencial", erbucket)):
            e, nn = evbucket(pd, lambda f, r=reg, c=campo: c[f] == r)
            cols.append(f"{e:+.2f}({nn})" if e is not None else "   -")
        print(f"  {etq:>18} |" + "".join(f"{c:>16}" for c in cols))
    print("=" * 104)
    print("LECTURA: buscar CUALQUIER celda EV>0 (un TA que gane en un regimen concreto).")

if __name__ == "__main__":
    main()
