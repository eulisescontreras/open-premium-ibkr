# -*- coding: utf-8 -*-
"""READ-ONLY. BARRIDO TOTAL: TA + premium + GEX/walls, NIVELES y CAMBIOS (deltas).
Objetivo: encontrar que separa el momento previo a un movimiento aprovechable.

Se separan DOS tipos de movimiento (peticion del usuario):
  BRUSCO  = >= 0.40 en 3 min   (llega rapido: el theta casi no cobra)
  GRADUAL = >= 0.60 en 15 min PERO < 0.40 en los primeros 3 (llega despacio)
Se reporta SIEMPRE la tasa base.
"""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _fecha import fecha_analisis   # fecha por argumento; por defecto, la ultima con datos

F = fecha_analisis()
ta = c.execute(
    "SELECT hora,spy,rsi,ema8,ema21,ema50,macd_line,macd_signal,macd_hist,bb_up,bb_mid,"
    "bb_low,atr,atr_pct,vwap,obv_trend,ta_score,net_call,net_put,diff,thr,momentum,"
    "prem_call_min,prem_put_min,net_call_min,net_put_min "
    "FROM ta_minute WHERE fecha=? AND spy IS NOT NULL ORDER BY hora", (F,)).fetchall()
wl = c.execute("SELECT hora,spot,gex_total,gamma_flip,call_wall,put_wall,prem_center,"
               "max_pain_dyn,spot_stale FROM walls_snapshot WHERE fecha=? ORDER BY hora",
               (F,)).fetchall()


def m(h):
    a = h.split(":")
    return int(a[0]) * 60 + int(a[1])


W = sorted([(m(x[0]), x) for x in wl])


def walls_en(t):
    r = None
    for tt, x in W:
        if tt <= t:
            r = x
        else:
            break
    return r


P = {}
for r in ta:
    t = m(r[0])
    spy, rsi = r[1], r[2]
    e8, e21, e50 = r[3], r[4], r[5]
    ml, ms, mh = r[6], r[7], r[8]
    bu, bm, bl = r[9], r[10], r[11]
    atr, atrp, vwap = r[12], r[13], r[14]
    sc = r[16]
    ww = walls_en(t)
    d = {"hora": r[0], "spy": spy, "rsi": rsi, "macd_line": ml, "macd_h": mh,
         "macd_dif": (ml - ms) if (ml is not None and ms is not None) else None,
         "atr_pct": atrp, "ta_score": sc, "obv": 1.0 if r[15] == "bullish" else 0.0,
         "bb_ancho": ((bu - bl) / bm * 100.0) if (bu and bl and bm) else None,
         # %B: donde esta el precio DENTRO de las bandas (0=banda baja, 1=banda alta)
         "pctB": ((spy - bl) / (bu - bl)) if (bu and bl and bu != bl) else None,
         "dist_vwap": (spy - vwap) if vwap else None,
         "abs_dist_vwap": abs(spy - vwap) if vwap else None,
         "e8_e21": (e8 - e21) if (e8 and e21) else None,
         "e21_e50": (e21 - e50) if (e21 and e50) else None,
         "spy_e8": (spy - e8) if e8 else None,
         "diff": r[19], "thr": r[20], "momentum": r[21],
         "abs_mom": abs(r[21]) if r[21] is not None else None,
         "diff_thr": (abs(r[19]) / r[20]) if (r[19] is not None and r[20]) else None,
         "prem_vela": ((r[22] or 0) + (r[23] or 0)) if r[22] is not None else None,
         "ratio_cp": ((r[22] / r[23]) if (r[22] and r[23]) else None),
         "net_vela": ((r[24] or 0) - (r[25] or 0)) if r[24] is not None else None,
         "abs_net_vela": (abs((r[24] or 0) - (r[25] or 0)) if r[24] is not None else None),
         }
    if ww and not (ww[8] == 1):        # excluir walls con spot congelado (GAP 17)
        d["gex_bn"] = (ww[2] / 1e9) if ww[2] else None
        d["dist_flip"] = (spy - ww[3]) if ww[3] else None
        d["abs_dist_flip"] = abs(spy - ww[3]) if ww[3] else None
        d["dist_CW"] = (ww[4] - spy) if ww[4] else None
        d["dist_PW"] = (spy - ww[5]) if ww[5] else None
        d["dist_peso"] = (spy - ww[6]) if ww[6] else None
        d["canal"] = (((spy - ww[5]) / (ww[4] - ww[5])) if (ww[4] and ww[5] and ww[4] != ww[5])
                      else None)
    P[t] = d

# ---- DELTAS (cambios), que suelen decir mas que los niveles ----
for t in sorted(P):
    p = P.get(t - 1)
    p3 = P.get(t - 3)
    for k in ("rsi", "macd_h", "atr_pct", "bb_ancho", "pctB", "dist_vwap", "gex_bn",
              "dist_flip", "ratio_cp", "prem_vela", "ta_score", "e8_e21"):
        v = P[t].get(k)
        P[t]["d_" + k] = (v - p[k]) if (p and v is not None and p.get(k) is not None) else None
    # velocidad y aceleracion del precio
    P[t]["vel1"] = (P[t]["spy"] - p["spy"]) if p else None
    P[t]["vel3"] = (P[t]["spy"] - p3["spy"]) if p3 else None
    P[t]["abs_vel3"] = abs(P[t]["vel3"]) if P[t]["vel3"] is not None else None


def mov(t0, mins):
    p0 = P[t0]["spy"]
    v = [abs(P[t]["spy"] - p0) for t in range(t0 + 1, t0 + mins + 1) if t in P]
    return max(v) if v else None


VARS = [k for k in P[sorted(P)[len(P) // 2]].keys() if k not in ("hora", "spy")]


def analizar(nombre, cond):
    si = []
    no = []
    for t in sorted(P):
        r = cond(t)
        if r is None:
            continue
        (si if r else no).append(t)
    if not si or not no:
        return
    base = len(si) / (len(si) + len(no)) * 100.0
    print("\n" + "=" * 78)
    print("%s   ->  %d de %d minutos (TASA BASE %.0f%%)" % (nombre, len(si), len(si) + len(no), base))
    print("=" * 78)
    filas = []
    for v in VARS:
        a = [P[t][v] for t in si if P[t].get(v) is not None]
        b = [P[t][v] for t in no if P[t].get(v) is not None]
        if len(a) < 10 or len(b) < 10:
            continue
        a_s = sorted(a)
        b_s = sorted(b)
        ma, mb = a_s[len(a_s) // 2], b_s[len(b_s) // 2]
        tod = sorted(a + b)
        iqr = tod[int(len(tod) * 0.75)] - tod[int(len(tod) * 0.25)]
        if not iqr:
            continue
        filas.append((abs((ma - mb) / iqr), v, ma, mb, (ma - mb) / iqr, len(a)))
    filas.sort(reverse=True)
    print("  variable            con MOV      sin MOV     separacion  n")
    for eff, v, ma, mb, s, na in filas[:12]:
        marca = "***" if eff > 0.5 else ("**" if eff > 0.35 else ("*" if eff > 0.2 else ""))
        print("  %-18s %11.4f %11.4f      %+.2f  %s  %d" % (v, ma, mb, s, marca, na))


def brusco(t):
    v3 = mov(t, 3)
    return None if v3 is None else v3 >= 0.40


def gradual(t):
    v3, v15 = mov(t, 3), mov(t, 15)
    if v3 is None or v15 is None:
        return None
    return (v15 >= 0.60) and (v3 < 0.40)


def plano(t):
    v10 = mov(t, 10)
    return None if v10 is None else v10 < 0.20


analizar("MOVIMIENTO BRUSCO: >=0.40 en 3 min", brusco)
analizar("MOVIMIENTO GRADUAL: >=0.60 en 15 min pero <0.40 en los primeros 3", gradual)
analizar("MERCADO PLANO: <0.20 en 10 min (donde NO hay que estar)", plano)
