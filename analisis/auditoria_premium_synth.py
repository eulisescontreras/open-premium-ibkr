# -*- coding: utf-8 -*-
"""AUDITORIA DEL PREMIUM SINTETICO CONTRA PRECIOS REALES, POR PROFUNDIDAD ITM.

Es el paso 3 (PRIORITARIO) de SISTEMA_ST3_ORB_CONGELADO_v2.md: todo el backtest de 2 años usa
premium SINTETICO calibrado con 3 dias. Si el modelo se desvia, TODOS los numeros estan
inflados o desinflados, y ninguna conclusion del backtest se sostiene.

QUE HACE, con datos REALES y las FUNCIONES REALES del modelo:
  1. Calibra con dias de ENTRENO usando `synth_premium.calibra` (la funcion real, importada).
  2. Predice el mid de dias que el modelo NO HA VISTO, con `synth_premium.extr` (real).
  3. Compara contra el mid REAL (bid/ask de IBKR guardados en premium_minute).
  4. Desglosa el error POR PROFUNDIDAD ITM y por tiempo a cierre, que es donde la spec
     sospecha el sesgo: "si el modelo sobreestima el extrinseco de los contratos poco ITM,
     todo el backtest esta inflado".

NOTA: `synth_premium.spy_min` lee spy_bars_pm.db, que no existe en este entorno. Se sustituye
por una lectura de `bars_minute` de la BD del dia (mismo dato: close del SPY por minuto RTH).
Se sustituye SOLO esa fuente; `calibra` y `extr` se ejecutan tal cual estan escritas.

Uso:  python analisis/auditoria_premium_synth.py [dias_entreno...] [--test dia...]
Por defecto: entrena con 2026-08-11 y 2026-08-12, prueba en 2026-08-13 y 2026-08-14.
"""
import os, sys, sqlite3, statistics as st

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "analisis"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def R(p):
    return os.path.join(RAIZ, p)


def db_dia(fk):
    return R("spy_history_%s.db" % fk.replace("-", ""))


def spy_min_desde_bars(fk):
    """Close del SPY por minuto RTH, leido de bars_minute de la BD del dia.
    Sustituye a synth_premium.spy_min (que usa spy_bars_pm.db, inexistente aqui)."""
    p = db_dia(fk)
    if not os.path.exists(p):
        return {}
    c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    d = {h: cl for h, cl in c.execute(
        "select hora,close from bars_minute where fecha=? and hora>='09:30' and hora<='16:00'",
        (fk,)) if cl is not None}
    c.close()
    return d


# --- se importa el modelo REAL y se le cambia SOLO la fuente del subyacente ---
try:
    import synth_premium as SP
except Exception as e:
    print("FALLO importando synth_premium: %s" % e)
    sys.exit(1)

SP.spy_min = spy_min_desde_bars
SP.DIAS = {}          # se rellena abajo con los dias que existan


def premium_real(fk):
    """mid REAL por (hora, strike, right) del expiry 0DTE de ese dia."""
    p = db_dia(fk)
    dk = fk.replace("-", "")
    c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    rows = c.execute(
        "select hora,strike,right,bid,ask from premium_minute "
        "where fecha=? and expiry=? and bid is not null and ask is not null "
        "and bid>0 and ask>0", (fk, dk)).fetchall()
    c.close()
    return rows


def clasifica(dep):
    """Bucket de profundidad. dep>0 = ITM, dep<0 = OTM."""
    if dep < -1.0:  return "OTM  < -1.0"
    if dep < 0.0:   return "OTM  -1.0..0"
    if dep < 1.0:   return "ITM   0..1"
    if dep < 2.0:   return "ITM   1..2"
    if dep < 3.0:   return "ITM   2..3"
    if dep < 5.0:   return "ITM   3..5"
    if dep < 10.0:  return "ITM   5..10"
    return "ITM   >=10"


ORDEN = ["OTM  < -1.0", "OTM  -1.0..0", "ITM   0..1", "ITM   1..2", "ITM   2..3",
         "ITM   3..5", "ITM   5..10", "ITM   >=10"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--test" in sys.argv:
        i = sys.argv.index("--test")
        entreno = [a for a in sys.argv[1:i] if not a.startswith("--")]
        prueba = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
    else:
        entreno = args or ["2026-08-11", "2026-08-12"]
        prueba = ["2026-08-13", "2026-08-14"]

    todos = sorted(set(entreno) | set(prueba))
    SP.DIAS = {d: d.replace("-", "") for d in todos}
    for d in todos:
        if not os.path.exists(db_dia(d)):
            print("FALTA la BD de %s (%s)" % (d, os.path.basename(db_dia(d))))
            return 1

    print("=" * 86)
    print("AUDITORIA DEL PREMIUM SINTETICO vs PRECIOS REALES")
    print("=" * 86)
    print("  entreno (calibra el modelo) : %s" % ", ".join(entreno))
    print("  prueba  (NO vistos)         : %s" % ", ".join(prueba))

    modelo = SP.calibra(entreno)          # FUNCION REAL
    print("  buckets calibrados          : %d" % len(modelo))
    if not modelo:
        print("  *** modelo vacio, no se puede auditar ***")
        return 1

    for fk in prueba:
        S = spy_min_desde_bars(fk)
        rows = premium_real(fk)
        if not rows or not S:
            print("\n  %s: sin datos (premium=%d, minutos=%d)" % (fk, len(rows), len(S)))
            continue

        por_bucket = {}
        sin_info = 0
        comp = []
        for h, K, r, b, a in rows:
            if h not in S:
                continue
            s = S[h]
            mid_real = (b + a) / 2.0
            intr = max(s - K, 0.0) if r == "C" else max(K - s, 0.0)
            dep = (s - K) if r == "C" else (K - s)
            t = SP.ttc(h)
            e = SP.extr(modelo, dep, t)          # FUNCION REAL
            if e == 0.0 and SP.bkt(dep, t) not in modelo:
                sin_info += 1
            mid_syn = max(intr + e, 0.01)
            comp.append((dep, mid_real, mid_syn))
            por_bucket.setdefault(clasifica(dep), []).append((mid_real, mid_syn))

        print("\n" + "-" * 86)
        print("DIA %s   %d contratos-minuto comparados   (%d sin bucket calibrado)"
              % (fk, len(comp), sin_info))
        print("-" * 86)
        print("  %-14s %6s %9s %9s %9s %9s %7s" %
              ("profundidad", "n", "real med", "synth med", "error", "error %", "sobre%"))
        for k in ORDEN:
            v = por_bucket.get(k)
            if not v:
                continue
            reales = [x[0] for x in v]
            syn = [x[1] for x in v]
            err = [x[1] - x[0] for x in v]
            errp = [100.0 * (x[1] - x[0]) / x[0] for x in v if x[0] > 0.02]
            sobre = 100.0 * sum(1 for e in err if e > 0) / len(err)
            print("  %-14s %6d %9.2f %9.2f %+9.3f %+8.1f%% %6.0f%%"
                  % (k, len(v), st.mean(reales), st.mean(syn), st.mean(err),
                     st.mean(errp) if errp else 0.0, sobre))

        err_tot = [x[2] - x[1] for x in comp]
        errp_tot = [100.0 * (x[2] - x[1]) / x[1] for x in comp if x[1] > 0.02]
        print("  " + "-" * 74)
        print("  %-14s %6d %9.2f %9.2f %+9.3f %+8.1f%% %6.0f%%"
              % ("TOTAL", len(comp), st.mean([x[1] for x in comp]),
                 st.mean([x[2] for x in comp]), st.mean(err_tot),
                 st.mean(errp_tot) if errp_tot else 0.0,
                 100.0 * sum(1 for e in err_tot if e > 0) / len(err_tot)))
        print("  mediana del error absoluto: %.3f$   |   p90: %.3f$"
              % (st.median([abs(e) for e in err_tot]),
                 sorted(abs(e) for e in err_tot)[int(0.9 * (len(err_tot) - 1))]))

    print("\n" + "=" * 86)
    print("COMO LEERLO")
    print("=" * 86)
    print("  error > 0  -> el modelo PAGA DE MAS que la realidad en ese tramo")
    print("  error < 0  -> el modelo compra MAS BARATO que la realidad -> INFLA el backtest")
    print("  La spec sospecha sesgo en los contratos POCO ITM (0..2). Si ahi el error es")
    print("  negativo y grande, el backtest esta comprando a precios que no existen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
