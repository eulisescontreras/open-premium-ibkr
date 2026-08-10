# SPY Direction — Open Premium casero vía IBKR

App de **1 archivo** (`spy_direction.py`) para **scalping de SPY** leyendo el **flujo de premium de
opciones** (net call vs put) en tiempo real desde **IB Gateway (paper)**. Proyecto **independiente**
(no tiene relación con ningún otro bot). Windows + Python. Idioma del proyecto: **español**.

> **Este README es la puerta de entrada para el otro agente.** Léelo completo y luego, ANTES de tocar
> nada, lee **`ANTI_COMPACT_CONTEXT.md`** (contexto vivo, estado VERIFICADO/NO VERIFICADO, gotchas y
> pendientes). Reglas de trabajo abajo (§Reglas).

---

## 1. Qué hace

1. **Señal en vivo (UP/DOWN):** usa el vencimiento **más cercano** y strikes **ATM/ITM** (call≤precio,
   put≥precio, nunca OTM). Clasifica cada trade por **agresor bid/ask** (last≥ask=compra, last≤bid=venta)
   y acumula **net_call vs net_put** por Δvolumen×precio×100. Un **umbral ADAPTATIVO** (escala con la
   magnitud del flujo) decide UP/DOWN, con aviso de "posible giro" por momentum. Alerta con banner +
   toast de Windows en cada giro.
2. **Ejecución automática (opcional, arranca OFF):** rota **1 sola opción** (compra el lado nuevo, vende
   el viejo) **SIEMPRE con LimitOrder al MID**, una sola orden a la vez, sin huérfanas, aplanado 15:45 ET.
   El strike operado = **ATM del lado OTM**.
3. **TA 1 min** (RSI/EMA/MACD/BB/ATR/VWAP/OBV) — informativo, registrado por minuto.
4. **Línea base:** acumula premium de expiraciones **futuras** en SQLite (para ver el cambio al abrir).
5. **Walls / GEX / Gamma Flip (NUEVO, informativo — "como el TA"):** ver §4.

## 2. Cómo correr

```bash
# Requiere IB Gateway paper abierto y logueado (puerto 4002, API habilitada, Trusted IP 127.0.0.1)
python spy_direction.py            # app real (GUI)
python spy_direction.py --demo     # datos simulados (sin IBKR)
python spy_direction.py --selftest # diagnóstico de conexión/cadena

python spy_walls_coldrun.py        # cold run HEADLESS de Walls/GEX (no requiere mercado) -> debe dar OK
python probe_oi_gamma.py           # LUNES con mercado abierto: verifica OI+gamma reales de IBKR
```
Dependencias: `ib_insync pandas tzdata pyinstaller`. Build exe: `install.bat` (o ver `build_exe.bat`).

## 3. Config (arriba de `spy_direction.py`)
`PORT=4002` (paper; live=4001) · `CLIENT_ID=7` (usar SIEMPRE este) · `QTY=1` ·
`SIGNAL_THRESHOLD=5000` (piso) · `ADAPTIVE=True/ADAPT_FRAC=0.15` · `REPRICE_SECS=4/MAX_FILL_SECS=60` ·
`FLATTEN_HHMM=15:45/STOP_NEW_HHMM=15:40` · `TRADING_ENABLED=False` (se ARMA con el botón) ·
Walls: `WALLS_ENABLED=True`, `WALLS_BAND=10`, `WALLS_RECALC_SECS=180` (3 min), `GEX_CALL_SIGN=+1`,
`GEX_PUT_SIGN=-1`.

## 4. Walls / GEX / Gamma Flip (informativo)
Para la **expiración cercana**, cada 3 min desde tickers en **streaming** (no satura el gateway):
- **Put/Call Wall** (máx OI put/call) y **Magneto**: **estático** (Max Pain con OI-EOD) y **dinámico**
  (Max Pain con OI+volumen intradía — sí se mueve).
- **prem_center**: centro de peso del dinero por strike (premium).
- **GEX** (Σ 100·spot²·(+γc·OIc −γp·OIp)) → régimen **LONG** (>0, mean-reverting) / **SHORT** (<0,
  tendencial); y **Gamma Flip** (nivel donde el GEX neto cruza cero; proxy por acumulada).
- **Gamma Ladder VISUAL (solo lectura, estilo MarketSnack):** Canvas con barras de **premium $ por
  strike** (verde≥precio / rojo<precio), etiquetas **CW/PW/MAG** (magneto), **precio** con señal UP/DOWN
  y **Gamma Flip** como rayas en su carril propio (izquierda, no encima de las barras). Más la raya del
  **contrato comprado** a su strike: su **precio se actualiza en vivo** (`_mid`) y la raya/etiqueta se
  pone **verde si sube / rojo si baja** desde la entrada; solo aparece si hay posición real en IBKR y
  desaparece al vender. Sin botones. NO incluye el "tape" institucional (IBKR no da ese feed) ni chart.
- **Notificaciones (toast Windows):** en cada **giro** de señal y en el **FILL real** de compra/venta
  (`_on_filled`, no al enviar la orden); al vender el toast incluye el **profit $/%**.
- ⚠️ **DECISIÓN DE COMPRA/VENTA = SOLO PREMIUM** (`net_call − net_put` + umbral adaptativo + momentum,
  en `_update_signal`→`self.target`). **TA, GEX, Walls y la Ladder son informativos: NO afectan la
  ejecución** (verificado por grep: `_update_signal`/`trade_poll` no leen ta_vals/gex/walls).
- **NO toca la señal ni la ejecución.** Se registra todo por minuto/3 min en SQLite (`walls_snapshot`,
  `premium_minute` con net_prem/OI/gamma) + logs, para **cruzarlo contra la gráfica** y decidir con
  datos cómo usarlo (mejorar la precisión de los cambios de dirección).
- **Detección de staleness:** avisa en el log si el gamma no cambia (posible dato viejo). OI es EOD.
- ⚠️ **Convención de signo GEX (+call/−put) es HIPÓTESIS** no verificable con IBKR: validar contra el
  precio real varios días antes de accionarlo. Plan completo: `~/.claude/plans/structured-pondering-noodle.md`.

## 5. Persistencia (SQLite `spy_history.db`)
`transitions` (giros), `strike_accum`/`strike_daily` (línea base), `ta_minute` (TA por minuto),
`premium_minute` (premium+net_prem+OI+gamma por strike), `walls_snapshot` (walls/GEX/flip cada 3 min).
Logs: `spy_activity.log` (actividad exhaustiva) y `spy_direction.log` (errores).

## 6. Gotchas de IBKR (IMPORTANTES)
- **`10197 "No market data during competing live session"`**: en fin de semana/mantenimiento IBKR corta
  el market data (precio+OI+greeks) en todos los modos. Se resuelve con **mercado abierto**. También lo
  causa tener la sesión LIVE de IBKR abierta en el teléfono.
- Usar **SIEMPRE clientId 7** y desconexión limpia (no crear muchos clients).
- OI de opciones = **end-of-day** (no intradía). El usuario tiene add-on OPRA ($4.50) → greeks/real-time
  deberían llegar en horario de mercado.
- `reqTickByTickData("AllLast")` NO soportado para opciones (10189) → se usa RTVolume "233".

## 7. Estado y pendientes (resumen — detalle en `ANTI_COMPACT_CONTEXT.md`)
- ✅ Conexión, señal+umbral, TA, ejecución MID-only/1-orden/sin-huérfanas, walls/GEX/flip — verificado
  **headless / cold run**. `spy_walls_coldrun.py` en **VERDE**.
- ❌ **NO VERIFICADO en vivo (LUNES apertura):** fills/rotación/aplanado reales, OI+gamma reales
  (`probe_oi_gamma.py`), frescura del gamma, coherencia GEX/flip/magneto vs precio, calibrar `ADAPT_FRAC`.

## 8. De qué debe estar pendiente el otro agente
- **No afirmar que algo "funciona" sin correrlo de verdad** (el mercado abierto es la única ventana real).
- Correr `probe_oi_gamma.py` **antes** de confiar en el panel Walls/GEX en vivo.
- Vigilar el **límite de líneas de market data** de IBKR (~100): señal+ejecución+baseline+banda; si se
  excede, bajar `WALLS_BAND`.
- Revisar `spy_direction.log` (0 errores) y el aviso de **staleness** en `spy_activity.log`.
- Con TRADING ON: verificar 1 sola posición, sin órdenes huérfanas, aplanado 15:45.

## 8-bis. Estado REAL de la API de IBKR (evidencia de logs, NO memoria)
Todas las funciones de la API de IBKR que usa el sistema (18, extraídas del código) y si dieron data
en corridas reales según `spy_activity.log`/`spy_direction.log`:

| # | Función IBKR | Para qué | ¿Dio data en corrida REAL? (evidencia log) |
|---|---|---|---|
| 1 | `ib.connect` | Conectar (clientId 7) | ✅ SÍ — "Conectado a IB Gateway 127.0.0.1:4002" (18:00, 20:48…) |
| 2 | `ib.reqMarketDataType` | Modo 1 LIVE / 3 DELAYED | ✅ SÍ (ejecutado; cayó a FROZEN/LIVE) |
| 3 | `ib.reqMktData` (precio SPY `""`) | Precio del subyacente | ✅ SÍ — `SPY=773.37 [FROZEN]`, luego `SPY=772.45 [LIVE]` |
| 4 | `ib.reqSecDefOptParams` | Cadena de opciones | ✅ SÍ — `cercano=20260810` + strikes |
| 5 | `ib.qualifyContracts` | Calificar contratos | ✅ SÍ — creó `CALL 772C / PUT 773P` |
| 6 | `ib.reqHistoricalData` | Barras 1 min (TA) | ✅ SÍ — `MIN 18:00 … rsi=59 macdh=+0.049` |
| 7 | `ib.reqContractDetails` | minTick para el MID | ✅ SÍ (órdenes al MID 1.05/2.05) |
| 8 | `ib.accountSummary` | Buying power | ✅ SÍ (corrida previa: $397.13; hubo BUY) |
| 9 | `ib.placeOrder` | Colocar LimitOrder MID | ✅ SÍ (paper) — `ORDEN BUY CALL @1.05` |
| 10-11 | `ib.openTrades` / `ib.positions` | Reconcile / huérfanas | ✅ SÍ — "Cancelada orden huerfana 8944" |
| 12 | `ib.cancelOrder` | Cancelar orden | ✅ SÍ |
| 13-14 | `ib.isConnected` / `ib.sleep` | Control de loop | ✅ SÍ |
| 15 | `errorEvent` (evento) | Capturar errores IBKR | ✅ SÍ (activo) |
| 16 | `pendingTickersEvent` (evento) | Ticks de opciones (flujo) | ⚠️ ejecutó pero SIN data → `netC=0 netP=0` |
| 17 | `ib.reqMktData` (opciones `"233"`) | Flujo de premium por trade | ⚠️ 0 trades (fin de semana, sin OPRA live) |
| 18 | `ib.reqMktData` (banda `"100,101,106"`) + `ib.ticker` | **OI + gamma (Walls/GEX)** | ❌ NUNCA probado en vivo — solo cold run con FakeIB |
| — | `ib.cancelMktData` | Liberar sub de precio | ✅ SÍ |

**Resumen honesto de qué DA data hoy:**
- ✅ **Funciona con IBKR real:** conexión, precio SPY, cadena de opciones, barras 1 min (TA), órdenes
  en paper (placeOrder/cancel/reconcile), lectura de cuenta.
- ⚠️ **Ejecuta pero llega vacío (por finde):** el **flujo de premium de opciones** (`net_call/net_put=0`)
  — el corazón de la señal. Necesita mercado abierto con trades reales.
- ❌ **NO probado contra IBKR nunca:** **OI y gamma de la banda** → todo el módulo Walls/GEX/Flip está
  verificado SOLO headless con **datos falsos (FakeIB)**. Que IBKR entregue OI+gamma reales es
  **HIPÓTESIS** hasta correr `probe_oi_gamma.py` el lunes.
- ⚠️ **OJO:** las líneas `WALLS …` en `spy_activity.log` son del **cold run (FakeIB)**, NO de IBKR.

**Dos observaciones de los logs a vigilar el lunes:**
1. Hubo un `FILL SELL CALL @ 0.00` (20:58) — precio de fill en cero, probable artefacto de paper/dato
   ausente. Confirmar que los fills reales traen precio.
2. `[LIVE]` apareció una vez (20:48) pero el flujo siguió en 0 → sin trades reales la señal no se
   alimenta. Con mercado abierto se resuelve.

**Conclusión:** de las 18 llamadas, ~14 ya dieron data real, 2 ejecutan pero vacías (flujo de opciones,
por finde) y las 2 clave de Walls (OI+gamma) están sin probar en vivo. El probe del lunes mide eso.

## 9. Reglas de trabajo (del usuario — OBLIGATORIAS)
- **Honestidad total.** Marcar siempre **VERIFICADO / NO VERIFICADO / HIPÓTESIS**.
- **No implementar sin probar.** Cold run del **código real** (no scripts que reimplementen la lógica).
- **Radio de cambio mínimo**, conectar/reutilizar (no duplicar), abrir el zoom al analizar.
- **Espejo prod↔cold run:** todo cambio de lógica actualiza su cold run en el mismo cambio y corre verde.
- Comunicación en **español**.

## 10. Documentos del repo
- `ANTI_COMPACT_CONTEXT.md` — **contexto vivo, leer primero** (estado, gotchas, §9 Walls, pendientes).
- `MANUAL.md` — manual de uso. `GUIA_AGENTE.md` / `PROMPT_AGENTE.md` — guía para agentes.
- `GUIA_MONITOR.md` — monitoreo + diagrama de flujo. `README.txt` — nota corta original.
