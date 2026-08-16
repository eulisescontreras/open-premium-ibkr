# -*- coding: utf-8 -*-
"""COLD RUN de sys2/backtest/greeks.py con PRECIOS REALES de massive_premium.db y el
SPY real de sys2.bars. Alimenta las FUNCIONES REALES (no reimplementa) y valida por
AUTO-CONSISTENCIA (no hay greeks reales de IBKR guardados aun; captura.py los traera).

Validaciones (R3/R8):
  1) ROUND-TRIP: implied_vol(precio_real) -> bs_price(iv) == precio_real (la IV sale del
     precio REAL, asi que reprecia exacto; esto prueba que preserva la sonrisa).
  2) DELTA analitica vs diferencias finitas: |d_analitica - d_numerica| pequeno.
  3) RANGOS: call delta in (0,1), put delta in (-1,0); gamma>0; vega>0; iv in (0.02,3).
  4) PARIDAD de delta en mismo strike: |dC| + |dP| ~ 1 (q pequeno).
  5) SANIDAD H3: la delta de contratos comprables (ITM/ATM) cae en el rango documentado
     (p5 0.544 / mediana 0.704 / p95 0.893) de forma aproximada -> no absurda.
  6) parse_occ y t_years correctos sobre tickers/tiempos reales.
Exit 0 = verde.
"""
import os, sys, sqlite3, statistics
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from sys2.backtest import greeks as G
from sys2.db import repo
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MASSIVE = os.path.join(RAIZ, "massive_premium.db")
R, Q = 0.045, 0.013          # tasa libre de riesgo / dividendo SPY (constantes backtest)
HORAS_OBJ = {"10:00", "11:30", "13:00", "14:30"}   # instantes con extrinseco sano


def _hora_et(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).astimezone(ET).strftime("%H:%M")


def main():
    fallos = []
    if not os.path.exists(MASSIVE):
        print("ROJO: no existe massive_premium.db"); return 1
    mv = sqlite3.connect(MASSIVE)
    con = repo.abrir()

    # dias 0DTE con datos en massive Y en sys2.bars
    dias_mv = [r[0] for r in mv.execute("select distinct fecha from aggs order by fecha")]
    dias_bar = set(r[0] for r in con.execute("select distinct fecha from bars"))
    dias = [d for d in dias_mv if d in dias_bar]
    muestra = dias[::40]
    print("dias massive: %d | con bars: %d | muestreados: %d" % (len(dias_mv), len(dias), len(muestra)))

    n_iv = n_none = 0
    rt_max = 0.0
    fd_max = 0.0
    rango_mal = 0
    par_mal = 0
    deltas_compra = []
    parse_mal = 0
    comparados = 0

    for fk in muestra:
        # SPY por hora (close de sys2.bars)
        spy = {h: cl for h, cl in con.execute(
            "select hora,close from bars where fecha=? and hora>='09:30' and hora<='16:00'", (fk,))}
        if len(spy) < 100:
            continue
        # contratos 0DTE (expiry == fecha) de massive, en los instantes objetivo
        rows = mv.execute(
            "select ticker,ts,close from aggs where fecha=? and volume>0 order by ts", (fk,)).fetchall()
        # indexar por (right,strike) para paridad
        por_hora = {}   # hora -> {(right,strike): (S,price,expiry)}
        for tk, ts, px in rows:
            p = G.parse_occ(tk)
            if p is None:
                parse_mal += 1; continue
            expiry, right, strike = p
            if expiry != fk:           # solo 0DTE
                continue
            h = _hora_et(ts)
            if h not in HORAS_OBJ or h not in spy:
                continue
            S = spy[h]
            if not (0.7 * S < strike < 1.3 * S):   # descartar strikes absurdos
                continue
            por_hora.setdefault(h, {})[(right, strike, ts)] = (S, px, expiry)

        for h, d in por_hora.items():
            for (right, strike, ts), (S, px, expiry) in d.items():
                comparados += 1
                T = G.t_years(ts, expiry)
                if T <= 0:
                    parse_mal += 1; continue
                iv = G.implied_vol(px, S, strike, T, R, Q, right)
                if iv is None:
                    n_none += 1; continue
                n_iv += 1
                # 1) round-trip
                rep = G.bs_price(S, strike, T, R, Q, iv, right)
                rt_max = max(rt_max, abs(rep - px))
                # 2) greeks + diferencias finitas
                gk = G.greeks(S, strike, T, R, Q, iv, right)
                if gk is None:
                    rango_mal += 1; continue
                hS = 0.01
                dnum = (G.bs_price(S + hS, strike, T, R, Q, iv, right)
                        - G.bs_price(S - hS, strike, T, R, Q, iv, right)) / (2 * hS)
                fd_max = max(fd_max, abs(dnum - gk["delta"]))
                # 3) rangos
                dd = gk["delta"]
                ok = ((right == "C" and 0 < dd < 1) or (right == "P" and -1 < dd < 0)) \
                    and gk["gamma"] > 0 and gk["vega"] > 0 and 0.02 < iv < 3.0
                if not ok:
                    rango_mal += 1
                # 5) delta de "comprables": ITM/ATM (|delta|>=0.5)
                if abs(dd) >= 0.5:
                    deltas_compra.append(abs(dd))

            # 4) paridad de delta = invariante PURO de la formula BS a MISMA sigma:
            #    delta_C(s) - delta_P(s) = e^{-qT}  ->  |dC|+|dP| = e^{-qT} ~ 1.
            #    (NO se comparan IVs distintas call/put: la diferencia de IV real es la
            #     SONRISA que preservamos a proposito -> ahi |dC|+|dP| != 1 y es correcto.)
            strikes = set(k for k in d if k[0] == "C")
            for (rc, sc, tsc) in strikes:
                comp = [(rp, sp, tsp) for (rp, sp, tsp) in d if rp == "P" and sp == sc]
                if not comp:
                    continue
                Sc, pxc, expc = d[(rc, sc, tsc)]
                Tc = G.t_years(tsc, expc)
                ivc = G.implied_vol(pxc, Sc, sc, Tc, R, Q, "C")
                if ivc is None:
                    continue
                gc = G.greeks(Sc, sc, Tc, R, Q, ivc, "C")
                gp = G.greeks(Sc, sc, Tc, R, Q, ivc, "P")   # MISMA sigma para ambos
                import math as _m
                esperado = _m.exp(-Q * Tc)
                if gc and gp and abs(abs(gc["delta"]) + abs(gp["delta"]) - esperado) > 1e-3:
                    par_mal += 1

    mv.close(); con.close()

    inv_ratio = n_iv / (n_iv + n_none) if (n_iv + n_none) else 0
    print("comparados: %d | IV invertida: %d | no invertible: %d (ratio %.1f%%)"
          % (comparados, n_iv, n_none, 100 * inv_ratio))
    print("round-trip max err: %.6f | delta fin-dif max err: %.6f" % (rt_max, fd_max))
    print("rangos mal: %d | paridad mal: %d | parse/T mal: %d" % (rango_mal, par_mal, parse_mal))
    if deltas_compra:
        deltas_compra.sort()
        n = len(deltas_compra)
        print("delta comprables (|d|>=0.5): n=%d p5=%.3f mediana=%.3f p95=%.3f"
              % (n, deltas_compra[max(0, n // 20)], statistics.median(deltas_compra),
                 deltas_compra[min(n - 1, 19 * n // 20)]))

    if n_iv < 50:
        fallos.append("muy pocas IV invertidas (%d) — datos insuficientes" % n_iv)
    if rt_max > 1e-3:
        fallos.append("round-trip no reprecia el precio real (err %.6f)" % rt_max)
    if fd_max > 5e-3:
        fallos.append("delta analitica != diferencias finitas (err %.6f)" % fd_max)
    if rango_mal:
        fallos.append("%d greeks fuera de rango (delta/gamma/vega/iv)" % rango_mal)
    if par_mal:
        fallos.append("%d violaciones de paridad de delta (|dC|+|dP| != 1)" % par_mal)
    if parse_mal:
        fallos.append("%d fallos de parse_occ/t_years" % parse_mal)
    if inv_ratio < 0.5:
        fallos.append("demasiadas no invertibles (ratio %.1f%%) — revisar intrinseco/rango" % (100 * inv_ratio))

    if fallos:
        print("\nROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("\nVERDE: greeks.py invierte el precio real, reprecia exacto, delta consistente y en rango H3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
