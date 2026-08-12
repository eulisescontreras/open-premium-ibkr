# Prompt para el siguiente agente

Proyecto: `C:\Users\eulis\proyectos\open-premium-ibkr` (scalping de SPY por flujo de opciones)

## ANTES DE NADA, LEE EN ESTE ORDEN

1. `ANTI_COMPACT_CONTEXT.md` — estado vivo. Sección A y luego I-bis.
2. `investigacion/INVESTIGACION_OPEN_PREMIUM.md` — la investigación previa.
3. `investigacion/INVESTIGACION_M1_M2.md` — **NUEVO (2026-08-11 noche).** La sesión de
   M1/M2. Contiene lo descartado con la prueba de por qué. **No repitas nada de su §3.**

## ESTADO

- 2 sesiones: 2026-08-10 y 2026-08-11. `integrity_check` ok. 23.269 filas en `tape`,
  8 trades, **0 abiertos**.
- **Los dos días de la muestra BAJARON** (−0,36 y −2,73). No hay ni una sesión alcista.
  Esto contamina todo: los métodos que dicen DOWN casi siempre lucen bien por construcción.
- GAP D **arreglado pero NO activo** en ninguna de las 2 sesiones. Entra en el próximo arranque.
- El repo se hizo público temporalmente para compartir datos. Contiene logs, trades y
  `DU7154467` (paper). Sin llaves.

## LO QUE NO HAY QUE REHACER (medido, con la prueba en el documento)

- `premium_minute.net_prem` es un dato roto (99% discrepancia contra el tape).
- El premium BRUTO es direccionalmente ciego.
- Los acumulados `cum_*`/`day_*` correlacionan con el reloj.
- **Combinar SEÑAL+M1+M2:** las 256 reglas posibles, **0 aciertan los 7 giros**. Las tres
  son transformaciones de los mismos dos números; colapsan a 3 estados con contradicciones.
  **Más sesiones NO lo arreglan.**
- **Medir "acierto en los giros":** una media móvil de 30 min saca 100% sin usar opciones.
  El marco de evaluación es tautológico. Hace falta otro criterio.
- **El barrido de las 32 variables de `ta_minute`:** ganó `sma200` con p=0,015, y es un
  cronómetro (rho −0,982 con la hora) que además solo existe en 1 de los 2 días.
- **`open_interest`** para distinguir apertura de cierre: un valor por día, no sirve intradía.

## LO QUE SÍ QUEDÓ EN PIE

1. **Las reglas de cierre pesan más que la señal.** FLATTEN a las 15:45 vs aguantar al
   cierre = 36$ en un solo trade, y convierte M1 de −3$ a +33$ el 08-10 con las MISMAS señales.
2. **IV real de las 0DTE ATM: 5-7%**, no 13%. Un ATM cuesta ~1,00-1,30$. Calibrar SIEMPRE
   contra `premium_minute.mid` o contra los `entry_price` reales de `trades`;
   nunca asumir una IV.
3. **Spread real: 1,7% del mid** (mediana, 2.116 cotizaciones 0DTE).
4. El único aviso anticipado real encontrado: **cruce de M1/M2 durante zona de convergencia
   del marcador** (10:25 del 08-10, 22 min antes del techo). n=1.

## SIGUIENTE PASO, POR ORDEN

1. **Los 40 contratos de la BANDA en `_on_ticks`.** Toca el hilo de la GUI ⇒ corrida en frío
   DIFERENCIAL obligatoria (patrón: `coldruns/gapD_coldrun.py`).
   **REQUIERE AUTORIZACIÓN EXPLÍCITA DEL USUARIO antes de tocar `spy_direction.py`.**
2. **Acumulador con VENTANA MÓVIL (15/30 min)** como script read-only en `analisis/`.
   El acumulador actual solo suma: no puede girar. A partir de las 13:00 del 08-10 las
   curvas de M1 y M2 son rampas rectas mientras el SPY sube, baja, sube y baja.
3. **Loguear M1/M2 en paralelo SIN operar con ellos.** El usuario pidió cambiar el
   disparador de flips a M1; **se le explicó por qué no está justificado todavía**
   (56% con IC95% [37%,72%], indistinguible de "siempre DOWN" = 52%; todo el resultado
   positivo son 2 trades en 2 días bajistas). Si insiste, que sea decisión suya informada,
   con backup + cold run diferencial + `trading OFF` primero.
4. Esperar una **sesión alcista** antes de concluir nada.

## CÓMO TRABAJA ESTE USUARIO (crítico)

- **Exige honestidad total.** No des un número sin haberlo ejecutado. Lo que no midas,
  márcalo como HIPÓTESIS.
- **Tiene buen olfato para los números que no cuadran.** En esta sesión detectó dos errores
  reales del agente: una IV asumida 2× la real, y un cierre de simulación fuera de las reglas
  del sistema. Corregirlos movió el resultado 200$. **Si dice que algo no tiene sentido,
  párate y verifica antes de defenderlo.**
- Escribe en mensajes cortos y fragmentados: une todas las partes antes de actuar.
- **NO reiniciar la app ni hacer push sin autorización explícita.** Antes de cada reinicio:
  backup de la BD + cold run diferencial + cerrar el trade abierto SIN inventar precio de
  salida (exit_price/profit/pct a NULL).
- La salida de los comandos NO le llega completa: si es larga, escríbela a un fichero en
  `investigacion\` y dale la RUTA COMPLETA.
- Las 16 reglas de `C:\Users\eulis\CLAUDE.md` aplican.

Pregunta al usuario por dónde quiere seguir.
