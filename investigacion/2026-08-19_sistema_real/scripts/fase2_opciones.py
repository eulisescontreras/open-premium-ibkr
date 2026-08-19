# -*- coding: utf-8 -*-
# FASE 2 — ¿LA CADENA DE OPCIONES ANTICIPA EL FLIP QUE SE DA LA VUELTA?  (485 sesiones)
#
# POR QUE ESTA VIA: todo lo probado hoy exige ESPERAR velas, y el retraso cuesta mas de lo que
# la señal salva (3 min +600$ / 12 min -3.912$ / 15 min -4.356$). La cadena de opciones esta
# disponible EN EL MINUTO DEL FLIP: coste de tiempo CERO.
#
# OBJETIVO (fase 1b): el 91% del valor del look-ahead esta en DESCARTA (+10.235$) e INVIERTE
# (+4.836$) = 385 flips de 1.502 donde el precio termina el tramo EN CONTRA.
# Se predicen dos etiquetas:
#   malo_pnl : el vertical pierde dinero (neto del tramo <= 0)   <- lo que de verdad importa
#   mal_reb2 : reb2 con vision completa dice DESCARTA o INVIERTE
#
# Predictores (todos disponibles en el minuto del flip, sin esperar):
#   skew   = reglas.skew_l2  (FUNCION REAL, ya existe en el sistema)
#   ratio  = reglas.ratio_otm (FUNCION REAL)
#   ivatm  = IV del ATM en la direccion del flip
#   costv  = precio del vertical ATM / ancho  (lo que cuesta apostar a favor del flip)
#   pcr    = put/call ratio de volumen (toda la cadena)
#   volrel = volumen del minuto / volumen medio de los 15 min previos
#   divN   = variacion de la IV ATM en los ultimos N minutos (informacion DINAMICA, sin coste)
import sqlite3, sys, os, statistics as stt

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import sen_p, reb2, _grupo
from sys2.core.supertrend import mm
from sys2.core import reglas as R
from sys2.backtest import greeks as G

ANCHO = 2.0
con = sqlite3.connect(RAIZ + r"\sys2.db")
mv = sqlite3.connect(RAIZ + r"\massive_premium.db")
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
_ET = ZoneInfo("America/New_York")


def hora_et(ts):
    return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).astimezone(_ET).strftime("%H:%M")


# las fechas las manda MASSIVE (es lo que hace motor.cargar:59); los ultimos dias de `bars`
# (2026-08-17/18/19) tienen velas pero NO cadena -> darian 0 flips utiles.
_bd = set(r[0] for r in con.execute("select distinct fecha from bars"))
FECHAS = [r[0] for r in mv.execute("select distinct fecha from aggs order by fecha")
          if r[0] in _bd]
# modo prueba: `python fase2_opciones.py 5` -> solo 5 dias repartidos (para depurar SIN esperar)
if len(sys.argv) > 1:
    k_ = int(sys.argv[1])
    paso = max(1, len(FECHAS) // k_)
    FECHAS = FECHAS[::paso][:k_]
    print("MODO PRUEBA: %d dias -> %s" % (len(FECHAS), FECHAS))
CORTE = FECHAS[len(FECHAS) // 2]
D = []

for nf, f in enumerate(FECHAS):
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                       (f,)).fetchall()
    if len(bars) < 100:
        continue
    cl_ = {h: cl for h, hi, lo, cl in bars if "09:30" <= h <= "16:00"}
    if len(cl_) < 100:
        continue
    try:
        sp, L, ks = sen_p(bars, C.ST_PER, C.ST_MULT)
    except Exception:
        continue
    ik = {kk: i for i, kk in enumerate(ks)}
    flips = [(h, d) for h, d in sp if h >= "09:45"]
    if not flips:
        continue
    # cadena del dia (solo 0DTE) por minuto. OJO: en massive cada minuto solo trae los
    # contratos QUE COTIZARON ese minuto (~13, no 82) -> hay que construir un LIBRO VIGENTE
    # con el ultimo precio conocido de cada strike (solo pasado; es lo que tendria el vivo).
    crudo = {}
    for tk, ts, cl, vol in mv.execute(
            "select ticker,ts,close,volume from aggs where fecha=?", (f,)):
        p = G.parse_occ(tk)
        if p is None or p[0] != f:
            continue
        crudo.setdefault(hora_et(ts), {})[(p[1], p[2])] = (cl, vol)
    if not crudo:
        continue
    PM = {}          # libro vigente: ultimo precio conocido (<=10 min) por strike
    VAC = {}         # volumen ACUMULADO del dia por strike hasta ese minuto
    VMIN = {}        # volumen del minuto (para 'volumen del minuto' y volrel)
    vig = {}
    acum = {}
    for hh in sorted(crudo):
        for kk, v in crudo[hh].items():
            vig[kk] = (v[0], v[1], mm(hh))
            acum[kk] = acum.get(kk, 0.0) + (v[1] or 0.0)
        lim = mm(hh) - 10
        PM[hh] = {kk: (v[0], v[1]) for kk, v in vig.items() if v[2] >= lim}
        VAC[hh] = dict(acum)
        VMIN[hh] = sum((v[1] or 0.0) for v in crudo[hh].values())
    horas = sorted(cl_)
    for n_, (h, d) in enumerate(flips):
        i = ik.get((mm(h) // 3) * 3)
        if i is None or i < 11 or i + 12 > len(ks) - 1:
            continue
        m = PM.get(h)
        S = cl_.get(h)
        if not m or S is None or len(m) < 8:
            continue
        lado = 1 if d == 'C' else -1
        atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
        if atr <= 0:
            continue
        fin = flips[n_ + 1][0] if n_ + 1 < len(flips) else "15:59"
        seg = [cl_[z] for z in horas if h <= z <= fin]
        if len(seg) < 3:
            continue
        neto = (seg[-1] - seg[0]) * lado
        pnl = (min(max(neto, 0.0), ANCHO) - ANCHO * 0.46) * 100.0
        r = reb2(L, ks, ik, h, d)
        g = _grupo(r, h, d)

        # ── predictores de la cadena ──
        skew = R.skew_l2(m, S, h, lado)
        ratio = R.ratio_otm(m, S)
        rt = 'C' if d == 'C' else 'P'

        def iv_de(k, right, mm_):
            v = mm_.get((right, k))
            if not v or v[0] <= 0.01:
                return None
            return R._iv(v[0], S, k, h, right == 'C')

        # strike ATM (el mas cercano al spot) y su vertical
        ks_dir = sorted({k for (rr, k) in m if rr == rt}, key=lambda k: abs(k - S))
        if not ks_dir:
            continue
        katm = ks_dir[0]
        ivatm = iv_de(katm, rt, m)
        kcorto = katm + ANCHO * lado
        vl, vc = m.get((rt, katm)), m.get((rt, kcorto))
        costv = ((vl[0] - vc[0]) / ANCHO) if (vl and vc and vl[0] > 0 and vc[0] > 0) else None
        # put/call sobre el volumen ACUMULADO del dia (el del minuto suelto es demasiado ralo)
        ac = VAC.get(h, {})
        volc = sum(v for (rr, k), v in ac.items() if rr == 'C')
        volp = sum(v for (rr, k), v in ac.items() if rr == 'P')
        pcr = volp / max(1.0, volc)
        vtot = VMIN.get(h, 0.0)                      # volumen del minuto
        hprev = [z for z in sorted(PM) if z < h][-15:]
        vprev = [VMIN.get(z, 0.0) for z in hprev]
        mprev = stt.mean(vprev) if vprev else 0.0
        volrel = (vtot / mprev) if mprev > 0 else None
        div5 = None
        if len(hprev) >= 5:
            i5 = iv_de(katm, rt, PM[hprev[-5]])
            if i5 and ivatm:
                div5 = ivatm - i5
        D.append(dict(f=f, g=g, neto=neto, pnl=pnl, malo=1 if neto <= 0 else 0,
                      mal2=1 if g in ("DESCARTA", "INVIERTE") else 0,
                      skew=skew, ratio=ratio, ivatm=ivatm, costv=costv,
                      pcr=pcr, vtot=vtot, volrel=volrel, div5=div5))
    if (nf + 1) % 120 == 0:
        print("  ... %d/%d dias, %d flips" % (nf + 1, len(FECHAS), len(D)), flush=True)

n = len(D)
# VOLCADO del dataset: recomputarlo cuesta ~10 min; con el JSON las combinaciones son instantaneas
if n:
    import json as _json
    _dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fase2_dataset.json")
    _json.dump(D, open(_dst, "w"))
    print("dataset volcado: %s (%d flips)" % (_dst, n))
if n == 0:
    print("\n*** 0 FLIPS RECOGIDOS — revisar filtros antes de lanzar la corrida completa ***")
    sys.exit(1)

# DIAGNOSTICO OBLIGATORIO antes de interpretar nada: cobertura de cada predictor
print("\n== COBERTURA DE PREDICTORES (cuantos flips tienen valor, no None) ==")
for c in ("skew", "ratio", "ivatm", "costv", "pcr", "vtot", "volrel", "div5"):
    v = [x[c] for x in D if x[c] is not None]
    if v:
        print("  %-8s %5d/%d (%.0f%%)   min %.3f  mediana %.3f  max %.3f"
              % (c, len(v), n, 100.0 * len(v) / n, min(v), sorted(v)[len(v) // 2], max(v)))
    else:
        print("  %-8s     0/%d  (VACIO — no se puede usar)" % (c, n))

bm = 100.0 * sum(x['malo'] for x in D) / n
b2 = 100.0 * sum(x['mal2'] for x in D) / n
print("\nFLIPS con cadena: %d   |   pierden (neto<=0): %.1f%%   |   DESCARTA/INVIERTE: %.1f%%"
      % (n, bm, b2))
print("corte A1/A2 = %s\n" % CORTE)


def evalua(campo, etiq):
    S = [x for x in D if x[campo] is not None]
    if len(S) < 200:
        print("%-10s  sin datos suficientes (n=%d)" % (etiq, len(S)))
        return
    S.sort(key=lambda x: x[campo])
    q = len(S) // 5
    print("%-8s %6s %10s %10s %9s %9s %8s %8s"
          % (etiq, "n", "rango", "%pierde", "%D/INV", "pnl$med", "A1%p", "A2%p"))
    for qi in range(5):
        sub = S[qi * q:(qi + 1) * q] if qi < 4 else S[4 * q:]
        if not sub:
            continue
        a1 = [x for x in sub if x['f'] < CORTE]
        a2 = [x for x in sub if x['f'] >= CORTE]
        print("  Q%d     %6d %10s %9.1f%% %8.1f%% %9.0f %7.1f%% %7.1f%%"
              % (qi + 1, len(sub),
                 "%.2f/%.2f" % (sub[0][campo], sub[-1][campo]),
                 100.0 * sum(x['malo'] for x in sub) / len(sub),
                 100.0 * sum(x['mal2'] for x in sub) / len(sub),
                 sum(x['pnl'] for x in sub) / len(sub),
                 100.0 * sum(x['malo'] for x in a1) / len(a1) if a1 else float('nan'),
                 100.0 * sum(x['malo'] for x in a2) / len(a2) if a2 else float('nan')))
    print()


print("BASE: %.1f%% pierden | pnl medio %.0f$\n" % (bm, sum(x['pnl'] for x in D) / n))
for campo, etiq in (("skew", "skew"), ("ratio", "ratioOTM"), ("ivatm", "IV_ATM"),
                    ("costv", "costoVert"), ("pcr", "put/call"), ("vtot", "volumen"),
                    ("volrel", "vol_rel"), ("div5", "dIV_5min")):
    evalua(campo, etiq)
