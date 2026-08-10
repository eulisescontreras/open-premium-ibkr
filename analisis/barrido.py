# -*- coding: utf-8 -*-
"""READ-ONLY. BARRIDO SISTEMATICO: de todo lo que guardamos, que separa un momento en que
viene un movimiento GRANDE de uno en que no?

Movimiento GRANDE = el que de verdad paga en una 0DTE. No 0.20 (pasa el 86% del tiempo:
tasa base inutil), sino umbrales que muevan la prima lo bastante para cubrir spread + theta.
Se reporta SIEMPRE la tasa base para poder juzgar si un predictor aporta algo.
"""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)
F = "2026-08-10"

ta = c.execute(
    "SELECT hora,spy,rsi,macd_hist,atr_pct,vwap,bb_up,bb_low,bb_mid,ta_score,obv_trend,"
    "net_call,net_put,diff,thr,momentum,prem_call_min,prem_put_min,net_call_min,net_put_min "
    "FROM ta_minute WHERE fecha=? AND spy IS NOT NULL ORDER BY hora", (F,)).fetchall()
w = c.execute("SELECT hora,spot,gex_total,gamma_flip,call_wall,put_wall,prem_center,"
              "max_pain_dyn FROM walls_snapshot WHERE fecha=? ORDER BY hora", (F,)).fetchall()


def m(h):
    a = h.split(":")
    return int(a[0]) * 60 + int(a[1])


# walls mas reciente <= t
wl = sorted([(m(x[0]), x) for x in w])


def walls_en(t):
    r = None
    for tt, x in wl:
        if tt <= t:
            r = x
        else:
            break
    return r


P = {}
for r in ta:
    t = m(r[0])
    spy = r[1]
    bb = ((r[6] - r[7]) / r[8] * 100.0) if (r[6] and r[7] and r[8]) else None
    ww = walls_en(t)
    P[t] = {
        "hora": r[0], "spy": spy,
        "rsi": r[2], "macd_h": r[3], "atr_pct": r[4],
        "dist_vwap": (spy - r[5]) if r[5] else None,
        "abs_dist_vwap": abs(spy - r[5]) if r[5] else None,
        "bb_ancho": bb,
        "ta_score": r[9], "abs_ta_score": abs(r[9]) if r[9] is not None else None,
        "diff": r[13], "thr": r[14], "momentum": r[15],
        "abs_momentum": abs(r[15]) if r[15] is not None else None,
        "diff_sobre_thr": (abs(r[13]) / r[14]) if (r[13] is not None and r[14]) else None,
        "prem_vela": ((r[16] or 0) + (r[17] or 0)) if r[16] is not None else None,
        "ratio_cp_vela": ((r[16] / r[17]) if (r[16] and r[17]) else None),
        "abs_net_vela": (abs((r[18] or 0) - (r[19] or 0)) if r[18] is not None else None),
        "dist_flip": (spy - ww[3]) if (ww and ww[3]) else None,
        "abs_dist_flip": (abs(spy - ww[3]) if (ww and ww[3]) else None),
        "dist_peso": (spy - ww[6]) if (ww and ww[6]) else None,
        "abs_dist_peso": (abs(spy - ww[6]) if (ww and ww[6]) else None),
        "gex_bn": (ww[2] / 1e9) if (ww and ww[2]) else None,
        "dist_CW": (ww[4] - spy) if (ww and ww[4]) else None,
        "dist_PW": (spy - ww[5]) if (ww and ww[5]) else None,
    }


def mov_max(t0, mins):
    p0 = P[t0]["spy"]
    v = [abs(P[t]["spy"] - p0) for t in range(t0 + 1, t0 + mins + 1) if t in P]
    return max(v) if v else None


VARS = ["bb_ancho", "atr_pct", "rsi", "abs_dist_vwap", "dist_vwap", "macd_h", "abs_ta_score",
        "abs_momentum", "diff_sobre_thr", "prem_vela", "ratio_cp_vela", "abs_net_vela",
        "abs_dist_flip", "abs_dist_peso", "gex_bn", "dist_CW", "dist_PW"]

for UMBRAL, H in ((0.40, 10), (0.60, 10), (0.40, 5)):
    print("\n" + "=" * 78)
    print("MOVIMIENTO GRANDE = >= %.2f del SPY en %d min" % (UMBRAL, H))
    print("=" * 78)
    si = []
    no = []
    for t in sorted(P):
        mv = mov_max(t, H)
        if mv is None:
            continue
        (si if mv >= UMBRAL else no).append(t)
    base = len(si) / (len(si) + len(no)) * 100.0
    print("  ocurre en %d de %d minutos -> TASA BASE %.0f%%" % (len(si), len(si) + len(no), base))
    print()
    print("  variable            con MOV     sin MOV    separacion   utilidad")
    filas = []
    for v in VARS:
        a = [P[t][v] for t in si if P[t].get(v) is not None]
        b = [P[t][v] for t in no if P[t].get(v) is not None]
        if len(a) < 8 or len(b) < 8:
            continue
        a_s = sorted(a)
        b_s = sorted(b)
        ma = a_s[len(a_s) // 2]
        mb = b_s[len(b_s) // 2]
        # separacion normalizada por la dispersion (una especie de tamano de efecto)
        todos = sorted(a + b)
        iqr = todos[int(len(todos) * 0.75)] - todos[int(len(todos) * 0.25)]
        eff = ((ma - mb) / iqr) if iqr else 0.0
        filas.append((abs(eff), v, ma, mb, eff))
    filas.sort(reverse=True)
    for eff_abs, v, ma, mb, eff in filas:
        util = "***" if eff_abs > 0.5 else ("**" if eff_abs > 0.3 else ("*" if eff_abs > 0.15 else ""))
        print("  %-18s %10.4f %10.4f     %+.2f      %s" % (v, ma, mb, eff, util))
    print("  (separacion = diferencia de medianas / rango intercuartilico. |x|>0.3 empieza")
    print("   a ser interesante; por debajo de 0.15 es ruido)")
