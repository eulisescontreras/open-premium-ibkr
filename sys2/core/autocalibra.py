# -*- coding: utf-8 -*-
"""AUTOCALIBRACIÓN POR NIVEL DE CAPITAL (MANUAL §13). El sistema elige su configuración al
arrancar cada sesión leyendo el SALDO REAL de la cuenta — NO lo decide el usuario.

Dos principios (§13.1): (1) el PEOR DÍA nunca supera el 35% de la cuenta; (2) TOPE DURO de 3
contratos (objetivo 5-8.000$/mes, no crecer sin límite). A partir de 5.400$ el sistema no crece.

Tabla VERBATIM del MANUAL §13.1 (cuenta, modo, ancho, tope$, unidades). Se elige el nivel más
alto cuyo `cuenta` <= saldo. OBLIGATORIO: antes de modificar, leer §13 y correr cr_autocalibra.py.
"""

# (cuenta_min, modo, ancho_pts, tope$, unidades)
TABLA = [
    (200, "vertical", 2, 35, 1),
    (250, "vertical", 2, 45, 1),
    (300, "vertical", 2, 55, 1),
    (400, "vertical", 2, 75, 1),
    (500, "vertical", 2, 90, 1),
    (600, "vertical", 2, 110, 1),
    (800, "vertical", 3, 140, 1),
    (1000, "vertical", 3, 175, 1),
    (1200, "vertical", 3, 210, 1),
    (1400, "vertical", 4, 250, 1),
    (1800, "vertical", 4, 320, 1),
    (2800, "vertical", 4, 320, 1),
    (3600, "vertical", 4, 320, 2),
    (4500, "vertical", 4, 320, 2),
    (5400, "vertical", 4, 320, 3),   # ← TOPE (a partir de aquí no crece)
    (8000, "vertical", 4, 320, 3),
    (12000, "vertical", 4, 320, 3),
    (20000, "vertical", 4, 320, 3),
]

TOPE_UNIDADES = 3            # tope duro de contratos
LIMITE_PEOR_DIA = 0.35       # el peor día no supera el 35% de la cuenta


def configuracion(saldo):
    """Devuelve la config para un saldo: dict(nivel, modo, ancho, tope, unidades).
    Si saldo < 200 -> None (no operar). unidades nunca supera TOPE_UNIDADES."""
    if saldo is None or saldo < TABLA[0][0]:
        return None
    elegido = TABLA[0]
    for fila in TABLA:
        if saldo >= fila[0]:
            elegido = fila
        else:
            break
    cuenta, modo, ancho, tope, unid = elegido
    return {
        "nivel": cuenta,
        "modo": modo,
        "ancho": float(ancho),
        "tope": float(tope),
        "unidades": min(unid, TOPE_UNIDADES),
        "saldo": saldo,
    }
