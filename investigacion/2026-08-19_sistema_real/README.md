# 2026-08-19 — DEL BACKTEST CON LOOK-AHEAD AL SISTEMA REAL

> ## ⚠️ CORRECCIÓN 2026-08-20 — LA CIFRA ANTERIOR (89.188$ / 149,4x) ERA IRREPRODUCIBLE
> El código commiteado da **83.805 $ (139,7x)**, verificado tres veces y determinista.
> **Qué pasó:** el 19/08, al probar un orden alternativo del filtro de opciones, se "restauró"
> el pipeline con un `mv` y se verificó SOLO con un `grep` de posiciones de línea — nunca se
> volvió a correr la medición. La pista estaba a la vista y se malinterpretó: `cr_motor` pasó de
> 51.030 a 48.022 entre dos tandas de cold runs y se achacó a "código a medio aplicar".
> La versión exacta que produjo 89.188 **se perdió y no está en ningún commit**.
> **Lección (regla 8):** comprobar con `grep` que un archivo "parece" correcto NO es verificar.
> La única comprobación válida es volver a correr la medición y comparar el número.
> Todas las cifras de este documento están corregidas a la base reproducible.


De **+72.497 $ que no existían** a **+83.805 $ medidos sin ver el futuro**, partiendo de 600 $.

Este documento explica **cómo se descubrió el look-ahead**, **cómo se eliminó** y sobre todo
**cómo se garantiza que el número nuevo no lo tiene**. Todos los scripts están en `scripts/`
y los resultados día a día en `resultados/`.

---

## 1. CÓMO SE DESCUBRIÓ EL LOOK-AHEAD

### 1.1 El primero (`reb2`, encontrado el 2026-08-18)

El backtest llamaba a `pipeline.construir_sen(bars…)` **una sola vez con TODAS las barras del
día**, antes del bucle de minutos (`motor.py:124`). Dentro, `rebote.reb2` clasifica cada flip del
ST-3 mirando **hasta 12 buckets hacia delante** (36 minutos). Resultado: al llegar al minuto del
flip, el motor ya "sabía" si ese flip iba a ser falso.

El sistema vivo llama a `construir_sen` **cada minuto** con las barras hasta ese momento: con ~1
bucket, el bucle de `reb2` no tiene nada que recorrer y devuelve **NORMAL siempre**.

Demostrado con los 2 flips reales del 2026-08-18, reevaluados con ventana creciente:
```
14:18 C -> NORMAL con 1-8 buckets, DESCARTA con 12
15:15 P -> NORMAL con 1-2 buckets, DESCARTA con 4
```
El vivo obedeció los dos. El backtest los habría ignorado. **Coste: -43% del sistema.**

### 1.2 El segundo (la "señal" del 2026-08-19 por la mañana, +17.477 $)

Se midió una regla nueva ("si tras el flip el precio se acerca a la línea del ST, no entrar")
que daba **+17.477 $ y pasaba los 4 tests de validación**. Era falsa, por DOS motivos
independientes, encontrados leyendo el código ejecutable:

**(a) Look-ahead**: el filtro consultaba los buckets `i+1..i+4` (12 minutos después del flip)
pero registraba la señal con **la hora del flip** — y el motor abre en esa hora
(`motor.py:215`). Compraba en el minuto `h` sabiendo lo que harían las 4 velas siguientes.

**(b) Fuga de objetivo** (más sutil y más grave): el test definía el objetivo como
`malo = reb2(...) devuelve DESCARTA/INVIERTE`. Pero `reb2` **define** DESCARTA como *"la mecha
tocó la línea a ≤1.0·ATR"* (`rebote.py:122,135`) — **el mismo criterio que el predictor**, con la
misma ATR. Predictor y objetivo eran la misma variable en ventanas distintas (4 velas vs 12).
Con un objetivo independiente la separación caía de **+28,6 pts a +15,2 pts**.

### 1.3 Los dos que quedaban

- **ORB futuro** (`pipeline.py:38-41`): una apertura de las 09:38 se descartaba por estar a <5
  min del ORB de las **09:40**, que aún no había ocurrido. Coste: **-1.503 $**.
- **`dia_bueno` desde el minuto 1** (`motor.py:158`): `nq` se calculaba antes del bucle, así que
  doblaba unidades a las 09:35 con datos de las 10:30. En vivo (`reglas.py:60`) devuelve False
  hasta tener 60 barras = 10:30. Coste: **-1.132 $**.

---

## 2. CÓMO SE GARANTIZA QUE EL NÚMERO NUEVO NO TIENE LOOK-AHEAD

Cinco mecanismos, todos verificables ejecutando los scripts de `scripts/`:

### 2.1 Cada regla usa SOLO información del pasado (verificado en código, no en comentarios)
| regla | qué mira | por qué es honesta |
|---|---|---|
| `reb2` con 1 bucket | las barras hasta el minuto actual | es literalmente lo que ve el vivo |
| filtro de opciones | la cadena **del minuto del flip** | coste de tiempo CERO, no espera nada |
| salida al 95% del ancho | el precio **actual** de la posición | no mira hacia delante |
| pausa tras 3 rojos | los días **anteriores** | pasado puro |
| sizing y supervivencia | el saldo **acumulado hasta ayer** | pasado puro |

El libro de opciones se construye con el **último precio conocido de cada strike (≤10 min)**,
nunca con precios posteriores (`fase2_opciones.py`).

### 2.2 Los umbrales se aprendieron SOLO con el AÑO 1
Los cortes del filtro de opciones (`costv≤0.195`, `IV≤0.150`, `skew≥0.031`) salen del percentil
25 del **año 1**. El año 2 **nunca se miró** para elegirlos. Resultado (`fase3_modelo.py`):
```
score  |  AÑO 1 (entrenamiento)  |  AÑO 2 (nunca visto)
  0    |        49,7% pierden    |      51,0%
  1    |        64,5%            |      59,1%
  2    |        75,4%            |      74,1%
  3    |       100,0%            |      89,3%
```
La escalera se mantiene en el año 2. Y el % de días que mejoran es **64,3% en train vs 65,4% en
test** — casi idéntico, que es la firma de una señal real. (Con `score≥3` cae de 91,7% a 61,5%:
**eso sí estaba sobreajustado**, por eso se usa `score≥2`.)

Control contra el azar: el score selecciona 153 flips del año 2 con 74,5% de perdedores;
muestras aleatorias del mismo tamaño dan mediana 57,5% y percentil 95 en 62,7%. **p = 0,0000.**

### 2.3 Todos los barridos llevan un CONTROL que debe reproducir la base exacta
Cada tanda incluye una variante neutra que **tiene que dar el mismo resultado día a día**. Si el
control se desvía, el parche está mal y la tanda se descarta. Ejemplos verificados:
`hn_base ≡ ap_base` (0 días distintos) · `tc_vivo` = +35.878 exacto · `rx_base_mt4` = +0.

Así se detectó un fallo real: un guard `>= "15:40"` movía 52 días y −234 $ porque `Sen` **también
cierra por giro** (`motor.py:165`), no solo abre.

### 2.4 Se mide contra el ruido, no contra cero
La base mueve **385 $ de desviación típica al día**. El ruido pareado (sd de las diferencias ×
√n) va de ±1.918 $ (80 días afectados) a ±6.000 $ (420 días). **Las 12 primeras variantes
probadas caían todas entre −1,03σ y +0,27σ: indistinguibles del azar.** Solo se aceptaron
cambios que superan ese umbral.

### 2.5 El look-ahead se usó a propósito, pero SOLO para medir techos
Las variantes `tc_*` (`barrido_techo.py`) usan `reb2` con visión completa **deliberadamente**,
para saber cuánto vale como máximo cada decisión antes de buscar el sustituto honesto. **No son
aplicables y están marcadas como tal.** Dieron: RETRASA +12.763 $ (5,08σ), INVIERTE +13.640 $,
DESCARTA +3.904 $.

---

## 3. EL CAMINO, PASO A PASO (cada cifra medida sobre 485 sesiones)

```
motor original CON look-ahead ......................... 72.497 $  (cuenta equivalente 1.800 $)
- fix reb2 (1 bucket = lo que ve el vivo) ............. 35.878 $
- fix ORB futuro ...................................... 34.375 $
- fix dia_bueno desde 10:31 ........................... 32.620 $   <- BASE HONESTA
- con el tamaño REAL del vivo (tope 110) ............... 6.442 $
+ COMPOSICIÓN (recalibrar con el saldo, como el vivo) . 38.012 $ desde 1.000 $ (600 $ MUERE)
+ HISTÉRESIS (el nivel sube pero nunca baja) .......... 37.540 $ desde 600 $
+ sizing 18% del saldo con suelo 140 .................. 48.689 $
+ PAUSA tras 3 días rojos ............................. 49.354 $   (racha 7 -> 3)
+ FILTRO POR CADENA DE OPCIONES (score ≥2) ............ 61.711 $
+ REGLA DE SUPERVIVENCIA (parar si saldo < 3,5×suelo) . igual $, riesgo de ruina 33% -> 0%
+ SALIDA AL 95% DEL ANCHO ............................. 83.805 $   (139,7x)
```

---

## 4. RESULTADO FINAL (capital 600 $, 485 sesiones, sin look-ahead)

```
Saldo final .............. 83.805 $ (139,7x)     Racha máxima de rojos ....  3 días
Beneficio ................ 83.205 $              Drawdown máximo ..........  -21,1%
Anualizado ...............  1.202 %              Saldo mínimo .............  600 $ (nunca bajó)
Días operados ............ 465 de 485            Mejor día ................ +2.368,85 $
Días verdes .............. 308 (66,4%)           Peor día ................. -1.411,56 $
Días rojos ............... 156 (33,6%)           Ratio ganancia/pérdida ...  1,46
AÑO 1 +30.559 $  ·  AÑO 2 +52.645 $   (los 5 peores días = 6,3% del beneficio)
```

---

## 5. LO QUE **NO** ESTÁ GARANTIZADO (leer antes de creerse la cifra)

1. **La distribución es BIMODAL.** Sobre 16 arranques distintos (de 50 en curso): 8 llegan a
   125-149x y **8 se quedan congelados en 0,5-0,8x**. Cero quiebras. El resultado se decide en
   las primeras semanas: con 600 $ y suelo 140, cada operación arriesga el 23% de la cuenta.
2. **Restricción de IBKR SIN RESOLVER.** Medido en real (2026-08-19 15:17, cuenta 1.500 $): IBKR
   rechaza con `Error 201: PROJECTED POST EXPIRATION MARGIN DEFICIT` los verticales cuya pata
   larga puede acabar ITM — **5 de 6 órdenes bloqueadas, incluso cruzando el spread**. Y el
   sistema compra deliberadamente el largo ITM (`instrumento.py:23-25`, `mny>=0.5`).
   Por la mañana SÍ llena (op132/133/134 entre 09:31 y 09:52). Impacto medido:
   `OTM solo desde las 14:00` → -7% · `OTM todo el día` → **el sistema muere (340 $)**.
   **PENDIENTE: medir a qué hora empieza a rechazar.**
3. **Coste de ejecución.** Con 2% el sistema da 129x, con 5% 100x, con 10% **muere**. Spreads
   reales medidos (15:14, peor momento): **3,4-4,8%** en los verticales que opera. Pero cuántos
   se pagan de verdad sigue sin medirse: solo hay 2 fills válidos.
4. **El backtest no modela** fills parciales, rechazos por margen ni cierres fallidos — los tres
   ocurrieron en días reales.
5. **El sistema no escala**: el techo son 3 contratos (`TOPE_UNIDADES`) de un vertical de ancho 4
   (~400 $), o sea ~1.200 $ por operación. Con la cuenta en 90.000 $ sigue arriesgando lo mismo.
   Por eso 490 $ y 1.500 $ acaban ambos en ~89.000 $: es una máquina de cuentas pequeñas.

---

## 6. ERRORES COMETIDOS EN ESTA INVESTIGACIÓN (documentados para no repetirlos)

1. **MFE no es la métrica**: `recorrido favorable máximo` coincide con "pierde dinero" solo el
   **44,6%** de las veces. Todas las señales medidas con MFE eran humo. Usar el **neto**.
2. **El proxy de P&L mintió**: decía DESCARTA 62% / RETRASA 9%; el motor real dice RETRASA
   +12.763 / INVIERTE +13.640 / DESCARTA +3.904. **Medir siempre con el motor.**
3. **"El vivo siempre ve NORMAL" era FALSO**: la simulación hacía `break` en la primera
   coincidencia. Prueba real: las señales 16 y 19 del 2026-08-19 tienen origen `ST-3 INVIERTE`.
4. **El ruido no es fijo**: depende de cuántos días toque la regla (80 días → ±1.918 $;
   420 días → ±6.000 $). Un filtro quirúrgico se detecta con mucho menos aporte.
5. **"Peor día -1.412 $" no era un fallo**: con composición hay que medir en % (era -5,8%).
6. **Un `replace` que no se aplica da resultados IDÉNTICOS y parece un hallazgo.** Pasó con el
   descuento de ejecución (0%/2%/5%/10% daban lo mismo). **Poner `assert` tras cada parche.**

---

## 7. CÓMO REPRODUCIR

Los barridos parchean `motor.py`/`pipeline.py`/`instrumento.py` con configuración por
`os.environ`, lanzan N variantes **en paralelo** y **restauran siempre** en el `finally`.

```bash
python scripts/barrido_realista.py     # los 3 fixes anti-look-ahead, paso a paso
python scripts/barrido_capmin.py       # capital mínimo (490 $) y suelo del tope
python scripts/barrido_tp.py           # salida por % del ancho
python scripts/barrido_montecarlo.py   # 50 arranques distintos -> distribución real
python scripts/fase3_modelo.py         # score de opciones, train A1 / test A2
python scripts/medir_spreads.py --seco # spreads reales de la cadena (sin enviar órdenes)
```
⚠️ Máximo **8-14 procesos** en paralelo: con 24 el sistema se queda sin recursos.
⚠️ Verificar SIEMPRE que no quedan `.bak` en `sys2/` antes de lanzar otro barrido.
