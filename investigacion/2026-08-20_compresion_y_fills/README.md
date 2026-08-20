# 2026-08-20 — LA COMPRESIÓN DEL ST-3 (+13.826 $) Y EL MAPA REAL DE FILLS

Dos investigaciones independientes del mismo día. La primera sale **entera de una observación
del usuario mirando el gráfico**; la segunda de lanzar 255 órdenes reales contra IBKR.

---

# PARTE 1 — LA COMPRESIÓN DE LA LÍNEA DEL ST-3

## La observación

> *"Cuando la línea del supertrend se mantiene estable en el mismo valor vela por vela, el precio
> se lateraliza. Eso es tiempo muerto que no se debería tradear."*
> Y después: *"aplanarse también significa fin de una tendencia, y se regresa en dirección al
> supertrend"*.

**Por qué tiene base mecánica** (verificado en `rebote.st_lin_p:68-69`): la línea solo se
actualiza cuando el precio hace un EXTREMO NUEVO (`lb > fl` o `CL[i-1] < fl`). Si se congela, es
que el precio no está haciendo extremos. No es correlación: **línea plana ES el rango**.
El usuario lo matizó bien: *"no siempre la toca; se mantiene plana MIENTRAS el precio esté en un
rango"*. Es simultaneidad, no causalidad.

## La cadena, medida eslabón a eslabón (56.205 buckets, 485 sesiones)

```
línea plana >= 8 buckets
   -> el precio YA está cerca de la línea    dist0  3,16 -> 1,67 ATR
   -> TOCA la línea en 36 min                50,5% -> 73,8%   (+14,3 pts)
   -> el ST FLIPEA en 36 min                 17,5% -> 36,3%   (+11,7 pts)
   -> doblar unidades ahí                    +13.826 $ sobre 83.805
```
Todo monótono y consistente en ambos años (%toca por año: 74/72, 75/76, 72/72).

**Por qué paga:** `plana>=8` NO marca "viene un movimiento grande" — marca **"la tendencia actual
está a punto de terminar"**. Y el sistema es de reversión: opera CONTRA la tendencia previa.
Doblar cuando el régimen va a romperse es doblar en las señales que van a acertar.

## Resultado en el motor

```
base honesta          83.805 $   drawdown -21,1%   308 verdes / 156 rojos   racha 3
con compresión d8     97.631 $   drawdown -28,7%   313 verdes / 154 rojos   racha 3
                      +13.826 (+16,5%)
```
4/4 bloques · p = 0,0000 · **6,20 sigmas** · A1 +4.001 / A2 +9.825 · toca 148 días (31%), de los
que mejora el 69,6%.

Curva del umbral, suave y con máximo plano: `d4 +11.693 · d6 +13.924 · d8 +13.826 · d10 +9.699 ·
d14 +5.178 · d20 +377`.

## LOS CINCO TESTS QUE TUVO QUE PASAR

**1 · ¿Apalancamiento disfrazado?** NO. *(el test que mató una regla equivalente del agente del
motor original: su regla de doblar por IV perdía contra "doblar siempre")*
```
doblar SIEMPRE            481 $   <- QUIEBRA la cuenta
doblar 31% AL AZAR     89-95 k    <- quiebra en 8 de 17 semillas (47%)
doblar por compresión  97.631 $   <- no quiebra NUNCA
```
La señal no arriesga más: **evita doblar en los días que hunden la cuenta**.

**2 · ¿Mecanismo o cobertura?** MECANISMO. Aporte normalizado POR DÍA TOCADO:
```
umbral   4     6     8    10    16    20
$/día   53    77    93    68    45     8
```
Máximo interior con ratio 11,4x. Si fuera cobertura sería plano y solo cambiaría el total.

**3 · ¿Solo funciona en SPY?** NO. Es geometría pura del ST, no necesita premium:
```
SPY +1,2 pts · QQQ +0,3 · IWM +1,6 · DIA +0,7   (mismo signo)
GLD -0,4  (falla, pero es oro: otra microestructura)
```

**4 · ¿Empeora la bimodalidad?** NO. 8 arranques distintos, con y sin compresión:
**4 prosperan y 4 se congelan, idéntico en ambas configuraciones.** En las 4 que sobreviven
aporta +9.487 a +13.826. No empuja ni una trayectoria más a la congelación: dobla en días que
salen bien, así que el drawdown mayor se produce sobre una equity más alta.

**5 · ¿Aguanta otros regímenes de precio?** (envolvente, ver Parte 3) SÍ:
```
régimen        sin compresión   con d8
precios reales     83.805       97.631
p25 (baratas)      56.310       64.392
p50 (mediana)      59.158       63.635
p10 / p75 / p90       muere      muere    <- el sistema BASE ya muere ahí
```
La fragilidad no la introduce la compresión: ya está en el sistema.

## SIN LOOK-AHEAD (auditado línea a línea)

- La planitud compara cada bucket con el **anterior** — ambos cerrados.
- Se consulta el bucket **anterior al de la señal**: `(mm(h)//3)*3 - 3`. Sin ese `-3` se usaba el
  bucket que EMPIEZA en `h` y no cierra hasta 2 min después. **Era look-ahead de 2 minutos.**
- **Prueba empírica:** al corregirlo el resultado **SUBIÓ** (86.275 -> 91.226 con d12). Un
  look-ahead siempre infla; quitarlo siempre baja. Que subiera confirma que no había ventaja de
  futuro — era un desplazamiento de umbral (d12 con bucket anterior ≈ d13 con bucket propio).

## LO QUE NO CUMPLE

**El drawdown sube más que el profit**: -21,1% -> -28,7% (+36%) para un P&L que sube 16,5%.
La eficiencia beneficio/drawdown EMPEORA. Y ese drawdown **no está repartido**: ocurre en 8 días
(8-19 mayo 2025) pero **un solo día pesa el 70%** (2025-05-15, -1.412 $, que ya existe en la base
— la compresión no lo crea, llega a él con más tamaño). En % de cuenta ese día es -5,8%.

## ERRORES DE MEDICIÓN COMETIDOS (los tres los detectó el usuario al insistir)

1. **Tope de 14 buckets**: aplastaba todos los tramos largos en "plana>=6". El día de la foto del
   usuario tenía **25 buckets planos** y no se medía por separado. Subido a 60.
2. **Empezar en `i-1`**: `sen_p` aplica `shift_sen(+3)`, así que `i-1` es el bucket donde la línea
   SALTA de lado. Daba `plana=0` en los 1.505 flips. Corregido a `i-2`.
3. **Métrica relativa sesgada**: definir "se acerca" como `dist_min < dist0/2` PENALIZA los tramos
   planos, porque ahí el precio ya está cerca (1,67 vs 3,16). Con umbral ABSOLUTO (<=1.0 ATR, el
   de `reb2`) el efecto aparece: +14,3 pts.

## LO QUE SE MIDIÓ Y NO DIO NADA

- **Convergencia precio-línea** (`test_convergencia.py`, 48.867 buckets): TODOS los grupos entre
  46,4% y 49,4% con base 47,4%. "La línea avanza y el precio no" -> 47,2%. Nada.
- **Línea plana como filtro de ENTRADA** (no operar en tramos planos): **-7.289 $**.
- **Tramos planos cortos como tiempo muerto**: cierto pero irrelevante (-3% de recorrido).

---

# PARTE 2 — MAPA REAL DE FILLS (255 órdenes contra IBKR)

## Dónde se puede operar de verdad

```
moneyness   %fill   spread     moneyness   %fill   spread
   -5        22%    45,4%          +1       67%     2,1%
   -3        35%    15,6%          +2       59%     2,4%
   -1        59%     4,5%          +3       39%     3,1%
   +0        87%     2,9%  <-mejor +5       23%     4,6%
                                  +10        0%    14,6%
                                  +20        0%    26,2%
```
**El punto dulce es ATM (moneyness 0), no ITM.** Y `elegir_vert` compra deliberadamente el ITM
**más profundo** que quepa (`instrumento.py:21-24`, `mny>=0.5`), que con cuentas grandes cae en
+10/+20 donde el fill es **0 de 41 pruebas**. El backtest asume que todo lo que está en la cadena
es comprable al mid. **No lo es.**

**El spread predice el fill casi perfectamente**: <4% llena casi siempre, >6% no llena nunca.

## La salida no llena JAMÁS al límite

**89 de 89 ventas forzadas a mercado.** Ni una sola llenó al límite, ni siquiera bajando por
escalones (mid -> -25% -> -50% -> -75% -> bid, 8 s cada uno).
Coste real medido: **~5,5 $ por operación** de fricción de salida (339 $ en 62 operaciones).
Sobre un tope de 140 $ eso es un **4% por operación** — justo donde el sistema pasa de 129x a 100x.

## Correcciones de método en el propio sondeo

- **`cerrar_todo` es una función de EMERGENCIA**: su cascada vende A MERCADO si el mid no llena en
  8 s. Medí -11% con ella y lo llamé "coste de ejecución". **Falso**: era el coste de cruzar el
  spread con prisa. Al mid CON PACIENCIA el ida y vuelta medio es **-1,4 $**.
- **El aviso 10349** ("Order TIF was set to DAY") hace que `ib_insync` marque `Cancelled` de forma
  TRANSITORIA. La orden sigue viva. Salir ahí daba "IBKR rechaza todo" (4 de 4 en 0,5 s): falso.
- **Órdenes cruzadas**: dejar una venta viva y comprar el mismo contrato da
  `Error 201: Cannot have open orders on both sides`. Rechazo del propio sondeo, no del mercado.
- **El combo BAG tiene libro propio**, desplazado respecto a la suma de patas (0,03 en las
  muestras iniciales). Con 150 muestras el desfase medio se diluye a -0,009 (C) y +0,003 (P):
  **se retira como conclusión general** — existe en casos concretos, no de forma sistemática.

## Margen de IBKR

Ayer (15:17) rechazó 5 de 6 con `PROJECTED POST EXPIRATION MARGIN DEFICIT`. **Hoy, en toda la
sesión, NI UNO SOLO.** La diferencia es la hora: por la tarde IBKR proyecta el ejercicio del largo
ITM y bloquea. Sigue **PENDIENTE** localizar la hora exacta del corte.

---

# PARTE 3 — LA ENVOLVENTE

Superficie de percentiles del extrínseco: `(precio - intrínseco) / rango_del_día` agrupado por
(moneyness, minutos a vencimiento, C/P), percentiles 10/25/50/75/90.
**294 celdas, 2.544.226 observaciones.** NO son datos nuevos ni más histórico — son las mismas
485 sesiones vistas con las opciones más caras o más baratas de lo que estuvieron.

⚠️ **Calls y puts SEPARADOS desde el principio**: mezclarlos le costó tres sesiones al agente del
motor original (daba -37.332 $ en el p90, y era un artefacto).

**El sistema muere en 3 de 5 regímenes** (p10, p75, p90). Solo vive con precios reales, p25 y p50.
HIPÓTESIS (no verificada): necesita que el extrínseco esté en una banda estrecha — demasiado
barato y `elegir_vert` rechaza por el mínimo de 20 $ o compra basura ilíquida; demasiado caro y
nada cabe en el tope (el `sin_contrato` que se ve en vivo).

---

# PENDIENTES

1. **🔴 A qué hora empieza IBKR a rechazar por margen** (ayer sí a las 15:17, hoy ninguno).
2. **🔴 Qué contrato comprar**: el sondeo dice ATM (87% fill) y el sistema compra ITM profundo
   (0% fill). Es el cuello de botella real, medido en vivo y en backtest.
3. **🟡 ¿Puede la compresión sustituir a `reb2`?** `reb2` vale +12.763 $ de techo pero necesita ver
   12 buckets adelante. La compresión predice el toque ANTES (+14,3 pts) sin ver nada.
4. **🟡 Momento de RUPTURA de la planitud**: si la planitud ES el rango, el momento predictivo es
   cuando la línea deja de estar plana. NO MEDIDO.
5. **🟢 Aplicar la compresión**: pasa los 5 tests, pero empeora el drawdown y conviene arreglar
   antes el punto 2 — doblar el tamaño en un sistema que no puede ejecutar sus entradas amplifica
   un problema sin resolver.

# SCRIPTS

```
test_tiempo_muerto.py      la prueba correcta de la hipótesis (56.156 buckets)
test_convergencia.py       la variante que NO dio nada (48.867 buckets)
test_compresion_etfs.py    réplica en QQQ/IWM/DIA/GLD
test_linea_plana.py        primera versión (con los dos bugs, se conserva como registro)
envolvente.py              construye la superficie de percentiles
barrido_fills_total.py     sondeo de fills contra IBKR (órdenes REALES)
sondeo_paciencia.py        mide si el mid llena con paciencia
sondeo_margen.py           primera versión (usaba cerrar_todo: medía el peor caso)
```
Datos: `resultados/fills_reales.db` (tablas `sondeo`, `paciencia`, `barrido` con el log completo
de IBKR por orden) y `resultados/envolvente.json`.
