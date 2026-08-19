# -*- coding: utf-8 -*-
"""REGLAS 3-5 del sistema validado: ratio call/put OTM (+3.030$), skew sobre RETRASA
(+3.874$), día bueno (+6.433$). Transcripción VERBATIM del motor (agente, 2026-08-16).

Interfaz de la cadena `m` (= PM[h]): dict {(right,strike): v} con v[0]=mid/precio, v[1]=volumen.
`iv()` del motor = greeks.implied_vol con r=0, q=0 (convención del motor). T = 252-day.
OBLIGATORIO: antes de modificar, leer el plan/ESTADO y correr el motor (cr_motor).
"""
from sys2.core.supertrend import mm
from sys2.backtest import greeks as _G
from sys2 import config as C


def _T(h):
    """Tiempo a vencimiento del motor: minutos hasta 16:00 sobre año de 252 días."""
    return max(1e-6, (960 - mm(h)) / (60 * 24 * 252))


def _iv(precio, S, K, h, esC):
    """iv() del motor: implied_vol con r=0, q=0."""
    return _G.implied_vol(precio, S, K, _T(h), C.GREEKS_R, C.GREEKS_Q, "C" if esC else "P")


# ─────────────────────────── REGLA 3 · ratio call/put OTM ───────────────────────────
def ratio_otm(m, S):
    """Ratio de volumen OTM: calls arriba del spot / puts abajo. None si <30 contratos.
    Veto (en el motor): rt=='C' y rr<RUMB -> no operar; rt=='P' y rr>1/RUMB -> no operar."""
    voc = sum(v[1] for (r, k), v in m.items() if r == 'C' and k > S)
    vop = sum(v[1] for (r, k), v in m.items() if r == 'P' and k < S)
    if voc + vop < 30:
        return None
    return voc / max(1.0, vop)


# ─────────────────────────── REGLA 4 · skew sobre RETRASA ───────────────────────────
def skew_l2(m, S, h, lado):
    """(mediana IV puts − mediana IV calls) * lado, sobre strikes OTM 0.8<dist<3.5.
    En el motor: si un flip clasifica RETRASA y skew_l2 > RETSK -> invertir la señal."""
    ivp = []
    ivc = []
    for (r, k), v in m.items():
        d = (k - S) if r == 'C' else (S - k)
        if not (0.8 < d < 3.5):
            continue
        s_ = _iv(max(v[0], 0.01), S, k, h, r == 'C')
        if s_ and 0.03 < s_ < 3:
            (ivc if r == 'C' else ivp).append(s_)
    if len(ivp) < 2 or len(ivc) < 2:
        return None
    import statistics as _st
    return (_st.median(ivp) - _st.median(ivc)) * lado


# ────────────── REGLA 6 · SCORE DE OPCIONES (2026-08-19, +9.606$) ──────────────
def libro_vigente(PM, ventana=10):
    """{hora: cadena vigente} con el ÚLTIMO precio conocido de cada strike (<= `ventana` min).
    HACE FALTA porque la cadena histórica solo trae los contratos QUE COTIZARON ese minuto
    (~13 de 82): sin esto el score no tiene datos y no dispara nunca.
    Solo usa el PASADO -> no introduce look-ahead."""
    vig, out = {}, {}
    for h in sorted(PM):
        for k, v in PM[h].items():
            vig[k] = (v[0], v[1] if len(v) > 1 else 0.0, mm(h))
        lim = mm(h) - ventana
        out[h] = {k: (v[0], v[1]) for k, v in vig.items() if v[2] >= lim}
    return out


def score_opciones(m, S, h, lado, rt, ancho=2.0):
    """Cuenta 0-3 condiciones ADVERSAS de la cadena EN EL MINUTO DEL FLIP (coste de tiempo CERO).
    Validado out-of-sample (umbrales del percentil 25 del AÑO 1, año 2 nunca visto al elegirlos):
      score 0 -> 51,0% pierden | 1 -> 59,1% | 2 -> 74,1% | 3 -> 89,3%   (p=0,0000 vs azar)
    Lectura económica: vertical barato = el mercado no paga el movimiento; IV muerta = sin
    recorrido; skew alto = pagan protección CONTRA la dirección del flip."""
    if not m or S is None:
        return 0
    sc = 0
    sk = skew_l2(m, S, h, lado)
    if sk is not None and sk >= C.SCORE_SKEW:
        sc += 1
    ks = sorted({k for (r_, k) in m if r_ == rt}, key=lambda k: abs(k - S))
    if not ks:
        return sc
    katm = ks[0]
    vl = m.get((rt, katm))
    vc = m.get((rt, katm + ancho * lado))
    if vl and vl[0] > 0.01:
        iv = _iv(vl[0], S, katm, h, rt == 'C')
        if iv is not None and iv <= C.SCORE_IV:
            sc += 1
    if vl and vc and vl[0] > 0 and vc[0] > 0:
        if (vl[0] - vc[0]) / ancho <= C.SCORE_COSTV:
            sc += 1
    return sc


# ─────────────────────────── REGLA 5 · día bueno (dobla) ────────────────────────────
def dia_bueno(cl_, dia_bars, tlt_bars):
    """True si efic60<E60B y mov_DIA>MDB y mov_TLT<MTB -> dobla unidades (nq=2).
    cl_      = {hora: close} de la sesión (RTH).
    dia_bars / tlt_bars = lista de (hora, hi, lo, cl) de DIA/TLT (índice [3]=cierre)."""
    hs = sorted(cl_)
    if len(hs) <= 60:
        return False
    sg = [cl_[x] for x in hs[:60]]
    rc = sum(abs(sg[i] - sg[i - 1]) for i in range(1, len(sg)))
    e60 = abs(sg[-1] - sg[0]) / rc if rc else 9

    def _mvetf(b):
        if not b:
            return None
        h9 = [x for x in b if "09:30" <= x[0] <= "10:00"]
        if len(h9) < 20:
            return None
        return (h9[-1][3] - h9[0][3]) / max(0.01, h9[0][3]) * 1000

    md = _mvetf(dia_bars)
    mt = _mvetf(tlt_bars)
    return (e60 < C.E60B and md is not None and md > C.MDB
            and mt is not None and mt < C.MTB)
