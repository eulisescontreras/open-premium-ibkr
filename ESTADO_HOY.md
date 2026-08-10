# ESTADO 2026-08-10 — LEER PRIMERO (traspaso completo)

Proyecto: `C:\Users\eulis\proyectos\open-premium-ibkr` (rama `main`, push autorizado).
Orden de lectura: **este** → `ANALISIS_ENTRADA_SALIDA.md` → `ANTI_COMPACT_CONTEXT.md` → `MEJORAS.md`.

Hoy fue la **primera corrida en vivo real**. Se cerraron 16 gaps por la mañana y 7 más por la
tarde, se construyó toda la instrumentación de operaciones, y se analizaron los datos a fondo.

---

## AHORA MISMO

- App **CORRIENDO**. Verificar SIEMPRE **1 sola instancia**:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? { $_.CommandLine -like '*spy_direction.py*' }`
- **NO reiniciar sin autorización explícita del usuario.**
- Antes de cualquier reinicio: **las 14 suites de cold run en verde** (rutas abajo).
- Cuenta paper. `TRADING_ENABLED=True`, `QTY=1`. Gateway paper 4002, clientId 7.
- `gh`/`git` necesitan `$env:GITHUB_TOKEN=''` antes (hay un token roto en el entorno).
- **10 arranques hoy.** Desde el de las 14:52 cada uno queda sellado en `sesion_config`.

---

## LO QUE SE HIZO HOY

### Mañana (agente anterior) — 16 gaps
1 reconexión · 3 strikes siguen al precio · 7 borrado OI/gamma · 8 contrato de salida ·
9 órdenes fantasma · 11 precio congelado · 12 contrato sin cotización · 13 fills perdidos ·
14 límite duro 1 contrato · 15 acumulado se perdía al reiniciar · 16 restauración completa.
Descartados: 6 (medición) y 10 (el TA solo esperaba 26 barras).

### Tarde — instrumentación completa (tablas nuevas)
- **`trades`** — 1 fila por operación: entrada, salida, duración, profit, **MFE/MAE + hora del
  máximo**, razón de salida, griegas de entrada y **16 columnas de contexto de mercado**
  (RSI, ancho BB, ATR%, distancias a VWAP / centro de peso / gamma flip / walls, GEX, régimen,
  minuto de sesión).
- **`posicion_minuto`** — recorrido del contrato: bid/ask/mid, P&L y **6 griegas**, con filas
  `entrada` y `salida` SIEMPRE + `minuto` cada `POS_LOG_SECS=60`.
- **`cum_net` / `day_net`** — acumulado NETO firmado por strike, **en paralelo** al bruto
  (`cum_prem` NO se tocó).
- **`ta_minute`** +`diff`,`thr`,`momentum`, **premium por vela** (`prem_call_min`,
  `prem_put_min`, `net_call_min`, `net_put_min`) y ventanas móviles **1/5/15 min**.
- **`walls_snapshot.spot_stale`** — marca las filas escritas con el precio congelado.
- **`sesion_config`** — sello por arranque (parámetros + criterio + gaps activos).

### Tarde — 7 arreglos más
| # | Qué |
|---|---|
| **GAP 17** | El stream de barras moría en silencio (`10182`) y nadie lo reponía: `ta_minute` se congeló 36 min y `walls_snapshot` siguió escribiendo con **spot falso**. Ahora se detecta **por frescura** (`bars[-1].date` no avanza en 120 s) **y** por evento, y se repone solo con backoff de 30 s |
| **GAP 2** | El premium de los 2 strikes de señal se contaba DOS veces (`_on_ticks` + `compute_walls`). Manda `_on_ticks` (mide por tick) |
| **GAP 4** | Pasadas las **15:50** las ventas **cruzan el spread** (van al BID). Antes una 0DTE que no llenara al MID expiraba valiendo 0 |
| **GAP 5** | El momentum medía **eventos**; ahora mide **30 s reales**. `diff_hist` eliminado (quedaba huérfano) |
| **M2** | ⚠️ **PARCIAL.** Se lee `RealizedPnL` de `accountSummary`… pero **IBKR no lo devuelve** por esa vía (verificado en vivo). El fallback avisa y marca el panel como `(interno)`, así que ya no se confunde el origen del dato — pero el P&L sigue siendo el cálculo interno. Arreglo pendiente: `ib.reqPnL()` |
| **M12** | `tif='DAY'` explícito → se acaban los 54 avisos `10349` |
| **Panel** | Decía `trading OFF` **estando armado** (el texto inicial nunca se refrescaba) |

### 🔴 GAP 18 — DETECTADO HOY, **SIN ARREGLAR**
Al arrancar, `setup_contracts` suscribe la señal **antes** de que `_load_intradia` restaure los
acumuladores. En esa ventana (~4 s) `net_call/net_put` valen 0 y el umbral cae al piso de 5.000
→ **giro espurio**. Ocurrió a las 14:52:29 (`GIRO -> DOWN, thr=5000`) y se corrigió solo 4 s
después, pero **ya causó daño real** por la mañana (*"4 giros en 34 s tras el reinicio de las
11:50, cerrando una posición que la señal real habría mantenido"*). Deja además **filas falsas
en `transitions`**.

---

## HALLAZGOS DEL ANÁLISIS (detalle en `ANALISIS_ENTRADA_SALIDA.md`)

- **El problema NO es la dirección, es el desgaste por entrar pronto.** Caso de hoy: compra a
  las 13:01 con SPY 773,00 y prima 0,73; a las 14:54 el SPY estaba en **773,11** (más arriba) y
  la prima en **0,50**. Dirección correcta, 23 $ perdidos por theta.
- **El premium NO anticipa el movimiento** a resolución de 1 minuto (todos los lags predictivos
  ≤ 0; el máximo, +0,203, está en lag **−2**: va detrás). *Limitación: haría falta resolución
  por segundo para zanjarlo.*
- **El TA tampoco**: 50,2% de acierto direccional frente al 49,6% del premium.
- **Compresión de Bollinger: probada y DESCARTADA** (1,17x con tasa base del 86%).
- ✅ **Lo único aprovechable: predecir el mercado PLANO.** `atr_pct` (−0,83), `abs_momentum`
  (284 vs 17.211, −0,76), `abs_dist_flip` (−0,43). Son **direccionalmente neutras** y separan
  más fuerte que cualquier predictor de movimiento.
- ⚠️ Los predictores de movimiento brusco (OBV, %B, EMAs, `dist_vwap`) están **contaminados**:
  el 63% de los movimientos grandes de hoy fueron bajistas y solo describen ese sesgo.

---

## LO QUE FALTA

### No necesita datos — se puede hacer ya
| # | Qué |
|---|---|
| **GAP 18** | Giro espurio en el arranque (ver arriba). **El más urgente** |
| **M1** | `REPRICE_SECS=4` es menor que la latencia real (mediana 1 s, cola 25 s) → subir a 12-15 s |
| **M6** | El piso `SIGNAL_THRESHOLD=5000` es 100x menor que el umbral maduro; hacerlo proporcional |
| **M11** | Marcar como parciales los snapshots con griegas incompletas tras reconectar |

### Necesita 3-5 sesiones limpias
- Calibrar **take-profit** sobre `trades.mfe` real *(hoy `trades` tiene 0 filas: la posición
  abierta se compró con el código viejo)*.
- Validar el filtro **"no entrar en plano"** (ATR + |momentum| + distancia al flip).
- Separar movimiento **brusco vs gradual** con n suficiente.
- Comparar **ventana móvil vs acumulado** (M4) con los datos que ya se guardan.

### Puede no tener solución
- **Acierto direccional ~50%.** Es posible que el flujo de premium simplemente no prediga la
  dirección del SPY a 2-3 minutos. Los datos lo dirán; ningún volumen de datos lo crea si no está.

### Datos que NO tenemos y harían falta
1. **Flujo con resolución por segundo** (el bucle ya corre a 1 Hz).
2. **Volumen del SUBYACENTE** (SPY/ES): hoy solo vemos el derivado.
3. Un día con **GEX negativo** (hoy fue LONG el 100%).
4. Días con **sesgo alcista**, para separar predictores reales del sesgo bajista de hoy.

---

## VERIFICACIÓN — 14 suites de cold run

Scratchpad `C:\Users\eulis\AppData\Local\Temp\claude\C--Users-eulis\ae335169-c2e3-4870-8f96-7162be8e61d5\scratchpad\`:
`fase1_ gap3_ gap7_ gap9_ gap11_ gap12_ gap13_ gap14_ gap15_ cuenta_ gaps_coldrun.py`
En el repo: `spy_walls_coldrun.py`, **`posicion_coldrun.py`**, **`gapsA_coldrun.py`** (nuevas).

**Las 14 deben salir verdes antes de cualquier reinicio.** Correr con
`$env:PYTHONPATH="C:\Users\eulis\proyectos\open-premium-ibkr"`.

Hoy se actualizaron 2 suites porque comprobaban lo viejo (no eran regresiones):
`gap15` usaba `diff_hist` (eliminado) y `gaps_coldrun` **demostraba** el GAP 5 (ya arreglado).

---

## REGLAS DURAS DEL CÓDIGO (no romper)

- **1 solo contrato**: `_place` bloquea si `pos_qty + buys_pend >= QTY`. Las VENTAS nunca
  consumen cupo (hay que poder salir siempre).
- **NUNCA restaurar** `prev_vol`, `band_prev_vol`, `buys_pend`, `last_buy_ts` → generarían
  **premium fantasma** (el volumen de IBKR es acumulado del día) u órdenes fantasma.
- Los contratos de EJECUCIÓN no se mueven con posición abierta ni orden viva.
- Ejecución en **ATM real**; walls por **exposición gamma**.
- **LIMIT al MID siempre**, salvo el cruce autorizado de las 15:50 (GAP 4).
- Las **griegas del contrato operado** se leen del ticker **de la banda**: `ib_insync` indexa
  los tickers por `id(objeto)`, no por `conId`, y los contratos de ejecución se piden con
  `genericTickList=""`. Su `modelGreeks` es SIEMPRE `None`.

---

## DATOS — ojo al analizar

- **Tramos NO homogéneos de hoy** (por eso existe `sesion_config`):
  09:30-11:03 walls por OI y ejecución OTM · 11:03-14:28 walls por gamma, ATM real y **premium
  de señal inflado (GAP 2)** · 13:26-14:00 **spot congelado en 773.03** · 14:28-cierre limpio.
- `cum_prem` es **BRUTO** (solo suma, nunca resta). El neto es `cum_net`, y es una **inferencia**
  por regla del agresor, no un dato de IBKR.
- **`day_prem` tiene cortes** por los 10 arranques. `cum_prem` sí es íntegro.
- `ta_minute` empieza a las **09:55**: el TA exige 26 barras y está ciego los primeros 26 min.
- Huecos de minuto: 09:59→10:01, 10:06→10:08, 10:48→10:50, 10:52→10:54, 12:08→12:10 y
  **13:24→14:00** (GAP 17 + reinicio).

---

## CÓMO TRABAJA ESTE USUARIO

Escribe en mensajes cortos y fragmentados — **unirlos antes de actuar**. Exige honestidad
total, VERIFICADO/NO VERIFICADO/HIPÓTESIS siempre, y **cold run con la función real** antes de
afirmar que algo funciona. Detecta problemas él mismo mirando la pantalla y suele tener razón
(hoy detectó el `trading OFF` y diagnosticó correctamente el desgaste por theta). Quiere **logs
en todo lo nuevo**. No reiniciar ni hacer push sin su autorización explícita.
