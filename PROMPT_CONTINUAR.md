# PROMPT PARA RETOMAR — estado al 2026-08-19 (fin de sesión)

Pegar tal cual tras `/clear`, o dárselo a otro agente. Este documento resume **toda la sesión
del 2026-08-19**: qué se hizo, qué se descubrió, qué se descartó y qué queda pendiente.

Repo: `C:\Users\eulis\proyectos\open-premium-ibkr` · rama `main` · commit `3a32c6c`.
Sistema SPY 0DTE, carpeta `sys2/`. Aplican las **16 reglas de `CLAUDE.md`**.
Las mediciones SIEMPRE sobre las **485 sesiones** con desglose **AÑO 1 / AÑO 2**.

**LEER PRIMERO:** `investigacion/2026-08-19_sistema_real/README.md` (el detalle técnico completo).

---

## 1. QUÉ PASÓ EN ESTA SESIÓN (en una frase)

Se descubrió que **los +72.497 $ del backtest no existían** (el motor veía el futuro), se
eliminó el look-ahead, y sobre la base honesta se encontraron mejoras reales que llevan el
sistema a **89.188 $ desde 600 $ (148,6x)** en 2 años — todo aplicado, validado y subido.

---

## 2. EL RECORRIDO, POR ORDEN

### 2.1 Se invalidó el hallazgo de la mañana (+17.477 $)
La sesión empezó con una "señal" medida esa mañana: *tras un flip, si el precio se acerca a la
línea del ST, no entrar*. Daba +17.477 $ y pasaba los 4 tests. **Era falsa por dos motivos:**
- **Look-ahead**: consultaba los buckets `i+1..i+4` (12 min después) pero registraba la señal
  con la hora del flip, y el motor abre ahí (`motor.py:215`).
- **Fuga de objetivo** (peor): el test definía `malo = reb2 dice DESCARTA`, pero `reb2` DEFINE
  DESCARTA como *"la mecha tocó la línea a ≤1.0·ATR"* — el mismo criterio que el predictor.
  Predictor y objetivo eran la misma variable. Con objetivo independiente: +28,6 → +15,2 pts.

### 2.2 Se limpiaron los 2 look-ahead que quedaban
- **ORB futuro** (`pipeline.py:38-41`): −1.503 $
- **`dia_bueno` desde el minuto 1** (`motor.py`): −1.132 $
```
motor con look-ahead 72.497$ → fix reb2 35.878$ → fix ORB 34.375$ → fix dia_bueno 32.620$
```

### 2.3 Se descubrió que la métrica estaba mal
Todo lo medido hasta entonces usaba **MFE** (recorrido favorable máximo). **Coincide con
"pierde dinero" solo el 44,6% de las veces.** El sistema compra verticales que SATURAN en el
ancho y liquidan por dónde está el precio AL CERRAR. Con MFE `reb2` parecía perder; con la
métrica correcta gana. **Regla: usar el neto, nunca el MFE.**

### 2.4 Se midió el techo de cada decisión (con look-ahead A PROPÓSITO)
Para saber dónde buscar antes de gastar tiempo. **No aplicables**, son techos:
```
RETRASA +12.763$ (5,08σ) · INVIERTE +13.640$ (3,62σ) · DESCARTA +3.904$ (2,04σ)
```
⚠️ Un proxy de P&L dio la descomposición AL REVÉS (decía DESCARTA 62% / RETRASA 9%).
**Medir siempre con el motor real, no con proxies.**

### 2.5 Se encontró la señal buena: LA CADENA DE OPCIONES
Todo lo probado exigía ESPERAR velas, y el retraso se comía la señal. Pero **en el minuto del
flip ya existe la cadena** — coste de tiempo CERO. Tres señales con lógica económica:
```
vertical ATM barato → el mercado no paga el movimiento    (Q1 72,9% pierde vs Q5 34,1%)
IV muerta          → sin recorrido esperado               (Q1 74,5% vs Q5 41,6%)
skew en contra     → pagan protección contra tu flip      (Q5 80,0% pierde)
```
Combinadas (score 0-3), umbrales del **AÑO 1** y validado en el **AÑO 2 que nunca se miró**:
`score 0 → 51,0% pierden · 1 → 59,1% · 2 → 74,1% · 3 → 89,3%` · **p = 0,0000**.

### 2.6 Se arregló el SIZING (el cuello de botella real)
La tabla de `autocalibra` BAJA de nivel al perder → con tope 75 $ no cabe ningún vertical
(cuestan 88-135 $) → **el sistema se autoapagaba**: con 600 $ operaba 6 días de 485 y moría.
Y con ancho 2 el ITM profundo cuesta ~200 $ y tampoco cabe → **`sin_contrato`**.
```
sizing 18% del saldo con suelo 140 + composición real   → 48.689$
+ pausa tras 3 días rojos (racha 7→3 Y GANA +665$)      → 49.354$
+ filtro por cadena de opciones (score ≥2)              → 61.711$
+ regla de supervivencia (ruina 33% → 0%, gratis)       → igual $
+ salida al 95% del ANCHO (+9.010$)                     → 89.638$ (149,4x)
```

### 2.7 Se verificó contra los días reales
Con la cadena viva (82 contratos/min con bid/ask, tabla `premium`):
```
             backtest   REALIDAD    señales → operaciones
2026-08-17   +402,52    no operó    3 señales, 2 "sin_contrato"
2026-08-18    +83,02     -92,58     7 señales, 4 "sin_contrato" + 2 "pos_abierta"
2026-08-19    +87,13     -53,33    12 señales, 3 "sin_contrato" + 3 "pos_abierta"
```
**La brecha NO era look-ahead (solo 92 $ de 718) ni ejecución: era que el sistema NO PODÍA
COMPRAR.** 9 de 22 señales perdidas por `sin_contrato`.

---

## 3. RESULTADO FINAL (aplicado y verificado)

```
capital 600$ · 485 sesiones · SIN look-ahead
Saldo final ......... 89.188$ (148,6x)      Racha máxima ......... 3 días
Anualizado .......... 1.248%                Drawdown máximo ...... -21,1%
Días operados ....... 465 de 485            Saldo mínimo ......... 600$ (nunca bajó)
Verdes .............. 316 (68%)             Mejor día ............ +2.368,85$
Rojos ............... 148 (32%)             Peor día ............. -1.411,56$
AÑO 1 +34.413$  ·  AÑO 2 +54.625$           Ratio gan/pérd ....... 1,46
```
**COLD RUNS: 11 VERDE / 1 ROJO** (`cr_validacion`, esperado: mide el aporte de reglas
informativas y ese aporte cambia al cambiar el sistema. PENDIENTE recalibrar sus targets).

**Capital mínimo: 490 $** (= `SIZING_KSUP` × `SIZING_SUELO` = 3,5 × 140). Con 450 $ NO ARRANCA.
Mínimo prudente **550 $** (mejor drawdown: −18,6%). Con 800 $: 112x y −24,7%.
⚠️ **El profit final es el mismo (88-90k) con cualquier capital entre 490 y 1.500 $**: el techo
son 3 contratos (`TOPE_UNIDADES`) de ancho 4 ≈ 1.200 $ por operación. **No escala.**

---

## 4. ⚠️ LO QUE NO ESTÁ GARANTIZADO (leer antes de creerse la cifra)

1. **DISTRIBUCIÓN BIMODAL.** De 16 arranques distintos: **8 llegan a 125-149x y 8 se quedan
   CONGELADOS en 0,5-0,8x**. Cero quiebras. No hay término medio: se decide en las primeras
   semanas (con 600 $ y suelo 140, cada operación arriesga el 23% de la cuenta).
2. **IBKR RECHAZA ÓRDENES.** Medido en real (2026-08-19 15:17): `Error 201: PROJECTED POST
   EXPIRATION MARGIN DEFICIT` — **5 de 6 bloqueadas, incluso cruzando el spread**. IBKR proyecta
   el ejercicio del largo ITM (100 acciones ≈ 77.000 $) y bloquea. Y el sistema compra el largo
   ITM a propósito (`instrumento.py:23-25`, `mny>=0.5`). **Por la mañana SÍ llena.**
   Impacto: OTM solo desde 14:00 → **−7%** · OTM todo el día → **MUERE (340 $)**.
3. **COSTE DE EJECUCIÓN.** 2% → 129x · 5% → 100x · **10% → MUERE**. Spreads reales medidos:
   **3,4-4,8%** en los verticales que opera (0,82-1,16 $). Solo hay **2 fills válidos**.
4. El backtest no modela fills parciales, rechazos ni cierres fallidos (los tres han ocurrido).

---

## 5. PENDIENTE — POR PRIORIDAD

1. **🔴 A QUÉ HORA EMPIEZA IBKR A RECHAZAR.** Es la incógnita que separa "149x" de "no
   funciona". Lanzar órdenes de prueba desde la apertura y anotar la hora del primer rechazo.
   Script listo: `investigacion/2026-08-19_sistema_real/scripts/diag_fill.py`.
2. **🔴 COSTE REAL DE EJECUCIÓN**: precio pedido vs conseguido en cada orden.
   Script: `scripts/medir_spreads.py` (tiene modo `--seco` que NO envía órdenes).
   ⚠️ El registro de fills tiene un BUG: 6 de 8 quedaron con `lleno=0, parcial=1` y precios NULL.
3. **🟡 Recalibrar los targets de `cr_validacion`** con el sistema honesto (único rojo).
4. **🟡 Reducir la bimodalidad**: si el problema es sobrevivir el arranque, probar arrancar con
   menos riesgo relativo (más capital con fracción más pequeña). NO MEDIDO.
5. **🟢 Terminar el Monte Carlo**: quedó en 16 de 50 arranques (`scripts/barrido_montecarlo.py`).

---

## 6. NO REPETIR (medido y descartado sobre 485 sesiones)

- **Esperar antes de entrar** (3/6/9/15/21 min, fijo o condicional): todo dentro del ruido o
  negativo. La espera condicional (idea buena) da **−3.912 $**.
- **Subir la fracción del sizing** (25/50/70/100%): PEOR y con drawdown hasta −88%. El 18% es
  el óptimo (Kelly) **y lo sigue siendo con el score activo**.
- **MAX_TRADES 6/8/99**: menos profit y peor día −1.547/−1.715. El cupo de 4 es protección.
- **Stops por operación** (−30/−50/−70%): cuanto más ajustado, peor. −30% deja la cuenta en 469 $.
- **Objetivo al 50% del débito** (479 $) y **tiempo máximo** (464 $): destruyen. El objetivo solo
  funciona atado al **ANCHO** (techo físico del vertical).
- **Freno de tamaño tras racha**: drawdown y racha IDÉNTICOS. La racha es propiedad de la SEÑAL.
- **Suelo dinámico** (operar más pequeño en vez de parar): −594 $. Operar herido alarga la
  sangría. El "estado absorbente" NO es un bug, es protección.
- **Reacción honesta** (reevaluar reb2 con ventana creciente): −4.772 $.
- **Bajar el suelo del tope a 110 para empezar con menos capital**: TRAMPA. Entra y muere en la
  primera pérdida en todos los capitales probados.
- Y lo de días anteriores: toma de beneficio por toques · soportes/resistencias · trailing ·
  filtrar giros por cuerpo/dist/hora · secuencias de velas previas.

---

## 7. ERRORES DE MÉTODO COMETIDOS (para no repetirlos)

1. **MFE no es la métrica** (coincide con "pierde dinero" solo el 44,6%).
2. **Los proxies de P&L mienten**: medir con el MOTOR real.
3. **El ruido no es fijo**: depende de cuántos días toque la regla (80 días → ±1.918 $;
   420 días → ±6.000 $). Un filtro quirúrgico se detecta con mucho menos aporte.
4. **Con composición hay que medir en %**, no en dólares (el "peor día −1.412 $" era −5,8%).
5. **Un `replace` que no se aplica da resultados IDÉNTICOS y parece un hallazgo.**
   Poner SIEMPRE `assert` tras cada parche. (Pasó con el descuento de ejecución.)
6. **En bash, `$?` tras un pipe captura el exit del ÚLTIMO comando**, no del script. Por eso
   los 12 cold runs salieron "todos verdes" cuando 2 estaban rojos.
7. **Verificar el resultado con pocos días ANTES de lanzar 485 sesiones.**

---

## 8. CÓMO ESTÁ LA MÁQUINA

- Aplicación **PARADA** (sistema y panel cerrados).
- Cuenta paper DU7154467 **plana**, saldo 1.497 $ (el usuario la reiniciará a 600 $).
- Repo **limpio** y sincronizado con GitHub (`3a32c6c`).
- Los barridos parchean `motor.py`/`pipeline.py`/`instrumento.py` por `os.environ`, corren N
  variantes **en paralelo** y **restauran siempre** en el `finally`.
  ⚠️ Máximo **8-14 procesos** (con 24 el sistema se queda sin recursos).
  ⚠️ **Verificar que no quedan `.bak` en `sys2/`** antes de lanzar otro barrido.
