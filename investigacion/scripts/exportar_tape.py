# Exporta el tape del SUBYACENTE de un dia desde spy_history.db al MISMO esquema que usa
# spy_tape_ayer.db (tabla trades_raw), para que los dos dias se analicen con codigo identico.
#
# NO TOCA LA DATA BUENA: spy_history.db se abre en SOLO-LECTURA y se cierra enseguida.
# La BD de salida es nueva: spy_tape_YYYYMMDD.db
#
# El `agresor` de la BD viva (calculado con bid/ask) NO se copia a proposito: el analisis lo
# recalcula con la regla del tick, igual que en el dia descargado. Se copia solo el hecho
# crudo -hora, precio, tamaño- que es identico en ambas fuentes.
import os
import sqlite3
import sys

SRC = "spy_history.db"
DIA = sys.argv[1] if len(sys.argv) > 1 else "2026-08-13"
DST = f"spy_tape_{DIA.replace('-', '')}.db"

if os.path.exists(DST):
    print(f"ABORTA: {DST} ya existe. No se pisa nada.")
    raise SystemExit(1)

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
filas = src.execute(
    "select substr(hora,1,8), substr(hora,1,5), last, size from tape "
    "where fecha=? and grupo='SPY' and last is not null and size is not null and size>0 "
    "order by ts, id", (DIA,)).fetchall()
src.close()
print(f"leidas {len(filas)} operaciones del tape SPY de {DIA}. BD viva CERRADA (solo lectura).")

if not filas:
    print("sin datos: no se escribe nada")
    raise SystemExit(1)

dst = sqlite3.connect(DST)
# MISMAS columnas que spy_tape_ayer.db. Sin la restriccion UNIQUE: alli servia para deduplicar
# los solapes de la paginacion de IBKR; aqui los datos vienen ya sin repetir del stream en vivo,
# y un UNIQUE borraria operaciones legitimamente identicas del mismo segundo.
dst.execute("CREATE TABLE trades_raw (ts_et TEXT, minuto TEXT, price REAL, size REAL, "
            "exchange TEXT, cond TEXT)")
dst.executemany("insert into trades_raw values (?,?,?,?,NULL,NULL)", filas)
dst.commit()
n, a, b = dst.execute("select count(*), min(ts_et), max(ts_et) from trades_raw").fetchone()
mins = dst.execute("select count(distinct minuto) from trades_raw").fetchone()[0]
vol = dst.execute("select sum(size) from trades_raw").fetchone()[0]
dst.close()
print(f"escrito {DST}: {n:,} ticks, {mins} minutos, de {a} a {b}")
print(f"volumen del tape: {vol:,.0f} acciones")

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
vv = src.execute("select sum(volume) from bars_minute where fecha=?", (DIA,)).fetchone()[0]
src.close()
print(f"volumen bars_minute: {vv:,.0f}  ->  el tape cubre el {100*vol/vv:.1f}%")
