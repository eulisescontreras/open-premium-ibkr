# RESUMEN — ¿Se puede predecir la dirección del SPY con precio/TA? (2026-08-12)

Investigación sobre 255 sesiones de SPY 1-min (2025-08-07 a 2026-08-12), bajadas de IBKR a
`historico_spy.db` (bars_historico + ta_historico reconstruido byte-fiel del bot). Método:
exploración (170) / reserva (85) fuera de muestra, métrica EV_op = 85*media_fav − 2.22,
listón de equilibrio 56.7% (capital 320) / 54.4% (capital 800).

## Todo lo PROBADO y DESCARTADO (con evidencia)
| Vía | Script | Resultado |
|---|---|---|
| Reversión a la media (SMA5 "vwap") | valida_media.py | 50.07% acierto, asim 1.05, EV −1.20 → pierde |
| ~940 reglas geométricas (F1..F5) | barrido_exploracion.py | plana ~50%; única candidata murió en reserva (EV +2.48→−3.79) |
| RSI/MACD/EMA-cross/Bollinger (55) | barrido_ta.py | ~50%, ninguna pasa las 6 condiciones |
| Analogía día-a-día (k-NN camino) | analog_dias.py | no bate la deriva (~54%); mejor celda = ruido a 1 SE |
| Figuras bandera/canal (k-NN forma, 27) | patrones_intradia.py | reserva ~50%, EV negativo en TODAS |
| Deriva del SPY (siempre CALL) | deriva_liston.py | 50.6% a 8min; 54-56.6% solo a 1-4 HORAS |

## Conclusión (VERIFICADO, 255 sesiones)
Nada basado en precio/TA predice la dirección del SPY a 8 min lo bastante para ganar con 0DTE.
Mercado eficiente/líquido. La vía "predecir con TA" queda CERRADA.

La deriva alcista es real pero solo a horas (no al horizonte 0DTE de 8 min) y su P&L de opción a
horas NO es modelable sin histórico de primas (que no existe).

## ACTUALIZACIÓN — Gate del híbrido M1/M2-dirección + TA-timing (oráculo)
Test `analisis/oraculo_timing.py` (255 ses, reserva OOS, `investigacion/oraculo_timing.txt`):
DADA la dirección PERFECTA del día (oráculo=cota superior), el TA-timing (reversión a la media)
SÍ aporta: (i) dirección sola EV +7.11 (57.1%); (iii) TA+dirección EV **+10.07 (58.9%)**, región
robusta (umbral 0.10-0.40 → EV +8.9..+10.6). (ii) TA sin dirección −1.25 (muerto).
CONCLUSIÓN: la arquitectura híbrida es VIABLE EN TEORÍA — el TA cronometra bien SI tiene la
dirección correcta. El cuello único pasa a ser: ¿puede M1/M2 (flujo) dar la dirección del DÍA?
NO verificable con histórico (flujo = 3 días, todos DOWN, n=3 nulo) → solo test FORWARD.

## Lo ÚNICO sin refutar
El FLUJO/TAPE de opciones (apuesta original: dónde entra el dinero, no el precio). NO backfilleable
(no hay histórico); solo se valida acumulando sesiones en vivo con la captura ya existente
(tape, premium_minute, walls_snapshot).

## Datos/artefactos
- `historico_spy.db`: bars_historico (255 ses), ta_historico (254 ses, byte-fiel a prod).
- Informes en `investigacion/`: PREREGISTRO_BARRIDO_SPY, barrido_exploracion, REGLA_CONGELADA_2026-08-12,
  reserva_resultado, barrido_ta, analog_dias, patrones_intradia, deriva_liston.
- Motor calibrado (reproduce la media exacta): analisis/barrido_exploracion.py.
