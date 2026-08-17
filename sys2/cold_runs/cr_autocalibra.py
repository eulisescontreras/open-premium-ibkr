# -*- coding: utf-8 -*-
"""COLD RUN de core/autocalibra.configuracion — reproduce la tabla §13.1 del MANUAL, respeta el
tope duro de 3 contratos y el arranque/tope. Exit 0 = verde."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from sys2.core import autocalibra as A

# saldo -> (ancho, tope, unidades) esperados (MANUAL §13.1)
ESPERADO = {
    200: (2, 35, 1), 400: (2, 75, 1), 600: (2, 110, 1), 800: (3, 140, 1),
    1200: (3, 210, 1), 1400: (4, 250, 1), 1800: (4, 320, 1), 2800: (4, 320, 1),
    3600: (4, 320, 2), 4500: (4, 320, 2), 5400: (4, 320, 3), 8000: (4, 320, 3),
    20000: (4, 320, 3),
}


def main():
    fallos = []
    for saldo, (an, to, un) in ESPERADO.items():
        c = A.configuracion(saldo)
        if c is None:
            fallos.append("saldo %d -> None (esperado)" % saldo); continue
        if (c["ancho"], c["tope"], c["unidades"]) != (an, to, un):
            fallos.append("saldo %d -> (%s,%s,%s) != (%s,%s,%s)"
                          % (saldo, c["ancho"], c["tope"], c["unidades"], an, to, un))
    # arranque: saldo < 200 -> None
    if A.configuracion(150) is not None or A.configuracion(0) is not None:
        fallos.append("saldo < 200 debería dar None")
    # interpolación: 700 usa el tramo de cuenta 600 (no el 800)
    if A.configuracion(700)["cuenta"] != 600:
        fallos.append("saldo 700 debería usar el tramo de cuenta 600")
    # meta y version presentes (para el panel)
    c5 = A.configuracion(5400)
    if c5.get("meta") != 8053 or c5.get("version") != "v4":
        fallos.append("saldo 5400 -> meta/version incorrectos: %s/%s" % (c5.get("meta"), c5.get("version")))
    # tope duro: ninguna config supera 3 unidades
    for saldo in (5400, 8000, 12000, 20000, 100000):
        if A.configuracion(saldo)["unidades"] > A.TOPE_UNIDADES:
            fallos.append("saldo %d supera el tope de %d contratos" % (saldo, A.TOPE_UNIDADES))

    if fallos:
        print("ROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("VERDE: autocalibra reproduce la tabla §13.1, arranque y tope de 3 contratos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
