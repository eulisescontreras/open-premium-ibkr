# -*- coding: utf-8 -*-
"""COLD RUN: migracion. Verifica invariantes sobre la sys2.db REAL ya migrada
(datos reales, funciones reales de migrar.py) y la IDEMPOTENCIA de re-migrar.
Exit 0 = verde, 1 = rojo. Requiere haber corrido `python -m sys2.db.migrar` antes.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from sys2.db import repo, migrar


def main():
    fallos = []
    if not os.path.exists(repo.DB_DEFAULT):
        print("ROJO: no existe sys2.db — corre primero: python -m sys2.db.migrar")
        return 1
    con = repo.abrir()

    # 1) bars: 2 anos continuos + premarket presente
    mn, mx, ndias = con.execute("select min(fecha),max(fecha),count(distinct fecha) from bars").fetchone()
    if ndias < 480:
        fallos.append("bars: solo %d dias distintos (esperado >=480)" % ndias)
    pm = con.execute("select count(*) from bars where hora<'09:30'").fetchone()[0]
    if pm < 100000:
        fallos.append("bars premarket: %d (esperado >100k; sin premarket el sistema pierde)" % pm)
    print("bars: %s..%s, %d dias, %d barras premarket" % (mn, mx, ndias, pm))

    # 2) bars_etf: DIA y TLT
    etf = dict(con.execute("select ticker,count(*) from bars_etf group by ticker"))
    for t in ("DIA", "TLT"):
        if etf.get(t, 0) < 100000:
            fallos.append("bars_etf %s: %d filas (esperado >100k)" % (t, etf.get(t, 0)))
    print("bars_etf: %s" % etf)

    # 3) dia_anterior coherente: max>=cierre>=min y max>=min, en todas las filas
    incoh = con.execute(
        "select count(*) from dia_anterior where not (maximo>=minimo and maximo>=cierre and cierre>=minimo)"
    ).fetchone()[0]
    if incoh:
        fallos.append("dia_anterior: %d filas incoherentes (max/cierre/min)" % incoh)
    print("dia_anterior: %d filas, %d incoherentes" % (repo.contar(con, "dia_anterior"), incoh))

    # 4) premium live migrada (los pocos dias con captura real)
    npl = con.execute("select count(*) from premium where fuente='live'").fetchone()[0]
    if npl < 1000:
        fallos.append("premium live: %d filas (esperado los dias 2026-08-10..13)" % npl)
    print("premium live: %d filas" % npl)

    # 5) IDEMPOTENCIA: re-migrar bars_etf y dia_anterior no cambia el total
    a1 = repo.contar(con, "bars_etf")
    migrar.migrar_bars_etf(con)
    a2 = repo.contar(con, "bars_etf")
    if a1 != a2:
        fallos.append("idempotencia bars_etf: %d -> %d (deberia ser igual)" % (a1, a2))
    d1 = repo.contar(con, "dia_anterior")
    migrar.derivar_dia_anterior(con)
    d2 = repo.contar(con, "dia_anterior")
    if d1 != d2:
        fallos.append("idempotencia dia_anterior: %d -> %d" % (d1, d2))
    print("idempotencia: bars_etf %d==%d, dia_anterior %d==%d" % (a1, a2, d1, d2))

    con.close()
    if fallos:
        print("\nROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("\nVERDE: migracion OK (invariantes + idempotencia)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
