# -*- coding: utf-8 -*-
"""MIGRACIÓN de `tape_und` al esquema nuevo (seq/bid/ask) + VALIDACIÓN con datos REALES.

POR QUÉ: la tabla existía desde el diseño con PK (fecha,ts,price,size,exch) y NADIE escribía en
ella (0 filas). Esa PK descarta en silencio los trades idénticos del mismo segundo: MEDIDO sobre
el tape real del 2026-08-12, 4.491 de 380.778 ticks (1,2%), y no son aleatorios — son ejecuciones
troceadas de órdenes grandes, justo la señal a estudiar.

SEGURIDAD: solo migra si la tabla está VACÍA (regla 12: clasificar antes de borrar). Si tuviera
filas, ABORTA — habría que escribir una migración con copia de datos.

VALIDACIÓN (regla 3): tras migrar, mete ticks REALES del tape del 2026-08-13 (spy_history.tape,
grupo='SPY', el único día que trae bid/ask y agresor) por la FUNCIÓN REAL `captura.guardar_tape`,
y comprueba que no se pierde ni un tick. No es un mock: es el mismo código que correrá el vivo.
"""
import os, sys, sqlite3, datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from sys2.db import repo
from sys2.data import captura as CAP

DB = os.path.join(RAIZ, "sys2.db")
FUENTE = os.path.join(RAIZ, "spy_history.db")


def migrar(db=DB):
    con = sqlite3.connect(db)
    cols = [d[1] for d in con.execute("pragma table_info(tape_und)")]
    if not cols:
        print("tape_und no existe en %s; la creará repo.abrir()" % db)
        con.close()
        return True
    if "seq" in cols and "bid" in cols:
        print("ya migrada (%s)" % ",".join(cols))
        con.close()
        return True
    n = con.execute("select count(*) from tape_und").fetchone()[0]
    print("tape_und actual: %d filas | columnas: %s" % (n, ",".join(cols)))
    if n:
        print("ABORTA: la tabla NO está vacía. Hace falta una migración con copia de datos.")
        con.close()
        return False
    con.execute("drop table tape_und")
    con.execute("""create table tape_und (
        fecha TEXT, ts TEXT, seq INTEGER, price REAL, size REAL, exch TEXT,
        bid REAL, ask REAL, signo TEXT, PRIMARY KEY (fecha, ts, seq))""")
    con.execute("create index if not exists ix_tape_fecha on tape_und(fecha, ts)")
    con.commit()
    cols2 = [d[1] for d in con.execute("pragma table_info(tape_und)")]
    con.close()
    print("MIGRADA -> %s" % ",".join(cols2))
    return True


def validar():
    """Corrida en frío con DATOS REALES por la FUNCIÓN REAL (no un mock)."""
    if not os.path.exists(FUENTE):
        print("sin %s: no se puede validar con datos reales" % FUENTE)
        return False
    src = sqlite3.connect("file:%s?mode=ro" % FUENTE.replace("\\", "/"), uri=True)
    filas = list(src.execute(
        "select hora, last, size, bid, ask, agresor from tape "
        "where grupo='SPY' order by hora limit 5000"))
    src.close()
    if not filas:
        print("la fuente no tiene ticks de subyacente")
        return False

    # se construyen las tuplas EXACTAMENTE como las devuelve ibkr.tape_drenar()
    ticks = []
    for i, (hora, px, sz, bid, ask, agr) in enumerate(filas, 1):
        hh, mm, resto = hora.split(":")
        seg, _, ms = resto.partition(".")
        t = datetime.datetime(2026, 8, 13, int(hh), int(mm), int(seg), int((ms or "0").ljust(3, "0")) * 1000)
        sg = {"COMPRA": "C", "VENTA": "V", "MID": "N"}.get(agr, None)
        ticks.append((t, i, float(px), float(sz or 0), "TEST", bid, ask, sg))

    d = os.path.join(RAIZ, "investigacion", "2026-08-20_compresion_y_fills", "resultados")
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "_valida_tape.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    con = repo.abrir(tmp)
    n = CAP.guardar_tape(con, "2026-08-13", ticks)          # <-- FUNCIÓN REAL
    leidas = con.execute("select count(*) from tape_und").fetchone()[0]
    # ¿se conservan los campos?
    m = con.execute("select count(*) from tape_und where bid is not null and ask is not null").fetchone()[0]
    sg = dict(con.execute("select signo, count(*) from tape_und group by signo"))
    muestra = con.execute("select fecha,ts,seq,price,size,bid,ask,signo from tape_und "
                          "order by ts limit 3").fetchall()
    con.close()

    print("\n=== VALIDACIÓN con ticks REALES (2026-08-13, spy_history.tape grupo='SPY') ===")
    print("  ticks de entrada ......... %d" % len(ticks))
    print("  devueltos por guardar_tape %d" % n)
    print("  leídos de la tabla ....... %d" % leidas)
    print("  con bid/ask conservado ... %d" % m)
    print("  signos ................... %s" % sg)
    for r in muestra:
        print("     %s" % (r,))
    ok = (leidas == len(ticks))
    print("  PÉRDIDA .................. %d ticks  ->  %s"
          % (len(ticks) - leidas, "OK, cero pérdida" if ok else "¡HAY PÉRDIDA!"))

    # contraste: ¿cuántos se habrían perdido con la PK VIEJA?
    vistos = set()
    perd = 0
    for t in ticks:
        k = (t[0].strftime("%H:%M:%S"), t[2], t[3], t[4])   # (ts sin ms, price, size, exch)
        if k in vistos:
            perd += 1
        vistos.add(k)
    print("  con la PK VIEJA se habrían perdido %d de %d (%.1f%%)"
          % (perd, len(ticks), 100.0 * perd / len(ticks)))
    os.remove(tmp)
    return ok


if __name__ == "__main__":
    ok = migrar()
    if ok:
        ok = validar()
    print("\n%s" % ("VERDE: tape_und migrada y validada con datos reales" if ok
                    else "ROJO: revisar"))
    sys.exit(0 if ok else 1)
