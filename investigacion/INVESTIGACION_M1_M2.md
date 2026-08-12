# Investigación M1 / M2 — dominancia acumulada del premium

**Sesión 2026-08-11 (tarde/noche).** Datos: 2 sesiones (08-10, 08-11).
Todo lo de aquí sale de ejecutar sobre `spy_history.db` en modo solo-lectura.

> **Aviso que gobierna el documento:** siguen siendo DOS DÍAS, y **los dos bajaron**
> (−0,36 y −2,73). No hay ni una sesión alcista en la muestra. Nada de lo que sigue
> está establecido.

---

## 1. Las tres lecturas definidas

Todas usan la misma regla: mayor CALL → UP, mayor PUT → DOWN, iguales → NEUTRAL.
Cambia **qué** se compara:

| | qué compara | velocidad |
|---|---|---|
| **SEÑAL** | `\|CALL\|` vs `\|PUT\|` **de ese minuto** | la más rápida (19 cambios/día) |
| **M1** | `#UP` vs `#DOWN` — contador de **minutos** acumulado | la más lenta (5 cambios/día) |
| **M2** | `$UP` vs `$DOWN` — contador de **dólares** acumulado | intermedia (7 cambios/día) |

`$UP` acumula `\|C\|−\|P\|` en los minutos que gana el call; `$DOWN` en los que gana el put.

**IDENTIDAD VERIFICADA:** el "acumulado neto con signo" (suma corrida de `\|C\|−\|P\|`)
es **exactamente `$UP − $DOWN`**. No es un cuarto método: es M2 visto de otra forma.

Salidas generadas (en `investigacion/`):
`TABLA_SENAL_M1_M2_ACUM.txt`, `contador_dolares_*.txt`, `cuadros_tendencias_08-10.txt`,
`bloques_senal_08-10.txt`, `magnitud_10min_*.txt`, `spy_1min_completo_*.txt`

---

## 2. VERIFICADO — hallazgos sobre la CALIDAD del dato

### 2.1 El re-centrado de strike contamina la MAGNITUD (GAP D, no activo en ninguna sesión)

Cruzando `spy_activity.log` con la BD:

```
minutos con re-centrado:   08-10: 38     08-11: 58
de los 15 mayores saltos de net_call de 1 min:
   9 caen en minuto con re-centrado (08-10)
   8 caen en minuto con re-centrado (08-11)
```

El mayor del 08-11 (12:24, +1.910.000) es el caso ya documentado en
`ANTI_COMPACT_CONTEXT.md` §D como *"+1,9M en un minuto: IMPOSIBLE"*.

⇒ **La magnitud en dólares NO es medible en estas dos sesiones.** El contador binario
(M1) aguanta razonablemente; M2 y el acumulado arrastran el fantasma para siempre,
porque solo suman.

Bloques de 10 min utilizables: **16 de 34 (08-10)** y **18 de 37 (08-11)**.
Y no son aleatorios: son los ratos en que el precio no se movió lo bastante para
recentrar. Se mide la magnitud justo cuando no pasaba nada.

### 2.2 El open interest no sirve para distinguir apertura de cierre

`premium_minute.open_interest` tiene **un solo valor distinto por strike y día**.
Es el OI del cierre anterior; no se actualiza intradía.

⇒ El agresor del tape dice **quién cruzó el spread**, no si la posición se **abre o se
cierra**. Comprar un put para cerrar un put corto es alcista y deja la misma huella que
abrir un put largo. **Esta ceguera no la arregla pasar de bruto a neto.**

### 2.3 Falta la primera media hora de la sesión

`ta_minute` empieza a las 09:55. Rellenando con Yahoo Finance 1m (validado: 323 minutos
solapados el 08-10, mediana +0,000, rango −0,02 a +0,14):

```
08-10: faltan 67 minutos, entre ellos 09:30-09:54 y 13:25-13:59
```

El hueco de 13:25-13:59 no escondía nada (deriva −0,29). **Pero 09:30-09:54 sí:**
la mejor ventana de 60 min del 08-10 es **09:45→10:45 = +2,09, al alza**, y el mayor
movimiento de 1 min es **09:33→09:34 = −0,64**. Ambos fuera del registro.

⇒ El 08-10 no fue "bajista con rebotes": fue una **subida de 2 puntos en la primera hora**
que el sistema ve ya empezada, y luego la devolución.

---

## 3. DESCARTADO — no volver a proponerlo

### 3.1 Combinar SEÑAL + M1 + M2 en una regla

En los 7 giros grandes de las 2 sesiones, las tres columnas producen solo
**3 estados distintos de los 8 posibles**, y dos son contradictorios:

```
DOWN/DOWN/DOWN  ->  2 veces UP y 2 veces DOWN
UP/UP/UP        ->  1 vez UP y 1 vez DOWN
UP/DOWN/UP      ->  1 vez DOWN
```

Enumeradas **las 256 reglas posibles** sobre 3 binarios: **0 aciertan los 7 eventos.**

⚠️ **NO es falta de muestra.** Es que la misma lectura precede a resultados opuestos.
Razón mecánica: las tres columnas son **tres transformaciones de los mismos dos números**
(`net_call`, `net_put`). No son tres miradas independientes. Más sesiones no lo arreglan.

### 3.2 Medir "acierto en los giros" como criterio

Un giro es **por definición** un máximo o mínimo local. Cualquier variable que mida
"el precio está alto" acierta por construcción. Comprobado:

```
gamma_flip (dist. al flip)     7/11 =  64%
media móvil de 30 min          9/9  = 100%   <- no usa opciones
media móvil de 60 min          9/9  = 100%   <- no usa opciones
punto medio del día            8/11 =  73%   <- no usa opciones
```

⇒ El 5/6 aparente del gamma flip queda invalidado. **Y el marco de evaluación entero
con él:** mientras se mida "acierto en los giros", no se puede distinguir un predictor
de una tautología.

### 3.3 El barrido de las 32 variables de `ta_minute` contra los flips

Mejor variable: `sma200`, separación 0,886, **p = 0,015** con nula por desplazamiento
circular. **Es basura:**
- `rho(sma200, hora del día) = −0,982` → es un cronómetro (§5.3 del doc original).
- Solo existe en el 08-11; el 08-10 la columna está vacía.
- Con 10 eventos positivos y 32 variables, la nula ya produce 0,730 de mediana y 0,906 de máximo.

### 3.4 El premium como "dinero que entra o sale del mercado"

Cada operación tiene dos lados: la prima que paga uno la cobra otro. El premium en puts
**no retira dinero del subyacente**. El canal real por el que las opciones mueven el SPY
es la **cobertura de los dealers** (gamma), que es lo que mide `walls_snapshot`.

---

## 4. MEDICIONES DE M1 / M2 (todas con n insuficiente)

### 4.1 Exactitud en los cambios de tendencia

27 giros (zigzag umbral 0,45) sobre las 2 sesiones:

```
M1 (minutos):   15/27 = 56%   IC95% [37% , 72%]   margen ±18 puntos
M2 (dólares):   13/27 = 48%   IC95% [31% , 66%]   margen ±18 puntos
referencia "siempre DOWN":  14/27 = 52%
```

M1 dice DOWN en **24 de 27** giros: acierta 13/14 de los DOWN y **2/13 de los UP**.
⇒ Toda la aparente exactitud viene de que el contador estuvo en DOWN casi todo el tiempo.
Un indicador que dice lo mismo el 89% del tiempo no puede detectar giros en ambos sentidos.

### 4.2 Qué predominaba ANTES del movimiento (ventanas 5/10/20/30 min)

```
 ventana     SENAL      M1       M2
  -5 min      2/8      4/8      4/8
 -10 min      3/8      4/8      4/8
 -20 min      4/8      4/8      4/8
 -30 min      5/8      4/8      4/7
```

Ampliar la ventana hacia atrás **no mejora nada**. Y el patrón por evento es que
*en cada giro acierta una columna distinta*: M2 salva el 11:36 y falla el 12:00;
M1 salva el 12:00 (30/30 minutos avisando) y falla el 11:36. En 2 de 5 no acierta ninguna
(12:43 y 15:09, este último con **0/30** en las tres).

### 4.3 Bloques de N minutos sobre la columna SEÑAL (N = 2..45)

Mejores: N=45 → predice 5/6 = 83%. **Descartado:** 6 predicciones, 44 valores de N
probados, resultado inestable entre vecinos (N=41 → 67%), y los ganadores tienen
`coincide` muy bajo → **es reversión, no anticipación**.
Sí es consistente que N=16..20 son los peores (19-27%), sobre 15-16 predicciones.

### 4.4 Zonas de convergencia del marcador (08-10)

Solo dos en todo el día:
```
10:02-10:27  (25 min, 5 empates exactos)  SPY plano 773,59-774,31
14:21-14:27  ( 7 min, 1 empate exacto)    SPY plano 772,55-772,66
```
Después de las 14:27 la diferencia nunca vuelve a bajar de 3 y cierra en 93.

📌 **El único aviso anticipado real de toda la investigación:** M1 y M2 giraron a la vez
a las **10:25**, 22 minutos antes del techo de las 10:47, **dentro de la zona de
convergencia**. Es 1 caso. Si hay algo que perseguir, es *cruce durante convergencia*,
no la dominancia por sí sola.

---

## 5. SIMULACIÓN DE TRADING (y los 3 errores que hubo que corregir)

Contrato ATM, 1 lote, flip al cambiar la señal, siempre en mercado.
Spread real medido en la BD: **1,7% del mid** (mediana de 2.116 cotizaciones 0DTE).
Comisión 1,30$/op.

### Correcciones sucesivas — el resultado se movió 200$ solo por calibrar

| versión | error | M1 08-10 |
|---|---|---|
| v1 | IV asumida 13% | −177,80$ |
| v2 | IV real calibrada (5,7% mediana) | −2,96$ |
| v3 | + reglas reales del sistema (FLATTEN 15:45) | **+32,89$** |
| v4 | + IV de mañana calibrada al trade real del usuario (6,94%) | ver abajo |

**IV real de las 0DTE ATM (08-11, 498 observaciones): mediana 5,69%, rango 4,74%-26,45%,
subiendo a 19% en los últimos minutos.** La IV de la mañana se calibró contra el trade
real del usuario (CALL 773 a 1,34 a las 09:35 → IV 6,94%).

### Resultado final

```
08-10   SENAL  20 ops, 8 ganadoras, NETO  -27,30$
        M1      6 ops, 2 ganadoras, NETO  +32,89$
        M2      8 ops, 3 ganadoras, NETO  -85,18$

08-11   las tres: 1 sola op (M1 nunca cambia)
        PUT 773 comprado 09:55 a 1,29 -> cerrado 15:45 a 2,51 = +122,36$
```

⚠️ **El 08-10 es SINTÉTICO**: la BD **no tiene ni un precio de opción de ese día**
(0 de 18.732 filas con bid/ask/mid). Los precios del 08-11 solo existen **desde las 11:48**.

### Lo que sí quedó establecido

1. **Las reglas de cierre valen más que la señal.** Aplanar a las 15:45 en vez de aguantar
   al cierre convirtió M1 de −3$ a +33$ **con las mismas señales**. Los últimos 13 minutos
   de un 0DTE valían 36$ en un solo trade.
2. **El theta no es el monstruo que parecía.** Con IV 5-7%, un ATM 0DTE cuesta ~1,00-1,30$.
3. **El resultado lo hacen 2 trades de 7** (+67$ y +122$), y los dos son lo mismo:
   aguantar un put durante una caída larga. M1 no detectó giros; estuvo del lado correcto
   en las dos caídas de la muestra.
4. **Cada flip cuesta el spread completo.** Por eso SEÑAL (20 ops) pierde más que M1 (6 ops)
   pese a tener mejor ratio de aciertos.

---

## 6. Lo siguiente, por orden

1. **Los 40 contratos de la BANDA en `_on_ticks` + GAP D activo.** Sin esto, todo se mide
   con 2 strikes de 40 y con premium fantasma dentro.
2. **Acumulador con VENTANA MÓVIL (15/30 min) en vez de desde apertura.** El actual solo
   suma: no puede bajar nunca, y por eso a partir de las 13:00 del 08-10 las curvas de M1
   y M2 son rampas rectas mientras el SPY sube, baja, sube y baja. Un confirmador tiene que
   poder cambiar de opinión.
3. **Registrar M1/M2 en paralelo SIN operar con ellos**, para acumular evidencia sin riesgo.
4. **Una sesión ALCISTA.** La muestra entera son dos días bajistas; es donde estos métodos
   están garantizados de lucir bien.
5. Perseguir el *cruce durante zona de convergencia* (§4.4), que es el único caso con
   antelación real.
