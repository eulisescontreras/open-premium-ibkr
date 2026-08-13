# INVESTIGACIÓN: TAPE DEL SUBYACENTE, MAGNITUD Y SALIDA POR TRAIL

**Sesión del 2026-08-13** · Datos: 08-12 y 08-13 completos (390 velas cada uno)

> ## ⚠️ LEE PRIMERO EL §11: EL SISTEMA QUE QUEDÓ DEFINIDO
>
> El §2 dice que el trailing **por extremo de 20 min** gana al porcentual. **Eso es cierto
> solo con las entradas que se probaron entonces (flujo/EMA).** Con la entrada por
> **Supertrend**, que es la que quedó, gana el **porcentual** y por mucho: **+316 $ contra
> −57 $**. La conclusión final está en el §11.

Todo lo de aquí está medido contra datos reales. Cada afirmación va marcada como
**VERIFICADO** (medido en los dos días), **REFUTADO** (medido y falla) o
**NO VERIFICADO** (no se pudo comprobar y por qué).

---

## 1. LO ÚNICO QUE SOBREVIVIÓ: LA MAGNITUD PREDICE AMPLITUD

**VERIFICADO en los dos días.** `|net_spy|` del minuto, normalizado por la mediana del
propio día, predice la probabilidad de que el SPY recorra ≥ $0,50 en los 30 minutos
siguientes:

```
                08-13                    08-12
  calma <2x      53%                      23%
  >= 3x          69%                      35%
  >= 5x          76%                      30%
  >= 10x          -                       43%
```

Los niveles absolutos difieren mucho (el 08-12 fue un día más quieto), pero **la dirección
se repite: el salto de flujo casi dobla la probabilidad respecto a la calma.**

Fórmulas aproximadas ajustadas al 08-13 (NO validadas en el 08-12):

```
ratio = |net_spy del minuto| / mediana del día
P(mover >= $0.50 en 30 min)  ≈  50 + 30·log10(ratio)     [acotar 50-85]
amplitud esperada (30 min)   ≈  0.66 + 0.10·ratio        [acotar ~1.7]
```

**Por qué esta sobrevive y el resto no:** usa **valor absoluto**. Todo lo que dependía del
signo de una inferencia (quién cruzó el spread) se cayó. Ver §3.

### El tamaño del mayor bloque también predice (08-12)

```
  mayor bloque del minuto    calma <2x   23%      >=5x   50%
```

Sin signo, sin filtrar nada. **Un bloque grande informa de cuánto se va a mover, no de
hacia dónde.**

---

## 2. SALIDA POR TRAIL: QUÉ FUNCIONA Y CUÁNTO

**VERIFICADO.** La salida por trailing sobre el **precio del SPY** (no sobre la prima)
captura los tramos largos. Comparativa con la MISMA entrada, 08-13:

```
                    salida   ops  gana  %acierto    puntos  g.medio  p.medio   dur
  anterior (oscilacion 5m)    29    15     51.7%     +1.57    +0.23    -0.13   3.8
    flujo flojo 5 seguidos    12     6     50.0%     +0.76    +0.69    -0.56  17.8
      trailing extremo 20m     5     4     80.0%     +7.61    +1.95    -0.17  56.4
```

Sumando los puntos de cada familia en las 6 combinaciones de ventana y umbral:

```
trailing extremo 20m    +31.44   <-- gana en las 6
trailing extremo 10m    +24.49
anterior (oscilacion)    +9.81
salida por flujo flojo   +7.50
```

**El trailing por extremo gana en TODAS las configuraciones.** Es región, no celda.

### Las salidas por flujo son las PEORES

Contraintuitivo pero medido: "flujo flojo N minutos seguidos" queda por debajo incluso de
la regla vieja. **El flujo sirve para entrar, no para salir**: mide energía instantánea y
en mitad de un tramo se apaga y reenciende constantemente. La estructura de precio es
mucho más estable para decidir cuándo se acabó.

### Trail por PORCENTAJE: la conversión correcta

La volatilidad escala con la **raíz** del tiempo, no linealmente:

```
σ(W minutos) = σ(diaria) × √(W / 390)
```

Volatilidad medida el 08-13: **0,0180 % por minuto** → 0,355 % diario (2,76 puntos).

```
  % diario      1 min      5 min     20 min     60 min   20min en pts
     0.55%     0.028%     0.062%     0.125%     0.216%          0.97
     0.95%     0.048%     0.108%     0.215%     0.373%          1.67
     1.90%     0.096%     0.215%     0.430%     0.745%          3.35
```

**Un trail del 1,9 % diario son 14,78 puntos de SPY: casi 3 veces el rango entero del día.
No salta nunca** (1 operación, 367 minutos dentro). Su equivalente a 1 minuto es
**0,096 % ≈ 0,75 puntos**, y ahí sí funciona.

Comparativa 08-13 (misma entrada):

```
           trail 0.060% (0.47 pts)     9 ops  77.8%   +4.91   dur 32.4
           trail 0.096% (0.75 pts)     4 ops   100%   +5.43   dur 86.8
           trail 0.110% (0.86 pts)     3 ops   100%   +5.82   dur 122.7
           trail 1.900% (14.78 pts)    1 op    100%   +2.26   dur 367.0
              trail extremo 20 min     6 ops  66.7%   +7.18   dur 53.2
```

Hay **meseta entre 0,096 % y 0,14 %** (+5,37 a +5,82): no depende de acertar el número.

**Fijando las mismas entradas** (comparación limpia, sin mezclar reentradas), el trail del
0,11 % y el extremo de 20 min quedan **empatados** (+7,21 vs +7,04). Cada uno gana en
tramos distintos: el extremo en los de retroceso brusco, el porcentual en los que suben
despacio y largo.

**Ventaja del trail sobre el SPY y no sobre la prima** (esto ya estaba documentado en
`spy_direction.py:215` y se confirma): un spread de 0,01 en la opción es 1 $ por tick. El
trailing sobre el subyacente no tiembla con el libro de la opción, y es inmune a caídas de
IV que no afectan a la tesis direccional.

**Matiz que no hay que olvidar:** el trailing acota el movimiento del **subyacente**, no la
pérdida en dinero. Con un ITM de delta ~0,7, 0,75 puntos de trail son ~52 $ por contrato —
y si además se mueve la IV, más.

---

## 3. LO QUE SE CAYÓ, Y POR QUÉ

### El "millón por minuto" era un artefacto del clasificador de agresor

Con el agresor calculado por bid/ask, los tramos parecían separarse limpio:

```
  T1 UP  +4.96   1.142 M$/min      T2 DOWN -3.82   0.034
  T3 UP  +1.91   1.219 M$/min      T4 DOWN -0.78   0.082
  separación 14-36x
```

**Recalculando el MISMO día con la regla del tick, la separación cae a 0,4x.** Y da igual
la columna de premium (`size` o `dvol`): desaparece en ambas.

**Lo que producía la separación era el método de clasificación, no el flujo.** Con el
agresor por bid/ask todos los tramos daban flujo positivo (incluso los bajistas): ese sesgo
constante hacía que la magnitud pareciera discriminar.

### `acum_call − acum_put`: muerto por el cronómetro

Era el mejor candidato direccional (65-76 % en 4 bloques), pero:

```
  rho(acum_call - acum_put, minuto del día) = +0.352   -> MUERTA (umbral 0.30)
  rho(precio, minuto del día)               = -0.014
```

El indicador deriva con el reloj y el precio no. Al quitar la deriva usando el **delta** en
ventana, el acierto se desploma a moneda (40-52 % en el bloque de 134 casos, contra 68,7 %
del nivel). **Ese 68,7 % era deriva temporal, no información.**

Es el mismo fallo que mató las 4 variantes del % de premium el 08-12.

### El straddle ATM: es un reloj

```
  rho(straddle ATM, minuto del día) = -0.977
```

Parecía un predictor de amplitud excelente (Q1 0,478 → Q4 1,287) pero es **theta puro**: el
straddle 0DTE se derrite hacia el cierre, y el movimiento también decae. La relación
aparece sola. Para usarlo habría que normalizarlo por tiempo hasta vencimiento.

### El signo del `net_spy` no da dirección

48,8 % · 48,5 % · 42,9 % · 49,3 % en los cuatro bloques probados. **Sistemáticamente por
debajo del 50 %.**

### El RPS de ChatGPT: no dispara

La regla `RPS >= 75 AND ruptura estructural` dio **n=0** en 326 minutos. Y el score estaba
invertido: el tramo 0-49 acertaba 29,7 % contra 19,9 % de base, mientras 50-64 daba 8,3 %.

Dos errores de diseño en la fórmula original: sumaba términos de escalas incomparables
(centavos con millones de dólares), y "Normalize" sin definir invitaba al look-ahead.

### La caída de dígitos NO detecta agotamiento

```
                08-13                              08-12
  base          +0.135  (58% sigue)      base      -0.052  (45%)
  caída dígitos +0.353  (68% sigue)      caída     -0.052  (48%)
```

Un día dice lo contrario de la hipótesis y el otro no dice nada. Los dígitos **altos** sí
predicen amplitud; la ausencia de flujo no informa.

---

## 4. PROBLEMAS DE CAPTURA DETECTADOS (afectan a producción)

### El tape en vivo captura el 23 % del volumen

```
  sum(size)  [lastSize] :  5,351,853 acciones  ->  22.9% del volumen real
  sum(dvol)  [delta vol]: 30,249,787 acciones  -> 129.3%
  volumen bars_minute   : 23,403,763
```

La columna `premium` (= `last * lastSize`) usada en todo el análisis **capta menos de una
cuarta parte del flujo**. `premium_dvol` capta el 129 % (se pasa, probablemente por saltos
al reconectar — hubo reinicio a las 11:21).

**Ninguna de las dos es exacta.** RTVolume agrega operaciones y solo reporta el `lastSize`
de cada actualización.

### El tape en vivo NO guarda exchange ni condición

El histórico de IBKR sí los trae, y son informativos:

```
  FINRA     174,938 ops   9,296,585 acciones   <- 41% del volumen (dark pools/OTC)
  condición 'I' (odd lot): 169,396 ops, solo 6.8% del volumen
```

**RTVolume (tick 233) no incluye el exchange**: el dato nunca llegó a la aplicación, no es
que se perdiera al guardar. Verificado también en los logs (0 coincidencias reales).

Consecuencia: **el filtro de FINRA no se puede aplicar en producción** sin cambiar la
captura.

### Filtrar FINRA limpia el dato pero empeora el sistema

```
  el salto de +302 M del 08-12 11:22 era UN bloque de 398,979 acciones en FINRA
  al quitarlo: el minuto pasa de +302 M a -1.08 M, y el acum del día de -497 M a +5.6 M
  la predicción de amplitud mejora: 23->30% pasa a 22->50%

  PERO el sistema completo empeora: 08-12 pasa de +66$ a +4$
```

**El filtro retrasa la señal** (la entrada buena se desplaza 26 minutos) y el retraso pesa
más que la ganancia en precisión. Para un sistema que ya entra tarde, filtrar lo agrava.

### El acumulado está dominado por una decena de operaciones

```
  HOY   las 10 mayores =  6.0% del importe total del día
  AYER  las 10 mayores =  8.0%
```

Con 380.778 operaciones, las 10 mayores pesan como decenas de miles. Y hay **ecos**: la
misma operación (126.034 acciones a 770,54) aparece **seis veces** en la tarde del 08-12.

---

## 5. LA ESCALA DE LOS TRAMOS: UN ERROR DE ANÁLISIS QUE COSTÓ CARO

Con umbral de ZigZag $0,75, el 08-12 parecía tener **9 tramos cortos** y lo diagnostiqué
como "día no operable". Con $1,50 aparecen los **3 tramos reales**:

```
08-13 (estable de $1.00 a $2.50)      08-12 (a $1.50)
  09:30->10:35   65 min  +4.96 UP       09:30->11:40  130 min  -2.28 DOWN
  10:35->11:59   84 min  -3.82 DOWN     11:40->14:41  181 min  +2.01 UP
  11:59->15:59  240 min  +2.23 UP       14:41->15:59   78 min  -1.08 DOWN
```

**Los dos días tienen 3 tramos largos, ninguno de menos de 65 minutos.** El diagnóstico de
"día troceado" era mío, no del mercado.

El umbral correcto ronda **1,5-2 veces la volatilidad diaria medida**. Es el mismo error
cometido tres veces en sitios distintos: umbral del ZigZag, trailing porcentual y filtro de
flujo, todos fijos cuando deberían escalar con la volatilidad del día.

---

## 6. RESULTADOS EN DINERO (400 $ de capital, tope 320 $, ITM que quepa, ASK/BID)

### Con oráculo (NO operable, sirve para diagnosticar)

```
+900 $   timing perfecto + dirección perfecta      <- el techo
+268 $   timing perfecto + EMA da el lado          <- la EMA cuesta 632 $
```

**En 5 de los 6 pivotes la EMA dijo justo lo contrario de lo que tocaba.** Acierta el 74 %
de los *minutos* y falla el 83 % de los *pivotes*: acierta durante el tramo y falla en los
extremos, que es donde se decide entrar.

### Operable (sin oráculos)

```
+250 $   Supertrend solo, sin tape                 <- el mejor
+147 $   flujo dispara + Supertrend + trail
 -43 $   flujo dispara + EMA + trail
```

**Supertrend ATR(10) mult 3.0**, rejilla de 16 combinaciones:

```
  mult 1.0 y 2.0  ->  pierde en TODAS (-322 a -574)
  mult 3.0 y 4.0  ->  gana en TODAS   (+88 a +250)
  el período (7/10/14/20) casi no importa
```

Región positiva completa, pero **el 08-12 pierde en las 16 combinaciones**: el total
positivo lo aporta enteramente el 08-13.

### Por qué el sistema operable no gana más

Las operaciones **largas ganan y las cortas pierden**, sistemáticamente:

```
08-13:  4 operaciones >40 min  ->  +418 $
        5 operaciones  <2 min  ->   -96 $
08-12:  2 operaciones >39 min  ->   +73 $
        7 operaciones  <8 min  ->  -182 $
```

El sistema hace 9-13 operaciones cuando el día tiene 3 giros. **Falta una regla de cuántas
veces se puede entrar** (separación mínima, o no reentrar donde acabas de salir).

---

## 7. EL FLUJO NO MARCA LOS GIROS

Medido en el 08-12, ratio de volumen en cada pivote real:

```
   giro   ratio en el giro    max ratio ±5 min
  09:30              14.59                14.59   <- apertura
  11:40               0.80                 8.01   <- POR DEBAJO de la mediana
  14:41               1.26                 1.43   <- apenas la mediana
  15:59              11.75                11.75   <- cierre
```

**En los dos giros reales del día el flujo estaba en actividad normal o por debajo.** Los
únicos ratios altos son la apertura y el cierre, que son subastas, no giros.

Y el reparto de disparos:

```
   1x mediana: 195 minutos de 390 (50.0% del día)   <- no discrimina nada
   2x mediana:  56 minutos (14.4%)
   5x mediana:   7 minutos ( 1.8%)                  <- apertura y cierre
```

Esto es compatible con §1 (la magnitud predice amplitud) y lo explica todo:
**el tape avisa de movimiento en los momentos donde no hay giro que aprovechar.**

---

## 8. ESTADO FINAL

```
VERIFICADO   |net_spy| predice AMPLITUD              2 días, robusto a columna y agresor
VERIFICADO   trailing sobre el SPY captura tramos    gana en 6/6 configuraciones
VERIFICADO   conversión de volatilidad √(W/390)      medida
REFUTADO     el "1 M$/min" separa tramos             artefacto del agresor bid/ask
REFUTADO     acum_call-acum_put como dirección       rho +0.352 con el reloj
REFUTADO     straddle ATM como amplitud              rho -0.977 (es theta)
REFUTADO     signo del net_spy como dirección        48-49% en 4 bloques
REFUTADO     RPS (ChatGPT)                           n=0 disparos, score invertido
REFUTADO     caída de dígitos como agotamiento       los 2 días se contradicen
REFUTADO     el flujo marca los giros                ratio 0.80 y 1.26 en los pivotes
ABIERTO      dirección en el pivote                  la EMA falla 5 de 6; Supertrend mejor
ABIERTO      captura: 23% del volumen, sin exchange  afecta a producción
```

**Lo que se llevó el día:** el tape del subyacente predice **cuánto**, nunca **hacia
dónde** — y lo hace en la apertura y el cierre, no en los giros. La dirección, si aparece,
no va a salir del tape: el dato que haría falta (quién cruzó el spread) **no se publica**.

**Lo más incómodo:** el mejor sistema operable (+250 $) **no usa el tape**.

---

## 9. PRÓXIMOS PASOS SUGERIDOS

1. **Limitar el número de entradas por día.** Las operaciones <8 min son las que sangran.
2. **Escalar los parámetros con la volatilidad del día** (ZigZag, trail, umbral de flujo).
   El error de usar constantes se cometió tres veces.
3. **Arreglar la captura**: decidir entre `premium` (23 %) y `premium_dvol` (129 %), y
   valorar si se puede obtener el exchange por otra vía.
4. **Probar el tape para dimensionar la posición** en vez de para entrar. Es lo único que
   predice y no se ha usado para eso.
5. **Más días.** Con 2 sesiones, el 08-12 pierde en casi todo y el 08-13 gana en casi todo.

---

## 11. EL SISTEMA QUE QUEDÓ DEFINIDO (lo último y lo que vale)

```
ENTRADA       Supertrend ATR(10) mult 3.0  -> se entra en cada CAMBIO de tendencia
SALIDA        trail sobre el SPY, 0.11%    (equivale a 1.9% diario escalado a 1 minuto)
PERMANENCIA   lo que salga del trail       -> NO hay parámetro de tiempo
CONTRATO      ITM más profundo que quepa en 320$ (80% de 400$)
MAGNITUD      no interviene
```

**Resultado, sin ningún oráculo, con spread y theta dentro:**

```
                salida  08-13 ops   08-13 USD  08-12 ops   08-12 USD      TOTAL
        extremo 20 min          5     +187.00          6     -244.00     -57.00
        extremo 30 min          6     +153.00          6     -244.00     -91.00
    0.096% (1.9%/1min)          6     +491.00          7     -191.00    +300.00
                 0.11%          6     +491.00          6     -175.00    +316.00
                 0.14%          6     +491.00          6     -140.00    +351.00
```

### CORRECCIÓN IMPORTANTE AL §2

El §2 concluye que el trailing **por extremo de 20 min** gana al porcentual. **Eso vale
solo para las entradas que se probaron allí** (flujo y EMA). **Con entrada por Supertrend
la conclusión se invierte:** el porcentual da **+316 $** y el de extremo **−57 $**.

La regla de salida no se puede evaluar sin fijar la entrada. Fue un error de método por mi
parte y así queda anotado.

**El 0,096 %, el 0,11 % y el 0,14 % dan los tres +491 $ en el 08-13**: la meseta es ancha y
no depende de afinar el número.

### Detalle de las operaciones (trail 0.11%)

```
2026-08-13:  6 operaciones, 4 ganadoras, +491.00$  (+123% del capital)
    09:42   10:44    62 min   774C   2.49 -> 4.63   +214.00
    10:44   12:05    81 min   781P   2.72 -> 4.76   +204.00
    12:05   13:33    88 min   774C   2.52 -> 2.92    +40.00
    13:33   14:30    57 min   780P   3.20 -> 2.88    -32.00
    14:30   15:13    43 min   774C   3.19 -> 3.86    +67.00
    15:13   15:59    46 min   780P   2.19 -> 2.17     -2.00

2026-08-12:  6 operaciones, 2 ganadoras, -175.00$  (-44% del capital)
    09:42   09:54    12 min   771C   2.68 -> 2.44    -24.00
    09:56   10:18    22 min   775P   3.20 -> 2.43    -77.00
    10:26   10:32     6 min   771C   2.75 -> 2.14    -61.00
    12:01   13:15    74 min   770C   2.58 -> 2.87    +29.00
    13:15   14:11    56 min   775P   2.32 -> 1.89    -43.00
    14:11   14:56    45 min   771C   2.28 -> 2.29     +1.00
```

**Las tres operaciones que hunden el 08-12 duran 12, 22 y 6 minutos** y se concentran entre
las 09:42 y las 10:32. Son giros del Supertrend que se desdicen enseguida, dentro de un
tramo bajista real de 130 minutos. Las de más de 43 minutos dan +29, −43 y +1.

### La magnitud como veto de falsos giros: PROBADO Y NO FUNCIONA

Idea (correcta sobre el papel): si hay magnitud alta, el movimiento no se está
desvaneciendo, así que el giro del Supertrend es falso y hay que ignorarlo. Base empírica
del 08-13: con flujo ≥3x solo el 32 % de los casos giran, contra el 41 % en calma.

**Medido, no funciona:**

```
     0.11%   sin veto      +491.00     -175.00    +316.00
     0.11%       1.0x      +250.00     -161.00     +89.00   <- pierde 227
     0.11%       1.5x      +491.00     -185.00    +306.00
     0.11%       2.0x      +491.00     -175.00    +316.00   <- idéntico, no se activa
     0.11%       3.0x      +491.00     -175.00    +316.00   <- idéntico, no se activa
```

Con veto exigente (2x, 3x) **no se activa nunca**: en los giros reales el flujo está en
0,80x y 1,26x la mediana (ver §7). Con veto laxo (1x) **bloquea un giro bueno** y cuesta
227 $ en el 08-13.

Y los tres falsos giros del 08-12 ocurren en la primera hora, que tiene volumen alto **por
ser la primera hora**: un veto por magnitud los dejaría pasar igual. **La magnitud
correlaciona con la hora del día, no con la calidad del giro.**

Lo que sí separa falsos de buenos es la **duración** (6-22 min contra 43-88), pero eso solo
se sabe a posteriori.

### ALCANCE

**Dos días. El 08-13 aporta +491 y el 08-12 resta −175: un día bueno tapando uno malo.**
Con esta muestra NO se puede afirmar que sea rentable. Es la primera configuración que sale
positiva sin oráculos, con spread y theta dentro, y con meseta ancha de parámetros — nada
más que eso.

Script: `investigacion/scripts/sistema_definitivo.py` · Salida: `SISTEMA_DEFINITIVO.txt`

---

## 10. FICHEROS GENERADOS

Análisis (todos en la raíz del proyecto):

```
TAPE_HOY.txt              tape del 08-13 por minuto + precio
TAPE_AYER.txt             tape del 08-12 reconstruido desde IBKR
TAPE_CRUDO_20260812.txt   380.778 operaciones crudas, sin procesar (22,5 MB)
TABLA_CUERPOS.txt         cuerpo de cada vela + acumulados + saltos
GIROS_HOY.txt             tramos del día y flujo por fase
SALIDAS_HOY.txt           comparativa de reglas de salida
SALIDA_POR_GIRO.txt       misma entrada, distinta salida, giro a giro
DIAGNOSTICO_HOY.txt       tramo a tramo: capturado / en contra / fuera
EVALUACION.txt            entrar / mantener / salir por separado
TRAIL_PCT_HOY.txt         trail porcentual vs extremo
SUPERTREND.txt            rejilla ATR × multiplicador
SISTEMA_FINAL.txt         sistema operable completo
TECHO.txt                 techo con oráculo
VALIDACION.txt            validación a ciegas
FLUJO_LIMPIO.txt          efecto de los filtros FINRA/odd lots
MINUTOS_0812.txt          el 08-12 minuto a minuto con disparos de flujo
MEDIAS.txt                medias móviles como dirección
MEDIA_MAS_FLUJO.txt       ¿confirma el flujo a la media? (no)
DIRECCION_HOY.txt         16 candidatos direccionales
SALTOS_HOY.txt            saltos bruscos del acumulado
CONTRATOS_HOY.txt         paridad put-call y straddle
MEJOR_CONTRATO_HOY.txt    qué strike conviene
DINERO_DOS_DIAS.txt       resultado en dinero de ambos días
```

Bases de datos derivadas (NO son la BD de producción):

```
spy_tape_ayer.db       380.778 ticks del 08-12 descargados de IBKR
spy_tape_20260813.db    31.161 ticks del 08-13 exportados del tape en vivo
spy_velas.db           copia de trabajo de las velas
```
