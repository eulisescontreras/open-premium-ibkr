# -*- coding: utf-8 -*-
"""MIGRACIÓN: pasa a hora de NUEVA YORK los ticks de `tape_und` que se guardaron en UTC.

POR QUÉ: el 2026-08-21, primer día de captura de tape, `captura.guardar_tape` hacía `strftime`
directo sobre el instante que entrega `ib_insync`, que viene en UTC. El resto del sistema
(`bars.hora`, `premium.hora`) usa ET, así que el tape no habría cuadrado al cruzarlo con las
velas — que es justo para lo que se captura. Los precios, tamaños y signos eran CORRECTOS: solo
el reloj estaba adelantado. Corregido en `captura._hora_et`.

Detecta los ticks a migrar por la hora: un tick del SPY nunca ocurre a las 12:00-20:00 ET
(el mercado cierra a las 16:00 y el premarket empieza a las 04:00), pero en UTC toda la sesión
cae justo en esa franja. Es idempotente: los ya migrados quedan fuera del rango y no se tocan.

Usa `zoneinfo`, NO un offset fijo: el desfase es -4 en verano y -5 en invierno.
"""
import os, sys, sqlite3, datetime
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(RAIZ, "sys2.db")
_ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc


def migrar(db=DB, fecha=None):
    con = sqlite3.connect(db)
    q = "select rowid, fecha, ts from tape_und"
    par = ()
    if fecha:
        q += " where fecha=?"
        par = (fecha,)
    filas = list(con.execute(q, par))
    if not filas:
        print("tape_und vacía: nada que migrar")
        con.close()
        return 0
    cambios = []
    ya = 0
    for rid, fk, ts in filas:
        hh = int(ts[:2])
        if not (11 <= hh <= 23):        # rango imposible en ET para el SPY -> está en UTC
            ya += 1
            continue
        d = datetime.datetime(int(fk[:4]), int(fk[5:7]), int(fk[8:10]),
                              hh, int(ts[3:5]), int(ts[6:8]),
                              int(ts[9:12]) * 1000 if len(ts) > 9 else 0, tzinfo=UTC)
        e = d.astimezone(_ET)
        cambios.append((e.strftime("%H:%M:%S.") + ("%03d" % (e.microsecond // 1000)), rid))
    print("ticks totales %d | ya en ET %d | a migrar %d" % (len(filas), ya, len(cambios)))
    if cambios:
        con.executemany("update tape_und set ts=? where rowid=?", cambios)
        con.commit()
    r = con.execute("select min(ts), max(ts), count(*) from tape_und").fetchone()
    print("rango tras migrar: %s .. %s  (%d ticks)" % r)
    con.close()
    return len(cambios)


if __name__ == "__main__":
    n = migrar(fecha=sys.argv[1] if len(sys.argv) > 1 else None)
    print("\nVERDE: %d ticks pasados a hora de Nueva York" % n)
