# ANTI-COMPACT CONTEXT — open-premium-ibkr (SPY 0DTE, `sys2/`)

> Leer ESTO primero tras `/compact` o `/clear`. Rama `main`. Aplican las 16 reglas de `CLAUDE.md`.
> Mediciones SIEMPRE sobre las 485 sesiones, con desglose AÑO 1 / AÑO 2.

## LECTURA OBLIGATORIA (en este orden)
1. `investigacion/2026-08-20_compresion_y_fills/README.md`
2. `investigacion/2026-08-19_sistema_real/README.md`
3. `PROMPT_CONTINUAR.md`

## ESTADO DEL SISTEMA
- Base honesta reproducible: **83.805 $** (139,7x desde 600 $), sin look-ahead.
  Se obtiene con `motor.SIS70(SES, PREM, ETFB, capital=600)` — la composición está APLICADA
  en `motor.py` (VERIFICADO: `motor.py:102-109`, `hasta` usado en `motor.py:123`).
  Saldo final = 600 + sum(D.values()), donde D = {fecha: pnl_dia}.
- Compresión del ST-3 (+13.826 $, 6,20 sigmas): pasa los 5 tests pero **NO está aplicada**.

## HALLAZGO DE LA SESIÓN 2026-08-20 (tarde) — CORRIGE EL README DE ESE MISMO DÍA

**El README dice "hoy, en toda la sesión, NI UNO SOLO" (rechazo de margen). Es FALSO.**
La BD `fills_reales.db` (tabla `barrido`) tiene **25 rechazos por MARGEN** el 2026-08-20.

> ## ⚠️ AUTOCORRECCIÓN (14:35) — LA CONCLUSIÓN DE ABAJO ERA PREMATURA
> Se dio como VERIFICADO "no es la hora, es el saldo" con datos que solo llegaban a las 14:07.
> Con la sesión más avanzada la frontera del 44% NO SE SOSTIENE:
> ```
> 13:59:32  C a4 mny+5  deb 367$  saldo ~622$  ->  Filled            (59% del saldo)
> 14:15:42  C a4 mny+5  deb 352$  saldo ~805$  ->  RECHAZADA MARGEN  (44%)
> 14:20:30  C a2 mny+3  deb 166$  saldo ~780$  ->  RECHAZADA MARGEN  (21%)
> ```
> **EL PATRÓN REAL (verificado sobre las 414 pruebas con moneyness de hoy) ES DOBLE:**
> ```
>                     pruebas   rechazos MARGEN
> ATM/OTM (mny<=0)      237          3    (1,3%)
> ITM     (mny>0)       177         45    (25,4%)
> ITM por hora:  10:xx 0%  ·  11:xx 0%  ·  12:xx 33%  ·  13:xx 38%  ·  14:xx 65%
> ```
> 1. **Solo se rechaza el ITM** — coherente con el mensaje literal de IBKR (proyecta el
>    ejercicio del largo ITM). Separación limpia y no depende de la hora.
> 2. **Dentro del ITM, el rechazo CRECE monótonamente con la hora.** La hora SÍ es una causa.
> 3. El saldo modula pero NO ordena los casos (ver las tres líneas de arriba).
> **NO VERIFICADO / SIN EXPLICAR:** el saldo pasó de 1.556,88 $ (14:15:21, clientId 36) a
> 805,23 $ (14:15:47, vigilante) — 750 $ en 26 s que ninguna operación del barrido justifica.
> **PENDIENTE:** rehacer el análisis con la SESIÓN COMPLETA al cierre (decisión del usuario).

> ## ✅ RESUELTO (15:17) — ES UNA FRONTERA MÓVIL: HORA × MONEYNESS
> El saldo queda DESCARTADO como causa: a las 15:16 IBKR rechazó un débito de 55 $ teniendo
> 1.298 $ en caja (4,2 % del saldo). Imposible que sea falta de margen.
> ```
> % RECHAZO POR MARGEN — hora x moneyness   (n entre paréntesis)
> hora      -5      -3      -2      -1      +0      +1      +2      +3      +4      +5
> 10:xx   0%(8)   0%(9)     -     0%(9)   0%(3)   0%(5)   0%(4)     -       -     0%(3)
> 11:xx  0%(16)  0%(13)     -    0%(12)   0%(3)   0%(3)   0%(7)   0%(8)     -    0%(10)
> 12:xx  0%(13)  0%(15)   0%(7)  0%(13)   0%(9)   0%(4)  60%(5)  50%(8) 100%(4) 33%(9)
> 13:xx  0%(15)  0%(15)  0%(15)   0%(9)   0%(4)     -    33%(3)  40%(5)  38%(8) 38%(13)
> 14:xx  0%(16)  0%(27)  0%(23)  22%(9) 100%(3)     -    67%(3)  86%(7) 85%(20) 55%(31)
> 15:xx    -      0%(3)   0%(6)  17%(6) 100%(6) 100%(6) 100%(3) 100%(6) 86%(7)  50%(6)
> ```
> 1. **Antes de las 12:00: CERO rechazos** en todo el rango (~130 pruebas).
> 2. **Desde las 12:00** se rechaza el ITM (mny >= +2).
> 3. **Desde las 14:00** la frontera baja hasta ATM (mny +0 -> 100 %).
> 4. **OTM (mny <= -2) NUNCA se rechaza**, a ninguna hora.
> Mecanismo coherente con el mensaje de IBKR: proyecta el ejercicio del largo, y cuanto más
> cerca del vencimiento menos margen de duda da a un strike cercano.
> **RUIDO PENDIENTE:** las 13:xx (33-40 %) salen más suaves que las 12:xx (50-100 %), y dentro
> de las 13:xx hubo un tramo 13:29-14:07 sin rechazos. n de 3-13 por celda. Reafinar al cierre.
> **CRUCE CON EL BACKTEST:** el 49,7 % de las operaciones del sistema son a las 09:xx (rechazo
> 0 %) y solo el 17,5 % a partir de las 13:00 -> el daño es MENOR de lo que dice el README.

**PREMATURO (ver autocorrección arriba) — el rechazo de IBKR NO depende de la hora, depende del SALDO.**
La cuenta se recargó a mitad de sesión (330 $ -> 711 $ hacia las 13:29), lo que rompió la
correlación hora/saldo y convirtió la observación en un experimento natural.
Solo pruebas con débito >= 140 $:

```
tramo                                    n   rech    %
A 09:45-10:57  saldo 588->491           14      0    0%
B 10:57-12:44  saldo 736->330           72      0    0%
C 12:44-13:29  saldo <330               28     25   89%
D 13:29-14:07  saldo 711->601 RECARGA   24      0    0%   <- MÁS TARDE que C, cero rechazos
```
D es posterior en hora a C, con débitos mayores (hasta 372 $), y CERO rechazos. Si la causa
fuera la hora, D tendría más rechazos, no ninguno.

Frontera (ratio débito / NetLiquidation): **0 rechazos en 259 pruebas por debajo del 40%**;
los 25 rechazos tienen ratio >= 44%; de 111 Filled solo 7 superan el 44%.

Refuerzo: la cuenta paper es CASH — `AvailableFunds == NetLiquidation` y `FullInitMarginReq = 0`
(medido 14:15:21). El margen disponible ES el saldo.

- **HIPÓTESIS (no separada):** en un vertical de débito, "débito alto" y "largo más ITM" van
  juntos; no se puede distinguir "consume caja" de "IBKR proyecta el ejercicio del largo".
- **NO VERIFICADO:** el rechazo de ayer (2026-08-19 15:17). Las tablas `sondeo`/`paciencia`
  solo contienen registros del 2026-08-20; no hay saldo de ayer que cruzar.

## SISTEMA INTEGRADO (compresión d8 + OTM desde las 14:00) — medido 2026-08-20 15:35
`barrido_integrado.py`. Los TRES controles replican exacto (83.805 / 97.631 / 79.394).
```
                          saldo    mult   drawdn  racha  verde  rojo   mejor día   peor día   mínimo
BASE                     83.805$  139,7x   21,1%      3    308   156   +2.368,85  -1.411,56    600$
+ compresión d8          97.631$  162,7x   28,7%      3    313   154   +2.368,85  -1.411,56    590$
+ OTM desde 14h          79.394$  132,3x   22,5%      3    309   153   +2.644,46  -1.064,46    600$
INTEGRADO (ambas)        92.179$  153,6x   35,0%      3    309   153   +2.644,46  -1.139,53    537$

                            AÑO 1        AÑO 2      AÑO 1 v/r    AÑO 2 v/r
BASE                      +30.559      +52.645        145/86       163/70
INTEGRADO                 +30.070      +61.510        141/88       168/65
```
**TRES AVISOS (no aplicar sin resolverlos):**
1. **NO es aditivo:** por separado +9.416 $, integrado +8.375 $. La interacción se come 1.041 $
   (el filtro horario quita operaciones de tarde que la compresión doblaba).
2. **Drawdown 21,1 % -> 35,0 %:** +66 % de drawdown por +10 % de profit. La eficiencia EMPEORA.
3. **Saldo mínimo 537 $, por debajo del capital inicial** (la base nunca bajaba de 600 $) y a
   solo 47 $ del apagado por supervivencia (KSUP x SUELO = 3,5 x 140 = 490 $).
**Y la mejora es TODA del AÑO 2** (+61.510 vs +52.645); en el AÑO 1 el integrado (+30.070) queda
POR DEBAJO de la base (+30.559). La compresión sola mejoraba los dos años.

### Nota de método: cómo calcular las métricas
Calculador VALIDADO contra la base publicada. La RACHA usa la definición del MOTOR
(`_racha = _racha+1 if tot < 0 else 0`): **un día sin operar (tot=0) RESETEA la racha**.
Con la definición ingenua (reset solo si tot>0) la base daría 5 en vez de 3.
Días operados: 464 con P&L != 0 + 21 días a cero (el README dice 465, un día de desfase).

### Look-ahead del sistema integrado
- **Compresión: NO** (auditada en el README; buckets ambos cerrados, consulta el anterior con -3;
  al CORREGIR el look-ahead de 2 min el resultado SUBIÓ, que es la prueba fuerte). Heredado, NO
  reauditado en esta sesión.
- **Frontera horaria: NO**, pero el corte de las 14:00 NO sale del backtest ni del AÑO 1: sale
  del sondeo de IBKR del 2026-08-20, POSTERIOR al periodo medido. Es un parámetro externo que
  describe una restricción de la plataforma, no una regularidad del precio. ⚠️ Las 14:00 resultan
  ser TAMBIÉN el mejor corte en P&L (12:00 cuesta el triple) — esa coincidencia hay que mirarla
  con desconfianza; el corte se sostiene por el mapa medido, no por el P&L.

## 💵 QUÉ SIGNIFICAN LOS NÚMEROS (aclarado al usuario el 2026-08-20; había confusión)

Todos son **el mismo sistema**. Lo que cambia es **cuánta realidad lleva dentro**. Ninguno tiene
look-ahead: la diferencia NO es ver el futuro, es suponer **ejecución perfecta**.

```
83.805$  señales limpias, SIN look-ahead. Supone que IBKR acepta TODO y que TODO llena. FALSO.
97.631$  lo mismo + compresión d8. Misma suposición falsa de base.
92.179$  lo mismo + filtro OTM desde las 14h. DESCARTADO (ver abajo). Ignorar este número.
41.122$  EL REAL (mediana de 8 semillas). Cuenta rechazos, fills reales y coste de salida.
46.410$  el real + compresión.
```

**LA CIFRA HONESTA: ~41.000$ desde 600$ (68x), ~46.000$ con compresión (77x).** La mitad del papel.

**Se pierde la mitad por tres cosas, todas MEDIDAS hoy:**
1. Por la tarde IBKR rechaza (12h el ITM, 14h hasta el ATM): esas operaciones no existen.
2. Aunque acepte, el fill real va del 50% al 84% según el contrato: el resto se queda colgado.
3. **139 de 139 ventas se forzaron a mercado.** Coste de salida -1,15% a -5,38% según débito.

**LO MÁS GRAVE NO ES EL DINERO: 3 de cada 8 arranques MUEREN** (4 de 8 con compresión). No pierden
poco a poco: empiezan con 600$, las primeras operaciones no llenan o las rechazan, la cuenta baja
de 490$ (`KSUP × SUELO`) y el sistema **se autoapaga para siempre**. Operan 2-4 días y se quedan.
Frase honesta: *"cuando arranca bien multiplica por 68, pero 3 de cada 8 veces no arranca"*.

**LÍMITE:** la superficie de ejecución sale de UN SOLO DÍA. Con un día no se puede prometer que
41.000$ sea el número; sí se puede afirmar que **83.805$ NO lo es**.

**POR QUÉ SE DESCARTÓ EL FILTRO OTM** (el usuario lo cuestionó con razón): no mejora nada, y su
premisa es FALSA — los OTM profundos (mny -2/-3/-5) tienen débitos de 2-14$ y **no llegan al
mínimo de 20$ del sistema** (0 de 68 en mny -5); el único OTM operable (-1) llena el 59% frente
al 84% del ATM. Integrarlo en el motor cambiaría el comportamiento del vivo sin dar nada a cambio.
Y "no abrir desde las 14h" (78.339$) sale casi igual que "OTM desde las 14h" (79.394$): **da
igual lo que se haga por la tarde**. El valor de la investigación de fills no fue cambiar el
sistema, fue saber que el número bueno no era alcanzable.

## 🗓️ SESIÓN 2026-08-21 — EL VENCIMIENTO SIGUIENTE (1DTE)

**DATOS NUEVOS** (los subió el usuario): `data_1dte/massive_premium_1dte.db` (782 MB, zip partido
en `data_1dte/`). 5.727.319 filas · 20.328 contratos · **482 días** (el 0DTE tiene 485) ·
2024-08-19→2026-08-12. DTE real: 1 → 78,0 % | 3 → 17,9 % (viernes) | 2 y 4 → 4,1 % (festivos).

### RESULTADOS (controles replicando exacto: 83.805 y 74.556)
```
0DTE sin score (referencia)  74.556$  dd 21,1%  461 días
1DTE TODO EL DÍA                428$  MUERE     3 días   <- se apaga por supervivencia
híbrido 1DTE desde 11:00     97.657$  dd 39,8%  474 días  +31,0%
híbrido desde 12:00          78.112$  dd 30,6%            +4,8%
híbrido desde 13:00          73.537$  dd 25,2%            -1,4%
híbrido desde 14:00          66.813$  dd 19,7%           -10,4%   <- el único que BAJA el dd
```
El **drawdown del 39,8 % es del ARRANQUE**, no de la madurez: el fondo es el 2024-08-26 con la
cuenta en **555 $** (sexto día). Pero eso es peor de lo que parece: **555 $ está a 65 $ del umbral
de apagado (490 $)**, o sea que el h11 pasa más cerca de morir en el arranque que la base.

### EL MECANISMO — POR QUÉ MUERE EL 1DTE PURO (medido, no supuesto)
```
% de sesiones en que el vertical ALCANZA...   0DTE     1DTE
  el 70% del ancho                           73,6%    58,4%
  el 95% (EL OBJETIVO DEL SISTEMA)           44,1%     4,8%   <- NUEVE veces menos
  el 100%                                    32,7%     1,7%
```
`TP_ANCHO=0.95` está calibrado para un instrumento que **se muere el mismo día**. Con 1DTE el
objetivo casi nunca se dispara → las operaciones se arrastran al cierre sin cobrar la saturación.
**PREDICCIÓN a contrastar:** el objetivo equivalente para 1DTE es el que se dispare ~44 % de las
veces = **≈75 % del ancho**. (Barrido en curso.)

### TRES HIPÓTESIS MÍAS QUE LOS DATOS TUMBARON
1. *"El 1DTE es más caro y no cabe en el tope"* → **FALSO**. El débito del VERTICAL es igual o
   MENOR (mny+2 a2: 117 $ contra 140 $): el valor temporal **se cancela entre las dos patas**.
   Los contratos sueltos sí son 2,36x más caros, el spread no.
2. *"El aporte del viernes se explica por el régimen de mercado"* → **NO**: sobrevive al control
   por rango (dif +88,3 $/día controlada vs +85,0 sin controlar).
3. *"Filtrar por régimen mejorará"* → **NO, EMPEORA** monótonamente: p40 −2.439 $, p60 −6.058 $,
   p80 −15.383 $. **Y contradice el análisis marginal**, que decía que esos días aportaban −2,2
   $/día. La causa es la COMPOSICIÓN: al no operar un día, el saldo crece menos y TODAS las
   operaciones siguientes son más pequeñas. **En este sistema ningún análisis marginal por día
   predice el efecto de un filtro: hay que correrlo entero.**

### LÍMITE DURO — DÍA Y DTE ESTÁN CONFUNDIDOS
Solo hay **1 vencimiento por sesión** en los 482 días: lunes {1} · martes {1,2} · miércoles {1,2}
· jueves {1,4} · **viernes {3,4}**. El DTE lo determina el día de la semana, así que "efecto
viernes" y "efecto 3DTE" **nunca varían por separado**. No se arregla con más análisis: hay que
descargar 2DTE/3DTE entre semana (ver IDEAS_Y_OPCIONES.md).
Reparto del aporte: lunes +82 · martes +201 · miércoles +7.900 · jueves +3.802 · **viernes
+11.115** (el 99 % está en mié/jue/vie).

### FILLS EN VIVO (2026-08-21, hasta las 10:02) — AVISO PARA EL HÍBRIDO
```
              n   filled   MARGEN   spread~
SINGLE 0DTE  10   9 (90%)     0      1,9%
SINGLE 3DTE  10   8 (80%)     0      1,4%
vert   0DTE  19  11 (58%)     0      4,4%
vert   3DTE  18   4 (22%)     0      4,8%   <- llena la MITAD
```
El vertical del vencimiento siguiente **llena el 22 %** con spread parecido: no es que sea caro de
cruzar, es que **no hay contrapartida** (volumen 4-7x menor, medido sobre los 2 años).
Y un hallazgo aparte: **los SINGLES llenan mucho mejor que los verticales** (80-90 % vs 22-58 %) y
con la mitad de spread — un vertical exige que alguien cruce LAS DOS PATAS a la vez.
⚠️ Cero rechazos por margen hasta las 10:02, que es lo ESPERADO (el bloqueo empieza a las 12:00).

### TAPE — FUNCIONANDO DESDE HOY
Primer día de captura. 65.740 ticks a las 10:03, con bid/ask y signo poblados.
⚠️ **BUG CORREGIDO EN CALIENTE**: se guardaba en **UTC** (el resto del sistema usa ET). Arreglado
en `captura._hora_et` con `zoneinfo` (no offset fijo: validado también contra un caso de
INVIERNO, UTC-5) y migrados 18.271 ticks con `sys2/db/migrar_tape_utc.py`. No daba ningún error:
precios y signos eran correctos, solo el reloj estaba 4 horas adelantado.

## PENDIENTES POR PRIORIDAD
1. 🔴 **Cerrar el punto anterior con la ventana 15:00-15:45 medida con saldo ALTO** (cuenta
   recargada a 1.556 $ a las 14:15). Si no hay rechazos, la hora queda descartada como causa.
2. 🔴 **Qué contrato comprar.** `elegir_vert` (`instrumento.py:21-24`) ordena por moneyness
   DESCENDENTE y devuelve el primero que quepa en el tope: compra el ITM MÁS PROFUNDO.
   Fill real medido: mny 0 -> 87%, +1 -> 67%, +2 -> 59%, +3 -> 39%, +5 -> 23%, +10/+20 -> 0%
   (0 de 41). Script nuevo: `investigacion/2026-08-20_compresion_y_fills/scripts/barrido_moneyness.py`.
   Humo (74 días, hasta 2024-12-01): base 10.171 · mny<=6 10.171 (idéntico) · mny<=4 6.804 ·
   mny<=3 6.551 · mny<=1.5 3.657 · mny<=2 3.470.
3. 🟡 **RUPTURA de la planitud (observación del usuario, 2026-08-20 tarde):** *"cuando la
   planicie termina, el precio coge impulso HACIA donde dice el supertrend"*. Distinto de lo
   medido (plana>=8 -> el ST FLIPEA el 36,3%, o sea el precio va CONTRA el ST previo). NO MEDIDO.
4. 🟡 ¿Puede la compresión sustituir a `reb2`? (techo +12.763 $, pero `reb2` ve 12 buckets).
5. 🟢 Aplicar la compresión — después del punto 2.

## CÓMO SE MIDE (patrón de la casa)
- Los barridos parchean `motor.py` / `pipeline.py` / `instrumento.py` por `os.environ`, lanzan
  N variantes en paralelo y **restauran siempre** en el `finally`.
- ⚠️ Máximo 8-14 procesos en paralelo.
- ⚠️ Verificar que NO quedan `.bak` en `sys2/` antes de lanzar otro barrido.
- **Todo barrido lleva un CONTROL neutro que debe reproducir la base exacta.** Si el control se
  desvía, el parche está mal y la tanda entera se descarta.
- `assert` sobre el patrón EXACTO tras cada parche, NO sobre el conteo del nombre: `RL_MNYMAX`
  contiene `_MNYMAX` como subcadena y hace que el conteo mienta (error cometido hoy).
- Poner el assert ANTES del `copy2` del `.bak`, o un fallo deja un `.bak` huérfano que bloquea
  el siguiente barrido (error cometido hoy).
- Verificar con POCOS días (`RL_HASTA` / `HUMO=fecha`) antes de lanzar las 485 sesiones.

## SEGURIDAD AL PARCHEAR CON EL VIVO EN MARCHA
VERIFICADO: no hay `reload`/`importlib` en `sys2/vivo/` ni `sys2/core/` -> los módulos se
importan una vez al arrancar y tocar el archivo en disco NO afecta al proceso en marcha.
Además `I.elegir_vert` solo se llama en `sistema.py:462` (dentro de `_abrir`), y con
`SOLO_CAPTURA=True` nunca se llega a `_abrir` (`sistema.py:294-298`).
HIPÓTESIS (riesgo residual): si el vivo se reiniciara con los archivos parcheados, arrancaría
con código parcheado.

## PROCESOS DE LA SESIÓN 2026-08-20
- `sys2.vivo.sistema` — modo `SOLO_CAPTURA=True` (`config.py:121`): captura barras y cadena, NO opera.
- `barrido_fills_total.py` — lanza órdenes REALES a IBKR hasta las 15:45.
  ⚠️ Su lista `MONEYNESS` (línea 37) ya NO incluye +10/+20: desde las 12:30 dejó de probar el
  ITM profundo, que es el caso que provocó el rechazo del 2026-08-19.
- `vigila_saldo.py` — umbral **950 $** (era 300 $; se subió porque la frontera de rechazo está
  en el 40% del saldo y el barrido usa débitos de hasta 372 $).
  ⚠️ El script hace `break` y TERMINA en cuanto el saldo baja del umbral: si se lanza con un
  umbral por encima del saldo actual, se apaga en la primera comprobación (pasó hoy).
- clientIds: vivo 17 · barrido 34 · vigilante 35 · consultas puntuales 36.

## NO REPETIR (medido y descartado)
Ver §6 de `PROMPT_CONTINUAR.md` y "LO QUE SE MIDIÓ Y NO DIO NADA" del README del 2026-08-20.
