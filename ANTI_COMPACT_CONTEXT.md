# ANTI-COMPACT — SPY Direction (contexto vivo para continuar)

> Léeme primero tras compact/clear. Proyecto **independiente**, local, NO tiene relación con el
> trading-bot del VPS. Carpeta: `C:\Users\17862\open-premium-ibkr\`. Idioma: español.
> Fecha de este contexto: 2026-08-09 (domingo). Mercado cerrado.

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
`SNAPSHOT_SECS=120` · `WALLS_BAND=20`, `WALLS_REFRESH=900` · `TRADING_ENABLED=False`.

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
- **Fuera de alcance (ahora):** comparador visual "Δ overnight" (default cierre vs apertura) y uso
  ACCIONABLE (veto/target) — solo tras validar datos y convención de signo con días reales.

## 10. IDEAS FUTURAS (dichas por el usuario, no comprometidas)
- Usar TA como filtro/veto ligero (no driver) SI los datos minuto a minuto lo respaldan.
- Delta real del OTM (leer modelGreeks tick 106) para confirmar ~0.40-0.48.
- Las Walls podrían pasar de informativas a filtro (no operar contra una wall / target al magneto).

## 11. REGLAS DE TRABAJO CON ESTE USUARIO (críticas)
- **Honestidad total** (R2) y **VERIFICADO/NO VERIFICADO** siempre (R7). No afirmar sin correr (R3).
- **No implementar nada sin probarlo antes** (lo pidió explícito para el OI).
- Escribe **por partes**: unir los mensajes cortos, no quedarse solo con el último.
- Cuenta paper ~$397 (DU7154467). Riesgo real del scalping: whipsaw + comisiones + 0DTE decay.
