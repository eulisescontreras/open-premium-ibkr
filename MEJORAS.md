# MEJORAS DETECTADAS — sesión del 2026-08-10 (primera corrida en vivo)

> Documento vivo. Cada mejora lleva la **evidencia numérica** que la respalda, sacada de
> `spy_activity.log`, `spy_history.db` y las ejecuciones reales de IBKR.
> Clasificado como VERIFICADO / HIPÓTESIS según la regla 7.

---

## ESTADO A CIERRE DEL 2026-08-10 (actualizado por la tarde)

| Punto | Estado |
|---|---|
| **M2** P&L descuadrado | ⚠️ **PARCIAL — ver nota** |
| **M5** momentum por eventos (=GAP 5) | ✅ **RESUELTO** — mide `MOMENTUM_SECS=30` s reales. `diff_hist` eliminado |
| **M9** falta sello de configuración | ✅ **RESUELTO** — `sesion_config` **no tenía escritor** (0 `INSERT` en todo el archivo, un `CREATE TABLE` huérfano). Ahora se sella cada arranque |
| **M12** ruido `10349` | ✅ **RESUELTO** — `tif='DAY'` explícito |
| **GAP 2** doble conteo ATM | ✅ **RESUELTO** — manda `_on_ticks` (mide por tick); `compute_walls` ya no suma esos strikes |
| **GAP 4** huérfana EOD | ✅ **RESUELTO** — a partir de `CROSS_HHMM=15:50` las ventas cruzan el spread al BID |
| **GAP 17** stream de barras muerto | ✅ **RESUELTO** (nuevo hoy) — detección por frescura + reposición automática con backoff |
| **M4** ventana móvil vs acumulado | 📊 **INSTRUMENTADO** — se guardan `net_call_1m/5m/15m`; faltan 3-4 sesiones |
| **M10** variables confundidas con la hora | 📊 **INSTRUMENTADO** — premium **por vela** (`prem_call_min`/`prem_put_min`) y distancias |
| **M1** `REPRICE_SECS=4` | ⏳ abierto — no necesita datos, la latencia ya está medida |
| **M3** rotación excesiva | ⏳ abierto — depende del take-profit, que necesita `trades.mfe` |
| **M6** piso 5.000 | ⏳ abierto — no necesita datos |
| **M7** precursor de movimiento | 📊 ver `ANALISIS_ENTRADA_SALIDA.md`: Bollinger **descartado**; lo aprovechable es predecir el mercado PLANO |
| **M8** el cuello de botella es la dirección | ✅ confirmado con más datos: TA 50,2% vs premium 49,6% |
| **M11** greeks incompletos tras reconectar | ⏳ abierto — no necesita datos |
| **GAP 18** giro espurio en el arranque | 🔴 **NUEVO, SIN ARREGLAR** — ver abajo |

### ⚠️ M2 — por qué está PARCIAL (VERIFICADO en vivo el 2026-08-10)

Se implementó leer `RealizedPnL`/`UnrealizedPnL` de `accountSummary()`. **IBKR no los devuelve
por esa vía** en este Gateway:

```
14:28:40  PNL: IBKR no expone RealizedPnL en accountSummary -> el panel sigue usando
          el calculo interno (puede desviarse, ver M2)
```

**Lo que SÍ quedó resuelto:** el sistema detecta la ausencia, avisa en el log, marca el panel
como `(interno)` y, si algún día llega el dato de IBKR y difiere en más de 1 $, lo reporta.
Ya no se puede confundir un número interno con uno del broker.

**Lo que NO:** el P&L mostrado sigue siendo el cálculo interno — el mismo que el 2026-08-10
marcaba −98,11 cuando la cuenta real decía −54.

**Arreglo pendiente:** usar `ib.reqPnL(account)` (stream de PnL) en vez de `accountSummary`.
Requiere suscripción explícita y su propio cold run. **NO implementado.**

### 🔴 GAP 18 — giro espurio en el arranque (VERIFICADO, sin arreglar)

`setup_contracts` suscribe el market data de la señal **antes** de que `_load_intradia`
restaure los acumuladores. En esa ventana (~4 s) `net_call`/`net_put` valen 0, el umbral cae al
piso de 5.000 y cualquier flujo mínimo dispara un giro.

```
14:52:25  NUEVO DIA - acumuladores intradia reiniciados (senal en 0)
14:52:29  GIRO -> DOWN (net_call=-10640 net_put=0 thr=5000)   <- espurio
14:52:33  ESTADO INTRADIA restaurado -> netC=6241134 ... estado=UP
```

Esta vez se corrigió solo en 4 s sin llegar a operar, pero **ya causó daño real** por la mañana:
*"4 giros en 34 s tras el reinicio de las 11:50, cerrando una posición que la señal real habría
mantenido"*. Además escribe **filas falsas en `transitions`** que contaminan el análisis.

Arreglo propuesto (no implementado): no evaluar la señal hasta que `_intradia_ok` sea True, o
suscribir el market data de la señal después de restaurar.

---

---

## PRIORIDAD 1 — Fricción de ejecución (dinero que se pierde sin equivocarse de dirección)

### M1. `REPRICE_SECS=4` es más agresivo que la latencia real de IBKR
**VERIFICADO.** Latencia medida entre colocar y ejecutar, sobre 16 fills:
```
min 1s   mediana 1s   media 3.4s   max 25s
órdenes que tardaron más de 10s: 2
```
El código cancela a los **4 segundos**, que cae justo dentro de la distribución. Se cancelan
órdenes que iban a llenarse, y luego llegan tarde: IBKR llenó una orden **22 s después** de
reportarla como cancelada (episodio 10:55, 3 contratos comprados).

Consecuencia medida:
```
órdenes colocadas : 54
fills             : 24     -> ratio 44%
cancelaciones     : 18
racha máxima de recotizaciones seguidas: 9
rachas de 3 o más: 5 (09:31, 10:22, 10:42, 10:55, 11:04)
```
**Propuesta:** subir `REPRICE_SECS` por encima del percentil alto de la latencia (12-15 s),
o mejor: **no recotizar las COMPRAS** (una entrada, y si no llena en `MAX_FILL_SECS`, se
abandona). Las entradas no son urgentes; las salidas sí.
**Riesgo:** menos fills de entrada. Es deseable dado el exceso de rotación.

### M2. El P&L registrado no cuadra con la cuenta
**VERIFICADO.** Suma de los `PROFIT` del log: **−98.11** en 10 operaciones.
Variación real de la cuenta: **397.13 → ~343 = −54**. Diferencia de ~44 USD.

Causas identificadas:
- El fill perdido de las 10:22 (SELL CALL de la orden 450) nunca calculó su P&L.
- El episodio de los 3 contratos usó un único `entry_price` (1.10) cuando el coste medio
  real fue 1.0933 (comprados a 1.10, 1.04 y 1.04).

**Propuesta:** no calcular el P&L internamente — **reconciliarlo con IBKR**
(`ib.pnl()` / `RealizedPnL` de `accountValues`). El broker ya lleva esa contabilidad.
**Impacto:** hoy el panel te decía −98 cuando la realidad era −54. Es un dato de decisión.

### M3. Rotación excesiva
**VERIFICADO.**
```
posiciones cerradas: 10
duración: mín 10s | mediana 47s | media 315s | máx 1711s
el 60% duraron menos de 60 segundos
42 giros en 102 minutos = 1 cada 2.4 min
```
Con spread de ~0.04 en la 0DTE ATM, cada ida y vuelta cuesta ~$8. **Buena parte de los −54
del día es fricción pura, no dirección equivocada.**
**Propuesta:** mínimo de permanencia (`MIN_HOLD_SECS`) o mínimo de tiempo entre giros.
Pendiente de calibrar con la sesión completa.

---

## PRIORIDAD 2 — Calidad de la señal

### M4. El acumulado desde la apertura podría ser un lastre
**HIPÓTESIS** (dos indicios convergentes, muestra pequeña).
Acierto de los giros según acumulación:
```
por tiempo:     <2min 54% | 2-5min 62% | 5-15min 33% | >15min 0% (n=1)
por magnitud:   BAJO 54%  | MEDIO 62%  | ALTO 38%
```
Ambos cortes apuntan a que **más flujo acumulado = peor acierto**. Un neto que solo suma
se llena de flujo viejo que ya no refleja el posicionamiento actual.
**Propuesta:** calcular `net_call`/`net_put` también en **ventana móvil de 5 y 15 min** y
guardar las tres versiones **sin cambiar la decisión**. En 3-4 días se compara con datos.
**Por qué así:** cambiar directamente a ventana móvil destruiría la posibilidad de comparar.

### M5. `MOMENTUM_WIN` cuenta eventos, no tiempo (GAP 5, sin cerrar)
**VERIFICADO.** La ventana de 8 muestras se llena en 0,0001 s en ráfaga. El comportamiento
es bimodal: vale 0 (mercado tranquilo, las 8 muestras idénticas) o un valor enorme (ráfaga).
Nunca mide una tendencia suave.
Efecto observado: en la apertura el aviso WARN y el FLIP salieron en el **mismo milisegundo**;
a las 10:20 el aviso precedió al giro por **110 segundos**. Sin escala temporal fija.
**Propuesta:** `diff_hist` con tuplas `(monotonic, diff)` y purga por `MOMENTUM_SECS=30`.
**Riesgo:** nulo sobre la ejecución — solo afecta la alerta WARN, no la decisión UP/DOWN.

### M6. El piso `SIGNAL_THRESHOLD=5000` es cien veces menor que el flujo real
**VERIFICADO.** El umbral adaptativo llegó a 146.501 con flujo maduro, pero al arrancar
(y tras cada reinicio) vuelve al piso de 5.000 y cualquier ráfaga lo cruza.
Los tres giros de 11:03:25, 11:03:29 y 11:03:35 (10 segundos) ocurrieron todos con `thr=5000`.
**Propuesta:** subir el piso, o hacerlo proporcional al flujo típico del día anterior.
Pendiente de calibrar.

---

## PRIORIDAD 3 — Detección de oportunidad (filtro de entrada)

### M7. Precursor de movimiento aprovechable
**HIPÓTESIS** (n≈2 episodios independientes, 11 predictores probados — no concluyente).
Con la definición del usuario (movimiento direccional ≥ 0.80 = ~40-50% en una ATM):
```
predictor                sin recorrido   oportunidad   separación
ancho Bollinger %            0.155%        0.109%       -0.79
distancia a VWAP             0.128         0.204        +0.70
precio - centro de peso      0.462         0.664        +0.70
GEX (Bn)                   239.7         256.9         +0.38  DÉBIL
posición en canal CW-PW      72%           70%          nula
```
Lectura: **rango comprimido + precio desplazado de su equilibrio**. Y es
**independiente del signo del GEX**, que es el requisito del usuario.
Hoy hubo oportunidad de ≥0.80 en el **25% de los minutos** y ≥1.00 en el **11%**, todo con
GEX positivo (LONG el 100% del día).
**Pendiente:** confirmar en 3-5 días más, y con al menos un día de GEX negativo.

### M8. El cuello de botella es la DIRECCIÓN, no el timing
**VERIFICADO.** En los momentos con oportunidad real, la señal acertó **8 de 15 (53%)**.
Total del día: **39 giros, 20 aciertos (51%)**.
Caso más claro: `10:44:51 GIRO -> UP` justo cuando empezaba la mayor caída del día (−1.66);
corrigió a DOWN 85 segundos después.
**Implicación:** un filtro de entrada perfecto sobre una señal del 51% sigue perdiendo por
el spread. **Pero** dejar de operar el 75% del tiempo ahorraría casi toda la fricción,
que es una mejora real aunque la dirección no mejore.

---

## PRIORIDAD 4 — Instrumentación y datos

### M9. Falta el sello de configuración
**VERIFICADO.** Hoy cambiaron dos criterios a mitad de sesión (walls OI→gamma a las ~11:03,
strikes OTM→ATM) y **nada en la BD lo indica**. Quien analice la tabla completa concluirá
en falso creyendo que la serie es homogénea.
**Estado:** tabla `sesion_config` ya escrita en el código, **aún no activa** (se activará en
el próximo arranque limpio, no hoy).

### M10. Las variables acumulativas están confundidas con la hora del día
**VERIFICADO.** `gex_total` creció monótonamente de +104 Bn (09:30) a +285 Bn (11:00).
Igual `net_call`/`net_put` (acumulan desde la apertura) y la distancia al gamma flip.
**"GEX alto" ≡ "más tarde en el día".** Cualquier análisis que los use sin controlar por
tiempo encontrará correlaciones falsas — me pasó en el primer análisis de rupturas.
**Propuesta:** guardar además la **variación** de estas magnitudes (delta respecto al
snapshot anterior), que sí es estacionaria.

### M11. Greeks incompletos tras reconectar
**VERIFICADO, menor.** 3 de 47 snapshots tuvieron algún greek ausente; peor caso 14 de 40
contratos. Ocurre en los segundos siguientes a una reconexión, mientras IBKR calcula.
Se autocorrige en el siguiente snapshot. **0 avisos de gamma estancado** en toda la sesión.
**Propuesta:** marcar esos snapshots como parciales en vez de guardarlos como completos.

### M12. Ruido de `code=10349` (54 veces)
**VERIFICADO, cosmético.** Cada orden genera `Order TIF was set to DAY based on order preset`.
Las órdenes se envían sin TIF explícito y el Gateway aplica su preset.
**Propuesta:** fijar `tif='DAY'` explícitamente en la `LimitOrder`. Elimina 54 líneas de ruido
del log y deja el camino abierto a usar IOC/FOK en el aplanado EOD si algún día se quiere.

---

## GAPS DE CÓDIGO AÚN ABIERTOS (del análisis inicial)

| Gap | Estado | Nota |
|---|---|---|
| **2** — doble conteo del premium en los 2 strikes ATM | ⏳ abierto | `_on_ticks` y `compute_walls` escriben la misma clave con deltas independientes |
| **4** — posición huérfana si la venta EOD no llena | ⏳ abierto | autorizado cruzar el spread a las 15:50, sin implementar |
| **5** — momentum por eventos | ⏳ abierto | ver M5 |

---

## LO QUE YA FUNCIONA (no tocar)

- Reconexión automática sin borrar la señal (GAP 1)
- `_sync_pos`: la posición real de IBKR manda sobre el estado interno (GAP 9) — **actuó 5 veces**
- `EXEC REAL` vía `execDetailsEvent`: llega 732 ms antes que el sondeo de estado (GAP 13)
- Límite duro de 1 contrato contando lo que va en vuelo (GAP 14)
- Adopción del contrato en cartera con su market data y su `avgCost` (GAP 8, 12)
- Walls por exposición gamma: CW=775 coincide con MarketSnack (antes 780)
- Strikes que siguen al precio: señal, ejecución (ATM real) y banda (GAP 3)
- `_log_minute` con `ON CONFLICT` en vez de `INSERT OR REPLACE` (GAP 7)
- Precio del SPY en vivo desde las barras (GAP 11)

**0 errores en `spy_direction.log` en toda la sesión. 9 suites de cold run en verde.**
