# Refresca spy_velas.db (velas + m1 + m2) y genera TABLA_CUERPOS.txt.
# Columnas: vela, hora, cuerpo (centavos), color, spy, acum_ver, acum_roj,
#           salto_ver, salto_roj, salta_mas, m1 + m1_val, m2 + m2_val.
# salto_ver = acum_ver / n_verdes  -> tamaño MEDIO del salto verde hasta ese minuto
# salto_roj = |acum_roj| / n_rojas -> tamaño MEDIO del salto rojo hasta ese minuto
# salta_mas = cual de los dos salta mas fuerte en ese momento
# m1_val = m1_minute.marcador  (n_up - n_down, contador de MINUTOS)
# m2_val = m2_minute.acumulado (usd_up - usd_down, acumulado en USD)
# Abre la BD viva en solo-lectura y la cierra en cuanto tiene los datos.
import os
import sqlite3

SRC = "spy_history.db"
DST = "spy_velas.db"
TXT = "TABLA_CUERPOS.txt"

# ---- 1. Leer de la BD viva y CERRAR cuanto antes ------------------------------
src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=10)
velas = src.execute("select fecha,hora,open,high,low,close,volume from bars_minute "
                    "order by fecha,hora").fetchall()
m1 = src.execute("select fecha,hora,m1,marcador,n_up,n_down from m1_minute "
                 "order by fecha,hora").fetchall()
m2 = src.execute("select fecha,hora,m2,acumulado,usd_up,usd_down from m2_minute "
                 "order by fecha,hora").fetchall()
src.close()
print(f"leidas {len(velas)} velas, {len(m1)} filas m1, {len(m2)} filas m2. BD viva CERRADA.")

# ---- 2. Reescribir la copia ---------------------------------------------------
if os.path.exists(DST):
    os.remove(DST)
dst = sqlite3.connect(DST)
dst.execute("CREATE TABLE bars_minute (fecha TEXT, hora TEXT, open REAL, high REAL, low REAL,"
            " close REAL, volume REAL, PRIMARY KEY(fecha,hora))")
dst.execute("CREATE TABLE m1_minute (fecha TEXT, hora TEXT, m1 TEXT, marcador REAL,"
            " n_up REAL, n_down REAL, PRIMARY KEY(fecha,hora))")
dst.execute("CREATE TABLE m2_minute (fecha TEXT, hora TEXT, m2 TEXT, acumulado REAL,"
            " usd_up REAL, usd_down REAL, PRIMARY KEY(fecha,hora))")
dst.executemany("insert into bars_minute values (?,?,?,?,?,?,?)", velas)
dst.executemany("insert into m1_minute values (?,?,?,?,?,?)", m1)
dst.executemany("insert into m2_minute values (?,?,?,?,?,?)", m2)
dst.commit()

# ---- 3. Generar la tabla ------------------------------------------------------
dias = [r[0] for r in dst.execute("select distinct fecha from bars_minute order by fecha")]
O = []
for d in dias:
    filas = dst.execute("select hora,open,close from bars_minute where fecha=? order by hora",
                        (d,)).fetchall()
    O.append(f"=== {d} ===")
    O.append(f"{'vela':>5} {'hora':>7} {'cuerpo':>7} {'color':>6} {'spy':>9} "
             f"{'acum_ver':>9} {'acum_roj':>9} {'salto_ver':>10} {'salto_roj':>10} "
             f"{'salta_mas':>10}")
    av = ar = 0
    nv = nr = 0
    for i, (hora, o_, cl) in enumerate(filas, 1):
        cu = round((cl - o_) * 100)
        if cu > 0:
            av += cu
            nv += 1
            col = "VERDE"
        elif cu < 0:
            ar += cu
            nr += 1
            col = "ROJA"
        else:
            col = "DOJI"
        sv = av / nv if nv else 0.0          # salto medio verde hasta aqui
        sr = -ar / nr if nr else 0.0         # salto medio rojo hasta aqui (positivo)
        if nv and nr:
            dom = "VERDE" if sv > sr else ("ROJA" if sr > sv else "=")
        else:
            dom = "-"
        O.append(f"{i:5} {hora:>7} {cu:+7d} {col:>6} {cl:9.2f} {av:+9d} {ar:+9d} "
                 f"{sv:10.2f} {sr:10.2f} {dom:>10}")
    O.append("")
dst.close()

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT}  ({len(O)} lineas)")
