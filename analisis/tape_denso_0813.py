# -*- coding: utf-8 -*-
"""Limpia mi descarga IBKR del 08-13 (spy_tape.db, tabla `trades`) al MISMO esquema
`trades_raw` que usa el simulador (replica exacta de investigacion/scripts/exportar_tape.py),
y corre el SIMULADOR REAL para el 08-13 con ese tape denso.

Diferencial (R8): tape VIVO (31k, +480.84 ref) vs tape DENSO IBKR (377k).
NO toca ningun archivo existente. La BD densa es NUEVA. No edita el simulador:
usa su parametro simular(..., db_tape=...).
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from simulador_st import simular, SENALES_MANUALES, CAPITAL_0, FUENTES  # simulador REAL

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)

SRC = R("spy_tape.db")                       # mi descarga IBKR (tabla trades)
DST = R("spy_tape_20260813_denso.db")        # BD nueva, esquema trades_raw

# ---- 1) LIMPIEZA: trades -> trades_raw (mismo formato que exportar_tape.py) ----
if os.path.exists(DST):
    print(f"[limpieza] {os.path.basename(DST)} ya existe -> se reutiliza (no se pisa).")
else:
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    # ts = "2026-08-13 09:30:53.000"  ->  ts_et=substr(12,8)="09:30:53" ; minuto=substr(12,5)="09:30"
    filas = src.execute(
        "select substr(ts,12,8), substr(ts,12,5), price, size from trades "
        "where price is not null and size is not null and size>0 "
        "order by ts").fetchall()
    src.close()
    dst = sqlite3.connect(DST)
    dst.execute("CREATE TABLE trades_raw (ts_et TEXT, minuto TEXT, price REAL, size REAL, "
                "exchange TEXT, cond TEXT)")
    dst.executemany("insert into trades_raw values (?,?,?,?,NULL,NULL)", filas)
    dst.commit()
    n, a, b = dst.execute("select count(*), min(ts_et), max(ts_et) from trades_raw").fetchone()
    mins = dst.execute("select count(distinct minuto) from trades_raw").fetchone()[0]
    vol = dst.execute("select sum(size) from trades_raw").fetchone()[0]
    dst.close()
    print(f"[limpieza] escrito {os.path.basename(DST)}: {n:,} ticks, {mins} min, {a}-{b}, vol {vol:,.0f}")

# ---- 2) SIMULADOR REAL, diferencial vivo vs denso ----
F = "2026-08-13"
sen = SENALES_MANUALES[F]
db_velas_0813, db_tape_vivo, expiry = FUENTES[F]

print("\n" + "=" * 78)
print("BASELINE  ·  tape VIVO (spy_tape_20260813.db, 31k)  ·  ref +480.84")
print("=" * 78)
ops_v, cap_v = simular(F, senales=sen, verbose=True)        # FUENTES default = vivo
g_v = cap_v - CAPITAL_0
print(f"   {F}: {len(ops_v)} ops   {g_v:+.2f}$")

print("\n" + "=" * 78)
print("DENSO  ·  tape IBKR (spy_tape_20260813_denso.db, 377k)  ·  MISMAS senales/config")
print("=" * 78)
ops_d, cap_d = simular(F, senales=sen, db_velas=db_velas_0813, db_tape=DST,
                       expiry=expiry, verbose=True)
g_d = cap_d - CAPITAL_0
print(f"   {F}: {len(ops_d)} ops   {g_d:+.2f}$")

print("\n" + "=" * 78)
print(f"DIFERENCIAL   vivo {g_v:+.2f}$   vs   denso {g_d:+.2f}$   (delta {g_d-g_v:+.2f}$)")
print("=" * 78)
