# Diccionario de datos — `spy_history.db`

Qué guarda cada tabla y qué significa cada columna. **Todo sacado de lógica ejecutable**
(`_init_db` y la función que escribe cada tabla), no de comentarios sueltos. Los valores de
las columnas de texto están sacados de los datos reales, no supuestos.

Estado al 2026-08-11 ~14:55 (2 sesiones: 08-10 completa, 08-11 en curso).

| Tabla | Filas | Cadencia | La escribe | Qué es |
|---|---|---|---|---|
| [`tape`](#tape) | 5.383 | **por tick con volumen nuevo** | `_flush_tape:2228` | Flujo con tamaño y agresor del instante (≈64 % son 1 operación exacta) |
| [`premium_minute`](#premium_minute) | 43.125 | 1 min (+3 min) | `_persist_walls:1544` · `_log_minute:3154/3180` | Dinero y precio **por strike** |
| [`ta_minute`](#ta_minute) | 613 | 1 min | `_log_minute:3118` | Precio del SPY, TA y estado de la señal |
| [`posicion_minuto`](#posicion_minuto) | 308 | 1 min con posición | `_pos_snapshot:1719` | Recorrido del contrato comprado |
| [`walls_snapshot`](#walls_snapshot) | 247 | 3 min | `_persist_walls:1521` | Walls, GEX, gamma flip |
| [`strike_daily`](#strike_daily) | 183 | al persistir | `_persist_accum:1329` | Premium del día por strike |
| [`transitions`](#transitions) | 108 | por evento | `_save:848` | Cada aviso y cada giro de señal |
| [`strike_accum`](#strike_accum) | 76 | al persistir | `_persist_accum:1321` | Premium histórico por strike |
| [`sesion_config`](#sesion_config) | 11 | por arranque | `_sellar_sesion:1284` | Con qué código/parámetros se generó cada tramo |
| [`trades`](#trades) | 8 | por operación | `_trade_abrir:1625` · `_trade_cerrar:1680` | Una fila por posición |
| [`estado_intradia`](#estado_intradia) | 2 | continuo | `_persist_accum:1337` | Para que un reinicio no empiece de cero |

---

## Conceptos que se repiten (leer una vez)

- **`cum_` vs `day_` vs "por vela"**: `cum_*` acumula **desde el primer día de uso**; `day_*`
  acumula **desde las 09:30 de hoy**; "por vela"/`_min` es lo que entró **en ese minuto**.
  ⚠️ Los dos primeros **crecen con el reloj**, así que correlacionarlos con cualquier cosa da
  falsos positivos. Para análisis intradía: `day_*`, nunca `cum_*`.
- **BRUTO vs NETO**: el bruto suma actividad (`precio × volumen × 100`) y es **direccionalmente
  ciego** — 1 M$ en calls es el mismo número lo compre un alcista o lo venda un bajista.
  El **neto** lleva el signo del agresor y es lo único que apunta a una dirección.
- **Agresor**: quién cruzó el spread. Es una **INFERENCIA**, no un dato de IBKR: toda opción
  negociada tiene comprador *y* vendedor. Regla usada (`_on_ticks:1843-1846`):
  `last >= ask` → COMPRA · `last <= bid` → VENTA · en medio → **MID, no atribuible**.
- **Los tres grupos de contratos suscritos** (68 líneas de market data de ~100 que da IBKR):
  **SEÑAL** (2: el call ATM/ITM y el put ATM/ITM de la expiry más cercana, los que deciden) ·
  **BASELINE** (24: ATM/ITM de las 3 expiraciones siguientes) ·
  **BANDA** (40: ±10 strikes alrededor del precio, para walls/GEX) ·
  más 2 de **EJECUCIÓN** (los ATM reales que se compran).
- **Un NULL es un dato**, no un cero: significa "esto no se pudo medir". El código evita
  rellenar huecos con ceros inventados a propósito.

---

## `tape`
**Una fila por ACTUALIZACIÓN DE TICKER que traía volumen nuevo** — que no es exactamente lo
mismo que "una fila por operación". La tabla más granular; entró en producción el 2026-08-11
14:36. Existe porque al agregar por minuto, un print institucional de 3.038 contratos y 50
operaciones de 60 quedaban **idénticos**: mismo volumen, mismo premium.

### ⚠️ LÍMITE MEDIDO: el tape es una MUESTRA, no un registro completo
`_on_ticks` se dispara con `pendingTickersEvent`, y ib_insync **agrupa** varias operaciones en
una sola actualización. `tk.lastSize` trae el tamaño de la **última** de ellas; `dvol` trae el
volumen de **todas**. Medido sobre las 5.383 filas del 2026-08-11:

| | filas | % |
|---|---|---|
| `size == dvol` → la fila **es** 1 operación exacta | 3.435 | **63,8 %** |
| `size < dvol` → la fila **agrupa varias**; solo se guarda el tamaño de la última | 1.657 | 30,8 % |
| `size > dvol` | 291 | 5,4 % |

**Σ`size` = 34.840 contratos frente a Σ`dvol` = 118.948 ⇒ `size` solo cubre el 29,3 % del
volumen negociado.** Consecuencia práctica: analizar la columna `premium` es analizar el ~29 %
del dinero con atribución exacta; analizar `premium_dvol` es tener el 100 % del dinero pero
volviendo a asignar todo el bloque al agresor del último trade.

📌 No es un bug arreglable con más código: `reqTickByTickData("AllLast")` **no está soportado
para opciones** (IBKR error 10189, ver anti-compact §7), por eso se usa RTVolume `"233"`. Es el
techo del feed. *(Ese punto viene documentado de antes; no lo he re-verificado yo.)*
📌 Las 291 filas con `size > dvol` **no están explicadas** — hipótesis: `lastSize` repetido entre
actualizaciones o el contador de volumen llegando con retraso. **NO VERIFICADO.**

| Columna | Qué es |
|---|---|
| `id` | autonumérico |
| `fecha` | `YYYY-MM-DD` |
| `hora` | **`HH:MM:SS.mmm`** — con milisegundos, es la única tabla con esa resolución |
| `ts` | el mismo instante en epoch (para ordenar y restar sin parsear) |
| `expiry` `strike` `right` | qué contrato (`C`/`P`) |
| `last` | precio de esta operación |
| `size` | **contratos de ESTA operación** (`tk.lastSize`). Es el dato que no existía antes |
| `dvol` | delta de volumen acumulado desde la lectura anterior — lo que usa la señal |
| `bid` `ask` | el spread **en el instante de esta operación**, no en el de la lectura |
| `agresor` | `COMPRA` / `VENTA` / `MID` (no atribuible) |
| `premium` | `last × size × 100` — **atribución exacta** de esta operación |
| `premium_dvol` | `last × dvol × 100` — lo que ve la señal. Se guardan **los dos** para medir cuánto distorsiona la agregación |
| `grupo` | `SENAL` (2.753 filas) o `BASELINE` (1.597) |

📌 Medido hoy: **MID = 18,5 %** del flujo. Con el método viejo el no atribuible era el **92 %**.

---

## `premium_minute`
**Dinero y precio por strike.** La tabla más grande. Ojo: la escriben **dos** funciones
distintas y por eso no todas las columnas están en todas las filas.

| Columna | Qué es |
|---|---|
| `fecha` `hora` | `HH:MM`. PK junto a expiry/strike/right |
| `expiry` `strike` `right` | qué contrato |
| `cum_prem` | premium bruto acumulado **desde el primer día de uso** |
| `day_prem` | premium bruto acumulado **del día** |
| `net_prem` | premium **firmado** acumulado del día (el del agresor). ⚠️ Es un **acumulado**, no el flujo del intervalo (`_on_ticks:1458` lo suma sobre sí mismo) |
| `day_vol` | contratos negociados en el día |
| `open_interest` | OI de IBKR. **Siempre es de AYER** (IBKR solo lo da end-of-day) |
| `gamma` | gamma del modelo, en vivo |
| `bid` `ask` `mid` `last` | precio del contrato ese minuto |
| `spread` | `ask − bid` guardado ya calculado: distingue un strike líquido de uno donde el precio existe pero no es operable |

**Quién escribe qué** (verificado):
- `_log_minute` (**cada minuto**, todos los contratos seguidos): `cum_prem`, `day_prem`, precio.
- `_persist_walls` (**cada 3 min**, solo los 40 de la BANDA): añade `net_prem`, `open_interest`,
  `gamma`, `day_vol`.

⇒ **Una fila con `net_prem` en NULL no es un fallo**: es un strike que ese minuto estaba fuera
de la banda de walls. Sólo la banda lleva neto/OI/gamma. Y `_log_minute` usa
`ON CONFLICT … DO UPDATE SET` nombrando **solo sus columnas**, así que no pisa las de walls.

---

## `ta_minute`
**Una fila por minuto con el precio del SPY, el análisis técnico y el estado de la señal.**
Es la serie de precio que usan todos los análisis. ⚠️ No arranca hasta que hay **26 barras**
(~09:56) — salvo el arreglo del GAP 21, activo desde hoy, que ya guarda el bloque de premium
aunque el TA no esté listo (las columnas de TA van a NULL).

**Precio y TA** — `spy` (cierre del minuto) · `rsi` · `ema8` `ema21` `ema50` ·
`sma20` `sma50` `sma200` (solo registro; la 200 es NULL hasta que hay 200 barras) ·
`macd_line` `macd_signal` `macd_hist` · `bb_up` `bb_mid` `bb_low` (Bollinger) ·
`atr` `atr_pct` · `vwap`.

**Derivadas del TA** (`TAEngine.compute:455-470`):
- `obv_trend`: `bullish` si el OBV supera su media de 20 en +5 %, `bearish` si queda −5 % por
  debajo, si no `neutral`.
- `ta_score`: suma de 7 sub-scores (rsi, ema, macd, bb, atr, vwap, obv). Rango práctico −12…+12.
- `ta_dir`: `BULL` si el score > 0, `BEAR` si < 0, `NEUTRAL` si 0.

**Estado de la señal** (lo que decide de verdad):
- `net_call` `net_put`: neto firmado **acumulado desde 09:30**, solo de los 2 strikes de SEÑAL.
- `diff` = `net_call − net_put` · `thr` = umbral adaptativo `ADAPT_FRAC×(|net_call|+|net_put|)`
  con piso 5.000 · `momentum` (30 s reales).
- `prem_state`: el estado vigente, `UP` o `DOWN`.

**Premium por vela** (estacionario, cruzable con el movimiento del minuto):
`prem_call_min` `prem_put_min` (bruto) · `net_call_min` `net_put_min` (firmado).

**Ventanas móviles**, solo guardadas, **no deciden nada**:
`net_call_1m/5m/15m` y `net_put_1m/5m/15m`.

🔑 **La decisión UP/DOWN usa EXCLUSIVAMENTE el acumulado** (`diff` vs `thr`). TA, SMA y ventanas
están ahí para poder comprobar después si otra regla habría girado antes.

---

## `posicion_minuto`
**El recorrido del contrato mientras la posición está viva.** Antes esto sólo existía como
texto en el log y se perdía.

`trade_id` (enlaza con `trades`) · `fecha` `hora` · `seg_desde_entrada` ·
`expiry` `strike` `right` · `spy` · `bid` `ask` `mid` · `entry_price` ·
`pnl` `pnl_pct` · `delta` `gamma` `theta` `vega` `iv` · `und_price` ·
`tipo` = `entrada` / `minuto` / `salida`.

📌 `tipo` existe porque con una permanencia mediana de 47 s, **el 60 % de las operaciones no
llega a generar ni una fila de minuto**: entrada y salida se fuerzan siempre.

---

## `walls_snapshot`
**Cada 3 minutos: la foto de la estructura de opciones.** Informativo: **no toca la señal**.

`fecha` `hora` `expiry` · `spot` (precio del SPY) ·
`put_wall` (strike con más OI de puts) · `call_wall` (ídem calls) ·
`max_pain_static` (max pain con el OI de ayer) · `max_pain_dyn` (con OI **+ volumen intradía**;
es el que se mueve) · `prem_center` (centro de gravedad del premium bruto: hacia dónde hay dinero) ·
`gex_total` (Σ 100·spot²·(+γc·OIc − γp·OIp)) · `regime` = `LONG` si el GEX es positivo, `SHORT`
si negativo, `FLAT` si cero · `gamma_flip` (**proxy**: strike donde la acumulada del GEX cruza
cero, interpolado) ·
`spot_stale` = **1 si el precio de esa fila estaba congelado** porque murió el stream de barras.

⚠️ El signo `+call/−put` del GEX es la **convención estándar, no verificable con IBKR**: es una
hipótesis, no un hecho.

---

## `trades`
**Una fila por posición.** 42 columnas.

**Identidad y resultado**: `trade_id` · `fecha` `expiry` `strike` `right` `side` ·
`hora_entrada` `hora_salida` `segundos` · `entry_price` `exit_price` `qty` · `profit` `pct` ·
`spy_entrada` `spy_salida`.

**Recorrido**: `mfe` (máximo a favor) · `mae` (máximo en contra) · `hora_mfe` · `spy_mfe`.
Sin esto no se puede saber cuánto se dejó sobre la mesa: el PUT del 10-ago llegó a +130 $ y se
vendió a +45 $, 18 minutos después del máximo.

**Griegas en la entrada**: `delta_entrada` `gamma_entrada` `theta_entrada` `vega_entrada`
`iv_entrada`.

**Contexto de mercado en la entrada** — para poder responder *"¿qué tenían en común las que
ganaron?"* y no sólo *"cuánto ganó cada una"*:
`rsi_entrada` · `ta_score_entrada` `ta_dir_entrada` · `atr_pct_entrada` · `bb_ancho_entrada` ·
`dist_vwap_entrada` · `gex_entrada` `regime_entrada` · `dist_flip_entrada` ·
`dist_prem_center_entrada` · `dist_call_wall_entrada` `dist_put_wall_entrada` ·
`diff_entrada` `thr_entrada` `momentum_entrada` · `minuto_sesion_entrada`.

`razon_salida`: texto libre. **Convención importante**: cuando la app se reinicia con la
posición abierta, la fila se cierra con `exit_price`/`profit`/`pct` en **NULL** y la razón lo
declara. **No se inventa un precio de salida.** Esas filas no sirven para estadísticas de
recorrido, y lo dicen.

---

## `transitions`
**Una fila por evento de señal.** `id` · `fecha` `hora` · `estado` (`UP` 53 / `DOWN` 55) ·
`tipo` (**`FLIP`** 61 = giro confirmado, **`WARN`** 47 = aviso previo) · `spy` ·
`net_call` `net_put` · `modo` (`LIVE`).

⚠️ Al leerla, **filtrar por `tipo`**: sin mirar esa columna, los WARN parecen giros duplicados.

---

## `strike_accum` y `strike_daily`
Los acumulados por strike que sobreviven a un reinicio.

- **`strike_accum`** — PK `(expiry, strike, right)`, **sin fecha**: histórico desde el primer
  día. `cum_prem` (bruto) · `cum_net` (firmado) · `updated`.
  📌 Es lo que hace que una expiry herede lo acumulado de días anteriores: la 0DTE de hoy
  arrancó con 45,5 M$ de ayer, cuando era la 1D del baseline.
- **`strike_daily`** — PK `(fecha, expiry, strike, right)`: `day_prem` · `day_net` del día.

---

## `estado_intradia`
**Una fila por día.** Existe para que un reinicio a media sesión **no empiece de cero**: sin
esto el umbral adaptativo vuelve al piso de 5.000 (cien veces menor que el maduro) y la app se
pone a picotear — 4 giros en 34 s tras el reinicio del 2026-08-10.

`fecha` (PK) · `hora` · `net_call` `net_put` · `pnl_realizado` `n_trades` `n_wins` ·
`acct_net_open` (saldo con el que abrió el día, base del `DIA +x%` del panel) · `estado`.

---

## `sesion_config`
**Un sello por arranque**: con qué código y qué parámetros se generó cada tramo de datos.
Sin esto, filas creadas con criterios distintos se mezclan en la misma tabla y el análisis
concluye cosas falsas creyendo que la serie es homogénea.

`fecha` `hora` `arranque` (PK con fecha) · `qty` · `signal_threshold` `adapt_frac` `mom_frac`
`momentum_win` · `reprice_secs` `max_fill_secs` · `walls_band` `walls_recalc_secs` ·
`itm_depth` `baseline_expiries` · `strike_exec` · `walls_criterio` · `trading` (0/1) ·
`cross_hhmm` · `bars_stale_secs` · `pos_log_secs` · **`gaps_activos`** · `bars_duration` ·
`start_trade_hhmm` · `open_hhmm` · `notas`.

🔑 **`gaps_activos` y `bars_duration` son los que de verdad separan un tramo de otro.** El
2026-08-10 la misma tabla mezcla datos de antes y después del GAP 2 y del GAP 17. Y cambiar de
`"1 D"` a `"2 D"` cambia el **valor** de ema8/21/50 y del OBV, que arrastran desde el inicio de
la serie: dos tramos con distinta `bars_duration` **no son comparables** y nada más lo delata.

---

## Lo que NO se guarda (huecos conocidos)

- **Prints individuales antes de las 14:36 del 2026-08-11**: el tape no existía. Todo lo
  anterior está agregado al minuto y no se puede desagregar.
- **`open_interest` intradía**: IBKR solo lo da end-of-day. Siempre es el de ayer.
- **Compra/venta explícita**: no existe en el dato de IBKR; el agresor se **infiere** del
  bid/ask. Por eso la columna `MID` importa: es la medida de cuánto no sabemos.
- **Precio del SPY antes de las 09:56** (o de las 09:30 con el GAP 21 activo): sale de las
  barras y `useRTH=True` no las da fuera de sesión.
- **Pre-market**: probado el 2026-08-11 y **descartado con datos**: 0 volumen, 0 premium,
  griegas None y el OI de ayer. Ver el anti-compact.
