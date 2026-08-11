# ANTI-COMPACT — SPY Direction (contexto vivo para continuar)

> Léeme primero tras compact/clear. Proyecto **independiente**, local, NO tiene relación con el
> trading-bot del VPS. Idioma: español.
> **Carpeta ACTUAL: `C:\Users\eulis\proyectos\open-premium-ibkr`** (antes `C:\Users\17862\...`,
> otra máquina — los logs viejos del repo tienen esa ruta).

## 0. SESIÓN EN CURSO — LUNES 2026-08-10 (PRIMERA CORRIDA EN VIVO REAL)

Hoy es el "LUNES" que el resto de este documento marca como bloqueador. Estado a las 09:14 ET:

**VERIFICADO HOY (evidencia de log/ejecución, no memoria):**
- BD `spy_history.db` arrancó **VACÍA** (7 tablas en 0 filas). Todo lo de hoy es dato nuevo.
- Conexión IB Gateway clientId 7, modo **`[LIVE]`** (el `10197` del finde YA NO aparece).
- `Market data farm connection is OK:usopt` → OPRA conectado.
- SPY leído real (772.59 → 773.00). Cadena OK, `cercano=20260810` = **0DTE**.
- 68 líneas de market data suscritas: 2 señal + 2 ejecución + 24 baseline + **40 banda**.
- **Read-Only API DESACTIVADO** por el usuario. Antes daba `Error 321` + `open orders request
  timed out`; tras desmarcarlo, ambos desaparecieron → `openTrades`/`positions` YA responden.
- `accountSummary`: **$397.13** disponibles. 0 órdenes vivas, 0 posiciones (arranque limpio).
- `_can_afford` → True hasta $3.97/contrato (techo real por el tamaño de la cuenta).

**CAMBIOS DE CÓDIGO HECHOS HOY (orden explícita del usuario):**
- `TRADING_ENABLED = False` → **`True`** (línea 80). Rompe a propósito la regla dura §4.6
  ("arranca OFF"); el usuario lo pidió para que opere sin intervención. El botón sigue sirviendo
  para DESARMAR.
- Botón GUI conectado al estado real: arranca diciendo "DESARMAR" si `trading` es True.
- **Cold run diferencial VERDE (exit 0), idéntico al baseline previo al cambio.**

**AÚN NO VERIFICADO (se resuelve con el mercado abierto):**
- `pendingTickersEvent` + flujo `"233"` → que `net_call`/`net_put` dejen de ser 0. **Es el corazón
  del sistema y nunca ha recibido un solo trade real.**
- OI + gamma reales de la banda (`probe_oi_gamma.py`). Walls/GEX sigue verificado SOLO con FakeIB.
- `placeOrder` / `cancelOrder` / `reqContractDetails` (se ejercitan en la primera orden).

**7 GAPS LEÍDOS DEL CÓDIGO (ninguno arreglado — decisión: observar hoy, no tocar):**
1. 🔴 `:1490` **Sin reconexión.** `connected["ok"]` no vuelve a False en sesión → si cae el socket,
   la app queda muda, sin error ni log, hasta las 16:00.
2. 🔴 `:862` vs `:696` **Doble conteo** de `today_prem` en los 2 strikes ATM (`_on_ticks` y
   `compute_walls` escriben la misma clave con deltas independientes).
3. 🟠 `:545-546` **Strikes congelados** al precio de apertura (`setup_contracts` corre 1 vez/sesión).
   YA OBSERVADO en vivo: cambiaron al moverse SPY de 772.59 a 773.00.
4. 🟠 `:1516-1520` **Posición huérfana** si la venta de las 15:45 no llena antes de las 16:00
   (`end_session` cancela y desconecta). Con 0DTE = expira.
5. 🟡 `:880-882` **Momentum mide eventos, no tiempo** (`MOMENTUM_WIN=8` sobre `pendingTickersEvent`).
6. 🟡 68 líneas de market data vs límite IBKR ~100 (margen, pero sin espacio para añadir).
7. 🟡 `:1268` `_log_minute` hace INSERT OR REPLACE de 7 columnas sobre filas de 10 →
   **deja `net_prem`/`open_interest`/`gamma` en NULL** al colisionar con `_persist_walls`.

**Objetivo del día (dicho por el usuario):** ver que se guarden GEX, TA, precio del SPY; que
detecte los flips; que compre y venda. Recolectar, no arreglar.

### RESULTADO DE LA PRIMERA APERTURA EN VIVO (09:30-09:32) — VERIFICADO

**FUNCIONÓ (todo lo que estaba ❌ NO VERIFICADO):**
- Flujo de premium real: `GIRO -> UP (net_call=6236 net_put=315 thr=5000)`. La señal se alimenta.
- **OI + gamma REALES de IBKR**: `faltan OI=0 greeks=0 de 40 | gamma cambiaron=40/40`.
  El módulo Walls/GEX deja de estar verificado-solo-con-FakeIB. GEX +104Bn→+167Bn, flip 774.92→773.92,
  magneto dinámico SE MUEVE (771→772) mientras el estático no. 80 filas con OI y gamma en BD.
- **Ciclo completo de trading**: `FILL BUY PUT @0.90` → giro → `FILL SELL PUT @0.84 | PROFIT -6.00 (-6.7%)`.
- Reconexión (arreglo de hoy) verificada en vivo: `CONECTADO (sesion 2026-08-10)`.
- `spy_direction.log`: **0 errores**.

**🔴 GAP 9 (NUEVO, CRÍTICO) — ÓRDENES FANTASMA. Ya corregido:**
Se colocaron 4 BUY PUT (reqId 148-151). La app vio 1 fill y 1 venta y se creyó **FLAT**.
La realidad en IBKR: **3 puts abiertas** (`SPY 260810P00772000 qty=3.0`), que vaciaron la cuenta
(`Equity with Loan Value -253.53`). Causa: `trade_poll` trataba el estado `Cancelled` como
"no pasó nada" y liberaba `self.order` **sin comprobar `orderStatus.filled`** — entre el
`cancelOrder` y su confirmación la orden sigue siendo ejecutable y se llenó igual.
Como `self.pos` decía FLAT, el aplanado de 15:45 **jamás** habría cerrado esas 3 puts (0DTE).
Rompía las invariantes duras §4.2 ("jamás 2 limits vivas") y §4.3 ("una sola opción").

**REQUISITO DEL USUARIO (2026-08-10):** con capital bajo, **1 sola posición y 1 solo contrato**;
se cierra ese contrato y solo DESPUÉS se abre otro, sucesivamente.

**Correcciones aplicadas (cold run `gap9_coldrun.py`, 11 checks VERDE):**
1. `trade_poll`: si el estado es `Cancelled`/`ApiCancelled`/`Inactive` pero `filled > 0`,
   se procesa como FILL en vez de descartarse.
2. `_sync_pos()` (nuevo): cada `SYNC_POS_SECS=20` la posición REAL de IBKR sobrescribe `self.pos`
   y `pos_qty`, y reapunta `buy_call`/`buy_put` al contrato poseído. No toca `self.target`.
3. `_live_orders()` (nuevo) + guarda en `_place`: no se coloca ninguna orden si IBKR reporta
   alguna viva. La invariante deja de ser una suposición y pasa a ser una verificación.
4. Guarda dura en el BUY: se re-sincroniza contra IBKR y **no se compra si `pos_qty > 0`**.
5. `_place(..., qty)`: las VENTAS usan la cantidad REAL en cartera (vender QTY=1 con 3 lotes
   dejaba 2 huérfanos). `_on_filled` calcula el profit con la cantidad realmente llenada.
6. Si `pos_qty > QTY` se fuerza `target=FLAT` para aplanar el exceso.

**GAP 10 DESCARTADO (mi hipótesis era falsa):** `ta_minute=0` NO era un fallo silencioso de
`reqHistoricalData`. Probado contra IBKR: devuelve barras bien, pero con `useRTH=True` + `"1 D"`
solo trae las de HOY (10 barras a las 09:39) y `TAEngine` exige **≥26**. El TA está ciego los
primeros 26 minutos de CADA sesión — consecuencia de diseño, no bug. Pedir `"2 D"` lo resolvería.

**⚠️ PENDIENTE SIN RESOLVER — WHIPSAW:** 5 giros en 90 segundos (09:30:06 UP, :13 DOWN, :30 UP,
:37 DOWN, 09:31:14 UP). Con 0DTE cada rotación paga el spread. Además **GAP 5 confirmado en
producción**: `ALERTA WARN` y `ALERTA FLIP` se dispararon en el MISMO milisegundo (09:30:13,650)
— el aviso no anticipa nada. Falta calibrar `ADAPT_FRAC` y/o un mínimo de tiempo entre giros.

### TARDE 2026-08-10 (13:00-14:00) — GAP 17 + INSTRUMENTACIÓN DE OPERACIONES

**🔴 GAP 17 ACTIVO AHORA MISMO (VERIFICADO):** a las 13:26:37 IBKR mandó
`10182 reqId=1547 Failed to request live updates`. Las granjas se repusieron solas
(`2104`/`2106`); **el stream de barras NO**, y nadie lo repedía.
```
13:22:47 spot=773.12 | 13:25:49 spot=773.08 | 13:28:49 spot=773.03 | 13:56:05 spot=773.03
ta_minute CONGELADA en 13:24 (comprobado a las 13:57)
```
Efecto: `spy_price` congelado (su única fuente es `ta_poll` desde el GAP 11) → `walls_snapshot`
se sigue escribiendo con **spot falso** (GEX usa spot², flip mal), `refresh_strikes` re-centra
contra un precio muerto, y `ta_minute` deja de escribirse. La señal UP/DOWN y `_mid` **siguen
vivos** (vienen de ticks de opciones), así que **la app sigue operando sin que nada avise**.
La app se ve CONECTADA porque **lo está**: murió un stream, no el socket → `ib.isConnected()`
no sirve para detectarlo. **Decisión del usuario: no reiniciar; que el sistema se repare solo.**

**CÓDIGO NUEVO YA ESCRITO Y VERIFICADO, PERO *NO* ACTIVO** (la app corre el código viejo en
memoria; entra en el próximo arranque, que el usuario debe autorizar):
- **`trades`** (1 fila por operación: entrada, salida, greeks de entrada, **MFE/MAE + hora del
  máximo**, razón de salida) y **`posicion_minuto`** (recorrido del contrato: bid/ask/mid, P&L,
  greeks; filas `entrada`/`salida` siempre + `minuto` cada `POS_LOG_SECS=60`).
- **`cum_net`/`day_net`**: acumulado NETO firmado por strike, EN PARALELO al bruto (`cum_prem`
  NO se toca). El signo ahora se calcula para TODOS los strikes, no solo los 2 de señal.
  **`net_call`/`net_put` siguen sumando solo los de señal: la decisión NO cambia.**
- **`ta_minute`**: +`diff`,`thr`,`momentum` y flujo en ventana móvil **1/5/15 min**
  (`_flujo_ventana`), solo GUARDADO. La decisión sigue usando el acumulado desde 09:30.
- **GAP 17**: `_subscribe_bars()` (único punto de petición), detección por **frescura**
  (`_chequear_barras`, `BARS_STALE_SECS=120`) **y** por evento (`10182` en `_on_error`),
  reposición automática con backoff (`BARS_RETRY_SECS=30`), y `walls_snapshot.spot_stale=1`
  para marcar las filas escritas con spot muerto.
- **`_greeks_de(contract)`**: las greeks del contrato operado se leen del ticker **de la banda**.
  Motivo (VERIFICADO): los contratos de ejecución se piden con `genericTickList=""` y
  **ib_insync indexa los tickers por `id(OBJETO)`, no por conId** (`wrapper.py:79,168`), así que
  `ticker(buy_call).modelGreeks` es SIEMPRE `None`. Cero suscripciones nuevas.

**VERIFICACIÓN HECHA:** `posicion_coldrun.py` (nuevo, 49 checks VERDE, ejercita los métodos
reales) · **diferencial 12/12 suites idénticas** al baseline (la única diferencia, `2.5s`
vs `2.6s` en fase1, se reproduce con el MISMO código → ruido de reloj) · migración sobre
**copia de la BD real**: 0 filas perdidas, idempotente, `integrity_check: ok`.
**NO VERIFICADO:** que `_greeks_de` devuelva greeks reales contra IBKR (necesita mercado
abierto y arranque). Hasta entonces es HIPÓTESIS FUERTE, no hecho.

**DATOS DE HOY (corrigen la 1ª versión de `ESTADO_HOY.md`):** 52+ FLIPs (no 39-42);
5 huecos de minuto (no 2). **Coste de girar crece con el día** — giros/hora 17→20→12→3 y a las
12:36 hacían falta 2,81 M de flujo nuevo (más que el generado en todo el día): `diff` es
acumulado desde 09:30 y `thr = ADAPT_FRAC*(|net_call|+|net_put|)` crece con él.
**Episodio del PUT 12:20** (la razón de todo esto): entrada 0.80 → **pico 2.10 (+130 $)** a las
12:43, >100 $ durante ~13 min → vendido a 1.25 (+45 $) a las 13:01, **18 min después del
máximo**. 85 $ dejados sobre la mesa. Ese recorrido solo existía en el log como texto.

### TARDE-2 (14:30-15:30) — 5 arreglos más, sello de sesión y ANÁLISIS

**Arreglados y verificados (14 suites verdes, activos desde el arranque de las 14:52):**
GAP 2 (doble conteo del premium en los strikes de señal) · GAP 4 (cruce de spread a las 15:50
para que la 0DTE no expire) · GAP 5 (momentum por **30 s reales**, `diff_hist` eliminado) ·
M2 (P&L realizado desde IBKR) · M12 (`tif='DAY'`) · panel que decía `trading OFF` estando
armado · **`sesion_config`** (no tenía escritor: 0 `INSERT` en todo el archivo) ·
**premium por vela** (`prem_call_min`/`prem_put_min`/`net_*_min`) · **contexto de entrada**
(16 columnas en `trades`).

**🔴 GAP 18 NUEVO, SIN ARREGLAR:** al arrancar, el market data de la señal se suscribe ANTES de
que `_load_intradia` restaure → ~4 s con el umbral en el piso de 5.000 → **giro espurio**
(`14:52:29 GIRO -> DOWN thr=5000`). Ya causó daño real por la mañana. Ensucia `transitions`.

**ANÁLISIS (detalle completo en `ANALISIS_ENTRADA_SALIDA.md`):**
- **El premium NO anticipa** el movimiento a 1 min: todos los lags predictivos ≤0; máximo
  +0,203 en lag **−2** (va detrás). La entrada de 1,1 M de las 12:36 ocurrió con el SPY
  movido −0,01. *Limitación: haría falta resolución por segundo para zanjarlo.*
- **El TA tampoco**: 50,2% vs 49,6% del premium.
- **Compresión de Bollinger: DESCARTADA** (1,17x sobre una tasa base del 86%).
- ✅ **Predecir el mercado PLANO sí funciona**: `atr_pct` (−0,83), `abs_momentum`
  (284 vs 17.211), `abs_dist_flip` (−0,43). **Direccionalmente neutras.**
- ⚠️ Los predictores de movimiento brusco (OBV −1,00, %B, EMAs, `dist_vwap`) están
  **contaminados** por el sesgo bajista del día (63% de los movimientos grandes fueron bajistas).
- **Líneas de market data: 68 de ~100** (2 señal + 2 ejecución + 24 baseline + 40 banda),
  0 errores de límite en toda la sesión.

### TARDE-3 (15:30-16:15) — cierre del día, 3 arreglos más

- ✅ **GAP 18 ARREGLADO** (guard `_intradia_ok` en `_update_signal`, excluye demo). Verificado
  en vivo: el arranque de las 15:23 y el de las 15:57 ya **no** dispararon giro espurio.
- 🔴 **GAP 19 — NUEVO, detectado en vivo y ARREGLADO.** En el aplanado de las 15:45, con el
  `EOD_REPRICE_SECS=1.5` que se introdujo esa tarde:
  ```
  15:45:01 SELL @0.32 (1955) · 15:45:06 code=10148 PendingCancel
  15:45:09/13/17/21 (1956-1959) -> las 4 RECHAZADAS por margen (15.493 USD)
  15:45:22 la ORIGINAL 1955 se llena igual
  ```
  **Causa (verificada en ib_insync):** IBKR reportó `Cancelled` —estado FINAL, en `DoneStates`—
  así que salió de `openTrades()`, `_live_orders()` la dio por muerta y se colocó encima.
  **No había ningún estado que consultar que lo evitara: la única defensa es el tiempo.**
  Arreglo: `CANCEL_SETTLE_SECS=10` + `EOD_REPRICE_SECS` 1,5 → **12 s** + traza de estados.
  *Mi error: el dato (latencia mediana 1 s, cola 25 s) ya estaba en M1 y no lo apliqué.*
- ✅ **GAP 17-bis**: `_subscribe_bars` limpiaba `bars_stale` al **pedir** el stream, no al ver el
  dato avanzar → `spot_stale=0` con el spot congelado en 773.07. Ahora la limpia solo
  `_chequear_barras` cuando `bars[-1].date` avanza de verdad.
- ⚠️ **`CLOSE_HHMM=16:15`** (era 16:00): se recolecta 15 min más, **sin operar** (verificado en
  cold run: a las 16:05, 0 órdenes y `target=FLAT`). Medido: +52.000 vol y ~1,6 M de premium que
  antes se tiraban, **pero con 0/40 griegas moviéndose** → es reporte TARDÍO del cierre, no
  negociación nueva. Queda fechado 16:00-16:15: **trampa nº7** del análisis.

**Cierre verificado:** `16:15:01 MERCADO CERRADO` con `_persist_accum` final · 0 órdenes ·
0 huérfanas · 0 `ALERTA EOD` · cuenta plana · `integrity_check: ok` · 3 sesiones selladas.
**BD final:** ta=323 · premium=18.732 · walls=139 · giros=95 · strike_accum=47.
**`trades` y `posicion_minuto` siguen en 0 filas**: la única posición del día se compró con el
código viejo. La primera operación registrada será la próxima compra.

### POST-CIERRE 2026-08-10 — CUENTA PAPER RESETEADA A ~$400

El usuario reseteó la cuenta paper de IBKR y la repuso a **$400** (la app y el Gateway ya cerrados).

- **VERIFICADO (código):** el saldo del panel (`Cuenta $X   disp $Y`) sale de
  `_read_account()` → `self.ib.accountSummary()` → tags `NetLiquidation` y `AvailableFunds`.
  **La fuente es IBKR, no un cálculo interno.** El bucle lo relee cada 10 s (`spy_direction.py:3032`)
  y SOLO dentro de `if app.ib.isConnected()` (`:3005`).
- **VERIFICADO (ib_insync `ib.py:1869-1896`):** `accountSummary()` es una **suscripción**
  (`reqAccountSummary`, nunca cancelada); la app lee un caché que **actualiza IBKR** cuando quiere.
  Los 10 s son la cadencia de LECTURA, no la de refresco del dato.
- **⚠️ VERIFICADO (BD):** `estado_intradia` de hoy tiene `acct_net_open = 297.04`. Si se relanza
  la app **el mismo 2026-08-10**, `_load_intradia` (`:1171`) restaura esa base y el panel mostraría
  **`DIA +102.96 (+34.6%)`** — que es el DEPÓSITO, no ganancia. Con fecha nueva (11-ago) no hay fila:
  `acct_net_open` queda None y la base del día será la 1ª lectura (400) → correcto.
- **NO VERIFICADO:** si el reset de cuenta paper corta/invalida la sesión del Gateway. Irrelevante
  hoy (todo cerrado), pero si algún día se resetea con la app viva, hay que confirmarlo.
- Efecto en `_can_afford` (`:2045`): con ~$400 el techo vuelve a ser ~**$4,00 por contrato**.

### POST-CIERRE 2026-08-10 — ANÁLISIS vs MARKETSNACK → `HIPOTESIS_2026-08-10.md`

Se cruzó nuestra BD contra MarketSnack (Gamma Exposure + Flow Feed del SPY). **Todo el detalle está
en `HIPOTESIS_2026-08-10.md` — leerlo antes de proponer nada sobre entradas/salidas.** Resumen:

- **VERIFICADO — el flip a horizonte fijo es una moneda:** 43,2 % a favor a 1 min · 48,6 % a 5 min ·
  52,2 % a 15 min. **54 % de los giros nunca estuvieron a favor ni un centavo.** 2 de 26 episodios
  (10:50 y 12:20) se llevan todo el recorrido. No es un problema de salida: se entra 24 veces de más.
- **VERIFICADO — theta medido:** ≈ −0,002 de prima/min. Con delta ~0,45 el SPY debe moverse
  ~0,0044/min solo para empatar; la mediana real a 5 min es −0,08, **en contra**.
- **VERIFICADO — el día en tramos:** UP 53 min · DOWN 83 min · **LATERAL 109 min**.
- **4 HIPÓTESIS (NO concluyentes, n=2):** H1 el régimen lo marca el **ancho CW−PW** (15→0 durante el
  día) · H2 la decisión debe usar **flujo nuevo** (`net_*_5m/15m`, ya guardado y sin usar) y no el
  acumulado (por la tarde +7 M constante con mercado lateral) · H3 el "evento" es **acumulación
  sostenida en un strike** (774P: OI 2.288 → vol 74.139 = **32×**), no un print gigante · H4 lo
  único operable es el **filtro negativo: no entrar en lateral**.
- **MarketSnack, lo NO replicable** (verificado en `:1601-1646`): prints individuales (`dvol` agrega
  varios trades), multi-leg vs single-leg, y Buy/Sell explícito (nosotros lo *inferimos*). Su
  **Mid 9,7 %** sirve de control de nuestra inferencia de agresor. Su Net GEX +$10,3 B vs nuestro
  +$334 B con selector `Per 1% move` → **NO VERIFICADO** de dónde sale el factor.

**🚫 DESCARTES DE HOY — no volver a proponerlos sin datos nuevos:**
1. **Salto de wall como predictor:** 5 min 28 % vs 14 %, 10 min 44 % vs 39 %, **15 min 56 % vs 59 %
   (peor que nada)**. 20 de los 22 saltos son de ±1 strike = ruido. El único grande (10:50) es n=1.
2. **`obv` / `dist_vwap` / `spy−ema8`:** contaminados — el 63 % de los movimientos grandes del día
   fueron bajistas. `obv` da separación **−1,00 perfecta**, que es una alarma, no un hallazgo.
3. **Take-profit fijo:** ya descartado; ningún objetivo de +0,10 a +1,00 mejora esperar al flip.

**LECCIÓN:** cada hipótesis se veía bien mirando primero los 2 casos buenos; todas se cayeron al
contrastarlas contra los 100+ restantes. **Ninguna variable entra en producción sin su tasa de
falsos positivos delante.**

### 2026-08-11 MAÑANA — experimento PRE-MARKET (probado y REVERTIDO) + estado

**🚫 PRE-MARKET: PROBADO CON DATOS REALES Y DESCARTADO. No volver a intentarlo a ciegas.**
Entre las 09:00 y las 09:07 ET se bajó `OPEN_HHMM` de "09:30" a "09:00" para ver si el pre-market
daba algo guardable. **NO da nada:**
```
de 68 filas de premium_minute:  day_vol>0 -> 0 | day_prem>0 -> 0 | gamma!=0 -> 0 (griegas None)
                                OI>0 -> 66, pero es el OI de AYER (EOD, estatico)
ta_minute -> 0 filas (sin barras useRTH=True no hay TA ni precio)
walls_snapshot -> GEX=0 · regime=FLAT · spot=773.07 (CIERRE DE AYER) y con spot_stale=0
```
Lo llamativo: `_read_price(SPY)` SÍ devolvía **774.23** en vivo, pero las walls escribían 773.07,
porque `spy_price` no sale de ahí sino de `ta_poll` (barras), que no existen antes de las 09:30.
**El daño no era el vacío sino el falso positivo:** filas en cero marcadas como válidas
(`spot_stale=0`, porque la bandera arranca en False y sin barras nunca se marcó sucia).
No es comparable a los 15 min de después del cierre: allí hay reportes TARDÍOS de operaciones
reales; en pre-market OPRA no ha abierto y no existe nada que reportar.
**Si algún día se reintenta hace falta ANTES:** barras con `useRTH=False` y marcar esas filas como
pre-market para poder excluirlas.

**REFACTOR QUE SÍ SE QUEDÓ (verificado, 15/15 suites verde):** se separaron las ventanas que el
código ya trataba por separado pero con literales duplicados:
- `OPEN_HHMM = "09:30"` → RECOLECCIÓN (`is_market_open`).
- `RTH_OPEN_HHMM = "09:30"` → apertura real. Gobierna **(a)** el trading (`in_session` en
  `trade_poll:2534`, antes literal `"09:30"`) y **(b)** la vigilancia de barras del GAP 17.
- **`is_rth()` NUEVO**: es lo que `is_market_open()` significaba antes. `_chequear_barras` y el
  repetidor del stream la usan, para que ampliar la recolección nunca genere un GAP 17 falso.
- Suite nueva **`coldruns/ventana_horaria_coldrun.py`** (deriva las expectativas de las constantes
  reales, así sigue valiendo si cambian). Ejercita `trade_poll` REAL: demuestra que fuera de RTH
  no se coloca ninguna orden.
- ⚠️ **El diferencial cazó una falsa regresión y por eso se hace:** `posicion_coldrun` bajó de 72 a
  70 porque hacía `app.is_market_open = lambda: True` (líneas 374 y 439) y esa rama pasó a
  `is_rth()`. Se actualizó el test (no era bug de producción). Volvió a 72.

**BD LIMPIADA (autorizado por el usuario):** se borraron las 108 filas de `premium_minute` y 3 de
`walls_snapshot` de hoy con `hora<'09:30'`. Los conteos volvieron EXACTAMENTE a los del cierre de
ayer (ta=323 · premium=18.732 · walls=139 · giros=95 · strike_accum=47), `integrity_check: ok`.
Copia previa en **`spy_history_backup_pre-limpieza_20260811.db`**.

**✅ VERIFICADO — el acumulado de ayer SÍ se hereda (y es correcto):** `setup_contracts:992` llama
a `_load_accum():1009`, que carga `strike_accum` entero en `self.accum`/`self.accum_net`. La expiry
**20260811 (0DTE de hoy) arranca con 45,5 M de `cum_prem`** de ayer, cuando era la 1D del baseline
(773C 9,36 M · 773P 7,53 M · 774P 6,58 M).
- **La SEÑAL no se ve afectada:** `net_call`/`net_put` las pone a 0 `reset_day()`.
- `today_prem`/`today_net` (→ `day_prem`) también arrancan en 0.
- Es lo correcto para la tesis del Open Premium (la curva del contrato viene desde que nace), pero
  **para análisis intradía hay que usar `day_prem`, NUNCA `cum_prem`**.
- Higiene menor: `strike_accum` conserva la expiry 20260810 ya vencida (8 strikes, 132 M). No
  molesta pero crece indefinidamente.

### 2026-08-11 — NO SE ABRE EN LOS PRIMEROS 5 MIN (`START_TRADE_HHMM = "09:35"`)

Petición del usuario: que el sistema **espere 5 min tras la apertura** antes de comprar, para ver
cómo se forma el acumulado y no reaccionar al ruido. **Respaldado por los datos del 10-ago:** en los
primeros 90 s hubo **5 giros** (09:30:06 UP · :13 DOWN · :30 UP · :37 DOWN · 09:31:14 UP), porque
`thr = ADAPT_FRAC*(|net_call|+|net_put|)` cae al piso `SIGNAL_THRESHOLD=5000` con el acumulado
vacío — ~100x menos que el umbral maduro (1,2 M). Es el gap **M6** por la vía barata: en vez de
rediseñar el umbral, no operar mientras no sea fiable.

```python
START_TRADE_HHMM = "09:35"                      # junto a STOP_NEW_HHMM
stop_new = ((not in_session)
            or (weekday and hhmm >= STOP_NEW_HHMM)
            or (weekday and hhmm < START_TRADE_HHMM))   # <- el termino nuevo
```
- **NO se tocó `in_session`** a propósito: significa "el mercado está en sesión", no "puedo abrir".
- **Las VENTAS no pasan por `stop_new`** → una posición se puede cerrar durante la espera
  (verificado: *"09:31 con posición y target=FLAT → SÍ VENDE"*).
- **La señal y la recolección siguen desde las 09:30** (`_on_ticks` es independiente de
  `trade_poll`): el acumulado se forma igual, solo no se opera sobre él todavía.
- `trade_msg` ahora distingue la espera del EOD (antes habría dicho "(EOD)" a las 09:31, mentira).
- **Verificado:** 15/15 suites, las 14 originales con conteos IDÉNTICOS al baseline;
  `ventana_horaria` 31 → 39 checks.
- ⚠️ Aviso metodológico: 3 de esos checks pasaban **trivialmente** (`msg=''`) porque el mensaje solo
  se escribe cuando `pos == target`. Corregido forzando `pos==target==FLAT`. **Un verde sin dato
  observable impreso es indistinguible de un verde vacío** — que los checks impriman el valor real.

**Nota de arranque (VERIFICADO):** `try_connect` se llama SOLO desde `:3062`, dentro de la rama
`elif app.is_market_open():` de `tick()`. La app **no conecta al arrancar**: lanzarla antes de las
09:30 es correcto y espera sola. No hay socket hasta la apertura — eso NO es un fallo.

### 2026-08-11 APERTURA — resultados en vivo + GAP 20 y rotación del log

**✅ EL RETRASO DE 5 MIN FUNCIONÓ AL SEGUNDO.** 4 giros en la ventana de espera
(09:30:14 UP · 09:30:28 DOWN · 09:33:38 UP · 09:34:34 DOWN) y **ninguna orden**. Primera orden:
`09:35:00,085 BUY PUT x1 LIMIT MID @1.10`. Cuatro rotaciones de spread+theta evitadas.

**✅ `trades` y `posicion_minuto` VERIFICADOS EN VIVO con griegas reales** — era lo único que
quedaba NO VERIFICADO de todo el trabajo del 10-ago:
```
trade #1 CALL 773 @1.34 | delta=0.5034 gamma=0.1245 theta=-1.2794 iv=0.1515
         spy=773.05 min_sesion=5 GEX=102.8Bn regime=LONG dist_flip=-1.97 CW=-1.95 PW=+0.05
posicion_minuto: entrada 09:35:54 mid=1.34 -> minuto 09:36:55 mid=1.38 pnl=+4.00
```

**✅ EL ARREGLO DEL GAP 9 SE AUTOCORRIGIÓ EN VIVO.** La orden 2134 se reportó `Cancelled` con
`filled=0.0` y **se llenó igual**:
```
09:35:08 Cancelled (id=2134 filled=0.0) · 09:35:12 EXEC REAL BOT ...P00773000 x1 @1.10 (id=2134)
09:35:12 SYNC posicion REAL de IBKR=PUT x1 | la app creia FLAT x0 -> corregido
09:35:12 Entrada recuperada de IBKR (avgCost=111.04) -> 1.1104
```
Detectado y adoptado en **4 s**. El 10-ago ese mismo fallo dejó 3 puts huérfanas y vació la cuenta.

**✅ GAP 5 mejorado:** WARN anticipó al FLIP **20 s** (09:34:14→09:34:34) y **10 s**
(09:35:05→09:35:15). El 10-ago salían en el mismo milisegundo.
*(Ojo al leer `transitions`: hay filas `WARN` y `FLIP`; sin mirar la columna `tipo` parecen giros
duplicados — no lo son.)*

**🔴 GAP 20 NUEVO — ARREGLADO, PENDIENTE DE ACTIVAR (entra en el próximo arranque).**
La posición adoptada por `_sync_pos` **no abría fila en `trades`**: el PUT 773 comprado a 1.1104 y
vendido a 1.12 (**+0.96**) no dejó rastro ni en `trades` ni en `posicion_minuto`. Se perdía el
recorrido de TODA posición recuperada de un fill fantasma.
- **Arreglo:** en `_sync_pos`, si `real in (CALL,PUT)` y `trade_id is None` → `_trade_abrir()` con
  el contrato adoptado y el `entry_price` del `avgCost`. Es el **simétrico exacto** del cierre
  `"externa"` que ya existía. Si no hay ni avgCost ni MID, **no se abre fila y no se inventa precio**.
- **La operación perdida se insertó A MANO** en `trades` (`trade_id=2`, cronológicamente anterior
  al #1). Solo con datos verificados del log; greeks, contexto y mfe/mae quedan **NULL a propósito**
  y `razon_salida` lo declara: **no usar esa fila para estadísticas de recorrido**.

**🔴 ROTACIÓN DEL LOG — ARREGLADA, PENDIENTE DE ACTIVAR.** En Windows no se puede renombrar un
fichero que otro proceso tiene abierto: `doRollover()` lanzaba `PermissionError`, el handler dejaba
el stream cerrado y **el logging quedaba mudo en silencio**. Pasó hoy de 09:00 a 09:32 (32 min de
traza perdidos) porque **el monitor de Claude tenía abierto `spy_activity.log`**. La BD no se vio
afectada.
- **Arreglo:** clase `_RotacionTolerante(TimedRotatingFileHandler)`: si la rotación falla, reabre el
  fichero, sigue escribiendo y **deja constancia del fallo en el propio log**.
- **Lección para monitorizar en Windows:** abrir, leer y **cerrar** en cada pasada. Nunca mantener
  el handle abierto sobre un log que alguien rota.

**Verificación de ambos:** `coldruns/gap20_coldrun.py` (23 checks, funciones reales: `_sync_pos`,
`_trade_abrir`, `_pos_snapshot`, `doRollover`) · **diferencial 16 suites, las 15 previas con
conteos IDÉNTICOS**.

### DECISIONES YA TOMADAS — no volver a proponerlas

- **Botón de venta manual en la GUI: RECHAZADO por el usuario** (2026-08-10).
  Motivo textual: *"ese botón después me tienta a presionarlo y comienzo a limitar ganancia;
  tenemos que tratar de detectar esos momentos de compra y venta con los datos, es mejor"*.
  La idea era buena técnicamente (reutilizaba toda la maquinaria de `_place`), pero introduce
  una decisión discrecional que sesga el resultado. **El objetivo es deducir la salida de los
  datos, no delegarla en el criterio del momento.**
- **Take-profit fijo, cambio de la señal a ventana móvil y multi-ticker**: aplazados hasta tener
  3-5 sesiones de datos. Ver `ANALISIS_ENTRADA_SALIDA.md` §5 y §7.

## 1. QUÉ ES / OBJETIVO
App de **1 archivo** (`spy_direction.py`, ~1000+ líneas) para **scalping de SPY** vía flujo de
opciones. Se conecta a **IB Gateway (paper, puerto 4002, clientId 7)** con `ib_insync`.
- **Señal:** vencimiento MÁS CERCANO, strikes ATM/ITM (call≤precio, put≥precio) → net premium
  call vs put (por Δvolumen×precio, agresor por bid/ask) → umbral **ADAPTATIVO** → estado UP/DOWN.
- **Alertas:** banner en pantalla + **toast de Windows** en cada GIRO confirmado (via PowerShell).
- **Ejecución (si TRADING ON):** rota **1 sola opción** (compra el lado nuevo, vende el viejo).
- **TA 1 min** (RSI/EMA/MACD/BB/ATR/VWAP/OBV, réplica del bot) — solo informativo/registro.
- **Baseline** de premium por strike de expiraciones FUTURAS (para "valor del día siguiente").
- **Registro por minuto** en SQLite + **2 logs** de texto.
- Origen de la teoría: MarketSnack "Open Premium" (ver `PROMPT_AGENTE.md`).

## 2. ESTADO (VERIFICADO / NO VERIFICADO) — R7
- ✅ Conexión IB Gateway, lectura de precio (fallback LIVE→FROZEN→DELAYED), cadena, selección de
  strikes señal (ATM/ITM) y ejecución (OTM) — probado contra paper (cuando había datos).
- ✅ Cálculo señal + umbral adaptativo, alertas/banner/toast — headless + smoke GUI.
- ✅ TAEngine (indicadores idénticos a pandas) + registro por minuto (`ta_minute`,`premium_minute`) — headless + 390 barras reales leídas.
- ✅ Ejecución: LIMIT SIEMPRE al MID, 1 sola orden, SELL relentless, BUY con timeout, sin
  huérfanas — **headless completo** (máx 1 orden viva; secuencia BUY→SELL→BUY correcta; strike OTM).
- ✅ Plumbing de órdenes en paper: placeOrder+cancel, 0 colgadas, buying power $397.13 leído.
- ✅ `compute_walls_from_oi` (Put/Call Wall + Max Pain) — **headless** (put_wall/call_wall/max_pain OK).
- ✅ **WALLS/GEX/FLIP IMPLEMENTADO (2026-08-09, informativo)** — funciones puras `_max_pain`,
  `compute_gex_from_greeks` (GEX+regime+gamma_flip proxy), `compute_prem_center`; método real
  `compute_walls()` + `_persist_walls()`; tabla `walls_snapshot`; `premium_minute` +net_prem/OI/gamma;
  panel GUI; logs exhaustivos + staleness. **Cold run headless VERDE** (`spy_walls_coldrun.py`,
  ejercita el método real con FakeIB: walls, GEX signo, flip, magneto estático/dinámico que SÍ se
  mueve, persistencia BD, staleness). Compila OK.
- ❌ **NO VERIFICADO en vivo (LUNES apertura):** flujo real de trades (fills, rotación, aplanado
  15:45), llenado de `premium_minute`/`strike_accum`, **OI+gamma reales de IBKR** para Walls/GEX
  (correr `probe_oi_gamma.py` primero), frescura real del gamma en streaming, y que el flip/GEX/
  magneto sean coherentes con el precio. Bloqueado por mercado cerrado + `10197` (ver §7).

## 3. ARCHIVOS
- `spy_direction.py` — la app (único código).
- `dist/spy_direction.exe` — ejecutable (se genera; ~56MB, incluye pandas+tzdata).
- `install.bat` / `build_exe.bat` — instalar/empaquetar (`--collect-all tzdata`).
- `MANUAL.md`, `GUIA_AGENTE.md`, `GUIA_MONITOR.md` (con diagrama de flujo), `PROMPT_AGENTE.md`,
  `README.txt`, `LEEME_PRIMERO.txt`.
- `spy_history.db` — SQLite. Tablas: `transitions`, `strike_accum`, `strike_daily`,
  `ta_minute`, `premium_minute`. (Falta crear `walls_snapshot` cuando se implemente Walls.)
- `spy_activity.log` (actividad exhaustiva) / `spy_direction.log` (errores).
- `spy_direction_paquete.zip` — paquete Gmail-safe (bats renombrados a .txt).

## 4. REGLAS DE EJECUCIÓN (DURAS — ya implementadas, NO romper)
1. **SIEMPRE `LimitOrder` al MID** = round((bid+ask)/2, minTick). NUNCA market/bid/ask. Si no hay
   bid/ask, `_mid()` devuelve None y NO coloca (espera). (`_mid`, `_place`.)
2. **Reintenta hasta llenar:** al vencer `REPRICE_SECS` solo CANCELA; recotiza al MID nuevo cuando
   el cancel se confirma → **jamás 2 límits vivas** (no short). SELL nunca se rinde; BUY abandona
   tras `MAX_FILL_SECS` (queda FLAT). (`trade_poll`.)
3. **Una sola opción / cero huérfanas:** `_cancel_working()` al arrancar (`_reconcile`) y al cerrar;
   `_reconcile` aplana si hay >1 posición.
4. **Strike que se OPERA = ATM del lado OTM** (call 1er strike >precio; put 1er strike <precio):
   `self.buy_call`/`self.buy_put`. La SEÑAL sigue en ATM/ITM (`self.call`/`self.put`). Delta OTM ~0.40-0.48.
5. **EOD 15:45 ET** aplana al MID (relentless, sin cruzar spread). `STOP_NEW 15:40` no abre nuevas.
6. **TRADING arranca OFF**; botón ARMAR/DESARMAR en la GUI. Paper (4002).

## 5. CONFIG (arriba de `spy_direction.py`)
`PORT=4002` (paper; live=4001) · `CLIENT_ID=7` · `QTY=1` · `SIGNAL_THRESHOLD=5000` (piso) ·
`ADAPTIVE=True`, `ADAPT_FRAC=0.15`, `MOM_FRAC=0.6` · `REPRICE_SECS=4`, `MAX_FILL_SECS=60` ·
`FLATTEN_HHMM=15:45`, `STOP_NEW_HHMM=15:40` · `ITM_DEPTH=3`, `BASELINE_EXPIRIES=3`,
`SNAPSHOT_SECS=120` · `WALLS_BAND=10`, `WALLS_RECALC_SECS=180` · `TRADING_ENABLED=True`.
(CORREGIDO 2026-08-10: este parrafo decia `WALLS_BAND=20`/`WALLS_REFRESH=900`, nombres y valores
que NO existen en el codigo. Los reales son los de arriba, verificados en `spy_direction.py:88-89`.)

## 6. CÓMO CORRER / PROBAR
- Real: `python spy_direction.py` (o `dist\spy_direction.exe`). Demo: `--demo`. Diagnóstico: `--selftest`.
- Build exe: `install.bat` (o `python -m PyInstaller --onefile --windowed --name spy_direction --collect-all tzdata --clean spy_direction.py`).
- Deps: `ib_insync pandas tzdata pyinstaller` (ya instaladas en esta PC).
- Cold run headless de órdenes: usar FakeIB (patrón en el historial); asertar precio==MID, ≤1 orden viva.

## 7. IBKR — GOTCHAS IMPORTANTES
- **`10197 "No market data during competing live session"`**: hoy bloquea TODO el market data
  (precio + OI) en todos los modos (1/2/3/4), aun sin otra sesión del usuario → es
  **indisponibilidad de datos de finde de IBKR** (mantenimiento). Granjas/cuenta/secdef SÍ OK.
  El precio a veces salió (frozen 773.37 / live 772.45) y otras NaN → intermitente en finde.
  **El lunes con mercado abierto se resuelve.**
- **Usar SIEMPRE clientId 7** y desconexión limpia (no crear muchos clients; ensucian el Gateway).
- API en Gateway: Configure→Settings→API: Enable Socket, puerto 4002, Trusted IP 127.0.0.1.
- Datos de opciones OI = **end-of-day** (no intradía). El usuario tiene add-on de opciones OPRA
  ($4.50) → real-time debería entrar el lunes.
- `reqTickByTickData("AllLast")` NO soportado para opciones (error 10189) → se usa RTVolume "233".

## 8. PENDIENTE (para el LUNES en la apertura, 9:30 ET)
1. **Validar en vivo:** app muestra `[LIVE]`; net_call/net_put reales; giros coherentes con SPY;
   `ta_minute`/`premium_minute`/`strike_accum` se llenan; alertas/toasts.
2. **Trading en paper:** ARMAR; verificar rotación 1 opción al MID, fills, invariante 1-posición,
   sin huérfanas, aplanado 15:45. Revisar `spy_activity.log` y `spy_direction.log` (0 errores).
3. **Calibrar `ADAPT_FRAC`** con la magnitud real del flujo (millones) para que no parpadee.
4. **WALLS/GEX/FLIP: ya IMPLEMENTADO (§9).** El LUNES: (a) correr `probe_oi_gamma.py` con mercado
   abierto → confirmar OI+gamma reales; (b) si OK, arrancar la app, ver poblarse el panel Walls/GEX y
   la tabla `walls_snapshot` + `premium_minute` (net_prem/OI/gamma); (c) revisar staleness en
   `spy_activity.log` (aviso si gamma no cambia); (d) validar signo GEX/regime/flip vs el precio real.
5. **Ya NO se manda Gmail.** El proyecto se comparte por **repositorio GitHub** (ver §12) con doc
   exhaustiva para el otro agente.

## 9. WALLS / GEX / GAMMA FLIP — IMPLEMENTADO 2026-08-09 (informativo, "como el TA")
Diseño final (aprobado por el usuario; plan en `~/.claude/plans/structured-pondering-noodle.md`):
- **Rol:** SOLO informativo — panel + registro por minuto/cada 3 min en BD + logs. NO toca la señal
  UP/DOWN ni la ejecución. Propósito: acumular datos y cruzarlos contra la gráfica para decidir CÓMO
  usarlos (y afinar la precisión de los cambios de dirección). Quedan vivos en `self.walls`/`self.gex`.
- **Fuente:** IBKR (NO massive — el bot del VPS ya no existe y no tenía esto). Banda ±`WALLS_BAND=10`
  strikes de `self.expiry` (la cercana), **STREAMING persistente** (`reqMktData "100,101,106"`,
  snapshot=False → no repite requests, no satura) suscrito en `setup_contracts` (`self.band_contracts`).
- **Recálculo cada `WALLS_RECALC_SECS=180`s (3 min):** `compute_walls()` lee los tickers vivos
  (`callOpenInterest/putOpenInterest`, `modelGreeks.gamma`, volume/last/bid/ask), computa y persiste.
- **Métricas:** PW=máx putOI, CW=máx callOI; **Magneto estático** (`_max_pain` con OI-EOD) y
  **dinámico** (`_max_pain` con OI+volumen intradía, sí se mueve); **prem_center** (centro de peso por
  premium bruto por strike = "hacia dónde hay dinero"); **GEX** (`compute_gex_from_greeks`:
  gex_total=Σ100·spot²·(+γc·OIc −γp·OIp), regime LONG/SHORT) y **Gamma Flip** (proxy: cruce por cero
  de la acumulada del GEX por strike, interpolado).
- **net_prem por strike:** premium neto firmado (agresor bid/ask) del Δvolumen entre lecturas de 3 min
  (NO toca `_on_ticks`; la señal queda intacta). Aproximación a resolución 3 min.
- **Persistencia:** tabla `walls_snapshot(fecha,hora,expiry,spot,put_wall,call_wall,max_pain_static,
  max_pain_dyn,prem_center,gex_total,regime,gamma_flip)` + `premium_minute` extendida con
  `net_prem,open_interest,gamma` (migración ALTER TABLE para BD viejas).
- **Staleness:** cada recálculo cuenta cuántos gamma cambiaron + hora del último tick; avisa en el log
  si nada cambió (posible dato viejo). IBKR: OI=EOD (siempre "de ayer", inevitable); gamma/vol=vivo.
- **Convención signo GEX = +call/−put:** HIPÓTESIS estándar, NO verificable con IBKR → validar vs
  precio real antes de accionar. `GEX_CALL_SIGN/GEX_PUT_SIGN` parametrizables.
- **Verificación:** `spy_walls_coldrun.py` (headless, VERDE) ejercita las puras + el método real.
  Falta LUNES en vivo: `probe_oi_gamma.py` (OI+gamma tick "100,101,106" snapshot ATM±5) + validar panel.
- **Gaps (R14):** límite de líneas IBKR (~100) con la banda + señal/ejec/baseline → si excede, bajar
  `WALLS_BAND`. Greeks NaN fuera de RTH. Escala GEX en miles de millones (panel muestra /1e9 "Bn").
- **Gamma Ladder VISUAL (2026-08-09, estilo MarketSnack, SOLO lectura):** Canvas Tkinter con barras
  de **premium $ por strike** de la banda (verde si strike≥precio, rojo si <), etiquetas **CW/PW/MAG**
  (magneto en morado), y en un **carril izquierdo propio** (no encima de las barras) las rayas de
  **precio+UP/DOWN**, **Gamma Flip** y **contrato comprado**. Método `ladder_rows()` + `_draw_ladder()`
  (cold run VERDE, dibujo Tk verificado headless). Sin botones. El **precio del contrato se actualiza
  en vivo** (`_mid`) y la raya se pone **verde/rojo** según suba/baje desde la entrada; aparece solo si
  `self.pos`≠FLAT y desaparece al vender. **Notificaciones (toast):** en cada giro y en el **FILL real**
  (`_on_filled`) de compra/venta; al vender el toast trae el **profit $/%**. `--demo` puebla datos
  sintéticos (`_demo_walls`) para previsualizar; el PnL del demo es decorativo (senos desacoplados).
  NO se replicó tape institucional ni chart temporal (fuera de alcance).
- **🔑 DECISIÓN DE COMPRA/VENTA = SOLO PREMIUM (VERIFICADO por grep):** `_update_signal` usa
  `diff = net_call − net_put` + umbral adaptativo + momentum → `self.target` (CALL si UP, PUT si DOWN);
  `trade_poll` ejecuta ese target. **TA, GEX, Walls y la Ladder son informativos: NO tocan la
  ejecución.** (Idea futura del usuario: quizá accionarlos, pero solo tras validar con datos reales.)
- **🆕 LOG súper exhaustivo + rotación DIARIA (2026-08-09):** `TimedRotatingFileHandler` (midnight, 120
  backups). Por minuto (`_log_minute`): TA completo, señal (diff/thr/mom), contrato+P&L, premium por
  strike con actividad. Eventos: giros, órdenes/fills(+profit), cancelaciones, TODOS los mensajes IBKR
  (`_on_error` loguea code+msg), y `TRADE` con la razón de cada decisión. Respaldo del día por si la BD
  falla. Cold run TEST G verde.
- **🆕 HORARIO DE MERCADO sencillo (2026-08-09):** `is_market_open()` (Lun-Vie, 09:30≤ET<16:00, SIN
  festivos). En `tick()`: `if demo / elif is_market_open() (recolecta+opera) / else (cerrado: end_session
  una vez)`. Al abrir: `reset_day()` (señal en 0) + `try_connect`→setup (nueva expiry). Al cerrar:
  `end_session()` (persist+cancel+disconnect). **Operaciones cesan 15:45** (trade_poll), **recolección
  sigue hasta 16:00**. Cold run TEST F verde. NOTA: el proceso debe quedar VIVO (la GUI) para que
  arranque/pare solo; si se cierra la ventana, hay que relanzarlo.
- **Fuera de alcance (ahora):** comparador visual "Δ overnight" (default cierre vs apertura), uso
  ACCIONABLE (veto/target), el "tape" institucional y el chart temporal — no ahora.

## 10. IDEAS FUTURAS (dichas por el usuario, no comprometidas)
- Usar TA como filtro/veto ligero (no driver) SI los datos minuto a minuto lo respaldan.
- Delta real del OTM (leer modelGreeks tick 106) para confirmar ~0.40-0.48.
- Las Walls podrían pasar de informativas a filtro (no operar contra una wall / target al magneto).

## 11. REGLAS DE TRABAJO CON ESTE USUARIO (críticas)
- **Honestidad total** (R2) y **VERIFICADO/NO VERIFICADO** siempre (R7). No afirmar sin correr (R3).
- **No implementar nada sin probarlo antes** (lo pidió explícito para el OI).
- Escribe **por partes**: unir los mensajes cortos, no quedarse solo con el último.
- Cuenta paper ~$397 (DU7154467). Riesgo real del scalping: whipsaw + comisiones + 0DTE decay.

## 12. REPOSITORIO GitHub (ya NO se manda Gmail)
- **URL:** https://github.com/eulisescontreras/open-premium-ibkr  (PRIVADO, cuenta `eulisescontreras`).
- Se sube **TODO** (código, docs, exe/dist, build, .db, logs, .zip) — el usuario lo quiere completo para
  pasar de máquina en máquina. NO hay `.gitignore` (por decisión del usuario). Sin llaves/secretos.
- El `README.md` es la **doc de entrada para el otro agente** (qué es, cómo correr, reglas, gotchas,
  estado, de qué estar pendiente). Este `ANTI_COMPACT_CONTEXT.md` es el contexto vivo (leer primero).
- Deploy de cambios: `git add -A && git commit && git push` (rama `main`). Los archivos de 53MB
  (exe/pkg) dan warning de GitHub (>50MB) pero suben bien.
