# -*- coding: utf-8 -*-
"""Reconstruye spy_bars_pm.db (tabla bars_pm) a partir de spy_bars_year.db.

POR QUE: `synth_premium.spy_min` -y por tanto `backtest_st3_orb.py`- necesitan
spy_bars_pm.db para saber el close del SPY por minuto en los dias de calibracion. Ese
fichero lo generaba `bajar_bars_pm_semana.py` pidiendoselo a IBKR, y NO esta en el repo
(el .gitignore excluye *.db), asi que el backtest no arranca en una maquina limpia.

NO se inventa ningun dato: las barras salen de spy_bars_year.db, que son las MISMAS
velas 1-min de IBKR (TRADES, useRTH=False, US/Eastern) pedidas por bajar_bars_year.py.
Solo se cambia el envoltorio: bars(fecha,hora,open,high,low,close,volume,wap)
-> bars_pm(fecha,hora,high,low,close).

Asi el backtest es reproducible sin volver a pedirle nada al broker.

Uso:  python analisis/rehacer_bars_pm.py [fecha_desde]
"""
import os
import sqlite3
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = [os.path.join(RAIZ, "spy_bars_year.db"), os.path.join(RAIZ, "spy_bars_year2.db")]
DST = os.path.join(RAIZ, "spy_bars_pm.db")
DESDE = sys.argv[1] if len(sys.argv) > 1 else "2026-08-01"


def main():
    filas = {}
    for p in SRC:
        if not os.path.exists(p):
            print("  aviso: no existe %s" % os.path.basename(p))
            continue
        c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
        n = 0
        for f, h, hi, lo, cl in c.execute(
                "select fecha,hora,high,low,close from bars where fecha>=? order by fecha,hora",
                (DESDE,)):
            filas[(f, h)] = (hi, lo, cl)      # dedup por (fecha,hora): 2025-07-31 esta en ambas
            n += 1
        c.close()
        print("  %-22s %6d filas desde %s" % (os.path.basename(p), n, DESDE))

    if not filas:
        print("SIN DATOS: no hay barras desde %s" % DESDE)
        return 1

    con = sqlite3.connect(DST)
    con.execute("CREATE TABLE IF NOT EXISTS bars_pm ("
                "fecha TEXT, hora TEXT, high REAL, low REAL, close REAL, "
                "PRIMARY KEY(fecha,hora))")
    con.executemany("INSERT OR REPLACE INTO bars_pm VALUES (?,?,?,?,?)",
                    [(f, h, v[0], v[1], v[2]) for (f, h), v in sorted(filas.items())])
    con.commit()
    d = con.execute("select count(distinct fecha) from bars_pm").fetchone()[0]
    n = con.execute("select count(*) from bars_pm").fetchone()[0]
    mn, mx = con.execute("select min(fecha),max(fecha) from bars_pm").fetchone()
    con.close()
    print("\n%s: %d filas | %d dias | %s .. %s" % (os.path.basename(DST), n, d, mn, mx))

    # los 3 dias que necesita la calibracion del premium sintetico
    con = sqlite3.connect("file:%s?mode=ro" % DST.replace("\\", "/"), uri=True)
    print("\ndias de calibracion:")
    ok = True
    for f in ("2026-08-11", "2026-08-12", "2026-08-13"):
        r = con.execute("select count(*),min(hora),max(hora) from bars_pm where fecha=? "
                        "and hora>='09:30' and hora<='16:00'", (f,)).fetchone()
        print("  %s  %3d minutos RTH  %s..%s" % (f, r[0], r[1], r[2]))
        if r[0] < 380:
            ok = False
    con.close()
    print("\n%s" % ("OK: la calibracion tiene los 3 dias completos" if ok
                    else "*** FALTAN MINUTOS en algun dia de calibracion ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
