# Plan — Sistema SPY 0DTE nuevo (ST-3 + ORB + aperturas + verticales)

## Context

La investigación (2 PDFs en `Downloads/`: `SISTEMA_VALIDADO_PREMIUM_REAL.pdf` 210 pág + `MANUAL_TRASPASO_AGENTE.pdf` 77 pág) cerró un sistema intradía sobre opciones **0DTE del SPY** validado sobre **485 sesiones con premium REAL** (Massive/OPRA, cadena completa 99%): **+71.396$/2 años**, ~**+31.000$/año operable** (aplanado 15:50), 140 días rojos, racha máx 4, drawdown −1.140$, 25/25 meses positivos. Grado de confianza **80‑85%**. Solo quedan 4 hipótesis abiertas que **exigen operar** (fills del vertical, cero órdenes reales, premarket en vivo, régimen VIX 60+).

El manual ordena **construir desde cero** (el monolito `spy_direction.py`, 5.596 líneas, arrastra 3 errores que inflaron resultados). Objetivo: un sistema nuevo que (a) **replica lo validado**, (b) **captura y guarda TODAS las mediciones** de cada componente para poder seguir investigando en vivo, (c) tiene **cold runs de validación** que garanticen que el día de la prueba **pone órdenes, guarda estadísticas y no falla**.

**Decisiones del usuario:** (1) app nueva modular desde cero, **rescatando toda la data** existente por mínima que sea; (2) arrancar en **SPY con aplanado 15:50**; (3) **motor de backtest + vivo comparten núcleo** de reglas; (4) **plan completo, build por fases**.

**⚠️ FRONTERA DE DATOS (decisión del usuario, 2026-08-16):** el sistema EN VIVO obtiene TODO de **IBKR** (barras + cadena + **greeks/IV reales**). **Massive es SOLO histórico del backtest** (contratos del pasado), FUERA del sistema. La tabla `premium` de `sys2.db` se llena **solo con IBKR** (`fuente='live'`). Los **greeks Black-Scholes** (`greeks.py`) viven en el lado del **backtest** (`sys2/backtest/`), se calculan sobre massive al vuelo solo para reproducir las cifras — nunca en vivo.

> Estado NO VERIFICADO / HIPÓTESIS que el propio doc marca abiertas: fills del vertical de 4 puntos (los 21 fills medidos son de una sola pata), y que las cifras se repliquen en vivo. El sistema debe **medirlas**, no asumirlas.

---

## Arquitectura (paquete nuevo modular `sys2/`)

Un paquete nuevo en el repo (`C:\Users\17862\open-premium-ibkr\sys2\`), todos los archivos **< 1000 líneas**. **Núcleo compartido** por backtest y vivo (misma lógica de señales/reglas → una sola fuente de verdad):

```
sys2/
  core/
    supertrend.py     # reusa year_backtest.st_dir (7,3.0 Wilder) + buckets 3-min (backtest_st3_orb.sen_principal) + shift_sen
    st1.py            # Supertrend de 1 min (regla 2: descarte por giro en 5 min)
    entradas.py       # A ST-3 · B ORB (reusa orb_senal) · C pm_rev · D gap_fade · E v1 · F ayer_rev  (C-F NUEVAS)
    rebote.py         # REGLA 1: toque a la línea con la MECHA, ventana 12 buckets → clasifica NORMAL/RETRASA/INVIERTE/DESCARTA
    reglas.py         # REGLA 2 (ST-1), 3 (ratio call/put OTM), 4 (skew sobre RETRASA), 5 (día bueno) + rodado por delta
    instrumento.py    # selección del vertical de débito 4pts (larga ITM profundo, corta +4 OTM, débito ≤ tope) + single fallback
    autocalibra.py    # configuracion(cuenta): modo/ancho/tope/unidades · tope duro 3 · límite 35% (MANUAL §13.1-bis)
    salida.py         # flip ST-3 · aplanado 15:50 · mercado 15:55 · verificación plana <16:00
    greeks.py         # Black-Scholes (delta/gamma/theta/vega/iv) para poblar premium histórico sin greeks
  data/
    ibkr.py           # ib_insync: conexión (clientId propio, NO 7/24/25), reqHistoricalData, placeOrder combo BAG
    backfill.py       # premarket 04:00→arranque (useRTH=False) + DIA/TLT 09:30-10:00 + dia_anterior  → persiste en bars
    captura.py        # loop de captura minuto a minuto (keepUpToDate) + cadena de opciones 8+ strikes/lado con day_vol/greeks
  db/
    schema.sql        # esquema nuevo (abajo)
    migrar.py         # rescata TODA la data del sistema anterior a las tablas nuevas
    repo.py           # capa de acceso (INSERT OR REPLACE idempotente)
  backtest/
    motor.py          # "motor nuevo": corre las 6 entradas + 5 reglas + verticales sobre massive_premium.db (cadena real)
    validacion.py     # los 4 tests (bloques / T2 / permutación / % días) — MANUAL §2.1
  vivo/
    sistema.py        # orquestador en vivo (arranque → backfill → captura → señales → reglas → ejecución → BD)
  cold_runs/          # ver sección Cold Runs
  config.py           # constantes congeladas (ST 7/3.0, ancho 4, umbrales de cada regla, horas)
```

**Reutilización (R9, verificado con file:line):** `simulador_st.py:151 simular()`, `year_backtest.py:27 st_dir()`, `backtest_st3_orb.py:65 sen_principal / :91 orb_senal`, `orb_senal.py:40`, `exp_timing_realista.py:31 shift_sen`, `exp_trail_2min.py:51 build_tmp`, `synth_premium.py:33 calibra / :51 extr`. Patrón de cold run: `coldruns/st3_signal_coldrun.py`.

> ⚠️ `simular()` opera **una sola pata ITM al ASK**; el motor nuevo necesita **verticales** y correr sobre la **cadena real**. Es una extensión del motor, no un reemplazo del núcleo de señales (que sí se reutiliza).

---

## Esquema de BD nuevo + migración

**Esquema nuevo** (`sys2/db/schema.sql`, base `sys2.db`) — tomado literal del MANUAL §4.1:
`bars`, `bars_etf` (DIA/TLT), `dia_anterior`, `premium` (cadena completa: bid/ask/mid/last, **day_vol**, OI, **iv/delta/gamma/theta/vega**), `senales` (con **grupo** del flip NORMAL/RETRASA/INVIERTE/DESCARTA, `hora_efectiva`, `direccion_final`, `descartada_por`, `invertida_por`, contexto `spy/atr3/dist_linea/skew/ratio_otm/iv_atm/giros_st1_5m`, `flip_falso`), `contexto_dia` (efic15/30/60, mov_DIA/TLT, dia_bueno, unidades, pnl), `operaciones` (n_op_dia, tipo vertical/single, strikes, greeks entrada, razon_salida, mfe/mae, **nivel/ancho/tope/unidades**), `fills` (**una fila por PATA**, `parcial`, precio_ordenado vs lleno vs bid/ask), `movimientos` (ingresos/retiros).

**Migración (`sys2/db/migrar.py`) — rescatar TODO** (decisión del usuario; VERIFICADO por el mapeo de BDs):
- `bars` ← `spy_bars_year.db` + `spy_bars_year2.db` (2 años 1‑min, ~490k filas) + los 2‑3 días live de `spy_history*.db:bars_minute`.
- `bars_etf` ← `dia_/tlt_bars_year*.db`.
- `premium` histórica ← `massive_premium.db:aggs` (485 días, **OHLCV puro**) → **recalcular greeks con Black‑Scholes** (`greeks.py`); el doc (H3) prueba que el sistema es **insensible a ±0,10 de delta**, así que BS es aceptable. Greeks/day_vol **reales** ← `spy_history*.db:premium_minute` + `posicion_minuto` + `trades` (solo 2026‑08‑10..13, se marcan como `fuente='live'`).
- `premium` 1DTE ← `massive_premium_1dte.db` (marca `expiry`).
- `operaciones` ← `spy_history*.db:trades` (mapeo 1:1, greeks de entrada + razon_salida).
- `dia_anterior`/`contexto_dia` ← `historico_spy.db:ta_historico` + `spy_history:walls_snapshot`.
- `tape` del subyacente (`spy_tape_und.db`, 28M ticks firmados) y `spy_prem_mix_*` → tabla `tape_und` / `premium_mix` propias (no se tiran; insumo de investigación futura del signo del flujo).
- Toda migración **idempotente** (`INSERT OR REPLACE`), con conteos antes/después (cold run de migración).

---

## Componentes del sistema (núcleo, todo se mide y se guarda)

**6 ENTRADAS** — `entradas.py`: A) ST‑3 flip (señales ≥09:45, shift +3); B) ORB 09:40/11:00 (rango 10 min, amplitud ≥0,40, **reversión**); C) **pm_rev** (rompe rango premarket → reversión); D) **gap_fade** (gap ≥0,40 → cerrar gap); E) **v1** (rompe 1ª vela 5 min → reversión); F) **ayer_rev** (rompe máx/mín ayer → reversión). C‑F se descartan si <5 min de una señal ORB. **Cada señal generada se escribe en `senales`, se opere o no.**

**5 REGLAS + rodado** — `rebote.py` + `reglas.py`:
1. **REBOTE** (+33.000$): toque a la línea del ST‑3 con la **mecha**, ventana 12 buckets → clasifica el flip en 4 grupos. **El grupo se guarda en `senales.grupo`** (variable más discriminante del proyecto).
2. **DESCARTE ST‑1** (+1.842$): si el ST‑1 gira ≥1 vez en los 5 min siguientes → no entrar.
3. **RATIO CALL/PUT OTM** (+3.030$): veto si el flujo direccional va >3:1 en contra.
4. **SKEW sobre RETRASA** (+3.874$): si el rebote clasifica RETRASA y skew orientado >0,04 → invertir.
5. **DÍA BUENO** (+6.433$): efic60<0,187 Y mov_DIA>1,23 Y mov_TLT<1,225 → **doblar unidades**.
+ **rodado por delta** (base): rodar el contrato si la delta cae bajo 0,35 (máx 3, hasta 15:30).

**INSTRUMENTO** — `instrumento.py`: vertical de débito **4 puntos** (larga = ITM más profundo, corta = +4 OTM), débito 20–320$, como **orden combinada** (`BAG`/`ComboLeg` — capacidad NUEVA, el bot viejo solo hacía single-leg). Fallback a **single** si fills parciales >5%.

**AUTOCALIBRACIÓN** — `autocalibra.py`: `configuracion(cuenta)` lee el saldo real del bróker, elige modo/ancho/tope/unidades, tope duro **3 contratos**, peor día ≤35% de la cuenta, solo al inicio de sesión, nunca con posición abierta.

**SALIDA** — `salida.py`: flip del ST‑3; **aplanar 15:50**, orden a **mercado 15:55** si sigue abierta, **verificación explícita de posición plana <16:00** (bloqueante de asignación).

---

## Premarket — backfill + minuto a minuto (las DOS, sin huecos)

`data/backfill.py` + `data/captura.py`:
1. Al arrancar (a la hora que sea): `reqHistoricalData(SPY, "1 min", useRTH=False, "2 D")` → **04:00 → momento de arranque**, persistido en `bars` minuto a minuto (idempotente).
2. Igual para **DIA y TLT** (09:25–10:05) y `dia_anterior` (cierre/máx/mín).
3. Acto seguido `keepUpToDate=True` → **arranque → cierre** minuto a minuto.
4. Resultado: `bars` poblada continua desde las 04:00 sin importar cuándo arrancó el sistema. ST‑3/ST‑1/pm_rev/gap_fade/ayer_rev calculan correctos desde el minuto 1.

---

## Cold runs de validación (la red de seguridad; MANUAL §5-6, patrón `st3_signal_coldrun.py`)

Cada cold run alimenta la **función REAL** con **datos reales** (nunca reimplementa) y compara contra referencia. Se corren TODOS en verde antes de cada fase.

**Datos/equivalencia:**
- `cr_backfill.py`: tras el backfill, `bars` tiene ~390 barras desde 04:00 y **cero huecos** entre arranque y live.
- `cr_migracion.py`: conteos por tabla antes/después; ninguna fila perdida.
- `cr_nucleo_equivale.py`: el motor en vivo replica **señal a señal** al motor de backtest sobre los mismos días (diferencial, R8).
- `cr_greeks_bs.py`: greeks BS vs greeks reales (los 3 días live) dentro de tolerancia; y que ±0,10 de delta no cambia decisiones.

**Sistema replica lo validado:**
- `cr_backtest_cifras.py`: el motor nuevo sobre `massive_premium.db` reproduce **+71.396$/2 años ± tolerancia**, 140 rojos, racha 4, aportes por regla (rebote +33k, día bueno +6.433, skew +3.874, ratio +3.030, ST‑1 +1.842).
- `cr_flips_grupos.py`: distribución NORMAL/RETRASA/INVIERTE/DESCARTA (675/393/243/100) y % de flips falsos por grupo.
- `cr_validacion_reglas.py`: los 4 tests (§2.1) pasan para cada regla.

**Que el día de la prueba NO falle (lo que pediste explícitamente):**
- `cr_pone_ordenes.py`: en paper, el sistema **efectivamente envía la orden combinada** del vertical y detecta el fill de **ambas patas** (`fills.parcial` poblado).
- `cr_guarda_estadisticas.py`: tras una sesión simulada, **todas** las tablas quedan pobladas (`senales` con grupo, `operaciones` con n_op_dia/razon_salida, `fills` por pata, `contexto_dia`).
- `cr_aplanado_asignacion.py`: a las 15:50 aplana, a 15:55 manda mercado, y **verifica posición plana <16:00** (simulando fill lento).
- `cr_autocalibra.py`: `configuracion(cuenta)` da la tabla del MANUAL §13 (nunca >3 contratos, peor día ≤35%).
- `cr_lookahead.py`: guardas contra las 6 trampas documentadas (pos=None sin contabilizar, resultado con otro nombre, menú de contratos, desfase horario fijo → `zoneinfo`, extrínseco negativo → suelo intrínseco, contrato que deja de cotizar).

---

## Fases de build (cada una con sus cold runs verdes antes de pasar)

- **Fase 0 — Datos/BD:** esquema nuevo + `migrar.py` (rescate total) + `backfill.py` + `captura.py`. Correr **2 semanas solo capturando** (verificar 390 barras/sesión, day_vol >95%, 8+ strikes/lado). Cold runs: backfill, migración, greeks.
- **Fase 1 — Motor de señales (sin órdenes):** núcleo compartido + `backtest/motor.py` sobre cadena real. Correr en paralelo comparando con el backtest señal a señal. Cold runs: núcleo-equivale, backtest-cifras, flips-grupos, validación-reglas, lookahead.
- **Fase 2 — Paper (verticales):** `ibkr.py` órdenes combinadas + `fills` por pata. Criterio de aceptación: <5% parciales, si no → single. Cold runs: pone-ordenes, guarda-estadisticas, aplanado-asignacion.
- **Fase 3 — Real capital mínimo:** autocalibración desde saldo real (arranque 320$ operativos, ~1.200$ en cuenta), regla de parada 12 días rojos. Cold run: autocalibra. Migración a XSP como línea futura (revalidar las 7 reglas).

---

## Verificación end-to-end

1. `python -m sys2.cold_runs.run_all` → **todos verdes** (equivalencia, cifras, anti-lookahead, órdenes, estadísticas, aplanado).
2. Backtest: `sys2/backtest/motor.py` sobre `massive_premium.db` → **+71.396$/2 años** dentro de tolerancia y aportes por regla correctos.
3. Diferencial (R8): motor vivo vs backtest sobre los mismos días → **idéntico** señal a señal.
4. Paper 1 mes: fills de ambas patas del vertical, tablas pobladas, aplanado 15:50 verificado plano <16:00.
5. Chequear que las tablas `senales/operaciones/fills/contexto_dia` permiten **replicar cualquier análisis de la investigación** en vivo (grupo del flip, flip_falso, n_op_dia, razon_salida presentes).

## Riesgos / notas honestas
- **Fills del vertical** = hipótesis abierta #1; el sistema debe medir `parcial` y auto‑degradar a single. NO asumir que se llenan las dos patas.
- **Greeks históricos**: 482/485 días serán BS (no reales) — aceptable por H3, pero marcado `fuente` en la BD para no confundir.
- **Órdenes combinadas BAG**: capacidad nueva no probada en esta cuenta; verificar en paper desde el primer día.
- **No** re-probar las ~2.500 configuraciones ya descartadas (MANUAL §8/§11); el principio "forzar el sistema hacia el lado bueno de X lo empeora" está medido 9 veces.
