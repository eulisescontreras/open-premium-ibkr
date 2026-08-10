# HIPÓTESIS 2026-08-10 — qué dicen los datos del primer día y qué mirar mañana

> ⚠️ **NADA DE ESTE DOCUMENTO ESTÁ CONFIRMADO.** Sale de **una sola sesión**, sucia (11 arranques,
> huecos, spot congelado 36 min) y con **n = 2** episodios buenos. Son hipótesis para **falsar**
> mañana, no reglas para implementar. Tres hipótesis que parecían sólidas ya se cayeron hoy mismo
> al contrastarlas.
>
> Orden de lectura: `ESTADO_HOY.md` → `ANALISIS_ENTRADA_SALIDA.md` → **este** → `ANTI_COMPACT_CONTEXT.md`.

## Por qué existe este documento

El flip **acierta la dirección** pero a veces entra mucho antes de que ocurra el movimiento, y con
0DTE el theta se come el contrato antes de que llegue. Este día se dedicó a cruzar nuestra BD contra
**MarketSnack** (la app de la que salió la teoría del Open Premium) para responder una pregunta:
**qué parámetro, en el instante del cruce, avisa de que el movimiento viene ya.**

El encuadre que salió de ahí no es "detectar dirección" sino **clasificar el régimen en tres
estados: SUBIDA · BAJADA · LATERAL**. Hoy el sistema solo sabe decir UP o DOWN; no tiene forma de
decir *"no está pasando nada"*, que fue el estado durante **109 de los 245 minutos** analizados y
donde se pierde el dinero por theta.

---

## 1. Lo VERIFICADO hoy (ejecutado sobre `spy_history.db`)

### 1.1 El flip, a horizonte fijo, es una moneda
`analisis/vida_del_giro.py`, 54 FLIPs:
```
A favor del giro:  1 min → 43,2 %   ·   5 min → 48,6 %   ·   15 min → 52,2 %
54 % de los giros NUNCA estuvieron a favor ni un centavo (MFE ≤ 0)
Duración mediana de un giro: 4 minutos
2 de 26 episodios (10:50 y 12:20, ambos DOWN) se llevan TODO el recorrido del día
Caso theta: 13:01 UP → 111 minutos de vida para un MFE de +0,25
Ningún take-profit fijo (+0,10 a +1,00) mejora esperar al flip
```
**Lectura:** no es un problema de salida. Se entra 24 veces de más.

### 1.2 Coste del theta, medido con un caso real
Prima 0,73 → 0,50 en 113 min **con el SPY prácticamente igual** (773,00 → 773,11)
⇒ **≈ −0,002 de prima por minuto**. Con delta ~0,45, el SPY debe moverse **~0,0044 a favor cada
minuto solo para empatar**. En los 4 minutos que dura un giro mediano hacen falta ~0,018; la mediana
real a 5 min es **−0,08, en contra**. El giro mediano pierde por las dos vías a la vez.

### 1.3 Segmentación del día
Umbral: neto de ±0,30 en 15 min. **UP 53 min · DOWN 83 min · LATERAL 109 min.**
```
tramo         tipo  min   neto   atr%    GEXbn  ancho CW-PW
09:55-10:06    UP    11  +0.69  0.0397    196      15
11:36-11:50    UP    15  +0.45  0.0281    225       1
12:16-12:30  DOWN    15  -0.37  0.0227    249       0
14:12-14:26   LAT    15  -0.26  0.0166    188       1
15:22-15:35   LAT    14  -0.42  0.0177    273       0
```

### 1.4 DESCARTADO — el salto de wall NO predice movimiento
Probado sobre los 122 snapshots del día:
```
Recorrido máximo del SPY tras un salto de wall:
   5 min:  con salto 28 % ≥0,40  |  sin salto 14 %     (5 casos de 18 — no es estadística)
  10 min:  con salto 44 %        |  sin salto 39 %
  15 min:  con salto 56 %        |  sin salto 59 %     ← peor que no tener señal
```
De los 22 saltos, **20 son de ±1 strike**: la wall oscilando entre strikes vecinos, ruido. El único
salto grande real fue **10:50** (`CW −5`, `PW +8`, corredor 15→2, GEX 313→197 Bn) y sí dio −1,50 en
10 min. **n = 1.** Queda como observación, no como regla. **No volver a proponerlo sin filtrar por
magnitud del salto.**

### 1.5 DESCARTADO — variables contaminadas por el sesgo del día
`analisis/barrido_total.py`: `obv` sale con separación **−1,00 perfecta**, seguido de `dist_vwap`
(−0,52) y `spy−ema8` (−0,47). El **63 % de los movimientos grandes de hoy fueron bajistas**: estas
variables pueden estar describiendo el sesgo del día, no prediciendo nada.
**Una separación perfecta es una alarma, no un hallazgo.**

### 1.6 Lo único robusto: detectar el PLANO
56 de 321 minutos. `atr_pct` **−0,74** (0,0181 en plano vs 0,0262 con movimiento) ·
`bb_ancho` −0,50 · `abs_momentum` 8.518 vs 18.692. Direccionalmente neutro — y es exactamente lo que
hace falta contra el theta: **saber cuándo NO entrar**.

### 1.7 Candidato vivo sin contrastar: explosión de vol/OI por strike
El **774P** tenía `OI = 2.288` y llegó a **74.139 de volumen (32×)** justo antes de la caída de las
12:20. Volumen de hoy ≫ OI de ayer significa **posición nueva**, no rotación.
**No se ha medido su tasa de falsos positivos**, que es justo lo que tumbó a 1.4 y 1.5.

---

## 2. Lo observado en MarketSnack (`app.marketsnack.com`)

### 2.1 Vista Gamma Exposure (`/app/assets/SPY/gex`)
- Gráfica **Underlying & Gamma**: precio, Call Wall, Put Wall, **Magnet**, Gamma Flip y Net GEX
  compartiendo eje temporal. Exactamente las mismas magnitudes que ya guardamos en `walls_snapshot`.
- **El magneto se mueve en escalones y el precio lo persigue.** Desde las **12:50 el precio queda
  pegado al magneto** hasta el cierre — la firma visual del lateral.
- `Net GEX` = **+$10,3 B**; nuestro `gex_total` del mismo día = **+$334 B**. Tienen un selector
  `Formula: Per 1% move`. **NO VERIFICADO** de dónde sale el factor: resolver antes de comparar
  magnitudes de GEX con ellos.
- Sesión Aug 10 (0DTE) = $10,3 B de gamma (61 %) frente a Aug 14 = $6,1 B (37 %).

### 2.2 Flow Feed (`/app/flow-feed`)
**Asset Sentiment Overview del día:**
| Métrica | Valor |
|---|---|
| Order Book Side | Bid $745,3 M (46,9 %) · **Mid $154 M (9,7 %)** · Ask $689,3 M (43,4 %) |
| Premium Sentiment | Puts $646,4 M (45,1 %) · Calls $788,2 M (54,9 %) → **Neutral** |

El **Mid 9,7 %** es el dato de control más útil: es la fracción de premium que se ejecuta dentro del
spread y **no se puede atribuir a comprador ni vendedor**. Nuestro `_on_ticks` descarta ese flujo
(`signed = 0`). Si nuestro porcentaje no atribuible se aleja mucho de ~10 %, nuestra inferencia de
agresor está mal.

**Sus detectores, en SPY, hoy:**
| Preset | Resultados |
|---|---|
| `Aggressive Opening` | **0** — coherente con un día neutral |
| `0DTE Momentum Spike` | **2** |
| `Clean Directional Play` | 35 |

**Los 2 spikes 0DTE, ambos en el mismo contrato:**
| Hora | Contrato | Ejecución | Premium | Size | Volume | OI | Delta |
|---|---|---|---|---|---|---|---|
| **12:20:29** | SPY Aug10 **774P** | $0,75 sobre rango 0,74–0,75 → **en el ASK** | $227.850 | 3.038 | 342.087 | 2.288 | −0,54 |
| **11:52:30** | SPY Aug10 **774P** | $0,70 sobre rango 0,69–0,70 → **en el ASK** | — | — | 272.652 | 2.288 | −0,49 |

**El de las 12:20 cruza con nuestros datos en el mismo minuto:**
```
NUESTRA SEÑAL (ta_minute)                  NUESTRO STRIKE (premium_minute 774P 0DTE)
12:19  spy=773,69  netP=  253.734  UP      12:19  day_vol = 23.670
12:20  spy=773,74  netP=  626.624  DOWN ←  12:22  day_vol = 33.410
12:26  spy=773,56  netP=1.136.492  DOWN    12:28  day_vol = 52.480
12:31  spy=772,64  netP=1.156.081  DOWN    12:31  day_vol = 60.211   (OI = 2.288)
→ SPY −1,10 en 11 minutos
```
**Contraejemplo:** el spike de las 11:52, mismo strike y también en el ask, **no** produjo caída —
el SPY subió de 773,72 a 774,33. **1 de 2.**

### 2.3 Qué de MarketSnack es replicable con lo que tenemos
Verificado leyendo `spy_direction.py:1601-1646`:

**NO replicable:**
1. **Prints individuales.** `dvol = vol − prev` es la diferencia de volumen entre dos
   actualizaciones del ticker, **no un trade**. Si en ese intervalo hubo 5 operaciones, las suma, y
   `last` es solo el precio de la última. **No podemos distinguir 1 print de 3.038 de 50 de 60.**
   Su columna `Size` no tiene equivalente posible con RTVolume.
2. **Multi-leg vs single-leg** (su `Cond: ML/SL`). No lo expone RTVolume: un spread se nos cuela
   como apuesta direccional.
3. **Buy/Sell explícito.** Nosotros lo **inferimos** por regla del agresor (`last ≥ ask` compra,
   `last ≤ bid` venta, dentro del spread se descarta). Es inferencia, no dato.

**Sí replicable, y ya está en la BD:** `open_interest` + `day_vol` por strike ⇒ **apertura vs
rotación**. Es la pieza del §1.7.

---

## 3. LAS CUATRO HIPÓTESIS

### H1 — El régimen lo marca el ANCHO DEL CORREDOR, no la dirección
Mientras `CW` y `PW` están separados hay espacio y el precio tiende; cuando el corredor se cierra
sobre el precio (`CW ≈ PW ≈ spot ≈ magneto`), el precio queda atrapado y solo corre el theta.
**Evidencia:** el ancho `CW − PW` se cerró monótonamente **15 → 3 → 1 → 0** y el movimiento se apagó
en paralelo (mañana `atr_pct` 0,027–0,040 con tramos de +0,69/+0,45; tarde 0,015–0,019 y casi todo
lateral).
**Cómo falsarla:** si mañana hay tendencia con corredor cerrado, o lateral con corredor ancho, cae.
**Confusor grave:** el corredor se cerró *con la hora*. Puede ser simplemente "por la tarde no pasa
nada" — la trampa de correlación con el reloj ya documentada en `ANALISIS_ENTRADA_SALIDA.md`.

### H2 — La decisión debe usar FLUJO NUEVO, no acumulado
El acumulado desde las 09:30 tiene memoria infinita: **por la tarde valía +7 M constante con el
mercado lateral**. Y como `thr = ADAPT_FRAC·(|net_call|+|net_put|)` crece con él, a las 12:36 hacían
falta **2,81 M de flujo nuevo para girar** — más de lo generado en todo el día. La ventana móvil
(`net_call_1m/5m/15m`, `prem_*_min`) **ya se guarda y nunca se ha usado**.
**Cómo falsarla:** si al etiquetar los flips la ventana corta no separa `RÁPIDO` de `MUERTO` mejor
que el acumulado, no aporta nada.

### H3 — El "evento" es acumulación sostenida en un strike, no un print gigante
Lo que respalda la caída de las 12:20 no es el print de 3.038 contratos: es que el 774P pasara de
**OI 2.288 a 74.139 de volumen (32×)** — muchas operaciones acumulándose, que es exactamente la
tesis original del Open Premium. Un print aislado puede ser un cierre o una pata de un spread; el
tape trae **compras y ventas**.
**Cómo falsarla:** el otro spike del día no movió el precio (1 de 2), y **falta medir cuántos
strikes explotan sin que pase nada**.

### H4 — Lo único operable hoy es un filtro NEGATIVO: no entrar en lateral
No mejora la puntería direccional —el flip seguirá siendo una moneda— pero evita las entradas que
mueren de theta, que son el **54 %**. Es lo único con respaldo estadístico real (§1.6). Encaja con
H1: *lateral = corredor cerrado + ATR bajo + precio pegado al magneto*.
**Cómo falsarla:** si los flips dentro de tramos marcados como lateral rinden igual que los de
fuera, el filtro no vale.

> **Lo que las cuatro tienen en común:** ninguna intenta predecir la dirección. Asumen que el flip
> ya la acierta y atacan **cuándo** merece la pena actuar. Coherente con lo medido: la dirección
> sale 50 %, pero el daño viene de operar cuando no había nada que ganar.

---

## 4. Lección metodológica (lo más importante del día)

Cada hipótesis se veía bien mirando primero los 2 casos buenos y buscando qué tenían en común; cada
una se cayó al contrastarla contra los 100+ casos restantes. La caída de las 10:50 tuvo salto de
wall **y** colapso de GEX **y** precio pegado al Call Wall: con n = 2, las tres "explican" el
movimiento.

**Ninguna variable entra en producción sin su tasa de falsos positivos delante.**

Y un matiz de la propia estructura del día: las walls vivieron casi toda la sesión en un corredor de
0–3 puntos, así que "pegado al Call Wall" describe el 70 % del día. **Una variable solo separa si su
valor en los eventos es raro en el resto del día** — y en un día plano, casi nada es raro.

---

## 5. Trabajo pendiente

**`analisis/punteria_entrada.py`** (aún no escrito) — read-only como los otros 11 de `analisis/`,
pensado para **re-correrse cada día**. Reutiliza el etiquetado de `vida_del_giro.py` y los lags de
`lead_lag.py`; ninguno de los existentes analiza **por strike** ni reporta tasa base.

0. Clasificar cada minuto en **SUBIDA / BAJADA / LATERAL** (§1.3). Es la etiqueta objetivo.
1. Etiquetar cada flip: `RÁPIDO` (MFE ≥ +0,20 en ≤5 min) · `TARDÍO` · `MUERTO` (MFE ≤ 0), y cruzarlo
   contra la etiqueta de régimen. Hipótesis: **los `MUERTO` caen en tramos LATERAL**.
2. Barrer **todas** las familias contra las 3 etiquetas, **en nivel y en derivada**:
   **PREMIUM** (acumulado `net_call/net_put`, `diff/thr` vs flujo nuevo `net_*_1m/5m/15m`,
   `prem_*_min`) · **TA** (`rsi`, EMAs, MACD, `bb_ancho`, `pctB`, `atr_pct`, `dist_vwap`,
   `obv_trend`, `ta_score`) · **GEX** (`gex_total`, su derivada, `regime`) · **WALLS** (`call_wall`,
   `put_wall`, **ancho CW−PW**, distancias) · **MAGNETO** (`max_pain_dyn/static`, `prem_center`,
   `gamma_flip`, distancia del precio al magneto) · **ESTRUCTURA DE STRIKE** (`day_vol/OI`,
   concentración del `day_prem` en el top-1).
3. **Tasa base obligatoria** en cada candidato: `n`, aciertos con la condición, aciertos sin ella, y
   **falsos positivos**.
4. **Salida por tiempo, no por precio**: con la duración mediana (4 min) y el coste (−0,002/min),
   calcular el tiempo máximo de tenencia tras el cual el movimiento pendiente ya no paga el theta.

**Idea anotada, NO incluida:** añadir un segundo contrato (mismo strike o el más ATM) cuando aparezca
el evento fuerte. Choca con `QTY = 1` y con la guarda de `_place` (`pos_qty + buys_pend >= QTY`),
puestas tras el **GAP 9** (órdenes fantasma que dejaron 3 puts abiertas y vaciaron la cuenta).
Exigiría: condición validada con tasa base, autorización explícita, corrida en frío diferencial
(14 suites verdes) y revisar el aplanado de las 15:45 con posición múltiple.

---

## 6. Condiciones para que la sesión de MAÑANA sirva

1. Lanzar la app **antes de las 09:30** y **no reiniciarla en todo el día** (hoy: 11 arranques; cada
   uno corta `day_prem` y mete un tramo no homogéneo).
2. En el arranque: `ESTADO INTRADIA restaurado`, `SELLO DE SESION`, y **ningún `GIRO ->` en los
   primeros segundos** (si aparece, volvió el GAP 18).
3. Si aparece `spot_stale = 1` en `walls_snapshot`, ese tramo queda inservible (GAP 17; hoy se
   perdió 13:26–14:00).
4. Comprobar que `trades` recibe su primera fila **con las griegas rellenas** — lo único que quedó
   NO VERIFICADO en vivo. Sin `trades.mfe` real no hay forma de calibrar la salida.
5. Cuenta reseteada a **$400**: relanzar con fecha 2026-08-10 mostraría un `DIA +102,96` falso (base
   vieja 297,04 en `estado_intradia`). Con fecha nueva se corrige solo.
6. Con sesión limpia, `diff`/`thr`/`momentum` estarán completas desde las 09:30 — hoy faltaban en
   **205 de 323 filas** y `|momentum|` no existía antes de las 14:34.

---

## 7. Números de referencia (baseline para comparar mañana)

| Magnitud | Valor 2026-08-10 |
|---|---|
| BD final | `ta_minute` 323 · `premium_minute` 18.732 · `walls_snapshot` 139 · `transitions` 95 (54 FLIP) · `strike_accum` 47 |
| Flips a favor | 1 min 43,2 % · 5 min 48,6 % · 15 min 52,2 % |
| Giros sin recorrido | 54 % con MFE ≤ 0 · duración mediana 4 min |
| Régimen | UP 53 min · DOWN 83 min · **LAT 109 min** |
| `atr_pct` | mañana 0,027–0,040 · tarde 0,015–0,019 · plano 0,0181 vs movimiento 0,0262 |
| Ancho `CW − PW` | 15 → 3 → 1 → 0 a lo largo del día |
| `gex_total` | 147–334 Bn · `regime` LONG el 100 % del día |
| Acumulado tarde | `netC − netP` ≈ **+7 M constante con mercado lateral** |
| Theta medido | ≈ −0,002 de prima/min |
| MarketSnack | Calls 54,9 % / Puts 45,1 % · Bid 46,9 % / **Mid 9,7 %** / Ask 43,4 % · Net GEX +$10,3 B · `Aggressive Opening` = 0 · `0DTE Momentum Spike` = 2 |
| Explosión de strike | 774P: OI 2.288 → volumen 74.139 = **32×** |

---

## 8. Riesgo principal

Un día, sucio, con **n = 2** episodios buenos. Hoy ya se cayeron tres hipótesis que parecían
sólidas. Cualquier condición que se invente separará 2 casos de 24 por puro azar. **Nada pasa a la
app hasta que un candidato sobreviva a 3-5 sesiones limpias con su tasa de falsos positivos
delante.**
