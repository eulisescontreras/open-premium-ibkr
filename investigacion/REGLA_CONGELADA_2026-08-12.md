# REGLA CONGELADA — 2026-08-12

Congelada ANTES de tocar la reserva, según el protocolo de `PREREGISTRO_BARRIDO_SPY.md`.

## Regla (parámetros EXACTOS)
- Familia: **F3 — reversión condicionada por volatilidad**
- Condición: rango de los últimos 15 min en el **tercil ALTO del día**
- Ventana media: **W = 5** (SMA(5) del precio típico (H+L+C)/3)
- Umbral: **u = 0.40** puntos (|close − media| ≥ 0.40)
- Horizonte: **H = 8** minutos
- Lado: reversión (precio ARRIBA de la media → PUT; ABAJO → CALL)
- Entrada no solapada, retraso 1 minuto.

## Resultado en EXPLORACIÓN (170 sesiones, 2025-08-07 a 2026-04-10)
- n_ops = 1560, acierto 52.2%, media_fav = +0.0553 pts, **EV = +2.48 $/op**, estabilidad 3/4 bloques, p_azar = 0.0067.

## Provenance
- Código: commit `19fced4457f25550e89d2e8cb016f10661bfd83f` (rama main).
- Motor: `analisis/barrido_exploracion.py` (calibrado: reproduce la media, EV −1.20 vs −1.18 esperado).

## ADVERTENCIAS (honestidad — el prior es que es FALSO POSITIVO)
1. **Multiplicidad**: superviviente único entre ~940 celdas a p=0.0067. FP esperados a p≤0.01 ≈ 9.
   Tras corrección por multiplicidad NO es significativa por sí sola.
2. **Cronómetro borderline**: rho(rango15, minuto_del_día) = −0.291 (umbral 0.30). Los minutos
   "tercil alto" caen 66% en las primeras 2.5 h → la condición es en parte un selector de mañana.
3. Acierto solo 52.2%; estabilidad 3/4 (no 4/4).

## Criterio de la reserva (una sola pasada, sin reajustar)
- Sesiones 171..255 (85, INTOCADAS).
- SOBREVIVE si EV > 0 con ≥ 400 operaciones → candidata real, puede ir a paper.
- NO sobrevive → se descarta y NO se reajusta. Ese es el valor del ejercicio.
