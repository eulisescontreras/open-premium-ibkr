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
