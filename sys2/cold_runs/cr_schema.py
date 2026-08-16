# -*- coding: utf-8 -*-
"""COLD RUN: esquema + repo. Verifica (con la funcion REAL repo.abrir) que la BD
se crea con TODAS las tablas y columnas criticas, y que insertar() es idempotente.
Corre contra una BD temporal (no toca sys2.db). Exit 0 = verde, 1 = rojo.
"""
import os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from sys2.db import repo

TABLAS_ESPERADAS = {
    "bars", "bars_etf", "dia_anterior", "premium", "senales", "contexto_dia",
    "operaciones", "fills", "movimientos", "tape_und", "premium_mix", "migracion_log",
}
COLS_CRITICAS = {
    "premium": {"day_vol", "delta", "gamma", "theta", "vega", "iv", "expiry", "fuente"},
    "senales": {"grupo", "flip_falso", "direccion_final", "descartada_por", "invertida_por"},
    "fills": {"parcial", "lleno"},
    "operaciones": {"n_op_dia", "razon_salida", "nivel", "unidades"},
    "contexto_dia": {"mov_DIA", "mov_TLT", "efic60", "dia_bueno"},
}


def main():
    fallos = []
    d = tempfile.mkdtemp()
    con = repo.abrir(os.path.join(d, "t.db"))

    tabs = set(repo.tablas(con))
    faltan = TABLAS_ESPERADAS - tabs
    if faltan:
        fallos.append("faltan tablas: %s" % sorted(faltan))
    print("tablas creadas: %d" % len(tabs))

    for t, req in COLS_CRITICAS.items():
        cols = set(repo.columnas(con, t))
        f = req - cols
        if f:
            fallos.append("%s: faltan columnas %s" % (t, sorted(f)))

    # idempotencia: insertar la MISMA fila 2 veces -> 1 sola fila (PK)
    fila = [dict(fecha="2026-08-16", hora="09:30", open=1, high=1, low=1, close=1,
                 volume=1, vwap=1, fuente="test")]
    repo.insertar(con, "bars", fila)
    repo.insertar(con, "bars", fila)
    con.commit()
    n = repo.contar(con, "bars")
    if n != 1:
        fallos.append("idempotencia rota: bars tiene %d filas (esperado 1)" % n)
    print("idempotencia bars: %d fila(s)" % n)

    # premium con expiry en PK: 2 expiries distintos NO colisionan
    base = dict(fecha="2026-08-16", hora="09:30", strike=640.0, right="C",
                bid=1, ask=1, mid=1, last=1, day_vol=0, open_interest=0,
                iv=0.2, delta=0.8, gamma=0, theta=0, vega=0, fuente="bs")
    repo.insertar(con, "premium", [dict(base, expiry="2026-08-16"),
                                   dict(base, expiry="2026-08-17")])
    con.commit()
    np = repo.contar(con, "premium")
    if np != 2:
        fallos.append("premium expiry-PK: %d filas (esperado 2)" % np)
    print("premium 2 expiries: %d filas" % np)

    con.close()
    if fallos:
        print("\nROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("\nVERDE: esquema + repo OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
