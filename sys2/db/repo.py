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


def log_migracion(con, origen, destino, filas):
    con.execute(
        "insert into migracion_log(cuando,origen,destino,filas) "
        "values (datetime('now'),?,?,?)", (origen, destino, filas))
