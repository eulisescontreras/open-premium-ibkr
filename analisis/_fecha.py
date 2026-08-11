# -*- coding: utf-8 -*-
"""Fecha de analisis compartida por todos los scripts de `analisis/`.

POR QUE EXISTE (2026-08-11): los 9 scripts tenian `F = "2026-08-10"` escrito a mano. El
2026-08-11, con el mercado abierto, se corrio `auditoria_datos.py` para revisar los datos DE HOY
y devolvio tan campante el informe DE AYER: 323 minutos de TA, 7 huecos, 6 reinicios... todo
correcto y todo del dia equivocado. Solo se detecto porque el hueco 13:24->14:00 era la firma
del GAP 17 del dia anterior.

Un script de analisis que analiza silenciosamente la fecha equivocada es peor que uno que falla:
el que falla se ve.

USO:
    python analisis\\auditoria_datos.py              -> ultima fecha CON DATOS en la BD
    python analisis\\auditoria_datos.py 2026-08-10   -> esa fecha
    python analisis\\auditoria_datos.py ayer         -> la penultima fecha con datos

El defecto es "la ultima fecha con datos" y NO "hoy" a proposito: asi sirve tambien en fin de
semana, de madrugada o antes de la apertura, cuando `hoy` no tiene ni una fila.

SIEMPRE imprime la fecha que va a usar. Ese es el punto: que sea imposible confundirse otra vez.
"""
import os
import sqlite3
import sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "spy_history.db")


def _fechas_con_datos():
    """Fechas presentes en la BD, de la mas reciente a la mas antigua.
    Se mira ta_minute y tambien premium_minute: un dia puede tener premium sin TA (GAP 21),
    y ese dia SI es analizable."""
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
        fs = [r[0] for r in c.execute(
            "SELECT fecha FROM ("
            "  SELECT DISTINCT fecha FROM ta_minute"
            "  UNION SELECT DISTINCT fecha FROM premium_minute"
            ") ORDER BY fecha DESC")]
        c.close()
        return fs
    except Exception as e:
        print(f"AVISO: no se pudo leer la BD ({e})")
        return []


def fecha_analisis(argv=None):
    """Devuelve la fecha a analizar y la ANUNCIA. Aborta si no hay datos de esa fecha."""
    argv = sys.argv[1:] if argv is None else argv
    fechas = _fechas_con_datos()
    pedida = argv[0].strip() if argv and argv[0].strip() else None

    if pedida in ("ayer", "anterior", "-1"):
        if len(fechas) < 2:
            print(f"ERROR: se pidio 'ayer' pero la BD solo tiene {len(fechas)} fecha(s): {fechas}")
            sys.exit(2)
        f = fechas[1]
    elif pedida:
        f = pedida
        if fechas and f not in fechas:
            print(f"ERROR: no hay datos de {f}. Fechas disponibles: {', '.join(fechas[:10])}")
            sys.exit(2)
    else:
        if not fechas:
            print("ERROR: la BD no tiene datos de ninguna fecha")
            sys.exit(2)
        f = fechas[0]

    otras = [x for x in fechas if x != f]
    print(f"=== ANALIZANDO {f} ===" +
          (f"   (otras fechas en la BD: {', '.join(otras[:6])}"
           f"{'...' if len(otras) > 6 else ''})" if otras else "   (unica fecha en la BD)"))
    print(f"    para otra fecha:  python {os.path.join('analisis', os.path.basename(sys.argv[0]))} "
          f"AAAA-MM-DD   |   'ayer' = la anterior")
    print()
    return f
