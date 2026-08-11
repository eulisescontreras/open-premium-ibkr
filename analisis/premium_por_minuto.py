"""
premium_por_minuto.py — READ-ONLY

La serie que pide el usuario: **premium acumulado POR MINUTO** (no el acumulado de la
sesion) de los strikes ITM/ATM, sumando todo lo que ocurre en ellos.

Se construye desde `tape`, que es la unica fuente con la MISMA cadencia para todos los
strikes. La alternativa (deltas de `day_prem` en premium_minute) tiene diente de sierra:
los 2 strikes de señal se miden por tick y los 40 de la banda cada 3 min, y el minuto en
que corre compute_walls absorbe el flujo de 3 minutos de golpe (medido: 5,4x el 08-10 y
8,3x el 08-11).

⚠️ COBERTURA — LEER ANTES DE USAR LOS NUMEROS
`_on_ticks:1817` solo procesa SENAL (2 strikes rotatorios de la 0DTE) y BASELINE (las
expiraciones futuras). Los 40 contratos de la BANDA no entran en el tape. Por tanto esta
serie NO es "todos los strikes ITM/ATM": es lo que pasa por los strikes de señal, que van
siguiendo al precio. El script imprime la cobertura real para que no se confunda.

Criterio ITM/ATM (el mismo que usa el codigo para la señal): call con strike <= spy,
put con strike >= spy.

Uso:
    python analisis\premium_por_minuto.py
    python analisis\premium_por_minuto.py 2026-08-11
    python analisis\premium_por_minuto.py 2026-08-11 --todos    # sin filtrar moneyness
"""
import os
import sqlite3
import sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "spy_history.db")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    solo_itm = "--todos" not in sys.argv

    db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    c = db.cursor()
    fechas = [x[0] for x in c.execute(
        "SELECT DISTINCT fecha FROM tape ORDER BY fecha").fetchall()]
    if not fechas:
        print("La tabla `tape` esta vacia.")
        sys.exit(2)
    F = args[0] if args else fechas[-1]
    if F not in fechas:
        print("Sin tape para %s. Hay: %s" % (F, ", ".join(fechas)))
        sys.exit(2)
    EXP = F.replace("-", "")

    # precio del SPY por minuto: hace falta para clasificar ITM/ATM en CADA minuto
    spy = {x[0]: x[1] for x in c.execute(
        "SELECT hora, spy FROM ta_minute WHERE fecha=? AND spy IS NOT NULL",
        (F,)).fetchall()}

    # ---------------- cobertura real, antes de ningun numero
    print("=" * 100)
    print("PREMIUM POR MINUTO desde `tape` — %s — expiry 0DTE %s" % (F, EXP))
    print("=" * 100)
    cob = c.execute("SELECT strike, right, COUNT(*) FROM tape WHERE fecha=? AND expiry=? "
                    "GROUP BY strike, right ORDER BY strike, right", (F, EXP)).fetchall()
    print("COBERTURA REAL: %d strikes distintos de la 0DTE en el tape -> %s"
          % (len(cob), ", ".join("%g%s" % (s, r) for s, r, _ in cob)))
    print("   (la BANDA de 40 strikes NO entra en el tape: `_on_ticks:1817` solo trata")
    print("    SENAL y BASELINE. Esto NO es 'todos los ITM/ATM'.)")
    print("   Filtro moneyness: %s" % ("ITM/ATM (call<=spy, put>=spy)" if solo_itm
                                       else "NINGUNO (--todos)"))

    filas = c.execute(
        "SELECT substr(hora,1,5) AS minuto, strike, right, agresor, premium, premium_dvol, size "
        "FROM tape WHERE fecha=? AND expiry=? ORDER BY hora", (F, EXP)).fetchall()

    por_min = {}
    fuera = 0
    for minuto, strike, right, agresor, prem, prem_dv, size in filas:
        px = spy.get(minuto)
        if solo_itm and px is not None:
            if right == "C" and strike > px:
                fuera += 1
                continue
            if right == "P" and strike < px:
                fuera += 1
                continue
        d = por_min.setdefault(minuto, {
            "ops": 0, "cC": 0.0, "cP": 0.0, "nC": 0.0, "nP": 0.0,
            "mid": 0, "size": 0.0})
        d["ops"] += 1
        d["size"] += size or 0
        val = prem_dv or 0.0                      # dinero completo del intervalo
        if right == "C":
            d["cC"] += val
            d["nC"] += val if agresor == "COMPRA" else (-val if agresor == "VENTA" else 0.0)
        else:
            d["cP"] += val
            d["nP"] += val if agresor == "COMPRA" else (-val if agresor == "VENTA" else 0.0)
        if agresor == "MID":
            d["mid"] += 1

    print("   Operaciones descartadas por el filtro de moneyness: %d de %d"
          % (fuera, len(filas)))
    print()
    print("%-6s %8s %5s %7s | %12s %12s | %12s %12s | %12s %6s" %
          ("hora", "spy", "ops", "contr", "BRUTO call", "BRUTO put",
           "NETO call", "NETO put", "NETO C-P", "MID%"))
    print("-" * 118)

    minutos = sorted(por_min)
    tot = {"ops": 0, "cC": 0.0, "cP": 0.0, "nC": 0.0, "nP": 0.0, "mid": 0}
    for m in minutos:
        d = por_min[m]
        px = spy.get(m)
        for k in tot:
            tot[k] += d[k]
        print("%-6s %8s %5d %7.0f | %12.0f %12.0f | %+12.0f %+12.0f | %+12.0f %5.0f%%" %
              (m, ("%.2f" % px) if px else "-", d["ops"], d["size"],
               d["cC"], d["cP"], d["nC"], d["nP"], d["nC"] - d["nP"],
               100.0 * d["mid"] / d["ops"] if d["ops"] else 0))

    print("-" * 118)
    print("%-6s %8s %5d %7s | %12.0f %12.0f | %+12.0f %+12.0f | %+12.0f %5.0f%%" %
          ("TOTAL", "", tot["ops"], "", tot["cC"], tot["cP"], tot["nC"], tot["nP"],
           tot["nC"] - tot["nP"], 100.0 * tot["mid"] / max(tot["ops"], 1)))
    print()
    print("BRUTO = todo el dinero que paso (direccionalmente CIEGO).")
    print("NETO  = firmado por agresor: +COMPRA, -VENTA, 0 si se cruzo en MID.")
    print("MID%%  = fraccion de operaciones NO atribuibles. Es la medida de lo que no sabemos.")
    db.close()


if __name__ == "__main__":
    main()
