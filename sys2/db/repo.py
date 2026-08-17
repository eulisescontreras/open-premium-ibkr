# -*- coding: utf-8 -*-
"""Capa de acceso a la BD del sistema sys2. Crea la BD aplicando schema.sql y
da helpers idempotentes. NUNCA reimplementa logica de negocio; solo persistencia.
OBLIGATORIO: antes de modificar, leer el plan aprobado y MANUAL_TRASPASO_AGENTE.
"""
import os
import sqlite3

DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(DIR, "schema.sql")
RAIZ = os.path.dirname(os.path.dirname(DIR))          # raiz del repo
DB_DEFAULT = os.path.join(RAIZ, "sys2.db")


def abrir(db_path=DB_DEFAULT):
    """Abre (o crea) la BD y aplica el esquema. Devuelve la conexion sqlite3."""
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    con.commit()
    return con


def tablas(con):
    """Lista de tablas de usuario (sin sqlite_*)."""
    q = "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
    return [r[0] for r in con.execute(q)]


def columnas(con, tabla):
    """Columnas (nombre) de una tabla, en orden."""
    return [r[1] for r in con.execute("PRAGMA table_info(%s)" % tabla)]


def insertar(con, tabla, filas, reemplaza=True):
    """INSERT (OR REPLACE) idempotente. `filas` = lista de dicts {columna: valor}.
    Devuelve el numero de filas insertadas. No hace commit (lo decide el caller)."""
    if not filas:
        return 0
    cols = list(filas[0].keys())
    verbo = "INSERT OR REPLACE" if reemplaza else "INSERT OR IGNORE"
    sql = "%s INTO %s (%s) VALUES (%s)" % (
        verbo, tabla, ",".join(cols), ",".join("?" * len(cols)))
    con.executemany(sql, [tuple(f.get(c) for c in cols) for f in filas])
    return len(filas)


def contar(con, tabla):
    return con.execute("select count(*) from %s" % tabla).fetchone()[0]


def prev_sesion(con, fecha):
    """(max_cierre, min_cierre, ultimo_cierre) del RTH de la ULTIMA sesion ANTERIOR a `fecha`.

    ⚠️ Son max/min de los CIERRES de 1 minuto, NO el high/low (con mechas) de la barra diaria.
    Es EXACTAMENTE lo que usa el motor de backtest (motor.py:255-256):
        prev = (max(cl_.values()), min(cl_.values()), cl_[hsd[-1]])
    con cl_ = cierres del RTH. El rango de mechas es mas ANCHO (medido: +0.29 pts de mediana,
    hasta +10.90) y por tanto mas dificil de romper -> si el vivo usara high/low generaria MENOS
    señales que el backtest (medido: ayer_rev 277 con mechas vs 293 con cierres).
    Alimenta prev_hi/prev_lo/prev_cl de las entradas `ayer_rev` y `gap_fade`.

    Devuelve (None, None, None) si no hay sesion anterior con datos RTH.
    """
    f = con.execute(
        "select max(fecha) from bars where fecha < ? and hora >= '09:30' and hora <= '16:00'",
        (fecha,)).fetchone()
    if not f or not f[0]:
        return (None, None, None)
    r = con.execute(
        "select max(close), min(close), "
        "(select close from bars b2 where b2.fecha=? and b2.hora>='09:30' and b2.hora<='16:00' "
        " order by b2.hora desc limit 1) "
        "from bars where fecha=? and hora>='09:30' and hora<='16:00'",
        (f[0], f[0])).fetchone()
    return (r[0], r[1], r[2]) if r else (None, None, None)


def log_migracion(con, origen, destino, filas):
    con.execute(
        "insert into migracion_log(cuando,origen,destino,filas) "
        "values (datetime('now'),?,?,?)", (origen, destino, filas))
