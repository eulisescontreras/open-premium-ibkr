# -*- coding: utf-8 -*-
"""COLD RUN DIFERENCIAL del REBOTE (core/rebote.py) contra los TARGETS medidos del sistema
validado (premium REAL), confirmados por el agente dueño del análisis (2026-08-16):
  total flips : 1.411
  días        : 479
  grupos      : NORMAL 675 · RETRASA 393 · INVIERTE 243 · DESCARTA 100
  split A1/A2 : 334/341 · 194/199 · 127/116 · 48/52   (A1<2025-08-01, A2>=)
  falsos %    : NORMAL 12.3/9.1 · RETRASA 42.8/42.2 · INVIERTE 53.5/62.1 · DESCARTA 31.2/40.4
Universo = días presentes en la cadena premium de massive (485 con datos) ∩ sys2.bars.
Alimenta la FUNCIÓN REAL clasificar_dia con barras reales (premarket incl). Exit 0 = verde.
"""
import os, sys, sqlite3
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from sys2.core import rebote
from sys2.db import repo

MASSIVE = os.path.join(RAIZ, "massive_premium.db")
CORTE = "2025-08-01"
TARGET = {"NORMAL": (675, 334, 341), "RETRASA": (393, 194, 199),
          "INVIERTE": (243, 127, 116), "DESCARTA": (100, 48, 52)}
TOTAL_FLIPS = 1411
TARGET_FALSO = {"NORMAL": (12.3, 9.1), "RETRASA": (42.8, 42.2),
                "INVIERTE": (53.5, 62.1), "DESCARTA": (31.2, 40.4)}


def main():
    fallos = []
    if not os.path.exists(MASSIVE):
        print("ROJO: no existe massive_premium.db"); return 1
    mv = sqlite3.connect(MASSIVE)
    dias_prem = set(r[0] for r in mv.execute("select distinct fecha from aggs"))
    mv.close()
    con = repo.abrir()
    dias_bar = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    dias = [d for d in dias_bar if d in dias_prem]
    print("días premium: %d | ∩ bars: %d" % (len(dias_prem), len(dias)))

    # conteos: grupo -> [n, nA1, nA2, falsos_A1, falsos_A2]
    cont = {g: [0, 0, 0, 0, 0] for g in TARGET}
    total = 0
    dias_con_flip = 0
    for fk in dias:
        rows = con.execute(
            "select hora,high,low,close from bars where fecha=? order by hora", (fk,)).fetchall()
        if len(rows) < 100:
            continue
        bars = [(h, hi, lo, cl) for h, hi, lo, cl in rows]
        rth = [(h, cl) for h, hi, lo, cl in rows if "09:30" <= h <= "16:00"]
        res = rebote.clasificar_dia(bars, rth)
        if res:
            dias_con_flip += 1
        a2 = fk >= CORTE
        for r in res:
            g = r["grupo"]
            total += 1
            cont[g][0] += 1
            cont[g][2 if a2 else 1] += 1
            if r["falso"]:
                cont[g][4 if a2 else 3] += 1
    con.close()

    print("\ntotal flips: %d (target %d)  |  días con flip: %d" % (total, TOTAL_FLIPS, dias_con_flip))
    print("%-9s %6s %6s %6s | %8s %8s" % ("grupo", "n", "A1", "A2", "falso%A1", "falso%A2"))
    for g in ("NORMAL", "RETRASA", "INVIERTE", "DESCARTA"):
        n, a1, a2, f1, f2 = cont[g]
        p1 = 100.0 * f1 / a1 if a1 else 0
        p2 = 100.0 * f2 / a2 if a2 else 0
        tn, ta1, ta2 = TARGET[g]
        tf1, tf2 = TARGET_FALSO[g]
        print("%-9s %6d %6d %6d | %7.1f%% %7.1f%%   target n=%d(%d/%d) falso=%.1f/%.1f"
              % (g, n, a1, a2, p1, p2, tn, ta1, ta2, tf1, tf2))
        if n != tn:
            fallos.append("%s n=%d != target %d" % (g, n, tn))
        if a1 != ta1 or a2 != ta2:
            fallos.append("%s split %d/%d != target %d/%d" % (g, a1, a2, ta1, ta2))
        # falsos: tolerancia 1.5 puntos porcentuales
        if abs(p1 - tf1) > 1.5 or abs(p2 - tf2) > 1.5:
            fallos.append("%s falso%% %.1f/%.1f != target %.1f/%.1f" % (g, p1, p2, tf1, tf2))

    if total != TOTAL_FLIPS:
        fallos.append("total flips %d != target %d" % (total, TOTAL_FLIPS))

    if fallos:
        print("\nROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("\nVERDE: rebote.py reproduce EXACTO 1.411 flips y 675/393/243/100 del sistema validado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
