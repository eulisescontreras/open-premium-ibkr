# SISTEMA 0DTE SPY — INVESTIGACIÓN COMPLETA (Supertrend momentum)
> Documento maestro. Fecha: 2026-08-14.

> # 🚨🚨 CRÍTICO — LEER PRIMERO (hallazgo 2026-08-14): EL "VALIDADO" ERA LOOK-AHEAD
> **El resultado titular (+$11-12k/año en 2 años OOS) está INVALIDADO.** El backtest entra
> en la ETIQUETA del bucket de 2-min (su minuto de INICIO, ej. "09:50") usando el precio de
> ese minuto, PERO el flip del ST 2-min recién se confirma con el cierre del bucket (final
> de 09:51, se sabe a las 09:52). → **el sistema compraba 2 minutos hacia el futuro**; ese
> impulso de 2-min "gratis" ERA todo el edge.
> **Corrida diferencial con timing REALISTA (entrar cuando la vela de 2-min ya cerró):**
> el sistema pasa a **NEGATIVO en AMBOS años** (año1 +16.075→−7.626, año2 +11.575→−9.455;
> %verde 62%→31%). Ningún skip (hasta 11:00) ni +1min lo rescata. Evidencia:
> `analisis/exp_timing_realista.py` y `analisis/exp_timing_skip.py`.
> **ESTADO REAL: la estrategia tal como está especificada NO es rentable con timing ejecutable.**
> Todo lo de abajo (config, sizing, días malos, premium sintético) describe el sistema CON
> look-ahead y queda SUPEDITADO a este hallazgo. Antes de retomar: rediseñar el timing de
> entrada a algo ejecutable y RE-VALIDAR desde cero. La reproducción de referencia (+524.40)
> sigue dando igual porque es un replay de señales manuales fijas, NO la validación OOS.

---

## 0. RESUMEN EN 30 SEGUNDOS

Sistema de **momentum 0DTE sobre SPY**: el **Supertrend(7, 3.0) en velas de 2-min** (con premarket) genera señales de dirección (CALL/PUT); se compra la **opción 0DTE ITM más profunda que quepa en el capital**; se sale por **trailing 0.04% sobre el precio del SPY** o al cierre. **NO usa el tape ni la magnitud** (se probó y no ayuda). Premium **sintético** (modelo intrínseco+extrínseco) porque no hay histórico real de opciones.

**Resultado validado (bid/ask, premium sintético, por 1 contrato):**
| | Año1 (2025-07→2026-08, tune) | Año2 (2024-07→2025-07, OOS) |
|---|---|---|
| Total | +$15.761 | +$11.273 |
| % días verdes | 63% | 61% |
| Días malos (suma) | −$4.975 | −$5.469 |
| Peor día | −$220 | −$167 |

**El edge base (~+$11-12k/año/contrato, ~60% días verdes, ratio win/loss ~2.2) se REPLICA en 2 años independientes → es REAL, no overfitting.**

---

## 1. CONFIG FINAL (los parámetros que SÍ funcionan)

```
SEÑAL:      Supertrend(period=7, multiplier=3.0) sobre velas de 2-min
            (velas 1-min agregadas a 2-min, CON premarket para calentar el ATR)
            Entra en cada flip: CALL si tendencia=+1, PUT si -1.
            Lógica "señal pendiente": si el ST gira estando DENTRO, se guarda y entra al salir.
TIMEFRAME:  2-min (1-min = whipsaw puro y peor; >4-min pierde tendencias)
TRAIL:      0.04% del precio del SPY (sobre el cierre de la vela). [baseline histórico era 0.10%]
SKIP APERTURA: NO entrar antes de 09:45 ET (hora_min="09:45") — mata el whipsaw de apertura.
STOP_NEW:   NO abrir nuevas posiciones después de 15:40 ET.
MAGNITUD:   OFF (mag_umbral=None). El tape NO se usa.
CONTRATO:   ITM más profundo cuyo ask*100 <= tope (tope = 80% del capital de sizing).
            Con $400 → casi-ATM (~$2.5-3.2, delta ~0.6). Al crecer el capital intradía → ITM más profundo (delta ~0.85).
SIZING:     FIJO $400 por posición (size_cap=400). NUNCA compounding de % del capital (arruina). Banco aparte.
PRICING:    compra al ASK, vende al BID (realista). Spread real ITM SPY ~2%. Comisión $1.72/trade.
SALIDAS:    trail 0.04% | cierre 15:59 | flip pendiente. (Sin permanencia por magnitud.)
```

**Candidato NO validado OOS:** ST multiplier 2.5 (más sensible) dio mejor total en Año1 (+$19.650) pero más días malos; NO se probó en Año2. Mantener 3.0 (validado) salvo re-test.

---

## 2. ARQUITECTURA / DATOS

### Motor de simulación
- **`simulador_st.py`** — EL simulador. Función `simular(...)`. Reutiliza el Supertrend real. Parámetros:
  - `trail` (%), `mid` (True=mid, False=ask/bid), `mag_umbral` (None=off), `net_ext` (inyectar magnitud externa), `size_cap` (sizing fijo), `cooldown`, `hora_min` (skip apertura), `ventana_no` (blackout franja), `stop_opt` (stop-loss opción), `max_trades`, `stop_racha`.
  - `elegir_contrato(P, hora, right, tope, mid)` — deepest ITM que quepa.
  - `carga(...)` — arma velas (del tape si hay, o bars_minute), premium, y NET (magnitud) del tape.
  - Reproducción de referencia (default): 08-12 +43.56, 08-13 +480.84 (ask/bid, señales manuales). **Si esto no da, hay regresión.**

### Premium sintético
- **`analisis/synth_premium.py`** — `calibra(dias)`, `extr(modelo, depth, ttc)`, `ttc(hora)`.
- Modelo: `prima_mid(K, right, S, ttc) = max(intrínseco, 0) + extrínseco[bucket(itm_depth, ttc)]`.
  - intrínseco = max(S-K,0) [call] o max(K-S,0) [put].
  - extrínseco calibrado con contratos REALES de 08-11/08-12/08-13 (los únicos días con premium real).
  - bucket = (depth redondeado a $0.5, ttc redondeado a 30min). depth = (S-K) call / (K-S) put.
- **Validación del modelo:** error OOS por-contrato ~**3.5%** (leave-one-day-out en los 3 días); error de P&L end-to-end en 08-13 (sintético calibrado solo con 11+12) = **1.7%** vs premium real. → El sintético es fiel para el rango casi-ATM que opera.
- Para bid/ask con spread realista: `bid=mid*0.99, ask=mid*1.01` (2% spread, medido en contratos reales).

### Bases de datos (LOCALES, regenerables, NO en git por tamaño)
- `spy_bars_year.db` — **Año1**: 261 días (2025-07-31 → 2026-08-13), velas 1-min con premarket + volumen.
- `spy_bars_year2.db` — **Año2 OOS**: 251 días (2024-07-31 → 2025-07-31).
- `spy_bars_year3.db` — parcial 2023-24 (bajando; IBKR corta ~2024-05).
- `spy_bars_pm.db` — velas premarket de la semana 08-05..08-13 (para los 4 días de tape).
- `spy_tape_*.db` — tape del subyacente 08-10/11/12/13 (**YA NO SE USA** — era para magnitud).
- `spy_history_YYYYMMDD.db` — premium REAL grabado por la app: 08-11 (tarde), 08-12, 08-13 (0DTE completo). +1 día/día hacia adelante.
- **LÍMITE IBKR:** `reqHistoricalData` de 1-min solo da ~2 años atrás (hasta ~2024-05). **2022/2023 NO disponibles** (year4/year5 volvieron 0 barras). Histórico de opciones real: IBKR NO lo da → solo se acumula grabando forward.

### Descargadores
- `analisis/bajar_bars_year.py FIN INICIO DB CLIENTID` — velas 1-min (useRTH=False), paginando. Reconecta ante caída de gateway. clientId parametrizable (para concurrencia).
- `analisis/descarga_tape_spy.py INI FIN` — tape (reqHistoricalTicks) → spy_tape.db. LENTO (~1h/día, pacing IBKR). YA NO NECESARIO.
- `analisis/bajar_bars_pm_semana.py` — velas premarket.

---

## 3. TODO LO QUE PROBAMOS Y EL VEREDICTO (para no repetir)

### ✅ FUNCIONA (validado)
| Cambio | Efecto | Nota |
|---|---|---|
| **2-min** (vs 1-min) | 1-min es whipsaw puro; agregar a 2-5min ayuda mucho | Curva de timeframe es RUIDOSA arriba de eso (no fitear el valor exacto) |
| **Trail más ceñido (0.04-0.06%)** vs 0.10% | Mejora CONSISTENCIA (más días verdes, menor drawdown) | El total ~neutro solo; con skip, 0.04 mejor |
| **skip apertura <09:45** | **Sube %verde y baja días malos en AMBOS años (generaliza)** | La ÚNICA mejora estructural que generalizó OOS |
| **Sizing FIJO $400 + banco** | Sobrevive (no arruina) | Ver sección 4 (sizing = vida o muerte) |

### ❌ NO FUNCIONA (probado y descartado — NO reintentar sin razón nueva)
| Idea | Resultado | Por qué |
|---|---|---|
| **Magnitud (permanencia por flujo)** | Neutro-a-dañino en el año; baja %verde | Solo ayudaba al 08-13 en muestra de 4 días. El tape ya no se usa. |
| **Proxy de magnitud (volumen→NET)** | Recupera 88% del efecto en 4 días, pero la magnitud NO ayuda en el año | Moot |
| **Confirmación (esperar N velas)** | DESASTRE: vuelve el sistema NEGATIVO (−11.409, 33% verde) | Demorar la entrada mata el edge; el falso y el verdadero son iguales al entrar |
| **Cooldown tras salir** | Baja el total | Bloquea re-entradas buenas |
| **Filtro régimen VWAP** | net −353 | Corta ganadores contra-tendencia que igual ganan |
| **Filtro régimen ST 5-min / 3-min** | net −23 / −65 | Arregla día malo pero rompe lateral |
| **KNN forma de la mañana → P&L del día (teoría cíclica)** | corr **+0.04 = CERO** | Intradía ≈ random walk; el régimen NO se predice temprano |
| **Predictores tempranos (rango/eficiencia/volumen 1ª hora)** | corr ~0.0-0.24, todos débiles | Idem — no se predice el día |
| **Stop-loss por trade sobre la opción (25-50%)** | IDÉNTICO al base | El trail 0.04% ya sale antes; redundante |
| **Max trades/día (2/3/4)** | Baja el total | Corta ganadores |
| **Stop por racha de pérdidas (2/3)** | Baja el total | Frena días que recuperan |
| **Objetivo de ganancia diario** | NO sube %verde, corta winners | Casi no hay días que suben a +T y se dan vuelta |
| **ST multiplier ANCHO (3.5-5.0)** | PEOR (pierde giros verdaderos) | Bandas anchas giran menos pero pierden los buenos |
| **Compounding día-a-día (80% del capital)** | **RUINA a $0** en ~1 mes | 80% en un 0DTE que puede perder 100% → ruina multiplicativa |
| **Escalado +1 contrato por $1000** | Exponencial: explota a fantasía ($59M) o arruina | Mismo problema que el 80% |
| **Skip apertura más agresivo (>09:45)** *(re-verif 2026-08-14)* | 09:45 es el óptimo; 10:00+ baja el total en AMBOS años; los malos quedan clavados ~−$5k para cualquier skip ≥09:45 | La única mejora de skip fue "sin skip"→09:45; más allá saca días buenos con los malos. Banco: `analisis/reverifica_dias_malos.py` |
| **Trail a 2-min (alinear con el ST) todo el día** *(re-verif 2026-08-14)* | **DESASTRE en ambos años**: total +16k→−6.7k / +11.5k→−9.9k; %verde 63/60%→36/32%; malos se TRIPLICAN | El trail rápido de 1-min es load-bearing: en los giros falsos (mayoría) sale barato. A 2-min deja correr la pérdida al doble. Banco: `analisis/exp_trail_2min.py` |
| **Trail 2-min SOLO en la apertura (operarla en vez de skipearla)** *(re-verif 2026-08-14)* | Peor que el baseline Y que el control (sin-skip 1-min) en ambos años: Δmalos −3.1k/−2.2k, Δ%verde −6.9%/−5.6% | La apertura es donde MÁS whipsaws hay → es donde el trail lento MÁS daña. Lo mejor con la apertura sigue siendo no operarla. Banco: `analisis/exp_trail_apertura.py` |

---

## 4. SIZING = VIDA O MUERTE (crítico)

- **Compounding % (tope = 80% del capital, arrastrando) → RUINA.** Un 0DTE casi-ATM ≈ 75-80% de $400; apostás casi todo cada trade; una mala racha (35% de días son rojos) → cero.
- **Reinicio diario a $400 (+21k/año) es ILUSIÓN** — nunca compone pérdidas; es una SUMA de apuestas independientes, no una cuenta.
- **CORRECTO: N FIJO de contratos + colchón.** El P&L escala lineal con N; el drawdown también. Nunca arruina con colchón.
  - 1 contrato, colchón $2.000 → banco final ~$14.500 (año1, bid/ask), maxDD $821.
  - 2 contratos, colchón $4.000 → ~$29.000; 5 contratos, colchón $10.000 → ~$72.000.
- **Arrancar con $400 EXACTOS:** ~**8% de ruina** (1 de 12 arranques mensuales del año1 murió — julio-31, racha mala de agosto). Con la config mejorada (skip+trail): **0/12 = 0% ruina** en año1. Pero con exactamente $400 hay fragilidad de arranque (las primeras 2-3 semanas). Recomendado: colchón ~$2.000-4.000 (1 contrato ≈ 10% de la cuenta).

---

## 5. LOS INSIGHTS CLAVE (la teoría del problema — CONSENSO)

★ **La raíz de las pérdidas son los GIROS FALSOS del Supertrend.** El 89% de las pérdidas de días malos son whipsaws cortos (<20min): el ST gira, entrás, se revierte en ~5 min, salís con pérdida.

★ **PERO un giro falso y uno verdadero son ESTADÍSTICAMENTE IDÉNTICOS en el momento que ocurren.** Medido: días buenos 6.1 flips/día, malos 6.2; misma tasa de whipsaws (<10min: 8% ambos). No se distinguen por frecuencia, forma ni features. **El régimen intradía NO es predecible** (mercado casi-eficiente / random-walk). Por eso TODO método de predicción falló (features, KNN, magnitud, régimen).

★ **De dónde sale el edge que SÍ existe:** cuando el ST gira, el precio SIGUE un poco más seguido de lo que se revierte (→ 60-67% días verdes) Y los winners son más grandes que los losers (ratio ~2.2). Edge pequeño pero real, persiste 2 años.

★ **Lo único controlable (y ya optimizado):** NO la tasa de acierto (no se predice), SÍ el **costo de equivocarse** (trail ceñido = falso flip barato) y **evitar la zona mala** (skip apertura, el hotspot #1 de whipsaws). Los días malos restantes (~−$5k/año) son el **costo IRREDUCIBLE** de hacer momentum en un mercado casi-eficiente.

★ **Ejemplo canónico — 2026-06-26** (día que chopeó 727-737, todos los flips pierden). **VERIFICADO contra el código real 2026-08-14** (corrección de una versión previa errónea que hablaba de un "09:44 CALL −$113.92" que NO existe). Los flips REALES del ST(7,3.0) 2-min con premarket:
  - El día **abre en tendencia bajista (−1) heredada del premarket** (el ATR se calienta con velas premarket, así que el estado al abrir es el que traía). Por eso el primer evento RTH es un **PUT a las 09:30**, no un CALL.
  - El **primer CALL nace a las 09:50** (≈09:52 en Webull), cuando el precio rompe la banda superior — NO a las 09:44.
  - **P&L real (bid/ask, sintético, size_cap $400, trail 0.04%):** sin skip = **−$232.00** (5 trades, todos rojos: 09:30 PUT −41.42, 09:50 CALL −21.85, 12:12 PUT −71.24, 13:08 CALL −33.79, 13:24 PUT −63.69). Con skip 09:45 = **−$190.58** (elimina solo el PUT de apertura de 09:30, −$41.42; NO un "killer" de −$113).
  - ★ El **09:50 CALL tenía la dirección CORRECTA** (el SPY subió hasta 736 después), pero el trail 0.04% lo cortó en 2 min por un dip de ruido (−$21.85). Es el retrato del insight raíz: en un día de chop, **la dirección puede acertar pero el trail ceñido corta la entrada en el ruido**; los 5 flips pierden no por dirección equivocada sino por whipsaw. Reproducir: `analisis/verifica_headline.py` (motor) + query directo del día.

---

## 6. CAVEATS HONESTOS (lo que es HIPÓTESIS, no verificado 100%)

1. **Premium SINTÉTICO** — calibrado en 3 días reales (08-11/12/13), aplicado a 2 años asumiendo extrínseco estable. Error medido ~1.7-3.5% en esos 3 días, pero **riesgo de modelo en regímenes de vol distintos**. Es el candado #1.
2. **Premium real** solo existe 08-11/12/13 (la app graba forward, +1/día). IBKR NO da histórico de opciones. Validación real = acumular días grabados.
3. **bid/ask = peor caso** (pago spread completo cada pata). Real con órdenes límite: entre mid y bid/ask → mejor.
4. **Solo 2 años** (2024-07 → 2026-08), 1 instrumento (SPY), régimen macro acotado. IBKR no da 1-min pre-2024.
5. La mejora skip+trail generaliza en CONSISTENCIA (%verde, drawdown) pero **el boost de TOTAL de año1 (+29%) NO se replicó en año2** (fue overfit de 1 año). El edge base sí replica.

---

## 7. SCRIPTS DE ANÁLISIS (en `analisis/`)
- `synth_premium.py` — modelo de premium (calibra/extr/ttc). **Núcleo, reutilizado en todo.**
- `year_backtest.py` / `year_backtest_mag.py` — backtest del año (sin/con magnitud ficticia).
- `run_dia_completo.py DK` — corre un día completo (premium real+sintético mezclado).
- `sim_semana_ibkr.py`, `sim_ibkr_premarket_0813.py` — corridas de la semana / día con ST premarket.
- `filtro_vwap.py`, `filtro_st5m.py` — filtros de régimen (descartados).
- `modelo_prima_itm.py` — calibración+validación del premium.
- `bajar_bars_year.py`, `descarga_tape_spy.py`, `bajar_bars_pm_semana.py` — descargas.
- Los tests de la sesión (batería stop/skip/trail/mult, KNN, ruina, compounding) se corrieron inline (ver este doc para resultados).

---

## 8. PRÓXIMOS PASOS (en orden de valor)
1. **Validar con premium REAL** acumulado (la app graba 0DTE forward desde 08-11; ya hay 3+ días). Cuando haya ~20-30 días reales, re-correr y comparar vs sintético. **Cierra el candado #1.**
2. Correr el test de ruina $400 sobre el **año2** (confirmar que el 0% también generaliza OOS).
3. Curva de equity de los **2 años seguidos** (concatenar year1+year2) con sizing fijo + colchón.
4. NO seguir tuneando parámetros sobre 1 año (overfitting garantizado — ya se demostró).
5. Considerar 2-min ST mult 2.5 (mejor total año1) SOLO si se valida OOS en año2.

---

## 9. CÓMO RETOMAR (para Claude tras compact)
1. Leer este archivo COMPLETO.
2. Verificar reproducción de referencia: `python simulador_st.py` → debe dar TOTAL +524.40 (08-12 +43.56, 08-13 +480.84). Si no, hay regresión.
3. Las DBs (`spy_bars_year*.db`, `spy_history_*.db`) están LOCALES (no en git). Si faltan, regenerar con `bajar_bars_year.py`.
4. La config final está en la sección 1. El simulador ya tiene TODOS los parámetros implementados.
