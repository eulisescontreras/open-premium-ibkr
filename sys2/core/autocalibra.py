# -*- coding: utf-8 -*-
"""AUTOCALIBRACIÓN POR NIVEL DE CAPITAL (MANUAL §13). El sistema elige su configuración al
arrancar cada sesión leyendo el SALDO REAL de la cuenta — NO lo decide el usuario.

Dos principios (§13.1): (1) el PEOR DÍA nunca supera el 35% de la cuenta; (2) TOPE DURO de 3
contratos (objetivo 5-8.000$/mes, no crecer sin límite). A partir de 5.400$ el sistema no crece.

Tabla VERBATIM del MANUAL §13.1 (cuenta, modo, ancho, tope$, unidades). Se elige el nivel más
alto cuyo `cuenta` <= saldo. OBLIGATORIO: antes de modificar, leer §13 y correr cr_autocalibra.py.
"""

# (cuenta_min, modo, ancho_pts, tope$, unidades, meta$/mes)  — meta = columna "al mes" del §13.1
TABLA = [
    (200, "vertical", 2, 35, 1, 225),
    (250, "vertical", 2, 45, 1, 289),
    (300, "vertical", 2, 55, 1, 353),
    (400, "vertical", 2, 75, 1, 481),
    (500, "vertical", 2, 90, 1, 578),
    (600, "vertical", 2, 110, 1, 706),
    (800, "vertical", 3, 140, 1, 1041),
    (1000, "vertical", 3, 175, 1, 1301),
    (1200, "vertical", 3, 210, 1, 1561),
    (1400, "vertical", 4, 250, 1, 2097),
    (1800, "vertical", 4, 320, 1, 2684),
    (2800, "vertical", 4, 320, 1, 2684),
    (3600, "vertical", 4, 320, 2, 5369),
    (4500, "vertical", 4, 320, 2, 5369),
    (5400, "vertical", 4, 320, 3, 8053),   # ← TOPE (a partir de aquí no crece)
    (8000, "vertical", 4, 320, 3, 8053),
    (12000, "vertical", 4, 320, 3, 8053),
    (20000, "vertical", 4, 320, 3, 8053),
]

TOPE_UNIDADES = 3            # tope duro de contratos
LIMITE_PEOR_DIA = 0.35       # el peor día no supera el 35% de la cuenta


def sizing(saldo):
    """SIZING POR FRACCIÓN DEL SALDO (2026-08-19). Sustituye a `configuracion` cuando
    C.SIZING_FRAC está activo. Devuelve dict(tope, ancho, unidades) o None (= NO OPERAR).

    POR QUÉ SUSTITUYE A LA TABLA: la TABLA BAJA DE NIVEL al perder, y con tope 75$ no cabe
    NINGÚN vertical (cuestan 88-135$) -> el sistema se AUTOAPAGA. Medido con 600$: la tabla
    opera 6 días de 485 y muere; esto opera 465 y llega a 83.805$.

    REGLA DE SUPERVIVENCIA (`SIZING_KSUP`): si el saldo no cubre K veces el suelo, NO se opera.
    Sin ella, con 200$ el sistema seguía arriesgando 140$ (el 70% de lo que queda) y la cuenta
    llegaba a NEGATIVO. Medido: riesgo de ruina 33% -> 0%, y NO cuesta profit (los arranques
    sanos dan el mismo número al céntimo, porque la regla solo actúa camino de la ruina).
    ⚠️ Fija el CAPITAL MÍNIMO: KSUP × SUELO = 3,5 × 140 = 490$. Con 450$ el sistema NO ARRANCA.
    ⚠️ NO bajar el suelo para poder empezar con menos: con suelo 110 la cuenta muere en todos
    los capitales probados (entra, pierde una vez y queda bloqueada bajo el umbral)."""
    from sys2 import config as C
    if saldo is None or not C.SIZING_FRAC:
        return None
    suelo = C.SIZING_SUELO
    if C.SIZING_KSUP and saldo < C.SIZING_KSUP * suelo:
        return None                      # la cuenta no soporta ni la operación mínima
    tope = max(saldo * C.SIZING_FRAC, suelo)
    if tope > saldo:
        return None
    # el ancho manda sobre la cobertura: con ancho 2 el ITM profundo cuesta ~200$ y NO CABE en
    # topes pequeños -> "sin_contrato". Medido: ancho 2 -> 1 operación en 485 días; ancho 4 -> 465.
    ancho = 2.0 if tope < 140 else (3.0 if tope < 250 else 4.0)
    unid = 1 if saldo < 3600 else (2 if saldo < 5400 else 3)
    return {"tope": float(tope), "ancho": ancho, "unidades": min(unid, TOPE_UNIDADES)}


def configuracion(saldo):
    """Devuelve la config para un saldo: dict(nivel, modo, ancho, tope, unidades).
    Si saldo < 200 -> None (no operar). unidades nunca supera TOPE_UNIDADES."""
    if saldo is None or saldo < TABLA[0][0]:
        return None
    elegido = TABLA[0]
    idx = 0
    for i, fila in enumerate(TABLA):
        if saldo >= fila[0]:
            elegido = fila
            idx = i
        else:
            break
    cuenta, modo, ancho, tope, unid, meta = elegido
    return {
        "nivel": idx + 1,               # 1..len(TABLA) (para el panel: "NIVEL N")
        "cuenta": cuenta,               # umbral de la cuenta de ese nivel
        "modo": modo,
        "version": "v%d" % ancho,       # v2 / v3 / v4 (según el ancho)
        "ancho": float(ancho),
        "tope": float(tope),
        "unidades": min(unid, TOPE_UNIDADES),
        "meta": meta,
        "saldo": saldo,
    }
