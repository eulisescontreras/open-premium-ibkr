# -*- coding: utf-8 -*-
"""REGLA 1 — EL REBOTE (la pieza clave, +33.000$). Clasifica cada flip del ST-3 en
NORMAL / RETRASA / INVIERTE / DESCARTA. Compartido backtest+vivo.

⚠️ FUENTE VERIFICADA (2026-08-16): transcripción VERBATIM del código real `reb2()` +
`st_lin_p()` + `sen_p()` + loop clasificador que produjo las cifras validadas con premium
REAL (+70.769$). El PDF §10.5 estaba DESACTUALIZADO (usaba ventana 8, cierre en vez de mecha).
Confirmado con el agente dueño del análisis. Target del cold run (cr_rebote):
  1.411 flips · 479 días · grupos 675/393/243/100 · falsos 12.3/9.1·42.8/42.2·53.5/62.1·31.2/40.4

DIFERENCIAS CLAVE vs el ST sintético (core/supertrend.st_dir / sen_principal):
  - st_lin_p: ATR = media corrida desde i=0 y luego Wilder (st_dir arranca en `per`).
  - init d=-1 (st_dir arranca d=1).
  - sen_p ACTUALIZA prev en premarket (flips_st3 no) -> puede mover el primer flip RTH.
  Por eso el rebote usa su PROPIA ST (st_lin_p), NO se reusa st_dir. La entrada A del sistema
  validado = flip de sen_p reclasificado por reb2 (reconciliar supertrend.py/entradas A aparte).

reb2: toque con la MECHA (punta=lo si CALL, hi si PUT; d_ac=|punta-linea|), separación con el
CIERRE (d_cl=|cl-linea|). Ventana espera=12 buckets (36 min). cerca=1.0 ATR, sep=1.5 ATR,
pegado=2. guard: entradas con hora >= "15:40" se descartan (return []).
OBLIGATORIO: antes de modificar, leer el plan, ESTADO.md y correr cr_rebote.py.
"""
from sys2.core.supertrend import mm, hhmm


def shift_sen(sen, n):
    """+n minutos a cada señal (exp_timing_realista.shift_sen, verbatim)."""
    return [(hhmm(mm(h) + n), lado) for h, lado in sen]


def st_lin_p(bars, per=7, mult=3.0):
    """Supertrend de 3 min que EXPONE la línea (fl/fu) por bucket. VERBATIM del sistema
    validado. bars = [(hora,high,low,close)] de 1 min DESDE 04:00 (premarket calienta ATR).
    Devuelve (out, ks, D): out[k] = {linea, cl, o, hi, lo, d}; ks buckets ordenados; D dirs.
    `o` = CLOSE del primer minuto del bucket (no el open real)."""
    b = {}
    for h, hi, lo, cl in bars:
        s = (mm(h) // 3) * 3
        a = b.setdefault(s, {"hi": hi, "lo": lo, "cl": cl, "o": None})
        if a["o"] is None:
            a["o"] = cl
        a["hi"] = max(a["hi"], hi)
        a["lo"] = min(a["lo"], lo)
        a["cl"] = cl
    ks = sorted(b)
    HI = [b[s]["hi"] for s in ks]
    LO = [b[s]["lo"] for s in ks]
    CL = [b[s]["cl"] for s in ks]
    OP = [b[s]["o"] for s in ks]
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
    D = []
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
        out[ks[i]] = dict(linea=fl if d == 1 else fu, cl=CL[i], o=OP[i],
                          hi=HI[i], lo=LO[i], d=d)
        D.append(d)
    return out, ks, D


def sen_p(bars, per=7, mult=3.0):
    """Flips del ST-3 del sistema validado (VERBATIM). Devuelve (sp, L, ks) donde sp son
    los flips ya con shift_sen(+3). Filtro aquí 09:30; el 09:45 lo aplica el llamador.
    OJO: prev se actualiza en premarket (distinto de core.flips_st3)."""
    L, ks, D = st_lin_p(bars, per, mult)
    out = []
    prev = None
    for i, k in enumerate(ks):
        h = hhmm(k)
        if h < "09:30" or h > "16:00" or D[i] == 0:
            prev = D[i]
            continue
        if prev is None or D[i] != prev:
            out.append((h, "C" if D[i] > 0 else "P"))
        prev = D[i]
    return shift_sen(out, 3), L, ks


def reb2(L, ks, ik, h, d, espera=12, cerca=1.0, sep=1.5, pegado=2):
    """Clasifica UN flip del ST-3. VERBATIM del sistema validado. Devuelve:
      [(h, d)]                 -> NORMAL (no tocó la línea, entra igual)
      [(hh, d)]                -> RETRASA (tocó y se separó >sep ATR, entra en hh, misma dir)
      [(hh, dir_contraria)]    -> INVIERTE (tocó y siguió pegado `pegado` buckets, invierte)
      []                       -> DESCARTA (tocó y no resolvió, o resolvió con hh>=15:40)
    Toque con la MECHA (punta), separación con el CIERRE. Ventana espera=12 buckets."""
    s0 = (mm(h) // 3) * 3
    i = ik.get(s0)
    if i is None:
        return [(h, d)]
    lado = 1 if d == 'C' else -1
    atrs = [L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(max(0, i - 10), i + 1)]
    atr = sum(atrs) / len(atrs) if atrs else 0.5
    contra = 0
    toco = False
    cn = 0
    for j in range(i + 1, min(i + espera + 1, len(ks))):
        x = L[ks[j]]
        if (x['cl'] - x['o']) * lado < 0:
            contra += 1
        punta = x['lo'] if lado > 0 else x['hi']
        d_ac = abs(punta - x['linea'])
        d_cl = abs(x['cl'] - x['linea'])
        if not toco and contra >= 1 and d_ac <= cerca * atr:
            toco = True
            cn = 0
            continue
        if toco:
            if d_cl > sep * atr:
                hh = hhmm(ks[j])
                return [(hh, d)] if hh < "15:40" else []
            if d_ac <= cerca * atr:
                cn += 1
                if cn >= pegado:
                    hh = hhmm(ks[j])
                    return [(hh, 'P' if d == 'C' else 'C')] if hh < "15:40" else []
    return [] if toco else [(h, d)]


def _grupo(r_, h, d):
    """Clasifica el resultado de reb2 en el nombre del grupo (loop llamador, verbatim)."""
    if not r_:
        return 'DESCARTA'
    if r_[0][0] == h and r_[0][1] == d:
        return 'NORMAL'
    if r_[0][1] != d:
        return 'INVIERTE'
    return 'RETRASA'


def clasificar_dia(bars, rth):
    """Corre el ST-3 del día, recorre sus flips en [09:45,15:30] y clasifica cada uno.
    bars = [(hora,high,low,close)] 1-min DESDE 04:00 (premarket incluido).
    rth   = [(hora, close)] de 09:30-16:00 (para 'falso' y el filtro de sesión válida).
    Devuelve lista de dicts por flip: hora, direccion, grupo, hora_efectiva, direccion_final,
    falso. VERBATIM del loop llamador (sin la dependencia de premium P: el filtro de día está
    en el llamador/cold run)."""
    import statistics as st
    cl_ = {h: x for h, x in rth}
    if len(cl_) < 100:
        return []
    sp, L, ks = sen_p(bars, 7, 3.0)
    ik = {k: i for i, k in enumerate(ks)}
    flips = [(h, d) for h, d in sp if "09:45" <= h <= "15:30"]
    salida = []
    for i, (h, d) in enumerate(flips):
        k = (mm(h) // 3) * 3
        j = ik.get(k)
        if j is None or j < 10 or j + 13 >= len(ks):
            continue
        lado = 1 if d == 'C' else -1
        atr = st.mean([L[ks[z]]['hi'] - L[ks[z]]['lo'] for z in range(j - 9, j + 1)])
        if atr <= 0:
            continue
        fin = flips[i + 1][0] if i + 1 < len(flips) else "15:59"
        seg = [cl_[z] for z in sorted(cl_) if h <= z <= fin]
        if len(seg) < 3:
            continue
        falso = 1 if max((y - seg[0]) * lado for y in seg) / atr < 1.0 else 0
        r_ = reb2(L, ks, ik, h, d)
        grupo = _grupo(r_, h, d)
        he = r_[0][0] if r_ else None
        df = r_[0][1] if r_ else None
        salida.append({"hora": h, "direccion": d, "grupo": grupo,
                       "hora_efectiva": he, "direccion_final": df, "falso": falso})
    return salida
