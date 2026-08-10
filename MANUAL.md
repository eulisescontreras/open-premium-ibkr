# SPY Direction — MANUAL COMPLETO

App **independiente** (no toca ningún bot) para apoyar **scalping de SPY** con el flujo
de opciones vía IBKR. Todo vive en `C:\Users\17862\open-premium-ibkr\`.

---

## 1. QUÉ HACE
Dos cosas a la vez:

**A) Señal en vivo — pantalla UP / DOWN**
- Toma el **vencimiento más cercano** (el próximo a expirar; puede ser hoy o a pocos días).
- Elige strikes **ATM/ITM** (CALL con strike ≤ precio, PUT con strike ≥ precio; nunca OTM).
- Mide el **neto de premium comprado en calls vs puts** desde la apertura.
- **UP** (verde) = domina el flujo de calls → sesgo alcista. **DOWN** (rojo) = domina puts.
- **Notificación de Windows** (esquina inferior derecha) + banner rojo **en el giro confirmado**
  (el momento de tomar acción). Banner naranja = aviso anticipado (posible giro).

**B) Línea base — "valor default por día" (fechas posteriores)**
- Acumula el premium ATM/ITM de **varias expiraciones FUTURAS** (las siguientes a la cercana).
- Guarda un **acumulado en la BD desde el primer día** de uso (crece día a día).
- Cada mañana tienes un **valor de referencia del día previo**; si al abrir el mercado ese
  valor **cambia drásticamente**, la pantalla lo marca **STRONG** → señal temprana del día.

---

## 2. REQUISITOS
- **IB Gateway** abierto y **logueado** (cuenta paper).
- API habilitada: *Configure → Settings → API → Settings*:
  - ✅ Enable ActiveX and Socket Clients
  - **Socket port: 4002** (paper). Live = 4001.
  - ✅ Allow connections from localhost (Trusted IP `127.0.0.1`).
- **Datos de opciones en tiempo real (OPRA)** — tu cuenta YA los tiene
  ("US Equity and Options Add-On Streaming Bundle"). Sin real-time, corre en DELAYED.
- Para el `.exe` no hace falta Python. Para correr el `.py`: Python 3.11 + `ib_insync`.

---

## 3. INSTALACIÓN (máquina nueva)
1. Copiar la carpeta `open-premium-ibkr` completa (incluye la BD si quieres conservar el historial).
2. Doble clic en **`install.bat`** → instala Python (si falta), dependencias y crea `dist\spy_direction.exe`.

Manual: `pip install ib_insync pyinstaller` y luego `build_exe.bat`.

---

## 4. CÓMO EJECUTAR
- **Producción:** doble clic en `dist\spy_direction.exe` (con IB Gateway abierto).
- **Con Python:**
  - Real: `python spy_direction.py`
  - Demo (sin mercado, para ver la pantalla): `python spy_direction.py --demo`
  - Diagnóstico (sin ventana): `python spy_direction.py --selftest`

---

## 5. QUÉ HACER AL ABRIR EL MERCADO (9:30 ET) — CHECKLIST
1. **Antes de las 9:30:** abre IB Gateway y loguéate (paper). Abre la app.
2. Verifica arriba en la pantalla el **modo**:
   - **`[LIVE]`** ✅ → datos en vivo, todo correcto.
   - **`[DELAYED]`/`[FROZEN]`** ⚠️ → NO hay flujo real por-trade (revisa OPRA / que sea horario de mercado).
3. Confirma que muestra el **vencimiento más cercano** y los strikes **CALL/PUT ATM**.
4. **Primeros 15–30 min (la ventana clave):** observa
   - La palabra grande **UP/DOWN** y los `CALL net` / `PUT net` moviéndose.
   - **Notificación** cuando haya **giro confirmado** = momento de evaluar entrada.
   - La sección **Línea base**: si algún lado sale **STRONG**, hubo un cambio fuerte
     respecto al día previo → confirma el sesgo del día.
5. Opera SPY según tu criterio de scalping usando la dirección como apoyo (no es garantía).

---

## 6. QUÉ VIGILAR (día a día)
- **Modo siempre en `[LIVE]`** durante el mercado. Si cae a DELAYED, la señal no sirve para scalping.
- **Coherencia:** que UP salga cuando `CALL net` > `PUT net` (y al revés).
- **Baseline STRONG** repetido: úsalo como confirmación del sesgo de apertura.
- El **historial de giros** (abajo) queda guardado en `spy_history.db`.

---

## 7. CÓMO CALIBRAR (IMPORTANTE — hacerlo el primer día en vivo)
Los umbrales vienen puestos para las magnitudes del **demo**. El flujo real de SPY es de
**millones de US$**, así que hay que subirlos para que no cambie de más.

**Pasos:**
1. Corre la app en vivo ~15–20 min y **mira los valores `CALL net` / `PUT net`** en pantalla.
2. Ajusta en `spy_direction.py` (arriba, sección CONFIG):
   - `SIGNAL_THRESHOLD` → ponlo alrededor de **10–20% del `net` típico** que veas
     (ej.: si el neto ronda ±$2.000.000, prueba `SIGNAL_THRESHOLD = 300000`).
   - `MOMENTUM_MIN` → similar, un poco menor que el umbral (ej. `150000`).
3. Guarda y reinicia (o reconstruye el `.exe` con `install.bat`).
4. Repite hasta que los giros ocurran **con sentido** (no cada segundo, no demasiado tarde).

| Constante | Qué hace | Cómo ajustar |
|---|---|---|
| `SIGNAL_THRESHOLD` | US$ neto para cambiar UP/DOWN | Subir si parpadea; bajar si tarda |
| `MOMENTUM_MIN` | Fuerza del aviso anticipado | ~50–70% del umbral |
| `WARN_BAND_FRAC` | Qué tan cerca del cruce avisa | 0.5–0.7 |
| `ITM_DEPTH` | Strikes ITM por lado en baseline | 2–5 |
| `BASELINE_EXPIRIES` | Expiraciones futuras a seguir | 2–4 |
| `OPEN_JUMP_FACTOR` | Umbral de "STRONG" (hoy vs prev) | 1.3–2.0 |

> ★ Recomendado: te lo puedo dejar **adaptativo** (umbral = % del premium total en vivo)
> para no tener que calibrar a mano. Pídelo y lo activo.

---

## 8. ARCHIVOS
| Archivo | Qué es |
|---|---|
| `spy_direction.py` | App completa |
| `dist\spy_direction.exe` | Ejecutable autónomo |
| `install.bat` / `build_exe.bat` | Instalar / empaquetar |
| `MANUAL.md` | Este manual |
| `GUIA_AGENTE.md` | Guía técnica para otro agente |
| `README.txt` | Guía corta |
| `spy_history.db` | **Historial + acumulado** (viaja con la app). NO borrar si quieres conservar la base. |
| `spy_activity.log` | **Actividad exhaustiva del día** (qué hizo el sistema minuto a minuto). |
| `spy_direction.log` | **Errores/excepciones** (vacío = todo bien). |
| `GUIA_MONITOR.md` | Guía + diagrama de flujo para el agente que monitorea en vivo. |

**Tablas en la BD:** `transitions` (giros), `strike_accum` (acumulado persistente por
strike/expiración desde el día 1), `strike_daily` (premium por día, para comparar aperturas).

---

## 9. PROBLEMAS COMUNES
- **"SIN CONEXION"** → IB Gateway cerrado / API off / puerto ≠ 4002.
- **`[DELAYED]`/`[FROZEN]`** → falta OPRA en vivo o mercado cerrado.
- **`net = 0` todo el tiempo** → mercado cerrado, o sin suscripción, o fuera de horario.
- **Cambia de dirección demasiado seguido** → sube `SIGNAL_THRESHOLD` (ver §7).
- **Baseline vacía los primeros días** → normal: el acumulado se construye con los días de uso.

---

## 11. TRADING AUTOMÁTICO (rotar 1 opción)
La app puede **ejecutar** en IBKR: al cambiar la dirección rota **una sola opción**
(UP → compra CALL; DOWN → compra PUT; en el giro vende la que tenía y abre la contraria).
Siempre **ATM/ITM del vencimiento más cercano**, **1 contrato**, **al MID con reintentos**,
**una sola opción abierta**, y **plana a las 15:45 ET**.

**Cómo usarlo (SEGURO):**
1. Arranca **APAGADO**. En la pantalla verás **TRADING OFF** (rojo).
2. Cuando quieras que opere, pulsa **ARMAR** → pasa a **TRADING ON** (verde).
3. La línea **POSICION** muestra FLAT / LONG CALL xxx / LONG PUT xxx y la última acción.
4. Para detenerlo, pulsa **DESARMAR** (deja de abrir; lo abierto se aplana igual a las 15:45).

**Reglas de ejecución:**
- **PAPER** primero (puerto 4002). Live (4001) solo cuando tú lo decidas en el config.
- **Buying power:** antes de comprar verifica fondos; si no alcanza para 1 contrato, NO abre.
- **SIEMPRE LimitOrder al MID** (nunca market/bid/ask). Si no hay MID, no coloca y espera.
- **Reintenta hasta llenar:** re-cotiza al MID nuevo cada ~4s. La VENTA (cierre) es RELENTLESS;
  la COMPRA se abandona si no llena en ~60s (queda FLAT). También en EOD cierra al MID (no cruza).
- **Una sola orden a la vez, sin órdenes huérfanas** (recotiza solo tras confirmar el cancel →
  nunca 2 límits → no se abre un short). Al arrancar/cerrar cancela colgadas; si hay >1 posición, aplana.
- **Strike operado = ATM del lado OTM** (compra call arriba del precio / put abajo). La señal
  sigue en ATM/ITM; se OPERA el OTM (más barato, más gamma; delta ~0.40–0.48).
- **Sin BD de trades** (no guarda profit; solo compra/vende).

**Config (arriba de `spy_direction.py`):** `TRADING_ENABLED` (default False), `QTY` (1),
`REPRICE_SECS` (4), `MAX_FILL_SECS` (60), `FLATTEN_HHMM` (15:45), `STOP_NEW_HHMM` (15:40),
puerto `PORT` (4002 paper / 4001 live).

**Umbrales ADAPTATIVOS:** `ADAPTIVE=True` → el umbral se auto-ajusta a la magnitud real
del flujo (`ADAPT_FRAC=0.15`). No hace falta calibrar a mano; súbelo/bájalo si opera de más/menos.

**Riesgo (honesto):** órdenes reales sin undo (por eso paper). 0DTE decae rápido; el whipsaw
y las comisiones pueden sangrar una cuenta chica. Empieza en paper y observa varios días.

## 12. TA DE 1 MIN + REGISTRO POR MINUTO (estadísticas)
La app calcula el **mismo TA del bot** sobre barras de **1 min** de SPY:
**RSI(14), EMA(8/21/50), MACD(12/26/9), Bollinger(20,2), ATR(14), VWAP, OBV**, con el mismo
scoring → dirección BULL/BEAR/NEUTRAL. Se ve en pantalla (línea "TA 1m: ...").

**Uso actual:** solo **informativo + registro** (NO bloquea las órdenes). Razón: el premium/tape
es adelantado; el TA es rezagado. Primero se registra para medir; más adelante, si los datos lo
respaldan, se usará como filtro/veto ligero (nunca como driver).

**Registro por minuto en la BD** (para sacar estadísticas), cada minuto guarda:
- `ta_minute`: fecha, hora, **precio SPY (close)**, RSI, EMA8/21/50, MACD (line/signal/hist),
  Bollinger, ATR/ATR%, VWAP, OBV trend, ta_score, ta_dir, net_call, net_put, estado premium.
- `premium_minute`: premium acumulado y del día **por cada strike** ATM/ITM seguido (call y put).

Así tienes el histórico minuto a minuto de **precio + TA + premium por strike** para cruzarlos
y ver qué anticipa los cambios. Todo en `spy_history.db` (viaja con la app).

**Dependencia:** pandas (la maneja `install.bat`). El `.exe` la trae incluida.

## 10. NOTA HONESTA
- Este "Open Premium" es **casero** (neto de premium call vs put por lado agresor);
  **no** es idéntico al de MarketSnack (fórmula propietaria), pero captura el mismo concepto.
- Es **apoyo direccional**, no garantía. La relación flujo→precio en la apertura está
  validada de forma **parcial**; la línea base necesita **varios días** para ser útil.
- Todo el flujo por-trade requiere **datos en vivo (LIVE)**; en DELAYED no sirve para scalping.
