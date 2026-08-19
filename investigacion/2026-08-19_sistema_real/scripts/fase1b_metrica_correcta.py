# -*- coding: utf-8 -*-
# FASE 1b — LA METRICA CORRECTA.  (485 sesiones)
#
# HALLAZGO DE FASE 1: medido con MFE (recorrido favorable MAXIMO, el criterio `falso` de
# rebote.clasificar_dia:177), reb2 con vision de futuro PIERDE -372 ATR... pero en el motor
# GANA +28.864$. Conclusion: el MFE NO es lo que cobra el sistema.
#
# El sistema compra un VERTICAL DE DEBITO de ancho C.ANCHO y lo cierra por FLIP CONTRARIO o
# aplanado -> el resultado depende de DONDE ESTA EL PRECIO AL CERRAR, y satura en el ancho.
# Aqui se comparan 4 metricas por flip:
#   mfe   = recorrido favorable maximo            (la que he usado hoy — sospechosa)
#   mae   = recorrido adverso maximo              (riesgo)
#   neto  = movimiento hasta el CIERRE del tramo  (lo que liquida el vertical)
#   pnl   = P&L del vertical saturado en el ancho, en $ aprox:
#           payoff = min(max(S_fin - K_largo, 0), ANCHO) - debito ; K_largo ~ ATM (spot entrada)
#           debito estimado = ANCHO * DEB_FRAC (fraccion tipica del ancho pagada)
import sqlite3, sys

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import sen_p, reb2, _grupo
from sys2.core.supertrend import mm

ANCHO = C.ANCHO or 2.0
DEB_FRAC = 0.5          # el vertical ATM de ancho 2 cuesta ~1.0 (mitad del ancho)

con = sqlite3.connect(RAIZ + r"\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
CORTE = FECHAS[len(FECHAS) // 2]

D = []
for f in FECHAS:
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
    horas = sorted(cl_)
    for n_, (h, d) in enumerate(flips):
        i = ik.get((mm(h) // 3) * 3)
        if i is None or i < 11 or i + 12 > len(ks) - 1:
            continue
        lado = 1 if d == 'C' else -1
        atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
        if atr <= 0:
            continue
        fin = flips[n_ + 1][0] if n_ + 1 < len(flips) else "15:59"

        def mide(desde, lad):
            seg = [cl_[z] for z in horas if desde <= z <= fin]
            if len(seg) < 3:
                return None
            s0 = seg[0]
            mfe = max((y - s0) * lad for y in seg) / atr
            mae = min((y - s0) * lad for y in seg) / atr
            neto = (seg[-1] - s0) * lad / atr
            # vertical de debito: largo ~ATM (strike = spot de entrada), corto a ANCHO de dist
            mov = (seg[-1] - s0) * lad
            payoff = min(max(mov, 0.0), ANCHO)
            pnl = (payoff - ANCHO * DEB_FRAC) * 100.0        # $ por contrato
            return mfe, mae, neto, pnl

        v = mide(h, lado)
        if v is None:
            continue
        r = reb2(L, ks, ik, h, d)
        g = _grupo(r, h, d)
        rv = None
        if r:
            he, df = r[0]
            rv = mide(he, 1 if df == 'C' else -1)
        D.append(dict(f=f, g=g, v=v, r=rv))

n = len(D)
print("FLIPS: %d   |   ancho %.1f  debito estimado %.2f   |   corte %s\n"
      % (n, ANCHO, ANCHO * DEB_FRAC, CORTE))

IDX = {"mfe": 0, "mae": 1, "neto": 2, "pnl": 3}
print("== QUE CAPTURA CADA DECISION, POR METRICA ==")
print("%-9s %5s | %-21s | %-21s" % ("grupo", "n", "VIVO (entra en h)", "reb2 (ve el futuro)"))
print("%-9s %5s | %6s %6s %6s %7s | %6s %6s %6s %7s"
      % ("", "", "mfe", "mae", "neto", "pnl$", "mfe", "mae", "neto", "pnl$"))
for g in ("NORMAL", "RETRASA", "INVIERTE", "DESCARTA"):
    S = [x for x in D if x['g'] == g]
    if not S:
        continue
    mv = [sum(x['v'][IDX[k]] for x in S) / len(S) for k in ("mfe", "mae", "neto", "pnl")]
    R = [x for x in S if x['r'] is not None]
    if R:
        mr = [sum(x['r'][IDX[k]] for x in R) / len(R) for k in ("mfe", "mae", "neto", "pnl")]
        srt = "%6.2f %6.2f %6.2f %7.1f" % tuple(mr)
    else:
        srt = "        NO ENTRA (0 $)"
    print("%-9s %5d | %6.2f %6.2f %6.2f %7.1f | %s"
          % (g, len(S), mv[0], mv[1], mv[2], mv[3], srt))

print("\n== TOTAL SOBRE LOS %d FLIPS (suma) ==" % n)
for k in ("mfe", "neto", "pnl"):
    sv = sum(x['v'][IDX[k]] for x in D)
    sr = sum((x['r'][IDX[k]] if x['r'] is not None else 0.0) for x in D)
    u = "$" if k == "pnl" else " ATR"
    print("  %-5s   vivo %10.1f%s   reb2 %10.1f%s   dif %+10.1f%s"
          % (k, sv, u, sr, u, sr - sv, u))

print("\n== VALOR DE CADA DECISION EN P&L ($, aprox) ==")
print("%-10s %6s %12s %12s %12s %10s %10s"
      % ("decision", "n", "vivo $", "reb2 $", "diferencia", "difA1", "difA2"))
for g in ("RETRASA", "INVIERTE", "DESCARTA"):
    S = [x for x in D if x['g'] == g]
    if not S:
        continue
    sv = sum(x['v'][3] for x in S)
    sr = sum((x['r'][3] if x['r'] is not None else 0.0) for x in S)
    d1 = sum((x['r'][3] if x['r'] is not None else 0.0) - x['v'][3]
             for x in S if x['f'] < CORTE)
    d2 = sum((x['r'][3] if x['r'] is not None else 0.0) - x['v'][3]
             for x in S if x['f'] >= CORTE)
    print("%-10s %6d %12.0f %12.0f %+12.0f %+10.0f %+10.0f"
          % (g, len(S), sv, sr, sr - sv, d1, d2))

print("\n== ¿MFE y P&L ordenan igual? (correlacion de signo sobre los %d flips) ==" % n)
mal_mfe = [1 if x['v'][0] < 1.0 else 0 for x in D]
mal_pnl = [1 if x['v'][3] < 0 else 0 for x in D]
ok = sum(1 for a, b in zip(mal_mfe, mal_pnl) if a == b)
print("  'malo por MFE<1.0 ATR' coincide con 'pierde dinero' en %.1f%% de los flips" % (100.0 * ok / n))
print("  malos por MFE: %.1f%%   |   pierden dinero: %.1f%%"
      % (100.0 * sum(mal_mfe) / n, 100.0 * sum(mal_pnl) / n))
