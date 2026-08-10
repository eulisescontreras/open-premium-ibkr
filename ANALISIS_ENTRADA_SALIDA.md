# ANÁLISIS — cuándo comprar y cuándo vender (sesión 2026-08-10)

> Documento de ANÁLISIS DE DATOS. Para mejoras de código ver `MEJORAS.md`; para el estado del
> proyecto, `ANTI_COMPACT_CONTEXT.md`.
> Todo lo de aquí sale de `spy_history.db` de la primera sesión en vivo. **Un solo día**: son
> HIPÓTESIS y descartes, no reglas. Cada cifra lleva su n y su tasa base.

---

## 0. LA PREGUNTA

No es "¿sube o baja?" — eso ya se mide y da **~50%**. La pregunta real, planteada por el
usuario tras ver el CALL del 13:01, es:

> *"La dirección no está siendo mal calculada. Es solo que el momento de la compra está siendo
> muy temprano, desgastando la opción."*

El caso que lo demuestra, con números exactos:

```
13:01  compra CALL 773   SPY = 773.00   prima = 0.73
14:54  (1h53m después)   SPY = 773.11   prima = 0.50
```

**El SPY quedó 11 céntimos MÁS ARRIBA y la prima valía 23 céntimos MENOS.** Dirección correcta,
resultado negativo. El theta se comió el acierto. Ese es el problema a resolver.

---

## 1. ¿EL FLUJO DE PREMIUM ANTICIPA EL MOVIMIENTO? — NO (a resolución de 1 min)

Correlación cruzada entre el flujo neto por minuto (Δnet_call − Δnet_put) y el movimiento del
SPY, sobre **227 minutos** en 5 tramos limpios (excluidos huecos y saltos por reinicio):

```
lag +1  (el flujo iría DELANTE)   -0.038
lag +2                            -0.010
lag +3                            -0.085
lag +4                            -0.048
lag  0  (mismo minuto)            +0.041
lag -2  (el flujo va DETRÁS)      +0.203   <- el máximo
```

**Todos los lags predictivos son cero o negativos.** El único valor apreciable dice que el
flujo va *detrás*.

Caso concreto — la mayor entrada de dinero del día:
```
minuto   SPY      ΔSPY     flujo neto del minuto
12:31   772.64   -0.69      -249.083    <- el movimiento GRANDE
12:36   772.88   -0.01      -811.910    <- la entrada de 1,1 M: el SPY NO se movió
12:37   772.74   -0.14      +181.438    <- y después el flujo se invierte
```

Y en vivo (14:37-14:43), el ratio bruto call/put cruzó a favor de las calls en **14:39**,
dos minutos después de que el SPY empezara a subir en 14:37.

### Objeción del usuario, y por qué es válida

> *"En el tape el dinero es lo que mueve el subyacente, no al revés."*

Cierto como principio. El matiz: **el dinero que mueve el SPY es el dinero EN el SPY**
(acciones y futuros ES). El premium de opciones empuja por delta-hedge del dealer, pero:
- ese hedge ocurre en **segundos**, no en minutos;
- escala: 1,1 M de premium en calls ATM ≈ 1.375 contratos × 50 delta ≈ **53 M $ de SPY**,
  frente a decenas de miles de millones diarios. No mueve el precio 0,69.

### Limitaciones REALES de esta medición (por las que NO es una sentencia)

1. **Resolución de 1 minuto.** Si el hedge es instantáneo, causa y efecto caen en el mismo
   minuto y son indistinguibles. Para zanjarlo harían falta **datos por segundo**.
2. `net_call`/`net_put` acumulados, **inflados por el GAP 2** hasta las 14:28.
3. Solo se clasifica ~20% del flujo (el resto cae dentro del spread y se descarta).

**Conclusión honesta: no sé si el premium anticipa. Sé que no lo detecto a un minuto.**

---

## 2. ¿EL TA ANTICIPA? — TAMPOCO

```
Correlación ta_score vs movimiento futuro:  +0.019 a +0.066 en TODOS los lags (0 a 5 min)

Acierto direccional del minuto siguiente:
   TA      (BULL/BEAR): 105 de 209 = 50.2%
   PREMIUM (UP/DOWN)  : 122 de 246 = 49.6%
```

Dos sistemas independientes, ambos en la moneda al aire. En la subida de 14:37→14:42 el TA pasó
a BULL en **14:41**, cuatro minutos tarde.

---

## 3. COMPRESIÓN DE BOLLINGER — HIPÓTESIS PROBADA Y **DESCARTADA**

Parecía prometedora en 3 casos aislados (12:26-12:30 y 14:32-14:36, con el ancho en mínimos
justo antes de sendos movimientos). Medida sobre **las 52 compresiones del día**:

```
compresión = bb_ancho en percentil 20 de los últimos 30 min
   3 min  -> 0.239 vs 0.204 normal = 1.17x
   5 min  -> 0.332 vs 0.282        = 1.18x
  10 min  -> 0.445 vs 0.421        = 1.06x
  15 min  -> 0.506 vs 0.552        = 0.92x  (PEOR)
```

Y el dato que la mata: **la tasa base de moverse ≥0,20 en 10 min es del 86%.** Tras compresión
sube al 90%. Cuatro puntos sobre algo que pasa casi siempre.

En el barrido total, `bb_ancho` sale entre **−0,10 y +0,18**: ruido.

**Lección metodológica:** los 3 casos iniciales fueron cherry-picking. Nunca evaluar un
predictor sin calcular antes la **tasa base**.

---

## 4. BARRIDO TOTAL — 40+ variables (niveles y deltas)

Variables probadas: RSI, MACD (línea/señal/histograma), EMA 8/21/50 y sus distancias, ATR,
ancho de Bollinger, **%B**, VWAP y distancia con signo, OBV, ta_score, diff/thr/momentum,
premium por vela (bruto y neto, ratio C/P), GEX, gamma flip, call/put wall, centro de peso,
magneto, posición en el canal — más los **deltas** de todas y la velocidad/aceleración del precio.

### 4.1 Movimiento BRUSCO (≥0,40 en 3 min) — tasa base 7% → ⚠️ CONTAMINADO

```
  obv          0.0000 vs 1.0000    -1.00
  spy_e8      -0.1499 vs 0.0268    -0.87
  dist_vwap   -0.1093 vs 0.0267    -0.70
  pctB         0.2208 vs 0.6160    -0.68
  e8_e21      -0.1130 vs 0.0119    -0.56
```

**NO USAR.** Una separación de −1,00 en OBV es demasiado perfecta. Todas estas variables dicen
lo mismo — *"el mercado está cayendo"* — y el **63% de los movimientos grandes de hoy fueron
bajistas**. Describen el sesgo del día, no predicen movimiento. Con n=19 y una sola sesión,
cualquier indicador bajista parecerá profético.

### 4.2 Mercado PLANO (<0,20 en 10 min) — tasa base 16% → ✅ **LO APROVECHABLE**

```
  atr_pct        0.0184 vs 0.0272    -0.83  ***
  abs_momentum      284  vs  17.211  -0.76  ***   (60 veces menor)
  abs_dist_flip  0.5855 vs 0.9287    -0.43  **
  abs_vel3       0.1000 vs 0.1500    -0.31  *
```

**Las cuatro son direccionalmente neutras** (valores absolutos): no pueden estar capturando el
sesgo bajista. Y separan **más fuerte** que cualquier predictor de movimiento.

> **No se puede predecir bien cuándo habrá movimiento; sí se puede predecir bastante bien
> cuándo NO lo habrá.**

Y eso ataca el problema real: no hace falta acertar el minuto de la explosión, hace falta
**no estar dentro pagando theta durante los minutos muertos**.

*Nota:* `abs_momentum` solo mide algo desde el arreglo del **GAP 5** de esta tarde; antes
contaba eventos y era bimodal (0 o enorme).

`abs_dist_flip` bajo → plano es coherente con la teoría de gamma: cerca del flip, los dealers
en gamma larga amortiguan el precio. **Primera vez que el GEX aporta algo con signo neutro.**

### 4.3 Movimiento GRADUAL (≥0,60 en 15 min pero <0,40 en los primeros 3) — tasa base 23%

Separaciones débiles (0,24-0,34): `abs_dist_flip` +0,34, `gex_bn` +0,33, `macd_h` −0,32,
`rsi` −0,30. Nada concluyente.

---

## 5. QUÉ FALTA PARA DECIDIR DE VERDAD

### 5.1 Datos que ya se guardan y solo necesitan tiempo

| Dato | Desde | Para qué |
|---|---|---|
| `trades` (MFE/MAE + hora del máximo + contexto de entrada) | 14:28 (**0 filas aún**) | Separar *"me equivoqué de dirección"* de *"acerté pero entré 40 min pronto"* |
| `posicion_minuto` (bid/ask/mid + 6 griegas por minuto) | 14:28 | Medir cuánto se come el theta **de verdad**, contrato a contrato |
| `prem_call_min` / `prem_put_min` / `net_*_min` | 14:28 | Flujo por vela, sin la contaminación del acumulado |
| `net_call_1m/5m/15m` | 14:28 | Comprobar si una ventana móvil habría girado antes |
| `cum_net` / `day_net` | 14:00 | Neto firmado por strike, en paralelo al bruto |

**Con 3-5 sesiones limpias** se puede: separar brusco/gradual con n suficiente, validar el
filtro de "no entrar en plano", y calibrar un take-profit sobre `mfe` real.

### 5.1-bis Presupuesto de líneas de market data (VERIFICADO por código y log)

```
señal      2   (call + put, "233")
ejecución  2   (buy_call + buy_put, "")
baseline  24   (3 expiries x 4 strikes x 2 lados, "233")
banda     40   (20 strikes x 2, "100,101,106")
TOTAL     68   de ~100 disponibles -> 68%
```
**0 errores de límite** (`101`/`102`/`309`/`10197`) en toda la sesión, con 72 re-centrados de
señal + 16 de ejecución + 20 de baseline: las suscripciones **no se están acumulando**.

- Cada strike de banda cuesta **2 líneas** → subir `WALLS_BAND` de 10 a 15 costaría 20 más (88/100).
- **NO VERIFICADO:** si IBKR cobra 1 o 2 líneas cuando dos objetos comparten `conId` (los 2
  contratos de ejecución son el mismo contrato que 2 de la banda).
- **Propuesta barata:** loguear `len(self.ib.tickers())` en cada snapshot de walls → convierte
  el cálculo teórico en dato medido y detecta fugas antes de que IBKR corte datos en silencio.

### 5.2 Datos que NO tenemos y harían falta

1. **Resolución por segundo del flujo.** Es lo único que zanjaría si el premium anticipa. El
   bucle ya corre a 1 Hz: sería guardar `(t, net_call, net_put, spy)` cada 1-5 s.
2. **Volumen y flujo del SUBYACENTE** (SPY/ES). Hoy solo vemos opciones, que es el derivado.
   Si el movimiento nace en los futuros, nunca lo veremos aquí.
3. **Un día con GEX negativo.** Hoy fue LONG el 100% del tiempo: el régimen no se pudo probar.
4. **Días con sesgo alcista**, para separar predictores reales del sesgo bajista de hoy.

### 5.3 Para la VENTA (no dejar dinero sobre la mesa)

El episodio del PUT de las 12:20 es el caso de referencia:
```
entrada 0.80 -> pico 2.10 (+130 $) a las 12:43 -> vendido a 1.25 (+45 $) a las 13:01
>100 $ durante ~13 minutos · 85 $ dejados sobre la mesa · giro 18 min DESPUÉS del máximo
```
Las mismas variables del §4.2 servirían al revés: **ATR y momentum colapsando estando dentro**
= el movimiento se agotó y a partir de ahí solo manda el theta. `posicion_minuto` ya graba
theta y mid minuto a minuto para poder contrastarlo.

⚠️ **Trampa ya cometida:** la simulación de objetivos fijos midió centavos del **SPY** y
concluyó *"ningún objetivo mejora al flip"*. Falso para opciones: el PUT hizo **+162%** con
~1,20 de SPY. **La salida hay que medirla sobre la PRIMA, no sobre el subyacente.**

---

## 6. TRAMPAS IDENTIFICADAS — no volver a caer

1. **Tasa base primero.** Con el SPY moviéndose 0,20 en 10 min el 86% del tiempo, cualquier
   indicador "acierta" el 90%.
2. **Sesgo de selección.** Mirar solo los movimientos grandes dio *8 de 8*; medido con los
   falsos positivos, **51%**.
3. **Todo lo acumulado correlaciona con el reloj** (M10): `gex_total`, `net_call`, `net_put` y
   la distancia al flip crecen con la hora. Usar **deltas por vela** y **distancias**.
4. **Cuidado con las variables direccionales en un día con sesgo.** OBV, %B, EMAs y `dist_vwap`
   parecieron predictores y solo describían un día bajista. **Preferir magnitudes absolutas.**
5. **Medir la salida sobre la prima, no sobre el subyacente** (convexidad).
6. **Excluir tramos sucios:** `walls_snapshot` con `spot=773.03` (13:26-14:00, GAP 17) y el
   premium de los strikes de señal anterior a las 14:28 (GAP 2). A partir de ahora,
   `sesion_config` sella cada arranque.

---

## 7. HOJA DE RUTA

| Orden | Qué | Requisito |
|---|---|---|
| 1 | Acumular 3-5 sesiones con la instrumentación completa | solo tiempo |
| 2 | Validar el filtro **"no entrar en plano"** (ATR + \|momentum\| + dist_flip) | 3-5 sesiones |
| 3 | Calibrar take-profit sobre `trades.mfe` REAL | 3-5 sesiones |
| 4 | Separar brusco/gradual con n suficiente | 3-5 sesiones |
| 5 | Guardar flujo por segundo y repetir el lead/lag | decisión + código |
| 6 | Repetir el barrido controlando por hora del día y por régimen GEX | 5+ sesiones, alguna con GEX negativo |

**Nada de esto debe tocar la señal hasta tener los datos.** El sistema hoy no está roto por
mala calibración: está limitado por una señal direccional del 50% y por entradas que pagan
theta esperando. Lo primero puede no tener arreglo; lo segundo sí, y es lo que atacan los
puntos 2 y 3.
