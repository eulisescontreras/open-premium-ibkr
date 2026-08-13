# Genera TAPE_AYER.txt leyendo spy_tape_ayer.db. Se puede ejecutar EN CUALQUIER MOMENTO,
# incluso con la descarga a medias: muestra lo que haya guardado hasta ese instante.
#
# Columnas: hora, spy, cuerpo, acum_spy, digitos, acum/tick, ticks_spy  (las mismas que hoy)
#
# IMPORTES Y CONTEOS: exactos (precio x tamaño de cada operacion real de IBKR).
# SIGNO: REGLA DEL TICK -> price > anterior = COMPRA, < = VENTA, igual = hereda el signo.
# La primera operacion no tiene anterior: MID, y NO entra en el neto (regla 13).
import os
import sqlite3

DB = "spy_tape_ayer.db"
SRC = "spy_history.db"
TXT = "TAPE_AYER.txt"
DIA = "2026-08-12"

if not os.path.exists(DB):
    raise SystemExit(f"no existe {DB}: la descarga aun no ha guardado nada")

db = sqlite3.connect(DB)
# rowid preserva el orden de llegada de IBKR dentro del mismo segundo. Ordenar por (ts, rowid)
# es lo correcto; el intento anterior de ordenar por x.index reventaba (era el metodo de tuple).
trades = db.execute("select ts_et, minuto, price, size from trades_raw "
                    "order by ts_et, rowid").fetchall()
print(f"{len(trades)} ticks leidos de {DB}")
if not trades:
    raise SystemExit("la BD esta vacia")

# ---------- signo por REGLA DEL TICK ----------
por_min = {}
prev_precio = prev_signo = None
n_mid = 0
for ts, minuto, price, size in trades:
    if prev_precio is None:
        ag = "MID"
    elif price > prev_precio:
        ag = "COMPRA"
    elif price < prev_precio:
        ag = "VENTA"
    else:
        ag = prev_signo or "MID"
    if ag in ("COMPRA", "VENTA"):
        prev_signo = ag
    else:
        n_mid += 1
    prev_precio = price
    c, v, n = por_min.get(minuto, (0.0, 0.0, 0))
    imp = price * size
    por_min[minuto] = (c + imp if ag == "COMPRA" else c,
                       v + imp if ag == "VENTA" else v,
                       n + 1)
db.close()
print(f"clasificados. sin signo (MID): {n_mid}")

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,open,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
src.close()

O = []
O.append(f"TAPE DEL SUBYACENTE (SPY) DE {DIA} POR MINUTO")
O.append("=" * 92)
O.append("acum_spy  = suma corrida del neto (COMPRA - VENTA) del tape del SPY, en USD")
O.append("digitos   = cuantas cifras tiene acum_spy (sin contar el signo)")
O.append("acum/tick = acum_spy dividido entre los ticks_spy de ESE minuto")
O.append("ticks_spy = operaciones del tape del SPY en ese minuto")
O.append("")
O.append("IMPORTES Y CONTEOS: exactos (precio x tamaño de cada operacion real de IBKR).")
O.append("SIGNO: REGLA DEL TICK (sube respecto a la operacion anterior = COMPRA, baja = VENTA,")
O.append("igual = hereda el signo). NO es la regla de HOY, que compara con el bid/ask vivo:")
O.append("bajar el historico de cotizaciones de un dia son ~14.000 peticiones (~43 h).")
O.append("")
O.append(f"{'hora':>7} {'spy':>9} {'cuerpo':>7} {'acum_spy':>15} "
         f"{'digitos':>8} {'acum/tick':>14} {'ticks_spy':>10}")

acum = 0.0
n_con = 0
for hora, o_, cl in velas:
    if hora not in por_min:
        continue                      # minuto aun no descargado: no se inventa una fila
    n_con += 1
    cu = round((cl - o_) * 100)
    sC, sV, sN = por_min[hora]
    acum += sC - sV
    dig = len(str(abs(int(round(acum)))))
    apt = f"{acum/sN:+14.0f}" if sN else f"{'-':>14}"
    dir_ = "UP" if cu > 0 else ("DOWN" if cu < 0 else "DOJI")
    O.append(f"{hora:>7} {cl:9.2f} {dir_:>7} {acum:+15.0f} {dig:8} {apt} {sN:10}")

horas = sorted(por_min)
O.append("")
O.append(f"minutos con tape: {n_con} de {len(velas)} velas del dia "
         f"(de {horas[0]} a {horas[-1]})")
if n_con < len(velas):
    O.append("PARCIAL: la descarga aun no ha cubierto el dia entero.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas), {n_con} minutos de {len(velas)}")
