# PRE-REGISTRO — Barrido de exploración direccional del SPY (255 sesiones)

Diseño acordado entre los dos agentes (chat + agente PC) ANTES de correr nada.
Fecha: 2026-08-12. Datos: `historico_spy.db / bars_historico`, 255 sesiones (2025-08-07 a 2026-08-12).

## Objetivo
No hacer rentable el sistema — averiguar si existe una VENTAJA DIRECCIONAL explotable en el SPY
sobre la que operar 0DTE. Toda regla se mide contra el listón estructural de la opción.

## Split (INTOCABLE)
- EXPLORACION: primeras 170 sesiones (por fecha).
- RESERVA: últimas 85 sesiones. NO se miran ni se consultan hasta congelar una regla por escrito.

## (d) Métrica de éxito (única)
```
EV_por_op ($) = 85 * media(fav_con_signo)  - 2.22
```
- `fav` = movimiento a favor en PUNTOS de SPY, con signo (+ si fue hacia donde decía la señal).
- 85 $/punto = delta realizado medido con ITM3 y tope 320$. 2.22 = comisión (1.72) + theta 8min (0.50).
- Umbral de equilibrio: `media(fav) >= 0.026` puntos.
- SIEMPRE reportar `media(fav)` en crudo además del EV (para reevaluar si cambian los costes).
- Aviso: si cambia el capital/tope, el 85 $/punto se recalcula.

## (a) Barrido — CERRADO y pre-registrado (nada de exploración abierta)
- **F1 Reversión** (línea base, ya muerta a 8min = calibración): ref SMA(3,5,8,13,21) del precio típico;
  umbral {0.10,0.15,0.20,0.25,0.30,0.40}; horizonte {3,5,8,12,20,30}.
- **F2 Continuación**: mismo grid, señal invertida.
- **F3 Reversión condicionada por volatilidad**: misma reversión, solo cuando el rango de los últimos
  15 min está en el tercil alto/medio/bajo DEL DÍA (relativo al día, no absoluto = evita medir el reloj).
- **F4 Acuerdo multi-escala**: operar solo cuando la desviación vs SMA5 y vs SMA21 apuntan al mismo lado.
- **F5 Estructura de sesión** (lo genuinamente nuevo): hueco de apertura (close ayer→open hoy);
  rango de los primeros 30 min; día de la semana.
- Contar el total de celdas ANTES de correr y escribir en la cabecera del informe los FP esperados al 5%.

## (b) Controles (en orden; cada uno mata antes de pasar al siguiente)
1. **Cronómetro** sobre la variable condicionante: `|rho(var, minuto_del_día)| >= 0.30` → fuera (F3,F5 en riesgo).
2. **Región, no celda**: candidata solo si sus vecinas (umbral ±1 paso, horizonte ±1 paso) también pasan.
3. **T2** sobre las 5 MEJORES sesiones (no solo la mejor).
4. **Nula por desplazamiento circular**, 200 desplazamientos, mirar la MEDIANA.
5. **Control de azar** con la MISMA exposición, 300 semillas, mismo nº de entradas por sesión.
6. **Estabilidad temporal**: partir las 170 en 4 bloques cronológicos; positiva en ≥3 de 4. (El más severo.)

## (c) Criterio EXACTO de congelación (las 6, sin negociación)
1. `EV >= +0.50 $/op` en las 170 de exploración.
2. `media(fav) >= 0.032` puntos (equilibrio 0.026 + 25% de colchón).
3. `>= 800` operaciones en exploración.
4. Región: las 4 celdas vecinas (umbral ±1, horizonte ±1) con `EV > 0`.
5. Positiva en `>= 3 de 4` bloques cronológicos.
6. `p <= 0.01` en el control de azar con misma exposición.

Protocolo: escribir `investigacion/REGLA_CONGELADA_<fecha>.md` con parámetros exactos, commit del
código y EV esperado → commit → correr UNA vez sobre las 85 de reserva.
- Reserva EV positivo con ≥400 ops → real, se puede llevar a paper.
- Negativo → se descarta y NO se reajusta.
- Si ninguna regla pasa el filtro → ese es el resultado y se reporta tal cual (es lo más probable).

## Salida estructural (radar, no hoy)
El listón 56.7% viene del pago asimétrico de comprar opciones, no de la señal. Palancas para bajarlo:
capital (320→800$ lo baja a 54.4%) y profundidad del contrato. Si el barrido encuentra algo entre
52% y 56%, la pregunta pasa de "predecir mejor" a "bajar el listón" (aritmética, no estadística).
