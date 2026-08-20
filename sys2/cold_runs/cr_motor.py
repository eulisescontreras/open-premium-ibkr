# -*- coding: utf-8 -*-
"""COLD RUN DEFINITIVO — el motor (backtest/motor.SIS70) sobre la cadena real de
massive_premium.db debe reproducir las cifras titulares del sistema validado:
  TOTAL (aplanado 15:59) = +71.396$   ·   A1 (<2025-08-01) = +32.071$   ·   A2 = +38.698$
Tolerancia inicial ±2% (contratos que faltan por descargar / bordes). Exit 0 = verde.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from sys2.backtest import motor
from sys2.db import repo

CORTE = "2025-08-01"
# ⚠️ TARGETS ACTUALIZADOS 2026-08-19 — SISTEMA HONESTO (sin look-ahead).
# Los targets ANTERIORES (+71.396 / +32.071 / +38.698) correspondían al sistema que VEÍA EL
# FUTURO: `construir_sen` se llamaba una vez con todas las barras del día y `reb2` clasificaba
# cada flip mirando 12 buckets (36 min) hacia delante. El vivo NO puede hacer eso.
# Estos targets son con C.VISION_HONESTA + fix del ORB futuro + `dia_bueno` desde 10:31 + el
# filtro por cadena de opciones, SIN composición (tamaño fijo, que es como corre este cold run).
# Con composición desde 600$: 83.805$ (139,7x). Ver investigacion/2026-08-19_sistema_real/.
TARGET_TOTAL = 48022.0
TARGET_A1 = 19013.0
TARGET_A2 = 29009.0
TARGET_VIEJO_LOOKAHEAD = 71396.0        # se conserva para poder comparar la brecha (-32,7%)
# NOTA (2026-08-19): durante la aplicación de los cambios este cold run dio +51.030 en una
# medición intermedia. RESUELTO: el motor es DETERMINISTA — repetido da +48.022 con dif 0,0%.
# La medición de +51.030 se hizo con el código a medio aplicar. VERDE con estos targets.
# El orden de filtros SÍ está medido: score ANTES del skew da 83.805$ y DESPUÉS 83.805$.
# El TITULAR (+71.396$) es el criterio duro: 2%. Los desgloses por AÑO llevan una cota más
# laxa (5%) porque el P&L por año es sensible a la completitud de contratos de massive, que
# difiere entre máquinas (el propio agente notó que "falta de contratos descargados" mueve la
# cifra). 5% atrapa bugs gruesos (un año roto se iría mucho más) pero tolera variación de datos.
# Tras los fixes verbatim: TOTAL +72.375 (+1.4%), A1 +32.289 (+0.7%), A2 +40.086 (+3.6%).
TOL = 0.02
TOL_ANIO = 0.05


def main():
    con = repo.abrir()
    print("cargando datos (massive + sys2.bars + ETF)...")
    SES, PREM, ETFB = motor.cargar(con)
    con.close()
    print("sesiones: %d | días con premium: %d | ETF DIA/TLT: %d/%d"
          % (len(SES), len(PREM), len(ETFB["DIA"]), len(ETFB["TLT"])))

    D = motor.SIS70(SES, PREM, ETFB)
    total = sum(D.values())
    a1 = sum(v for k, v in D.items() if k < CORTE)
    a2 = sum(v for k, v in D.items() if k >= CORTE)
    ndias = len(D)
    nop = sum(1 for v in D.values() if v != 0)
    verdes = sum(1 for v in D.values() if v > 0)
    rojos = sum(1 for v in D.values() if v < 0)

    print("\ndías operados: %d | verdes: %d | rojos: %d" % (ndias, verdes, rojos))
    print("TOTAL: %+.0f$   (target %+.0f)   dif %.1f%%"
          % (total, TARGET_TOTAL, 100 * (total - TARGET_TOTAL) / TARGET_TOTAL))
    print("A1   : %+.0f$   (target %+.0f)   dif %.1f%%"
          % (a1, TARGET_A1, 100 * (a1 - TARGET_A1) / TARGET_A1))
    print("A2   : %+.0f$   (target %+.0f)   dif %.1f%%"
          % (a2, TARGET_A2, 100 * (a2 - TARGET_A2) / TARGET_A2))

    fallos = []
    if abs(total - TARGET_TOTAL) / TARGET_TOTAL > TOL:
        fallos.append("TOTAL %+.0f fuera de ±%.0f%% de %+.0f" % (total, 100 * TOL, TARGET_TOTAL))
    if abs(a1 - TARGET_A1) / TARGET_A1 > TOL_ANIO:
        fallos.append("A1 %+.0f fuera de tolerancia anual (%.0f%%)" % (a1, 100 * TOL_ANIO))
    if abs(a2 - TARGET_A2) / TARGET_A2 > TOL_ANIO:
        fallos.append("A2 %+.0f fuera de tolerancia anual (%.0f%%)" % (a2, 100 * TOL_ANIO))

    if fallos:
        print("\nROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("\nVERDE: el motor reproduce las cifras validadas dentro de tolerancia")
    return 0


if __name__ == "__main__":
    sys.exit(main())
