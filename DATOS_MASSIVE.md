# `massive_premium.db` — premium REAL de opciones (Massive / OPRA)

**Qué es:** el precio REAL al que se negociaron los contratos 0DTE que el backtest opera.
Existe para responder la única pregunta que puede tumbar los +25.769$: **¿los precios del
backtest existieron?** Hasta ahora todo el histórico de 2 años usaba premium **SINTÉTICO**,
calibrado con 3 días (2026-08-11/12/13) y extrapolado a 511 sesiones.

Se descarga con `analisis/massive_premium_real.py` (resumible). Origen: API REST de
[massive.com](https://massive.com), datos OPRA.

---

# ⚠️ LA DESCARGA ESTÁ INCOMPLETA — FALTA APROXIMADAMENTE LA MITAD

**Esta BD NO contiene los 1.268 contratos del plan.** La descarga se hizo en una tanda acotada
por tiempo (el rate limit obliga a 4,4 h para el total) y quedó a medias.

**Lo que hay y lo que falta se consulta con esto, en cualquier momento:**

```powershell
python analisis/massive_premium_real.py estado
```

Imprime cuántos hay, cuántos faltan, cuánto tardarían, el periodo cubierto, las sesiones del año
de reserva y cuál sería el siguiente contrato. **No toca la API ni descarga nada** (abre la BD en
solo lectura). Ejemplo de salida real:

```
contratos en el plan : 1268
ya descargados       : 533  (42%)
PENDIENTES           : 735  -> 2.6 h a 4.8/min
  OK       533
barras de 1 min      : 195750
periodo cubierto     : 2024-08-15 .. 2026-08-13
sesiones del AÑO DE RESERVA (2025-08-01+): 176

lo siguiente que bajaria: 2025-11-13 O:SPY251113C00678000
```

> ⚠️ **NO usar `bajar 0` para consultar.** Con `minutos=0` la guarda del script
> (`if minutos and ...`) es falsa y **no corta nunca**: bajaría el plan entero, 4,4 horas. Para
> eso está el modo `estado`.

O directamente contra la BD:

```sql
-- cuántos hay
SELECT COUNT(*) FROM hechos;                        -- descargados
SELECT COUNT(*) FROM hechos WHERE estado='OK';      -- con datos
-- qué periodo está cubierto
SELECT MIN(fecha), MAX(fecha) FROM hechos;
-- cuántas sesiones del año de reserva
SELECT COUNT(DISTINCT fecha) FROM hechos WHERE fecha >= '2025-08-01';
```

**Qué falta, concretamente:** como la descarga va de lo **más reciente hacia atrás**, lo que está
cubierto es el **año de reserva OOS** (2025-08-01 → 2026-08-13) y lo que falta es el **año 1, el
de entrenamiento** (2024-08-15 → 2025-07-31). Se eligió ese orden a propósito: si la descarga se
corta, lo que queda completo es el año cuyo número importa.

> **Consecuencia para el análisis:** cualquier cifra que se saque con esta BD cubre solo las
> sesiones descargadas. `gate_premium_real.py` solo procesa las que encuentra, así que **no
> falla** — pero el resultado es de una muestra parcial y hay que decirlo al publicarlo.

## CÓMO CONTINUAR SIN VOLVER A DESCARGAR LO MISMO

```powershell
$env:MASSIVE_KEY = [Environment]::GetEnvironmentVariable("MASSIVE_KEY","User")
cd C:\Users\eulis\proyectos\open-premium-ibkr

python analisis/massive_premium_real.py bajar 120    # tanda de 120 minutos
python analisis/massive_premium_real.py bajar        # sin límite, hasta terminar
```

**Retoma exactamente donde se quedó. No hay nada que configurar.** El mecanismo, en el código:

```python
hechos = {r[0] for r in c.execute("select ticker from hechos")}   # lo ya descargado
pend   = [p for p in plan if p["ticker"] not in hechos]           # solo lo que falta
pend.sort(key=lambda p: p["fecha"], reverse=True)                 # reciente primero
```

Y cada contrato se registra **en el momento** de recibirlo, con `commit` inmediato:

```python
c.execute("insert or replace into hechos values(?,?,?,?,datetime('now'))", ...)
c.commit()
```

Por eso da igual cómo se interrumpa —límite de tiempo, Ctrl-C, apagón, matar el proceso—: lo
descargado ya está confirmado en disco y **nunca se vuelve a pedir**. Se puede parar y continuar
tantas veces como haga falta, en tandas de la duración que sea.

**Dos avisos:**
- **No borrar `massive_premium.db`**: es el registro de lo ya hecho. Borrarla obliga a repetir las
  4,4 horas enteras.
- **No regenerar `massive_plan_contratos.json` sin motivo** (`... .py plan`). Si el backtest
  cambia, el plan cambia y podrían aparecer contratos nuevos como pendientes. Los ya descargados
  se conservan igualmente, porque el cruce es por `ticker`.

---

## Esquema

### `aggs` — una fila por contrato y minuto

| campo | tipo | qué es |
|---|---|---|
| `ticker` | TEXT | contrato OPRA, p.ej. `O:SPY260813C00778000` |
| `fecha` | TEXT | `YYYY-MM-DD` de la sesión (= vencimiento, son todos 0DTE) |
| `ts` | INTEGER | timestamp de inicio del minuto, **milisegundos UTC** |
| `open` `high` `low` `close` | REAL | precio del CONTRATO en ese minuto (dólares por acción; ×100 = por contrato) |
| `volume` | REAL | contratos negociados en ese minuto |
| `vwap` | REAL | precio medio ponderado por volumen del minuto |

Clave primaria `(ticker, ts)`.

### `hechos` — control de la descarga (permite reanudar)

| campo | qué es |
|---|---|
| `ticker`, `fecha` | contrato descargado |
| `barras` | cuántos minutos se recibieron |
| `estado` | `OK` / `VACIO` / `HTTP nnn` |
| `cuando` | marca de tiempo de la descarga |

### Cómo se lee el ticker OPRA

```
O:SPY  260813  C  00778000
  │      │     │     │
  │      │     │     └── strike × 1000, 8 dígitos -> 778.00
  │      │     └──────── C = call, P = put
  │      └────────────── vencimiento YYMMDD
  └───────────────────── subyacente
```

---

## ⚠️ La hora está en UTC, no en ET

`ts` son **milisegundos UTC**. Para casar con el resto del proyecto (que trabaja en hora del
Este) hay que convertir:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
hora_et = datetime.fromtimestamp(ts/1000, tz=timezone.utc)\
                  .astimezone(ZoneInfo("America/New_York")).strftime("%H:%M")
```

Ignorar esto desplaza todo 4-5 horas y hace que nada cuadre con `bars_minute`.

---

## Qué NO contiene

| falta | por qué | alternativa |
|---|---|---|
| **bid / ask** | están en `quotes_v1`, que pesa **123-143 GB por día** y está bloqueado | reconstruir como `close*0.99` / `close*1.01` (ver abajo) |
| **griegas** (delta, gamma, theta, vega) | el endpoint `snapshot` da **HTTP 403** con el plan gratuito | `trades.delta_entrada` etc. de la app (vienen de IBKR), o calcularlas con Black-Scholes |
| **IV implícita** | igual que las griegas | despejarla invirtiendo Black-Scholes desde el precio real |
| **minutos sin operaciones** | los agregados solo existen si hubo alguna operación | ver "huecos" abajo |

---

## Cómo reconstruir el bid/ask (y por qué es correcto)

```python
bid = close * 0.99
ask = close * 1.01     # 2% total, el mismo que aplica exp_trail_2min.build_tmp
```

**VERIFICADO**, no supuesto. Se comparó el `close` del agregado contra el `(bid+ask)/2` REAL
guardado por la app en `premium_minute`, midiendo `posicion = (close-bid)/(ask-bid)`:

```
2026-08-11    232 pares    mediana 0.50
2026-08-12    727 pares    mediana 0.50
2026-08-13   1544 pares    mediana 0.50
(0 = pegado al BID, 0.5 = MID, 1 = pegado al ASK)
```

La mediana clavada en 0,50 los tres días significa que **el precio ejecutado cae en el MID**:
el agregado NO lleva el spread dentro, así que aplicarlo por fuera es correcto y **no se cuenta
dos veces**. Y el spread real medido en los datos es 2,2-2,3%, o sea que el 2% está bien
calibrado. Script: `analisis/calibra_ejecutado_vs_mid.py`.

> El 45,5% de los pares cae fuera de `[bid, ask]`. No son ejecuciones fuera de mercado: se
> compara un trade de un instante contra un snapshot de bid/ask de otro instante del mismo
> minuto (la app guarda el bid/ask una vez por minuto). La dispersión es grande pero
> **simétrica**, y por eso el estadístico válido es la mediana.

---

## Huecos: minutos sin barra

Los agregados solo traen minutos en los que **hubo alguna operación en ese contrato**. Medido
con `analisis/huecos_minute_aggs.py`:

```
cobertura mediana             376 de ~390 minutos RTH (96%)
minuto de ENTRADA sin barra    5,7%
minuto de SALIDA  sin barra   14,3%
```

**No son aleatorios.** Las salidas que faltan se concentran en **15:59** (el aplanado de cierre
del sistema) y en **12:00-12:24** (valle de mediodía). Tiene explicación mecánica: las entradas
ocurren en flips, que por definición son momentos con movimiento; las salidas ocurren por reloj
o por cierre, cuando el contrato puede llevar minutos sin negociarse.

**Cómo se tratan** (decidido con el agente de investigación, implementado en
`analisis/gate_premium_real.py`):

| variante | regla |
|---|---|
| **A** | intrínseco desde las 15:55 + última barra dentro de 3 min + descartar y contar el resto |
| **B** | descartar toda operación con hueco en cualquier extremo |
| **C** | última barra hasta 5 min, sin intrínseco |
| **LIMPIO** | solo sesiones sin ningún hueco — no depende de ninguna imputación |

El **intrínseco a partir de las 15:55 no es un apaño**: a un minuto de expirar, el extrínseco de
un 0DTE es ~0 y el sistema sale ITM (profundidad mediana 4,11 en ganadoras, 1,59 en perdedoras),
donde el intrínseco domina. Además **subestima** el precio de venta, o sea perjudica al sistema
— que es el sesgo que conviene cuando uno valida algo propio.

---

## Límites del plan gratuito (`Options Basic`, $0/mes) — todos VERIFICADOS ejecutando

| | |
|---|---|
| **Ventana histórica** | **24 meses móviles**. Medido: 15, 18, 21, 22 y 23 meses OK; 24 meses (2024-08-09) → `HTTP 403` |
| **Rate limit** | ~**5 peticiones/minuto**. A 20/min salta `429` a la tercera. El script usa 12,5 s (4,8/min) |
| **¿Por key o por cuenta?** | **POR CUENTA.** Con una segunda key creada, y la primera descargando, la nueva aguantó 2 peticiones y empezó a dar `429`. **Paralelizar no sirve** |
| **Flat files (S3)** | se pueden **LISTAR** (`us_options_opra`: `minute_aggs` y `trades` desde 2014, `quotes` desde 2022) pero `get_object` da **`HTTP 403`**. No se pueden descargar |
| **Snapshot con griegas** | `HTTP 403` en contrato vivo, con `?date` y vencido |

**Consecuencia práctica:** el backtest empieza el 2024-07-31 y la ventana alcanza hasta
~2024-08-14, así que quedan fuera solo las **~10 primeras sesiones**: es accesible el **98%**.

---

## Qué se descarga y por qué

**No** se bajan los 12 GB de todo OPRA (además de estar bloqueados): solo **los contratos que el
backtest opera de verdad**. La lista está en `massive_plan_contratos.json`, que sale de correr
`backtest_st3_orb.py` recolectando sus operaciones:

```
1.268 contratos 0DTE únicos, 2024-08-15 .. 2026-08-13
~12,5 s por petición  ->  4,4 h el total
```

Se descarga **de lo más reciente hacia atrás**, para tener entero el año de reserva OOS
(2025-08-01 .. 2026-08-13, +11.786$ sintético) antes que el de entrenamiento. Si la descarga se
corta, lo que está completo es el año que importa.

---

## CÓMO SE DESCARGÓ, paso a paso (reproducible)

### Paso 0 — averiguar qué se puede sacar (no fiarse de la web)

La documentación del proveedor no aclara qué incluye cada plan. Todo lo de la tabla de límites se
midió **ejecutando la API**, y hubo dos trampas que conviene conocer:

- **`list` y `get` son permisos distintos.** El bucket S3 se puede listar entero (parece que hay
  12 años de datos) pero `get_object` da `403`. Quedarse en el `list` habría llevado a la
  conclusión contraria.
- **`429` no es `403`.** Al encadenar peticiones sin pausa, el rate limit aparece de formas
  distintas y puede confundirse con falta de permisos. Solo separando las llamadas 14 s apareció
  el patrón real: `403` sostenido a los 24 meses, OK por debajo.

### Paso 1 — saber QUÉ contratos hacen falta

No se descarga "el histórico del SPY" (son 12 GB y están bloqueados). Se descargan **solo los
contratos que el backtest compra**. Se obtienen corriendo el backtest real y recolectando sus
operaciones:

```
python analisis/massive_premium_real.py plan
```

Esto ejecuta `backtest_st3_orb.sesiones()` + `sen_principal` + `orb_senal` + `simular()`, y de
cada operación toma `fecha`, `strike` y `right`. Resultado: `massive_plan_contratos.json`, con
**1.268 contratos únicos** (un contrato puede repetirse dentro del día; se baja una sola vez).

### Paso 2 — construir el ticker OPRA

El backtest da `(fecha, strike, right)`; la API necesita el símbolo OPRA. Como el sistema solo
opera 0DTE, **el vencimiento es la propia fecha de la operación**:

```python
def ticker_opra(fecha, strike, right):
    yy = fecha[2:4]; mm = fecha[5:7]; dd = fecha[8:10]
    return "O:SPY%s%s%s%s%08d" % (yy, mm, dd, right, int(round(float(strike) * 1000)))

# 2026-08-13, strike 778.0, call  ->  O:SPY260813C00778000
```

Comprobado sobre los contratos descargados: el vencimiento coincide con el día de operación en
el 100% de los casos, y **0 vacíos** — el SPY tiene vencimientos diarios de lunes a viernes desde
2022, así que no hay huecos de contratos inexistentes.

### Paso 3 — pedir los agregados de 1 minuto

Un contrato = una petición. Endpoint:

```
GET https://api.massive.com/v2/aggs/ticker/{TICKER}/range/1/minute/{FECHA}/{FECHA}
    ?adjusted=true&sort=asc&limit=50000&apiKey={KEY}
```

Como es 0DTE, la fecha de inicio y de fin son la misma: toda la vida del contrato cabe en una
sesión. `limit=50000` sobra de largo (máximo ~390 barras) pero evita paginación.

### Paso 4 — respetar el rate limit

```python
PAUSA = 12.5   # segundos -> ~4,8 peticiones/minuto
```

Medido: a 20/min salta `429` a la **tercera** petición. Con 12,5 s se sostiene indefinidamente —
verificado con más de 200 peticiones seguidas sin un solo `429`. Ante un `429` el script espera
30 s y reintenta hasta 3 veces.

**No se puede acelerar paralelizando**: el cupo es de la CUENTA, no de la key. Se comprobó
creando una segunda API key y usándola mientras la primera descargaba — aguantó 2 peticiones y
empezó a dar `429`.

### Paso 5 — orden de descarga y reanudabilidad

Se baja **de lo más reciente hacia atrás** (`pend.sort(key=fecha, reverse=True)`), para que si la
descarga se corta esté completo el **año de reserva OOS**, que es el número que vale, y no la
mitad del año de entrenamiento.

Cada contrato se registra en la tabla `hechos` nada más recibirlo, con `commit` inmediato. Al
arrancar, el script lee `hechos` y salta lo ya descargado, así que **se puede parar y continuar
cuantas veces haga falta**:

```powershell
$env:MASSIVE_KEY = [Environment]::GetEnvironmentVariable("MASSIVE_KEY","User")
python analisis/massive_premium_real.py bajar 120     # tanda de 120 minutos
python analisis/massive_premium_real.py bajar         # sin límite, hasta acabar
```

Los contratos anteriores a `LIMITE_ANTIGUEDAD = "2024-08-15"` se excluyen del plan: están fuera
de la ventana de 24 meses y devolverían `403`.

### Coste total

```
1.268 contratos x 12,5 s  =  4,4 horas
```

Repartibles en tandas. La primera cubrió el año de reserva; el año de entrenamiento queda para
una segunda.

---

## Cómo usarlo

**Reanudar la descarga:**
```powershell
$env:MASSIVE_KEY = [Environment]::GetEnvironmentVariable("MASSIVE_KEY","User")
python analisis/massive_premium_real.py bajar 120      # 120 minutos, o sin número = todo
```
Salta lo ya descargado (tabla `hechos`), así que se puede parar y continuar sin repetir nada.

**Correr el gate (real vs sintético):**
```
python analisis/gate_premium_real.py [desde_fecha]
```
Construye un `premium_minute` desde estos agregados y se lo pasa a `simular()` como `db_velas`,
igual que el backtest hace con la sintética: **lo único que cambia entre las dos corridas es la
fuente de precios**.

**La credencial** se lee de la variable de entorno `MASSIVE_KEY`. NO está en el código ni en el
repositorio. Se borra con:
```powershell
[Environment]::SetEnvironmentVariable('MASSIVE_KEY',$null,'User')
```

---

## Resultado obtenido hasta ahora

Con 30 sesiones del año de reserva (`analisis/gate_premium_real.py`):

```
var           SINTETICO       REAL     diferencia   ops
A intr+3m     +2822.44$    +818.03$    -2004.41$     67
B descarta    +2822.44$    +562.73$    -2259.71$     64
C prev 5m     +2822.44$    +849.71$    -1972.73$     67

SUBCONJUNTO LIMPIO (18 sesiones, 41 ops, sin imputación ninguna):
  SINTETICO +1464.07$   REAL +997.60$   -> el real es el 68% del sintético
```

- **Las tres variantes coinciden** (−1.973 a −2.260): la regla de imputación **no** decide el
  resultado.
- Pero hay una **discrepancia importante**: en la muestra completa el real es el **29%** del
  sintético y en el subconjunto limpio el **68%**. El desplome se concentra en las sesiones
  **con** huecos. HIPÓTESIS: los huecos aparecen en contratos poco líquidos y ahí el precio real
  es mucho peor que el sintético, que asume liquidez perfecta. La cifra honesta está entre ambas
  y depende de si esas operaciones eran realmente ejecutables.
- Los huecos **no** eliminan un tipo de día: de las 12 sesiones con hueco, 7 cerraron en positivo
  y 5 en negativo.

**NO VERIFICADO:** son 30 de las 260 sesiones del año de reserva. Hay que repetirlo con el año
completo y compararlo contra los +11.786$ antes de dar una cifra definitiva.
