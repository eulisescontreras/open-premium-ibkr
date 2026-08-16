# -*- coding: utf-8 -*-
"""Nucleo del Supertrend del sistema (ST-3) — compartido por backtest y vivo.
Sin dependencias del backtest (no arrastra simulador_st/synth_premium): el sistema en
vivo debe quedar limpio. La equivalencia EXACTA con la funcion validada del backtest
(year_backtest.st_dir y backtest_st3_orb.sen_principal) la garantiza cr_supertrend.py.

st_dir es copia LITERAL de analisis/year_backtest.py:27 (VERIFICADO 2026-08-16). NO se
reimplementa la matematica: es la misma formula que produjo las cifras validadas; el cold
run diferencial falla si divergen.
OBLIGATORIO: antes de modificar, leer el plan aprobado y correr cr_supertrend.py.
"""


def mm(h):
    """'HH:MM' -> minutos desde medianoche."""
    return int(h[:2]) * 60 + int(h[3:5])


def hhmm(m):
    return "%02d:%02d" % (m // 60, m % 60)


def st_dir(hi, lo, cl, per=7, mult=3.0):
    """Supertrend Wilder. Devuelve tend[i] en {+1,-1} (0 hasta que hay ATR).
    Copia literal de year_backtest.st_dir (equivalencia verificada por cold run)."""
    n = len(cl)
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    atr = [None] * n
    if n > per:
        atr[per] = sum(tr[1:per + 1]) / per
        for i in range(per + 1, n):
            atr[i] = (atr[i - 1] * (per - 1) + tr[i]) / per
    tend = [0] * n
    fu = fl = None
    d = 1
    for i in range(n):
        if atr[i] is None:
            continue
        med = (hi[i] + lo[i]) / 2
        bu = med + mult * atr[i]
        bl = med - mult * atr[i]
        fu = bu if (fu is None or bu < fu or cl[i - 1] > fu) else fu
        fl = bl if (fl is None or bl > fl or cl[i - 1] < fl) else fl
        if d == 1 and cl[i] < fl:
            d = -1
        elif d == -1 and cl[i] > fu:
            d = 1
        tend[i] = d
    return tend


def buckets3(bars, n=3):
    """bars = lista de (hora,'HH:MM', high, low, close) de 1 min.
    Agrupa en buckets de n minutos (label = inicio del bucket). Premarket incluido
    (calienta el ATR). Devuelve (HO, HI, LO, CL) alineados y ordenados por hora."""
    buck = {}
    for h, hi, lo, cl in bars:
        s = (mm(h) // n) * n
        a = buck.setdefault(s, {"hi": hi, "lo": lo, "cl": cl})
        a["hi"] = max(a["hi"], hi)
        a["lo"] = min(a["lo"], lo)
        a["cl"] = cl                    # close del bucket = ultimo close de 1 min
    st = sorted(buck)
    return ([hhmm(s) for s in st],
            [buck[s]["hi"] for s in st],
            [buck[s]["lo"] for s in st],
            [buck[s]["cl"] for s in st])


def flips_st3(bars, per=7, mult=3.0, shift=3, ini="09:45"):
    """Flips del ST-3 EJECUTABLES del sistema. Equivale a
    backtest_st3_orb.sen_principal(bars): bucketing 3-min con premarket, st_dir,
    flips RTH, shift_sen(+3) y filtro desde `ini` (09:45).
    bars = [(hora,high,low,close)] de 1 min DESDE LAS 04:00.
    Devuelve [(hora_ejecutable, 'C'|'P')]. Anti-look-ahead: el flip del bucket que
    cierra en T se ejecuta en T+shift."""
    HO, HI, LO, CL = buckets3(bars, 3)
    D = st_dir(HI, LO, CL, per, mult)
    out = []
    prev = None
    for i in range(len(HO)):
        # el premarket calienta el ATR pero NO cuenta como flip previo: se SALTA sin
        # tocar prev (identico a backtest_st3_orb.sen_principal). La primera senal RTH
        # siempre se emite (prev sigue None hasta la primera vela >=09:30).
        if HO[i] < "09:30" or HO[i] > "16:00" or D[i] == 0:
            continue
        if prev is None or D[i] != prev:
            out.append((HO[i], "C" if D[i] > 0 else "P"))
        prev = D[i]
    # shift_sen(+3) y filtro desde ini (09:45) sobre el resultado ya desplazado
    return [(hhmm(mm(h) + shift), d) for h, d in out if hhmm(mm(h) + shift) >= ini]
