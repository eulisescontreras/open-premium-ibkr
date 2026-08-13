# Vuelca el TAPE CRUDO descargado tal cual esta en la BD, sin ningun procesado:
# ni agresor, ni acumulados, ni filtros. Una linea por operacion, en el orden de llegada.
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "spy_tape_ayer.db"
TXT = sys.argv[2] if len(sys.argv) > 2 else "TAPE_CRUDO_20260812.txt"

d = sqlite3.connect(DB)
filas = d.execute("select ts_et, price, size from trades_raw order by ts_et, rowid").fetchall()
n, vol = d.execute("select count(*), sum(size) from trades_raw").fetchone()
d.close()

with open(TXT, "w", encoding="utf-8") as f:
    f.write(f"TAPE CRUDO DEL SUBYACENTE (SPY) descargado de IBKR -- SIN PROCESAR\n")
    f.write("=" * 60 + "\n")
    f.write(f"origen: {DB}\n")
    f.write(f"{n:,} operaciones | {vol:,.0f} acciones\n")
    f.write("una linea por operacion, en el orden real de ejecucion\n")
    f.write("importe = precio x tamaño de ESA operacion (sin acumular nada)\n\n")
    f.write(f"{'#':>8} {'hora':>12} {'precio':>10} {'size':>10} {'importe USD':>16}\n")
    for i, (ts, p, s) in enumerate(filas, 1):
        f.write(f"{i:8} {ts:>12} {p:10.2f} {s:10.0f} {p*s:16,.2f}\n")

print(f"escrito {TXT}: {n:,} operaciones")
