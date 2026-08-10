# GUÍA DEL AGENTE MONITOR — SPY Direction (en vivo)

Este documento es para el **agente que monitorea la app en vivo** junto al usuario y le da
feedback. Explica qué es, cómo se conecta TODO, qué vigilar minuto a minuto, y dónde mirar.

---

## 1. QUÉ ES (en 3 líneas)
App **independiente** (1 archivo `spy_direction.py`, o `dist\spy_direction.exe`) que:
- Lee flujo de opciones de SPY (IBKR) → calcula **dirección UP/DOWN** por premium call vs put.
- Puede **ejecutar** (rotar 1 opción, paper) y calcula **TA de 1 min** (informativo).
- Registra **todo por minuto** en SQLite y en logs de texto.

---

## 2. DIAGRAMA DE FLUJO (cómo se conecta absolutamente todo)

```
                        ┌──────────────────────────────────────────────┐
                        │              IB GATEWAY (paper 4002)          │
                        │   (cuenta IBKR, datos OPRA en vivo + cuenta)  │
                        └───────────────▲───────────────┬──────────────┘
                                        │ órdenes       │ market data
              placeOrder/cancelOrder    │               │ reqMktData(233), reqHistoricalData(1min),
              (LimitOrder MID+reintentos)│               │ reqSecDefOptParams, accountSummary, positions
                                        │               ▼
   ┌────────────────────────────────────┴───────────────────────────────────────────────┐
   │                              spy_direction.py  (ib_insync)                            │
   │                                                                                      │
   │  DATOS ENTRANTES                         NÚCLEO                      SALIDAS          │
   │  ─────────────                           ──────                      ───────          │
   │  • SPY precio (fallback LIVE→FROZEN)                                                  │
   │  • Opciones ATM/ITM venc. más cercano ─► _on_ticks(): Δvolumen×precio ─► net_call/put │
   │    (call+put) RTVolume 233               │    (agresor por bid/ask)     │             │
   │  • Banda ATM/ITM de expiraciones  ──────►│    cum_prem/today_prem por strike           │
   │    FUTURAS (baseline)                     │                              │             │
   │  • Barras 1 min (keepUpToDate) ─────────► TAEngine (RSI/EMA/MACD/BB/ATR/VWAP/OBV)      │
   │                                          │                              │             │
   │                          _update_signal(): umbral ADAPTATIVO ─► estado UP/DOWN         │
   │                                          │                              │             │
   │                    ┌─────────────────────┼──────────────────────────────┐            │
   │                    ▼                     ▼                              ▼            │
   │              ALERTAS                TRADE MANAGER                    REGISTRO          │
   │        banner + toast Win        (si TRADING ON):               SQLite spy_history.db │
   │        en cada GIRO (FLIP)       rota 1 opción: SELL viejo       • transitions (giros) │
   │                                  + BUY nuevo al MID, reintentos, • ta_minute (x min)   │
   │                                  1 sola opción, EOD 15:45 aplana • premium_minute(xmin)│
   │                                                                  • strike_accum/daily  │
   │                                                                                      │
   │  PANTALLA Tkinter: UP/DOWN gigante · POSICION · TRADING ON/OFF · TA 1m · baseline ·   │
   │                    historial · botón ARMAR/DESARMAR                                   │
   │                                                                                      │
   │  LOGS (carpeta de la app):  spy_activity.log (qué hizo, exhaustivo)                   │
   │                             spy_direction.log (errores/excepciones)                  │
   └──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. QUÉ MONITOREAR (checklist en vivo, lunes 9:30–16:00 ET)

**A) Conexión y datos**
- [ ] Pantalla muestra **`[LIVE]`** (no DELAYED/FROZEN). Si no → sin flujo real, avisar.
- [ ] `spy_activity.log` tiene línea `Conectado...` y `SETUP OK ...` con strikes correctos.
- [ ] Aparecen líneas `MIN hh:mm SPY=... TA=... netC=.. netP=..` **cada minuto** (registro vivo).

**B) Señal (premium)**
- [ ] `CALL net` / `PUT net` se mueven de forma coherente (millones, no miles).
- [ ] Los **GIROS** (UP↔DOWN) coinciden con el sentido del precio de SPY.
- [ ] No hay parpadeo excesivo (si cambia cada segundo → subir `SIGNAL_THRESHOLD`/`ADAPT_FRAC`).

**C) Ejecución (si el usuario pulsó ARMAR → TRADING ON)**
- [ ] **Una sola opción** abierta a la vez (POSICION: FLAT / LONG CALL / LONG PUT).
- [ ] En cada giro: vende la vieja y compra la nueva **al MID** (ver `ORDEN`/`FILL` en activity log).
- [ ] **Sin órdenes colgadas** (si una no llena, re-precia; ver reintentos).
- [ ] **Buying power**: si no alcanza, log dice "sin buying power" y NO abre.
- [ ] **15:45 ET**: se **aplana** todo (FILL SELL → pos FLAT). Al cierre NO debe quedar ninguna opción.

**D) TA (informativo)**
- [ ] `TA 1m` se actualiza cada minuto (dir/RSI/MACD). No bloquea órdenes (por diseño).

**E) Registro / estadísticas**
- [ ] `ta_minute` y `premium_minute` crecen ~1 fila/min (ver §5 SQL).

**F) Errores**
- [ ] `spy_direction.log` **vacío o sin ERROR/EXCEPCION**. Si aparece algo → reportar el traceback.

## 4. BANDERAS ROJAS (alertar fuerte al usuario)
- Modo `DELAYED`/`FROZEN` en horario de mercado (no hay datos en vivo).
- Dos opciones abiertas a la vez, o una opción que quedó abierta después de 15:45.
- Órdenes que nunca llenan y se acumulan (colgadas).
- `spy_direction.log` con excepciones repetidas.
- Giros cada pocos segundos (whipsaw) quemando comisiones.

## 5. DÓNDE MIRAR (archivos y consultas)
Carpeta de la app: `C:\Users\17862\open-premium-ibkr\`
- **Logs:** `spy_activity.log` (qué hizo), `spy_direction.log` (errores).
- **BD:** `spy_history.db`. Consultas útiles (sqlite3):
```sql
-- últimos minutos: precio + TA + premium neto + estado
SELECT hora,spy,ta_dir,rsi,macd_hist,net_call,net_put,prem_state
FROM ta_minute ORDER BY fecha DESC,hora DESC LIMIT 20;

-- premium por strike en el último minuto
SELECT hora,expiry,strike,right,cum_prem,day_prem
FROM premium_minute ORDER BY fecha DESC,hora DESC LIMIT 20;

-- giros del día
SELECT fecha,hora,tipo,estado,spy FROM transitions ORDER BY id DESC LIMIT 20;
```

## 6. FEEDBACK AL USUARIO (formato sugerido cada ~15–20 min)
- Estado: `[LIVE]` OK / problema.
- Última señal y hora; ¿coincidió con el precio?
- Posición actual y últimas órdenes (llenaron al mid, sí/no).
- Registro por minuto creciendo (sí/no).
- Errores en `spy_direction.log` (sí/no + cuál).
- Recomendación de calibración si parpadea o no dispara.

## 7. HONESTIDAD (contexto para el agente)
- El premium es **adelantado**; el TA es **rezagado** (solo se registra para medir, no decide).
- Es cuenta **paper** (~$397). 0DTE decae rápido; whipsaw + comisiones son el riesgo principal.
- La app es **1 archivo** + 1 exe; sin servidores. Si algo falla, casi siempre es IB Gateway
  (cerrado / API off / sin datos en vivo) o los umbrales mal calibrados.
```
