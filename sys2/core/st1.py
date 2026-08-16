# -*- coding: utf-8 -*-
"""REGLA — DESCARTE ST-1 (+1.842$). Descarta un flip del ST-3 si el Supertrend de 1 MINUTO
gira ≥1 vez en los 5 min siguientes al flip (los flips falsos suben a ~66-68% cuando gira).
Se evalúa ANTES del rebote: un flip descartado por ST-1 nunca llega a reb2.

Transcripción VERBATIM del motor validado (agente, 2026-08-16). `st_full` generaliza la ST a
cualquier timeframe tf; para el ST-1 se usa tf=1 (per=7, mult=3.0, igual que el ST-3). Arranca
desde donde arranquen las barras (04:00, premarket). Ventana N=5 semiabierta [m0, m0+5).

Nota (R9): st_full(bars,3) es equivalente a core/rebote.st_lin_p (misma ST); no se unifica para
no tocar el rebote ya validado bit-exact (R15). st_full añade el guard len(ks)<per+2 y 'atr'.
OBLIGATORIO: antes de modificar, leer el plan/ESTADO y correr cr_st1.py (y el motor).
"""
from sys2.core.supertrend import mm


def st_full(bars, tf, per=7, mult=3.0):
    """Supertrend sobre buckets de `tf` minutos. Devuelve (out, ks): out[k] =
    {d, linea, cl, o, hi, lo, atr}. bars = [(hora,high,low,close)] 1-min desde 04:00."""
    b = {}
    for h, hi, lo, cl in bars:
        s = (mm(h) // tf) * tf
        a = b.setdefault(s, {"hi": hi, "lo": lo, "cl": cl, "o": None})
        if a["o"] is None:
            a["o"] = cl
        a["hi"] = max(a["hi"], hi)
        a["lo"] = min(a["lo"], lo)
        a["cl"] = cl
    ks = sorted(b)
    if len(ks) < per + 2:
        return {}, []
    HI = [b[s]["hi"] for s in ks]
    LO = [b[s]["lo"] for s in ks]
    CL = [b[s]["cl"] for s in ks]
    tr = []
    atr = []
    for i in range(len(CL)):
        t = HI[i] - LO[i] if i == 0 else max(
            HI[i] - LO[i], abs(HI[i] - CL[i - 1]), abs(LO[i] - CL[i - 1]))
        tr.append(t)
        atr.append(sum(tr) / len(tr) if i < per else atr[-1] + (t - atr[-1]) / per)
    d = -1
    fu = fl = None
    out = {}
    for i in range(len(ks)):
        m = (HI[i] + LO[i]) / 2
        ub = m + mult * atr[i]
        lb = m - mult * atr[i]
        if i == 0:
            fu, fl = ub, lb
        else:
            fu = ub if (ub < fu or CL[i - 1] > fu) else fu
            fl = lb if (lb > fl or CL[i - 1] < fl) else fl
        if d == 1 and CL[i] < fl:
            d = -1
        elif d == -1 and CL[i] > fu:
            d = 1
        out[ks[i]] = dict(d=d, linea=fl if d == 1 else fu, cl=CL[i], o=b[ks[i]]["o"],
                          hi=HI[i], lo=LO[i], atr=atr[i])
    return out, ks


def giros(S1, k1, h, N=5):
    """Cuenta cambios de dirección del ST-1 en la ventana [mm(h), mm(h)+N).
    S1,k1 = st_full(bars,1). Si giros>=1 tras un flip -> descartar la señal."""
    m0 = mm(h)
    sub = [S1[x]['d'] for x in k1 if m0 <= x < m0 + N and x in S1]
    if len(sub) < 2:
        return 0
    return sum(1 for z in range(1, len(sub)) if sub[z] != sub[z - 1])
