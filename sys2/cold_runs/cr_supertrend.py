# -*- coding: utf-8 -*-
"""COLD RUN DIFERENCIAL (R8): el nucleo core/supertrend debe dar EXACTAMENTE lo mismo
que las funciones validadas del backtest, sobre datos REALES de sys2.bars:
  1) core.st_dir  ==  year_backtest.st_dir   (elemento por elemento, sobre buckets reales)
  2) core.flips_st3(bars)  ==  backtest_st3_orb.sen_principal(bars)  (dia a dia)
Si divergen, ROJO. Exit 0 = verde.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "analisis"))

from sys2.core import supertrend as core
from sys2.db import repo
import year_backtest as yb
import backtest_st3_orb as B


def main():
    fallos = []
    con = repo.abrir()
    # dias reales con premarket: muestreo (1 de cada ~25) para cubrir ambos anos
    dias = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    muestra = dias[::25]
    print("dias muestreados: %d de %d" % (len(muestra), len(dias)))

    difs_stdir = 0
    difs_flips = 0
    comparados = 0
    for fk in muestra:
        rows = con.execute(
            "select hora,high,low,close from bars where fecha=? order by hora", (fk,)).fetchall()
        if len(rows) < 100:
            continue
        bars = [(h, hi, lo, cl) for h, hi, lo, cl in rows]
        comparados += 1

        # 1) st_dir sobre los mismos buckets de 3 min
        HO, HI, LO, CL = core.buckets3(bars, 3)
        d_core = core.st_dir(HI, LO, CL)
        d_yb = yb.st_dir(HI, LO, CL)
        if d_core != d_yb:
            difs_stdir += 1
            if difs_stdir <= 2:
                print("  st_dir DIFIERE en %s" % fk)

        # 2) flips del ST-3 ejecutables
        f_core = core.flips_st3(bars)
        f_ref = B.sen_principal(bars)
        if f_core != f_ref:
            difs_flips += 1
            if difs_flips <= 3:
                print("  flips DIFIEREN en %s:\n     core=%s\n     ref =%s"
                      % (fk, f_core[:6], f_ref[:6]))

    con.close()
    print("comparados: %d dias | st_dir difs: %d | flips difs: %d"
          % (comparados, difs_stdir, difs_flips))
    if difs_stdir:
        fallos.append("st_dir difiere de year_backtest en %d dias" % difs_stdir)
    if difs_flips:
        fallos.append("flips_st3 difiere de sen_principal en %d dias" % difs_flips)
    if comparados < 10:
        fallos.append("muy pocos dias comparados (%d)" % comparados)

    if fallos:
        print("\nROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("\nVERDE: core/supertrend equivale EXACTO al backtest validado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
