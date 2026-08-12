# INVESTIGACIÓN 2026-08-12 — la señal de la MEDIA CORTA, y las 7 líneas que murieron

> **Para el siguiente agente.** Esto es todo lo que se probó el 2026-08-12 después del cierre,
> con qué datos, y con qué prueba murió cada cosa. El objetivo era el que fijó el usuario:
> *entrar preciso, aguantar sin que el theta dañe, y salir con el contrato alto — exprimirlo*.
>
> **Léelo entero antes de proponer nada.** Casi todo lo que parecía funcionar murió con el
> control correcto, y aquí está escrito cuál fue ese control en cada caso.

---

## 0. El marco: cuánto dinero había de verdad

Sin esto no se puede juzgar ninguna estrategia. Medido sobre `premium_minute` con precios
reales, capital **400 $** (el usuario reinicia la paper cada día) y tope
`acct_avail × CAPITAL_FRAC_MAX(0.80)`:

```
15 movimientos fuertes del 08-12 (>=0.60 pts), cada uno con su mejor contrato:
   tope 228$ (disponible real 285$)   mid +987$    ejecucion real (ask/bid) +947$
   tope 320$ (400 x 0.80)             mid +1136$                            +1079$

por franja:  09:30-10:59 ->  9 movimientos  +726$   <- 60% del dia
             11:00-12:59 ->  3              +210$
             13:00-14:59 ->  2              +180$
             15:00-16:00 ->  1               +84$

el sistema real hizo: -76.44$
```

**El dato que reencuadra el problema:** el SPY recorrió **23,77 pts** para acabar en **−0,67**
(19 tramos arriba, 19 abajo). *La dirección del día no existía; el recorrido sí.* M1/M2 buscan
dirección: están resolviendo el problema equivocado.

**Duración de los tramos** (ZigZag 0.30 sobre `bars_minute`): mediana ~10 min el 08-12 y ~18 min
el 08-11. Ninguno de los 137 medidos llegó a 60 min. Con `RETARDO_M1_MIN = 20`, llegar tarde no
es mala suerte: es aritmética.

---

## 1. LO QUE SOBREVIVIÓ: distancia a la media corta

```
ENTRADA   |SPY - media| >= 0.20   ->  comprar HACIA la media
                                      (precio ARRIBA -> PUT ; ABAJO -> CALL)
CONTRATO  el ITM mas profundo que quepa en 320$
SALIDA    a los 8 MINUTOS exactos
REENTRADA inmediata
```

**Resultado con ejecución realista** (señal de la vela cerrada, compra al minuto siguiente):
`08-11 +109.20$ | 08-12 +222.66$ | 2 días +331.86$ en 37 operaciones`.

### ⚠️ La `media` NO es un VWAP

`spy_direction.py:541` calcula `((high+low+close)/3).rolling(5).mean()` — **una SMA de 5
periodos del precio típico, SIN volumen**. La columna se llama `vwap` por herencia del bot
original. Lo que funciona es *la media corta*. **Queda sin probar el VWAP de verdad**
(`bars_minute.volume` existe): es la primera mejora que debería intentarse.

### Cómo se encontró (importa, porque es replicable)

Se barrieron **las 54 variables** de `ta_minute` + derivadas. Ninguna pasaba el umbral… hasta
que se vio que `dist_vwap` daba lift positivo **en los DOS extremos** de su distribución:

```
dist_ema8   ALTO +5.7/+5.2    BAJO +2.8/+3.9
dist_vwap   ALTO +4.3/+6.5    BAJO +2.8/+5.2
```

Se estaba midiendo **con signo**, partiendo la señal en dos mitades que se anulaban. Con
**valor absoluto** el efecto aparece entero:

```
|dist_vwap| top20%   lift +7.1 (08-11)  +6.5 (08-12)
|dist_vwap| top10%   lift +5.8 (08-11) +14.5 (08-12)
```

📌 **Regla general:** si una variable da lift positivo en ambos extremos, **la magnitud importa
y el signo no**. Aplícalo a cualquier variable nueva antes de descartarla.

Y la dirección se resuelve sola: de los inicios de tramo fuerte en el top20 % de |dist|,
**30 de 30 van CONTRA la desviación** (7/7 y 8/8 con la media; 6/6 y 9/9 con ema8).

### Los controles que pasó

| control | resultado |
|---|---|
| **Tautología** (el que mató al gamma flip) | +6,8/+6,5 contra `extremo del rango 30` **+5,3/+4,5**, `SMA30` +2,5/+4,5, `distancia al medio del día` +2,3/+1,6. Gana a las 4 líneas base tontas en los 2 días — **pero solo por +1,5/+2,0 sobre el extremo de rango: parte del efecto SÍ es la tautología del extremo local** |
| **Nula por desplazamiento circular** | 0 de 10 la superan, **mediana −4** (sin sesgo estructural) |
| **Azar con la MISMA exposición** | 300 semillas: mediana **−127 $**, solo 25 % positivas. **3/300 la superan → p = 0.0100** |
| **Direccional** | siempre-CALL **−360 $**, siempre-PUT **−3 $**. Ninguna dirección fija gana |
| **T2 (quitar las mejores)** | aguanta quitar las 3 mejores en los dos días |
| **Robustez §7** | con salida t8, umbrales **0.20-0.28 positivos en LOS DOS días** |

### Sesgo de ejecución (cuantificado, no ignorado)

```
entrar en el mismo minuto de la señal   +468$   <- look-ahead, NO es alcanzable
entrar al minuto siguiente (realista)   +332$   -29%
entrar 2 minutos tarde                  +163$
```
Y la robustez se estrecha: la rejilla pasa de **36/36** a **18/25**, y **solo la columna t8
aguanta**. Todo lo publicado usa la cifra realista.

---

## 2. LO QUE MURIÓ, y con qué prueba

**No re-proponer sin pasar antes el control que lo mató.**

| idea | la prueba que la mató |
|---|---|
| **Seguir el movimiento** (zigzag, breakout) | breakout **0 %** de 27 combinaciones positivas; zigzag 7 %. Pierde −321 a −398 $ en los 7 umbrales. **Es aritmético**: confirmar un giro cuesta 2C y los tramos son de 0,60-1,38 pts ⇒ el peaje es el 67-100 % del tramo. No hay valor de C donde salga |
| **Soportes/resistencias por pivotes previos** | rebota **44,2 %** y **47,9 %** — los dos días POR DEBAJO del 50 %. n=224 y n=140 |
| **Cambiar de modo por régimen** (lateral→revertir, tendencia→seguir) | **0 %** de 9 combinaciones positivas, mediana −372 $. Es lo que intentaba el efficiency ratio |
| **Flujo → dirección** | signo contrario entre días (−19,0 vs +25,9), n=7 y n=13 |
| **Flujo → magnitud del recorrido** (parecía 2,06x) | **ES UN CRONÓMETRO**: `rho(volumen, minuto del día)` = **−0,536 / −0,573**. 10 de 13 picos antes de las 11:00, y la mañana ya se mueve 0,940 vs 0,330 la tarde |
| **Tape** (agresor, presión neta, desequilibrio) | 0,76x-1,11x = **no separa nada**. Además solo es fiable desde las 12:25 del 08-12 (antes veía 4-6 strikes de 40) |
| **28 de las 54 variables de `ta_minute`** | muertas por el **test del cronómetro** ANTES de mirar ningún lift: atr −0,78, bb_mid −0,94, ema50 −0,97, diff +0,79… |
| **Reversor puro** (sin la media) | pasa T4 pero con **mediana de la nula +62** (sesgo estructural), rejilla dentada (−232 a +426) y T2 lo deja NEGATIVO los 2 días |
| **Filtro de volatilidad sobre el reversor** | **REDUNDANTE**: `vol>=0.20/0.30/0.40` dan resultado IDÉNTICO — si la señal ya exige 0,35 en 5 min, el rango de 15 min ya es ≥0,40. Su "+69 % de mejora" era **una sola operación de −59 $** |
| **Filtro de walls sobre el reversor** | 12/12 positivas pero **NO mejora el dinero** (137,46/88,90 vs 137,64/85,20 del crudo): solo opera la mitad de veces |
| **Salir al cruzar la media** (en vez de por reloj) | daba más (+505) y rejilla constante, pero **FALLA la nula circular**: 2/10 la superan, mediana **+332**. Usar la media también en la salida hace que la nula rotada conserve estructura |
| **Umbral adaptativo por ATR** | peor que el fijo (+39/+294 vs +155/+314). El ATR ya era un cronómetro (rho −0,78): mete la hora por la puerta de atrás |
| **Filtrar por la mañana** | **NO EVALUABLE**: el 08-11 no tiene precios antes de las 11:48 ⇒ 0 operaciones. Pendiente con más datos |

---

## 3. METODOLOGÍA — el orden que funcionó

1. **TEST DEL CRONÓMETRO PRIMERO.** `|rho(variable, minuto del día)| >= 0.30` → muerta. Tres
   líneas de código; mató 28 variables y una hipótesis que parecía sólida. **Antes que nada.**
2. **T2: quitar la mejor operación**, antes que cualquier estadístico fino. Un resultado que
   depende de un trade es una historia, no una estrategia.
3. **Mirar el número de OPERACIONES antes que el P&L.** Si una variante "mejora" operando
   menos, casi siempre lo que hizo fue quitar una operación mala por azar.
4. **Nula por desplazamiento circular — y mirar su MEDIANA.** Si la nula ya gana, hay sesgo
   estructural (le pasó al reversor: +62).
5. **Control de azar con la MISMA exposición al mercado.** El más severo y el más barato:
   300 semillas en un segundo. Ajusta la frecuencia de entrada para comparar peras con peras.
6. **Control de multiplicidad:** esperadas por azar = `%pos(día1) × %pos(día2) × n`.
7. **Cuidado con filtros lógicamente redundantes** con la señal que filtran.
8. **Leer la REGIÓN de la rejilla, nunca la celda máxima.**

---

## 4. LOS DATOS: qué hay y qué no

| día | precios de opción | barras | tape | sirve para |
|---|---|---|---|---|
| 08-10 | **0** | **0** | — | **nada** |
| 08-11 | 15.614 desde **11:48** | 390 | desde 14:36 | media sesión |
| 08-12 | 24.391 desde 09:30 | 390 | **40 strikes solo desde las 12:25** | día completo |

- `premium_minute` tiene `bid/ask/mid/spread` **por strike y minuto**: es la tabla clave para
  simular. Ningún script anterior la usaba para esto.
- `ta_minute` guarda el TA de la **vela CERRADA** (`spy_direction.py:3817` usa `df.iloc[:-1]`),
  así que **no hay look-ahead en la columna**. El sesgo está en la ejecución, no en el dato.
- **Spread por profundidad** (0DTE, medido): ATM 0,011 → 1,07 $ ida y vuelta; ITM3 0,053 →
  5,26 $; ITM5 0,106 → 10,61 $. Con tope 320 $ solo caben ITM de 1-2 pts ⇒ spread barato.
- **El ITM es palanca, no arreglo:** con buen timing 52 → 162 $; con el timing real solo
  amortigua (−83 → −37). Aporta ~4 % de la brecha, no la mitad.
  ⚠️ El **"+39,00 del 770C"** que justificó el commit del ITM **NO se reproduce**: con los
  precios de la BD (10:25 mid 3,18 → 15:45 mid 2,83) da **−36,72 $**.

---

## 5. POR DÓNDE SEGUIR (en orden de valor esperado)

1. **El VWAP de verdad.** La señal usa una SMA(5) del precio típico. `bars_minute.volume`
   existe. Si el VWAP real mejora el lift, es la mejora más barata que queda.
2. **La primera hora y media.** Ahí está el **60 % del dinero** y es donde peor están los datos
   (el 08-11 no tiene precios y el tape estuvo ciego hasta las 12:25). Con una sesión completa
   nueva se puede atacar por fin.
3. **Distancia adaptativa que NO sea un reloj.** El ATR falló por cronómetro. Habría que
   destendenciar cualquier candidato antes de probarlo.
4. **Combinar la media con el flujo por VENTANA MÓVIL** (`net_call_1m/5m/15m`,
   `net_call_min`): son las únicas columnas de flujo que **no** murieron por cronómetro, y no
   se han probado en combinación con la media.
5. **Volver a medirlo todo con 5 sesiones.** Nada de lo de aquí está establecido.

---

## 6. HERRAMIENTAS

`analisis/simulador_media.py` — motor de simulación read-only: capital 400 $/día, tope 80 %,
ITM que quepa, precios al mid, comisión 1,72 $/op, FLATTEN 15:45, y **no obliga a estar en
mercado** (clave en 0DTE: estar siempre comprado paga theta las 6 horas).
Incluye el control de azar y el de desplazamiento circular.

`coldruns/media_coldrun.py` — cold run del disparador con las FUNCIONES REALES: la regla, el
borde exacto del umbral, mantener pese al giro, la salida por tiempo, **la reentrada sin
duplicar posición** (con el `_place` real, porque el guard vive dentro), el aviso cuando falta
la media, y el interruptor A/B.

---

## 7. LÍMITE — leer esto antes de creerse nada de arriba

**2 días**, uno de ellos solo desde las 11:48, y **37 operaciones**. `p = 0.01` es significativo
pero **no es una validación**: es la mejor hipótesis disponible, no un resultado. La
confirmación real es la primera sesión nueva, out-of-sample, con la configuración congelada.

Y el aviso que ya está escrito en `INVESTIGACION_M1_M2.md` y sigue valiendo:
**si se ajusta el valor DESPUÉS de ver los datos nuevos, se vuelve al punto de partida.**
