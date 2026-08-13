# Copia SOLO la tabla de velas (bars_minute) a spy_velas.db y saca el inventario.
# No toca IBKR. Abre la BD viva en solo-lectura y la cierra en cuanto tiene los datos.
import os
import sqlite3
import sys
from collections import Counter

SRC = "spy_history.db"
DST = "spy_velas.db"
TXT = "INVENTARIO_VELAS.txt"

if os.path.exists(DST):
    print(f"ABORTA: {DST} ya existe. No se pisa nada.")
    sys.exit(1)

# ---- 1. Leer de la BD viva y CERRAR cuanto antes ------------------------------
src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=10)
ddl = src.execute(
    "select sql from sqlite_master where type='table' and name='bars_minute'"
).fetchone()[0]
idx = [r[0] for r in src.execute(
    "select sql from sqlite_master where type='index' and tbl_name='bars_minute' "
    "and sql is not null")]
cols = [d[1] for d in src.execute("PRAGMA table_info(bars_minute)")]
rows = src.execute("select * from bars_minute").fetchall()
src.close()
print(f"Leidas {len(rows)} filas de {SRC}. Conexion a la BD viva CERRADA.")

# ---- 2. Escribir la copia -----------------------------------------------------
dst = sqlite3.connect(DST)
dst.execute(ddl)
for s in idx:
    dst.execute(s)
dst.executemany(
    f"insert into bars_minute ({','.join(cols)}) values ({','.join('?' * len(cols))})", rows)
dst.commit()
n_dst = dst.execute("select count(*) from bars_minute").fetchone()[0]
print(f"Escritas {n_dst} filas en {DST}  (origen {len(rows)} -> {'OK' if n_dst == len(rows) else 'DESCUADRE'})")

# ---- 3. Inventario ------------------------------------------------------------
O = []
def p(s=""):
    print(s)
    O.append(s)

p("INVENTARIO DE VELAS  -  tabla bars_minute")
p("=" * 78)
p(f"origen : {SRC}")
p(f"copia  : {DST}")
p(f"filas  : {n_dst}")
p(f"columnas: {', '.join(cols)}")
p(f"DDL    : {ddl}")
p(f"indices: {idx if idx else '(ninguno)'}")
p()

p("COBERTURA POR DIA")
p("-" * 78)
p(f"{'fecha':12} {'velas':>6} {'1a hora':>9} {'ult hora':>9} {'span_min':>9} {'huecos':>7} {'dup':>5}")
q = """select fecha, count(*), min(hora), max(hora), count(distinct hora)
       from bars_minute group by fecha order by fecha"""
tot_h = 0
for fecha, n, h0, h1, ndist in dst.execute(q):
    def mins(h):
        pt = str(h).split(":")
        return int(pt[0]) * 60 + int(pt[1])
    span = mins(h1) - mins(h0) + 1
    huecos = span - ndist
    dup = n - ndist
    tot_h += huecos
    p(f"{fecha:12} {n:6} {str(h0):>9} {str(h1):>9} {span:9} {huecos:7} {dup:5}")
p()

p("NULOS Y CEROS POR COLUMNA")
p("-" * 78)
p(f"{'columna':10} {'nulos':>7} {'ceros':>7} {'min':>14} {'max':>14}")
for c in cols:
    nn = dst.execute(f"select count(*) from bars_minute where \"{c}\" is null").fetchone()[0]
    if c in ("open", "high", "low", "close", "volume"):
        nz = dst.execute(f"select count(*) from bars_minute where \"{c}\"=0").fetchone()[0]
        mn, mx = dst.execute(f'select min("{c}"), max("{c}") from bars_minute').fetchone()
        p(f"{c:10} {nn:7} {nz:7} {mn!s:>14} {mx!s:>14}")
    else:
        mn, mx = dst.execute(f'select min("{c}"), max("{c}") from bars_minute').fetchone()
        p(f"{c:10} {nn:7} {'-':>7} {mn!s:>14} {mx!s:>14}")
p()

p("VOLUMEN (lo que decide si el VWAP real es posible)")
p("-" * 78)
r = dst.execute("select count(*), sum(volume=0), sum(volume is null), "
                "round(avg(volume),1), min(volume), max(volume) from bars_minute").fetchone()
p(f"velas={r[0]}  vol_cero={r[1]}  vol_nulo={r[2]}  vol_medio={r[3]}  min={r[4]}  max={r[5]}")
p()
p(f"TOTAL huecos de minuto dentro del horario cubierto: {tot_h}")

dst.close()
with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"\nInventario escrito en {TXT}")
