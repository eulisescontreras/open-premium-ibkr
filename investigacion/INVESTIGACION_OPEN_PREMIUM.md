# Investigación: ¿el open premium anticipa la dirección del SPY?

**Sesión 2026-08-11.** Datos disponibles: 2 sesiones (2026-08-10 completa, 2026-08-11 completa).
Todo lo de aquí sale de ejecutar sobre `spy_history.db`, no de lectura de código ni de memoria.

> **Aviso que gobierna todo el documento:** son **DOS DÍAS**. Nada de lo que sigue está
> establecido. Lo que hay son mediciones sobre una muestra que no permite distinguir una
> señal real del azar. El valor de esto es saber **qué medir** cuando haya 5-10 sesiones,
> y sobre todo **qué NO volver a medir** porque ya se descartó.

---

## 1. La pregunta

¿Hay algo en el premium de opciones que diga hacia dónde va el SPY **antes** de que ocurra?
El parámetro de giro actual lo hace mal: el 2026-08-11 marcó `UP` durante toda la sesión
mientras el SPY caía de 774 a 770,3.

---

## 2. VERIFICADO — hallazgos sobre la CALIDAD del dato

Esto es lo más importante de la sesión, porque invalida análisis previos.

### 2.1 `premium_minute.net_prem` NO es un neto fiable

`compute_walls` clasifica el Δvolumen de **3 minutos enteros** como compra o venta usando
**un solo `last` y un solo bid/ask**, los del instante de la lectura. Si en esos 3 minutos
hubo compras y ventas mezcladas —lo normal— el resultado no es el neto: es el signo de la
última operación multiplicado por todo el volumen del intervalo.

Comparado contra el `tape` (que clasifica operación a operación con el bid/ask de su propio
instante), en los mismos intervalos y los mismos strikes:

```
76 comparables | 75 con ratio fuera de [0.5, 2.0] = 99% de discrepancia
inversiones de signo:  14:49 770C -> net_prem +434.760  vs  tape -1.060.284
                       14:55 770C -> net_prem -538.848  vs  tape    +85.592
```

⇒ **Cualquier medida de dirección construida sobre `net_prem` está medida sobre un dato roto.**
El barrido de 38 variables × 6 horizontes que se hizo antes en esta misma sesión cae por aquí.

### 2.2 `net_call` / `net_put` (los del panel) SÍ vienen de la atribución buena

Los alimenta `_on_ticks` **por tick**, con el bid/ask del propio momento del trade — la misma
vía que el tape. No pasan por `compute_walls`. Son la fuente correcta.
Limitación: **solo los 2 strikes de SEÑAL**, que van rotando con el precio.

### 2.3 El precio del SPY que guardamos es correcto

Contrastado contra `posicion_minuto.und_price`, que viene de `modelGreeks.undPrice` de IBKR
y **no** de las barras: 363 comparaciones, diferencia **mediana −0,01**, rango −0,64 a +0,51.
Dos fuentes independientes de IBKR coinciden.

### 2.4 El `tape` es una muestra, no un registro completo

`_on_ticks` procesa solo SEÑAL y BASELINE ⇒ del vencimiento 0DTE el tape ve **4-6 strikes**,
no los 40 de la banda. Y existe desde las 14:36 del 2026-08-11.
Además ib_insync agrupa operaciones: `size == dvol` solo en el **63,8 %** de las filas, y
Σ`size` cubre el **29,3 %** del volumen.

---

## 3. LA TESIS QUE SE ESTÁ FORMANDO — dominancia en valor absoluto

**Idea del usuario:** no mirar el signo del neto, sino **qué lado mueve más dinero** en valor
absoluto. Si `|net_put| > |net_call|` ⇒ DOWN; si `|net_call| > |net_put|` ⇒ UP.

Es **la lectura opuesta** a la que usa la app hoy. La app decide con `diff = net_call − net_put`
respetando el signo. El 2026-08-11 los dos netos fueron negativos toda la sesión, y cuando ambos
comparten signo `|C| − |P|` es exactamente `−(C − P)`:

```
diff de la señal (con signo):  +7.015.145  ->  UP    (lo que hizo la app)
|C| - |P| (dominancia):        -7.015.145  ->  DOWN  (la lectura alternativa)
SPY: 773,06 -> 770,33 = -2,73
```

### 3.1 VERIFICADO — la observación, en los dos días

| | minutos con \|PUT\| > \|CALL\| | SPY del día |
|---|---|---|
| 2026-08-11 | **359 de 359 = 100 %** | **−2,73** |
| 2026-08-10 | 115 de 323 = 35,6 % | −0,36 (plano) |

El ratio `|P|/|C|` arranca parecido los dos días (3,24 y 3,35 a las 09:55) y **se separa a media
mañana**: el 08-10 se derrumba a 0,36 hacia las 10:43 y cierra en 0,12; el 08-11 nunca baja de 1,
toca 8,69 a las 12:25 y cierra en 3,20.

**HIPÓTESIS (no verificada):** el régimen de dominancia se establece durante la mañana y persiste.
Sería una lectura **de sesión**, no minuto a minuto.

### 3.2 VERIFICADO — la asimetría UP/DOWN a horizontes largos (08-10)

Midiendo qué hace el SPY **después** de cada cambio de señal:

```
                        +5min      +10min      +15min      +30min      +60min
ACIERTO                 10/17       10/20       11/20        8/18       10/20
                          59%         50%         55%         44%         50%
solo        UP        5/9 56%    5/10 50%    6/10 60%     2/8 25%    1/10 10%
solo      DOWN        5/8 62%    5/10 50%    5/10 50%    6/10 60%    9/10 90%
```

El agregado (50 %) tapa dos comportamientos opuestos. A +60 min el `DOWN` acierta 9 de 10 y el
`UP` acierta 1 de 10. **Un lado acierta y el otro acierta al revés.**
La separación **no existe** a 5-15 min y **aparece a partir de los 30**.

### 3.3 ⛔ PERO — el solapamiento invalida esa cuenta

De los 21 bloques de señal, **solo 2 aciertan los cinco horizontes**: `10:47 DOWN` (duró 1 min)
y `10:50 DOWN` (duró 12 min). Y hay un tercero sin fallos, `10:44 DOWN` (2 min).

**Los tres están entre las 10:44 y las 10:50** — seis minutos de reloj, sobre el máximo del día
(774,60-774,97), justo antes de la caída a 773,68 de las 11:02.
**No son tres aciertos independientes: son la misma caída contada tres veces.**
Sus ventanas de +60 min se solapan casi por completo.

⇒ El 9/10 del `DOWN` no son diez eventos. Son unos pocos tramos de caída con la señal repicando
encima. **Es la misma trampa de solapamiento que ya invalidó un "89 % de acierto" en este
proyecto.** Contar bien exige separar los eventos al menos por el horizonte que se mide.

### 3.4 VERIFICADO — la persistencia NO predice nada

Agrupando los bloques por cuántos minutos seguidos se repitió la palabra:

```
minutos seguidos   bloques      +5min      +10min     +15min     +30min     +60min
1-2                      8        4/6         4/8        4/8        2/7        3/8
3-9                      5        3/4         1/5        2/5        3/5        2/5
10-29                    5        3/5         3/5        3/5        2/5        4/5
30+                      3        0/3         2/3        2/3        1/2        1/3
```

No hay curva. Duraciones de los que aciertan ≥4 horizontes: `1, 2, 8, 12, 29, 41`.
De los que aciertan ≤1: `1, 1, 2, 5, 6, 359`. **Hay bloques de 1 minuto en los dos grupos.**

### 3.5 El caso que rompe la idea de usarla para entrar

```
2026-08-11  09:55  DOWN  359 min     +5 ✗   +10 ✗   +15 ✗   +30 ✗   +60 ✗
```

El bloque que **acertó el día entero** falla en los cinco horizontes: dijo DOWN a las 09:55 con
el SPY en 773,06, y el SPY subió hasta 774,03 a las 10:00. La caída llegó hacia las 14:30.

⇒ **Acertó la dirección del día y falló todos los momentos de entrada.** Para scalping es la peor
combinación posible. Son dos preguntas distintas: *hacia dónde va el día* y *cuándo entrar*.

---

### 3.6 El MARCADOR DEL DÍA — contadores acumulados de UP y DOWN

Idea del usuario: llevar dos contadores desde la apertura (cuántos minutos lleva cada palabra)
y mirar dónde se igualan o dónde uno adelanta al otro.

```
                    MARCADOR FINAL         cruces (empates + adelantamientos)
2026-08-10          UP 208 - DOWN 115      12, y ONCE de ellos entre 10:05 y 10:25
2026-08-11          UP   0 - DOWN 359      ninguno
```

**VERIFICADO — el 08-11 el contador de UP nunca llega a 1.** Los 359 minutos son DOWN.
El 08-10, en cambio, tiene el marcador disputado: 12 cambios de liderazgo, casi todos
apretados en **veinte minutos** (10:05-10:25). Después no vuelve a igualarse hasta las **14:24**
(115-115), cuatro horas más tarde.

**HIPÓTESIS (no verificada, n=1 día):** los empates aparecen cuando el mercado no va a ningún
lado. En la franja 10:05-10:25 el SPY oscila entre 773,68 y 774,29 sin dirección.

#### Los tres intervalos que pidió mirar el usuario (08-10)

| intervalo | marcador antes | marcador al salir | dentro | SPY | empates |
|---|---|---|---|---|---|
| 09:53-10:12 | *(sin dato previo)* | 8-8 (dif 0) | 8 UP / 8 DOWN | **+1,06** (rango 1,08) | 10:05, 10:12 |
| 10:16-10:30 | 8-11 (dif −3) | 14-20 (dif −6) | 6 UP / 9 DOWN | **+0,25** (rango 0,50) | 10:18, 10:22, 10:24 |
| 11:34-12:32 | 39-56 (dif −17) | 66-87 (dif −21) | 27 UP / 31 DOWN | **−0,48** (rango **1,73**) | **ninguno** |

📌 Los dos intervalos **con empates suben**; el único **sin empates baja**, y es el de mayor rango.
📌 El 10:16-10:30 es el contraejemplo dentro de la propia tabla: el DOWN dobla su ventaja
(−3 → −6) y el SPY **sube**.

#### Los 8 mayores movimientos de 1 minuto del 08-10, con el marcador de ese instante

```
12:31  dSPY=-0.69  senal=DOWN   marcador  66-86  (dif -20)
15:50  dSPY=-0.61  senal=UP     marcador 201-115 (dif +86)
10:54  dSPY=-0.44  senal=DOWN   marcador  19-37  (dif -18)
11:01  dSPY=+0.39  senal=DOWN   marcador  19-44  (dif -25)   <- contraejemplo
11:25  dSPY=-0.37  senal=DOWN   marcador  39-48  (dif  -9)
15:58  dSPY=+0.35  senal=UP     marcador 208-115 (dif +93)
10:45  dSPY=+0.34  senal=DOWN   marcador  17-32  (dif -15)
10:59  dSPY=-0.32  senal=DOWN   marcador  19-42  (dif -23)
```

Seis de los ocho ocurren con DOWN mandando, y cuatro de esos seis son caídas.
⚠️ Pero el **11:01** es el mayor desequilibrio de la mañana (−25) y coincide con una **subida**
de +0,39. Un solo caso, pero impide leerlo como regla.

**Columnas añadidas a `net_acumulado_*.txt`:** `#UP`, `#DOWN` (acumulados) y una sección
`MARCADOR DEL DIA: EMPATES Y ADELANTAMIENTOS`.

---

## 4. HIPÓTESIS ABIERTA — la magnitud distingue el parpadeo del evento

La señal binaria tira la información que importa. En el tramo de las 10:44-10:50 del 08-10 la
señal cambió **siete veces en diez minutos**, y todas las lecturas son la misma palabra sobre
situaciones incomparables:

```
10:47  |CALL|  45.292  |PUT|  45.471  -> DOWN por 179 dolares
10:50  |CALL|  26.407  |PUT| 196.988  -> DOWN, put 7,5x el call
10:51  |CALL|  13.471  |PUT| 416.677  -> DOWN, put 31x
10:54  |CALL|   7.432  |PUT| 445.714  -> DOWN, put 60x
```

📌 Detalle no explorado: el `|CALL|` **se desploma** de 190.707 a 7.432 mientras el put sube. No
es solo "entra dinero al put" — es que **desaparece del call**. Es una firma distinta y medible.

**Siguiente medición propuesta:** filtrar por magnitud (ratio ≥ 3, o un mínimo en dólares) y
recontar los bloques. Eliminaría los siete parpadeos y dejaría el evento de las 10:50.
**NO HECHO.**

---

## 5. DESCARTADO en esta sesión — no volver a proponerlo sin datos nuevos

1. **El barrido de 38 variables sobre `premium_minute` por strike.** Medido sobre `net_prem`,
   que es un dato roto (§2.1). No es un resultado negativo: es un resultado inválido.
2. **El premium BRUTO como indicador direccional.** Es ciego por construcción: 1 M$ en calls es
   el mismo número lo compre un alcista o lo venda un bajista.
3. **Los acumulados `cum_*` y `day_*` como variable.** Crecen con el reloj; correlacionarlos con
   el precio da falsos positivos (el control del reloj marcó varias como "cronómetro disfrazado",
   con rho hasta −0,75 contra la hora del día).
4. **Juzgar un bloque de su inicio a su fin.** El final se elige a posteriori; en vivo no se sabe
   cuándo termina.

---

## 6. Trampas metodológicas encontradas (y en las que caí)

- **Permutación plana sobre series temporales.** Barajar destruye la autocorrelación y estrecha la
  nula: daba p=0,005. Con desplazamiento circular, p=0,015 sobre 11 puntos independientes.
  **La nula correcta para series temporales es el shift, no el shuffle.**
- **Tratar el ausente como cero.** `net_prem`/`day_vol` solo existen en las filas de walls;
  sumarlas como 0 en las de minuto metía falsos empates y contaminaba la tasa base.
- **Distancia absoluta al strike.** Un call a +1,5 (OTM, apuesta alcista) caía en el mismo cubo
  que uno a −1,5 (ITM, cierre) y se cancelaban. Hay que usar distancia **con signo**.
- **Solapamiento de ventanas.** Ver §3.3.
- **Comparaciones múltiples.** Con ~200 combinaciones probadas, que una salga con +5 puntos de
  lift es lo normal aunque no haya señal.
- **Reusar el cursor sqlite dentro del bucle que lo itera** → solo procesa la primera fecha.

---

## 7. Los scripts (todos READ-ONLY, en `analisis/`)

| Script | Qué produce |
|---|---|
| `net_acumulado.py` | **El principal.** Tabla minuto a minuto con `\|CALL\|`, `\|PUT\|`, `\|C\|−\|P\|`, SPY, SEÑAL, RACHA y OK. Más: bloques de señal con GEX y TA, comparación aciertan-vs-fallan, y qué hace el SPY a +5/10/15/30/60 min de cada cambio |
| `open_premium.py` | Neto por lado (todos los strikes ATM/ITM) con SPY, lado ganador, GEX y TA. ⚠️ Se apoya en `net_prem`: ver §2.1 |
| `neto_por_strike.py` | Neto por STRIKE y por minuto desde el `tape`, con el dinero MID sin atribuir |
| `matriz_minuto.py` | Rejilla completa 09:30→cierre con el premium de cada minuto y las 13 columnas de TA |
| `premium_por_minuto.py` | Serie por minuto desde el `tape` (expone `serie_por_minuto()`) |
| `direccion_premium.py` · `direccion_foco.py` · `control_reloj.py` · `significancia.py` · `atribucion.py` | El barrido y sus controles. **Sus resultados están invalidados por §2.1**, pero los controles (reloj, permutación, sensibilidad) siguen siendo reutilizables |

Salidas generadas: `net_acumulado_*.txt`, `open_premium_*.txt`, `neto_por_strike_*.txt`,
`matriz_minuto_*.txt`.

---

## 8. Lo siguiente, por orden

1. **Meter los 40 contratos de la BANDA en `_on_ticks`.** Es el cambio que da el neto real por
   tick de todos los strikes ATM/ITM, en vez de los 2 de señal. Toca la ruta que corre en el hilo
   de la GUI ⇒ corrida en frío diferencial obligatoria. **Sin esto, todo lo demás se mide con 2
   strikes de 40.**
2. **Filtrar la señal por magnitud** y recontar los bloques (§4).
3. **Acumular 5-10 sesiones** y repetir §3.2 contando **solo eventos no solapados**.
4. Controlar por hora del día: los cambios de señal se amontonan en franjas concretas.
