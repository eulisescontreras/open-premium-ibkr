# -*- coding: utf-8 -*-
"""MOTOR de backtest (SIS70) — corre el sistema COMPLETO validado sobre la cadena real de
massive_premium.db y reproduce las cifras titulares (+71.396$ base / +61.999$ operable).
Transcripción VERBATIM del motor del sistema validado (agente dueño del análisis, 2026-08-16).

Núcleo compartido con el vivo: usa core/rebote (sen_p, reb2), core/st1 (st_full, giros),
core/reglas (ratio_otm, skew_l2, dia_bueno), core/instrumento (suelo, elegir_vert, elegir),
core/entradas (orb_en + aperturas), backtest/greeks (iv/greeks, r=0 q=0).

DATOS (solo backtest): PREM[fk][hora][(right,strike)] = (close, vol) desde massive (0DTE del día);
Sx = close del SPY del minuto (sys2.bars); ETFB[tk][fk] = [(hora,hi,lo,cl)] (DIA/TLT).
El P&L usa el CLOSE real de massive; los greeks (BS) solo alimentan decisiones.
OBLIGATORIO: antes de modificar, leer el plan/ESTADO y correr cr_motor.py.
"""
import os
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sys2 import config as C
from sys2.core.supertrend import mm
from sys2.core import entradas as E
from sys2.core.rebote import sen_p, reb2
from sys2.core.st1 import st_full, giros
from sys2.core import reglas as R
from sys2.core import instrumento as I
from sys2.backtest import greeks as G

_ET = ZoneInfo("America/New_York")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MASSIVE = os.path.join(RAIZ, "massive_premium.db")


# ─────────────────────────── greeks helpers (convención motor) ──────────────────────
def iv(precio, S, K, T, esC):
    return G.implied_vol(precio, S, K, T, C.GREEKS_R, C.GREEKS_Q, "C" if esC else "P")


def greeks(S, K, T, s_, esC):
    g = G.greeks(S, K, T, C.GREEKS_R, C.GREEKS_Q, s_, "C" if esC else "P")
    if g is None:
        return None, None, None
    return g["delta"], g["gamma"], g["vega"]


def _T(h):
    return max(1e-6, (960 - mm(h)) / (60 * 24 * 252))


# ─────────────────────────────── carga de datos (backtest) ──────────────────────────
def _hora_et(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).astimezone(_ET).strftime("%H:%M")


def cargar(con, dias=None):
    """Devuelve (SES, PREM, ETFB): SES=[(fk,bars,rth)], PREM[fk][h][(rt,k)]=(close,vol),
    ETFB[tk][fk]=[(h,hi,lo,cl)]. bars = 1-min desde 04:00; rth = (h,close,hi,lo,cl) 09:30-16:00."""
    # dias con premium en massive (0DTE)
    mv = sqlite3.connect(MASSIVE)
    PREM = {}
    prem_dias = set(r[0] for r in mv.execute("select distinct fecha from aggs"))
    if dias is None:
        dias = sorted(prem_dias)
    else:
        dias = [d for d in dias if d in prem_dias]
    for fk in dias:
        dd = {}
        for tk, ts, cl, vol in mv.execute(
                "select ticker,ts,close,volume from aggs where fecha=?", (fk,)):
            p = G.parse_occ(tk)
            if p is None:
                continue
            expiry, right, strike = p
            if expiry != fk:                 # solo 0DTE
                continue
            dd.setdefault(_hora_et(ts), {})[(right, strike)] = (cl, vol)
        if dd:
            PREM[fk] = dd
    mv.close()

    # bars (1-min con premarket) + rth  desde sys2.bars
    SES = []
    for fk in dias:
        rows = con.execute(
            "select hora,open,high,low,close from bars where fecha=? order by hora", (fk,)).fetchall()
        if not rows:
            continue
        bars = [(h, hi, lo, cl) for h, op, hi, lo, cl in rows]
        rth = [(h, cl, hi, lo, cl) for h, op, hi, lo, cl in rows if "09:30" <= h <= "16:00"]
        SES.append((fk, bars, rth))

    # ETF (DIA/TLT)
    ETFB = {"DIA": {}, "TLT": {}}
    for tk in ("DIA", "TLT"):
        for fk, h, cl in con.execute(
                "select fecha,hora,close from bars_etf where ticker=? order by fecha,hora", (tk,)):
            ETFB[tk].setdefault(fk, []).append((h, cl, cl, cl))   # (h,hi,lo,cl); solo cl disponible
    return SES, PREM, ETFB


# ─────────────────────────────── señales de apertura ────────────────────────────────
def senales_apertura(bars, ph, pl, pc, ex):
    """Aperturas C-F (ph=max_ayer, pl=min_ayer, pc=cierre_ayer). VERBATIM del motor validado."""
    return E.senales_apertura(bars, ph, pl, pc, ex)


# ─────────────────────────────────── SIS70 (motor) ──────────────────────────────────
def SIS70(SES, PREM, ETFB, extra=None, modo_strike="presupuesto", tope=None, pir=None,
          desde=None, hasta=None, aplanado=None):
    """Corre el sistema completo. Devuelve D = {fecha: pnl_dia}. Params por config."""
    extra = extra if extra is not None else C.APERTURAS_ORDEN
    tope = tope if tope is not None else C.TOPE
    pir = pir if pir is not None else C.PIR
    aplan = aplanado if aplanado is not None else C.APLANADO
    D = {}
    prev = None
    for fk, bars, rth in SES:
        if desde and fk < desde:
            continue
        if hasta and fk >= hasta:
            continue
        cl_ = {h: x for h, x, _, _, _ in rth}
        if len(cl_) < 100 or fk not in PREM:
            if cl_:
                hsd = sorted(cl_)
                prev = (max(cl_.values()), min(cl_.values()), cl_[hsd[-1]])
            continue
        PM = PREM[fk]
        ph, pl, pc = prev if prev else (None, None, None)

        # ── señales: sp (flips), L/ks (rebote), S (ORB+aperturas), p (flips reclasificados) ──
        sp, L, ks = sen_p(bars, C.ST_PER, C.ST_MULT)
        ik = {k: i for i, k in enumerate(ks)}
        S1, k1 = st_full(bars, 1, C.ST_PER, C.ST_MULT)
        S = []
        for a in C.ORB_ANCLAS:
            s = E.orb_en(bars, a)
            if s:
                S += s
        for ex in extra:
            sg = senales_apertura(bars, ph, pl, pc, ex)
            if sg and all(abs(mm(sg[0][0]) - mm(x[0])) > C.DESCARTE_MIN for x in S):
                S += sg
        p = []
        for h, d in sp:
            if h < "09:45":
                continue
            if C.ST1_ON and giros(S1, k1, h, C.ST1_VENTANA) >= 1:   # descarte ST-1 ANTES del rebote
                continue
            if C.RETMOD:                                   # skew sobre RETRASA
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
                            p.append((_hh, 'P' if d == 'C' else 'C'))
                            continue
            p += reb2(L, ks, ik, h, d)
        sen = sorted(set(S + p))
        Sen = dict(sen)

        # ── día bueno (dobla unidades) ──
        nq = 1
        if C.DIABUENO and R.dia_bueno(cl_, ETFB.get("DIA", {}).get(fk), ETFB.get("TLT", {}).get(fk)):
            nq = 2

        # ── bucle por minuto ──
        tot = 0.0
        pos = None
        hechas = 0
        for h in sorted(PM):
            if h < '09:30' or h > '16:00':
                continue
            Sx = cl_.get(h)
            if Sx is None:
                continue
            # (b) VALORACIÓN
            if pos:
                _intr = max(0.0, (Sx - pos['k']) if pos['rt'] == 'C' else (pos['k'] - Sx))
                q = PM[h].get((pos['rt'], pos['k']))
                _long = max(q[0], _intr) if q else max(pos.get('_l', _intr), _intr)
                pos['_l'] = _long
                if pos.get('vert'):
                    _is = max(0.0, (Sx - pos['ks']) if pos['rt'] == 'C' else (pos['ks'] - Sx))
                    q2 = PM[h].get((pos['rt'], pos['ks']))
                    _sh = max(q2[0], _is) if q2 else max(pos.get('_s', _is), _is)
                    pos['_s'] = _sh
                    pos['mid'] = _long - _sh
                else:
                    pos['mid'] = _long

            # gestión: gira / piramidar / rodar
            # ⚠️ piramidar/rodar: el `dl` sale de invertir el DÉBITO como si fuera un single en el
            # strike largo. `iv()` devuelve None cuando el débito < intrínseco de la pata larga
            # (~67% del tiempo) -> ese None es en realidad un FILTRO BINARIO DE ESTADO del spread,
            # no una delta económica. VERIFICADO por el agente (2026-08-16): es lo que produce el
            # perfil validado (140 rojos/racha 4); reformularlo como métrica continua lo EMPEORA.
            # Se replica tal cual (reproduce +71.396). Mejora opcional para vivo (determinista):
            #   piramidar/rodar solo si  pos['mid'] > max(0, intrínseco_largo)  (== dl is not None).
            if pos:
                gira = h in Sen and Sen[h] != pos['rt']
                dl = None
                T = _T(h)
                s_ = iv(pos['mid'], Sx, pos['k'], T, pos['rt'] == 'C')
                if s_:
                    d_, _, _ = greeks(Sx, pos['k'], T, s_, pos['rt'] == 'C')
                    dl = abs(d_) if d_ is not None else None
                if (pir and not pos['extra'] and not gira and h < C.PIR_HASTA
                        and mm(h) - mm(pos['h0']) >= C.PIR_ESPERA_MIN
                        and dl is not None and pos['d0'] is not None and dl - pos['d0'] > C.PIR_DELTA):
                    cd = [(k, v) for (r_, k), v in PM[h].items() if r_ == pos['rt']]
                    e = I.elegir(cd, Sx, h, pos['rt'], modo_strike, tope)
                    if e:
                        pos['extra'] = dict(k=e[0], ask=e[1][0] * 1.01, mid=e[1][0])
                rodar = (not gira and pos['rod'] < C.ROD_MAX and h < C.ROD_HASTA
                         and dl is not None and dl < C.ROD_DELTA and not pos['extra'])
                if pos['extra']:
                    _i2 = max(0.0, (Sx - pos['extra']['k']) if pos['rt'] == 'C' else (pos['extra']['k'] - Sx))
                    q2 = PM[h].get((pos['rt'], pos['extra']['k']))
                    pos['extra']['mid'] = max(q2[0], _i2) if q2 else max(pos['extra']['mid'], _i2)
                if gira or h >= aplan:
                    # VERBATIM: nq (día bueno) SOLO en la pata principal; el extra de piramidar
                    # se suma SIN nq. nq vive en pos.get('nq',1) (se pierde tras rodar -> vuelve a 1).
                    g = ((pos['mid'] - pos['ask']) * 100 - C.COMISION) * pos.get('nq', 1)
                    if pos['extra']:
                        _ge = (pos['extra']['mid'] - pos['extra']['ask']) * 100 - C.COMISION
                        g += _ge
                    tot += g
                    hechas += 1
                    pos = None
                elif rodar:
                    # VERBATIM: el cierre por rodado SÍ lleva nq (a diferencia del extra)
                    tot += ((pos['mid'] - pos['ask']) * 100 - C.COMISION) * pos.get('nq', 1)
                    rt = pos['rt']
                    r2 = pos['rod'] + 1
                    h0 = pos['h0']
                    pos = None
                    cd = [(k, v) for (r_, k), v in PM[h].items() if r_ == rt]
                    e = I.elegir(cd, Sx, h, rt, modo_strike, tope)
                    if e:
                        T = _T(h)
                        s_ = iv(e[1][0], Sx, e[0], T, rt == 'C')
                        d0 = None
                        if s_:
                            dd, _, _ = greeks(Sx, e[0], T, s_, rt == 'C')
                            d0 = abs(dd) if dd is not None else None
                        pos = {'k': e[0], 'rt': rt, 'ask': e[1][0] * 1.01, 'mid': e[1][0],
                               'rod': r2, 'extra': None, 'h0': h0, 'd0': d0}

            # apertura
            if pos is None and h in Sen and hechas < C.MAX_TRADES and h < C.ABRIR_HASTA:
                rt = Sen[h]
                if C.RUMB:
                    rr = R.ratio_otm(PM[h], Sx)
                    if rr is not None:
                        if rt == 'C' and rr < C.RUMB:
                            continue
                        if rt == 'P' and rr > 1.0 / C.RUMB:
                            continue
                cd = [(k, v) for (r_, k), v in PM[h].items() if r_ == rt]
                if C.ANCHO:
                    cd2 = [(k, I.suelo(k, v, Sx, rt)) for k, v in cd]
                    ev = I.elegir_vert(cd2, Sx, h, rt, tope, C.ANCHO)
                    if ev:
                        kl, pl_, ksh, psh = ev
                        T = _T(h)
                        s_ = iv(pl_, Sx, kl, T, rt == 'C')
                        d0 = None
                        if s_:
                            dd, _, _ = greeks(Sx, kl, T, s_, rt == 'C')
                            d0 = abs(dd) if dd is not None else None
                        pos = {'k': kl, 'ks': ksh, 'rt': rt, 'ask': (pl_ - psh) * 1.01,
                               'mid': pl_ - psh, 'rod': 0, 'extra': None, 'h0': h, 'd0': d0,
                               'vert': True, 'nq': nq}
                    # ⚠️ continue INCONDICIONAL bajo `if ANCHO`: si no hay vertical disponible,
                    # se DESCARTA la señal (no cae al single). Verbatim del motor validado; ponerlo
                    # dentro del `if ev` abre 272 singles de más que inflan piramidar +26k (bug corregido).
                    continue
                e = I.elegir(cd, Sx, h, rt, modo_strike, tope)
                if e:
                    T = _T(h)
                    s_ = iv(e[1][0], Sx, e[0], T, rt == 'C')
                    d0 = None
                    if s_:
                        dd, _, _ = greeks(Sx, e[0], T, s_, rt == 'C')
                        d0 = abs(dd) if dd is not None else None
                    pos = {'k': e[0], 'rt': rt, 'ask': e[1][0] * 1.01, 'mid': e[1][0],
                           'rod': 0, 'extra': None, 'h0': h, 'd0': d0, 'nq': nq}

        D[fk] = tot
        hsd = sorted(cl_)
        prev = (max(cl_.values()), min(cl_.values()), cl_[hsd[-1]])
    return D
