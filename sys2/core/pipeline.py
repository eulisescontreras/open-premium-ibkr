# -*- coding: utf-8 -*-
"""PIPELINE de señales COMPARTIDO por backtest y vivo (única fuente de verdad, R9).
Construye el dict `Sen` (unión de las 6 entradas + reglas de descarte/inversión) tal como lo
hace el motor validado. Extraído VERBATIM de backtest/motor.SIS70 (verificado por cr_motor:
tras usar esta función el motor sigue dando +72.375$; y cr_pipeline lo compara señal a señal).

Orden EXACTO: ST-3 flips (sen_p) → ORB(09:40,11:00) → aperturas (pm_rev,v1,gap_fade,ayer_rev,
descarte >5 contra TODO S) → por cada flip ≥09:45: descarte ST-1 (antes del rebote) → skew sobre
RETRASA (RETMOD/RETSK) → reb2. Sen=dict(sorted(set(S+p))) (colisión mismo minuto: gana 'P').
"""
from sys2 import config as C
from sys2.core.supertrend import mm
from sys2.core import entradas as E
from sys2.core.rebote import sen_p, reb2
from sys2.core.st1 import st_full, giros
from sys2.core import reglas as R


def construir_sen(bars, cl_, PM, ph, pl, pc, extra=None):
    """bars = [(hora,high,low,close)] 1-min desde 04:00. cl_ = {hora: close SPY}.
    PM = {hora: {(right,strike): (mid, day_vol)}} (para el skew). ph/pl/pc = max/min/cierre de AYER.
    Devuelve (Sen, L, ks, ik, sp): Sen dict hora->'C'/'P'; L/ks/ik del rebote; sp flips ST-3."""
    extra = extra if extra is not None else C.APERTURAS_ORDEN
    sp, L, ks = sen_p(bars, C.ST_PER, C.ST_MULT)
    ik = {k: i for i, k in enumerate(ks)}
    S1, k1 = st_full(bars, 1, C.ST_PER, C.ST_MULT)

    orig = {}   # (hora,dir) -> origen ('ORB'/'pm_rev'/'ST-3'/'ST-3 SKEW'/...)

    # S = ORB (2 anclas) + aperturas (descarte >5 contra TODO S, en orden)
    S = []
    for a in C.ORB_ANCLAS:
        s = E.orb_en(bars, a)
        if s:
            S += s
            for x in s:
                orig[x] = "ORB"
    for ex in extra:
        sg = E.senales_apertura(bars, ph, pl, pc, ex)
        if sg and all(abs(mm(sg[0][0]) - mm(x[0])) > C.DESCARTE_MIN for x in S):
            S += sg
            for x in sg:
                orig[x] = ex

    # p = flips reclasificados (ST-1 antes del rebote, skew sobre RETRASA)
    p = []
    for h, d in sp:
        if h < "09:45":
            continue
        if C.ST1_ON and giros(S1, k1, h, C.ST1_VENTANA) >= 1:
            continue
        if C.RETMOD:
            _r = reb2(L, ks, ik, h, d)
            _esret = bool(_r) and _r[0][0] != h and _r[0][1] == d
            if _esret:
                _lado = 1 if d == 'C' else -1
                _S = cl_.get(h)
                _m = PM.get(h)
                _sk = R.skew_l2(_m, _S, h, _lado) if (_m and _S is not None) else None
                _mal = (_sk is not None and _sk > C.RETSK)
                if _mal:
                    _hh = _r[0][0]
                    if C.RETMOD == "quita" or _hh >= "15:40":
                        continue
                    if C.RETMOD == "invierte":
                        x = (_hh, 'P' if d == 'C' else 'C')
                        p.append(x)
                        orig[x] = "ST-3 SKEW"
                        continue
        rr = reb2(L, ks, ik, h, d)
        p += rr
        for x in rr:
            # NORMAL = misma hora y dir; RETRASA = otra hora; INVIERTE = dir contraria
            g = "NORMAL" if (x[0] == h and x[1] == d) else ("INVIERTE" if x[1] != d else "RETRASA")
            orig[x] = "ST-3 " + g

    Sen = dict(sorted(set(S + p)))
    origen = {h: orig.get((h, Sen[h])) for h in Sen}
    return Sen, L, ks, ik, sp, origen
