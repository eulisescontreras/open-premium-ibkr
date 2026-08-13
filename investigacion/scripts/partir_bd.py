# Parte spy_history.db (151,6 MB, por encima del limite de 100 MB de GitHub) en una BD por
# DIA. Asi cada fichero cabe y el historico deja de ser un unico archivo que crece sin fin.
#
# NO TOCA LA BD DE PRODUCCION: se abre en SOLO-LECTURA. Las BD por dia son nuevas.
# Se copian TODAS las tablas que tengan columna `fecha`, filtradas por ese dia, con su DDL
# original. Las que no la tengan se avisan y se omiten (no se inventa a que dia pertenecen).
import os
import sqlite3

SRC = "spy_history.db"

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=20)
tablas = [r[0] for r in src.execute(
    "select name from sqlite_master where type='table' and name not like 'sqlite_%' "
    "order by name")]

con_fecha, sin_fecha = [], []
for t in tablas:
    cols = [d[1] for d in src.execute(f'PRAGMA table_info("{t}")')]
    (con_fecha if "fecha" in cols else sin_fecha).append(t)

fechas = set()
for t in con_fecha:
    for (f,) in src.execute(f'select distinct fecha from "{t}"'):
        if f:
            fechas.add(f)
fechas = sorted(fechas)
print(f"tablas con fecha: {len(con_fecha)} | sin fecha (se omiten): {sin_fecha}")
print(f"dias encontrados: {fechas}\n")

for dia in fechas:
    dst_path = f"spy_history_{dia.replace('-', '')}.db"
    if os.path.exists(dst_path):
        print(f"  {dst_path} ya existe, se omite")
        continue
    dst = sqlite3.connect(dst_path)
    total = 0
    for t in con_fecha:
        ddl = src.execute(
            "select sql from sqlite_master where type='table' and name=?", (t,)).fetchone()[0]
        dst.execute(ddl)
        cols = [d[1] for d in src.execute(f'PRAGMA table_info("{t}")')]
        filas = src.execute(f'select * from "{t}" where fecha=?', (dia,)).fetchall()
        if filas:
            ph = ",".join("?" * len(cols))
            dst.executemany(f'insert into "{t}" values ({ph})', filas)
            total += len(filas)
        # indices de esa tabla
        for (isql,) in src.execute(
                "select sql from sqlite_master where type='index' and tbl_name=? "
                "and sql is not null", (t,)):
            try:
                dst.execute(isql)
            except sqlite3.OperationalError:
                pass
    dst.commit()
    dst.execute("VACUUM")
    dst.close()
    mb = os.path.getsize(dst_path) / 1024 / 1024
    print(f"  {dst_path}: {total:,} filas, {mb:.1f} MB")

src.close()
print("\nLA BD DE PRODUCCION NO SE HA TOCADO (solo lectura).")
