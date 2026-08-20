# IDEAS Y OPCIONES SOBRE LA MESA — cierre del 2026-08-20

> Documento vivo. Recoge **todo lo hablado**, medido o no, para que ninguna idea se pierda.
> Cada opción dice qué ataca, **cuánto puede recuperar como máximo**, qué está VERIFICADO y qué no.
> Contexto numérico completo en `.claude/anti-compact-context.md`; arranque en `PROMPT_CONTINUAR.md`.

---

## EL PROBLEMA, EN UNA TABLA

El sistema vale **83.805 $** en el papel y **~41.000 $** con la ejecución real medida. Los
42.683 $ que faltan se reparten así (medido en el MISMO montaje, control replicando 83.805 exacto):

| causa | cuesta | drawdown | mata la cuenta |
|---|---|---|---|
| no hay contrapartida (**fill**) | **−29.813 $** | 20,7 % | 1 de 4 |
| **venta forzada** a mercado | −23.673 $ | **36,9 %** | 0 de 1 |
| **rechazo por margen** de IBKR | −13.488 $ | 22,5 % | 0 de 4 |
| las tres juntas | −42.683 $ | 40,8 % | **3 de 8** |

⚠️ **NO son aditivas**: por separado suman 66.974 $ y juntas cuestan 42.683 $. Se solapan (una
orden ya rechazada no puede además fallar el fill). Reparto proporcional aproximado —**HIPÓTESIS,
no medición**—: fill ~19.000 $, salida ~15.100 $, margen ~8.600 $.

**Lo más grave no es el dinero: 3 de cada 8 arranques mueren en la primera semana.** La cuenta
baja de 490 $ (`KSUP × SUELO`) y el sistema se autoapaga para siempre.

---

## OPCIONES QUE ATACAN EL MARGEN (techo: ~13.488 $, el más pequeño de los tres)

### A. Comprar el vencimiento SIGUIENTE en vez del 0DTE  🔬 SCRIPT LISTO
**Idea del usuario.** IBKR rechaza con `PROJECTED POST EXPIRATION MARGIN DEFICIT`: proyecta el
ejercicio **al vencimiento de HOY**. Si el contrato vence después, hoy no hay nada que proyectar.
**Lo respalda el mapa medido**: el rechazo no es "por la tarde", es por PROXIMIDAD al vencimiento
(0 % antes de las 12h → 100 % del ATM a las 15h; el OTM, que nunca se proyecta ejercido, NUNCA
se rechaza a ninguna hora).
- **Script:** `scripts/barrido_0dte_vs_1dte.py` — lanzar EN LA APERTURA, todo el día.
- **RIESGO PRINCIPAL (no medido):** el sistema gana porque el vertical **SATURA en el ancho**
  (95 % del ancho = 139,7x; por % del débito DESTRUYE = 479 $). Un 0DTE satura porque el tiempo
  se acaba HOY; un vencimiento posterior tiene valor temporal por delante y **puede no llegar
  nunca al 95 % intradía**.
- **Riesgo secundario:** menos líquido que el 0DTE → **puede empeorar el fill, que es la causa
  MAYOR**. Se arreglaría un problema de 13.488 $ estropeando uno de 29.813 $.
- **VERIFICADO:** `massive_premium.db` NO tiene ni un contrato no-0DTE (2.616.094 filas, 100 %
  0DTE) → la mitad de rentabilidad **no se puede medir** hasta tener esos datos (el usuario los
  está descargando).

### B. Comprar SINGLES en vez de verticales  🔬 SCRIPT LISTO
**Pregunta del usuario:** ¿el bloqueo es cosa de spreads o pasa también con una sola pata?
- **VERIFICADO: NO HAY NI UN DATO.** Las 606 pruebas del día 20 fueron todas verticales.
- **HIPÓTESIS:** debería bloquear IGUAL o PEOR. En el escenario que preocupa a IBKR (vencimiento),
  un largo ITM suelto y un vertical cuyo largo acaba ITM producen el MISMO ejercicio (100 acciones
  ≈ 76.400 $). Y el single es peor: en el vertical, si el precio pasa del strike corto las dos
  patas se compensan; en el single no hay nada que compense.
- Importa porque **el sistema TIENE modo single** (`instrumento.elegir`) para piramidar y rodar.
- Va en el mismo script que (A): matriz 2×2 vencimiento × tipo.

### C. Concentrarse en las PRIMERAS HORAS  📊 MIDIÉNDOSE
**Plan B del usuario:** *"si esto no se resuelve, enfocar los esfuerzos en las primeras horas"*.
- **Lo respaldan los datos:** 0 % de rechazo antes de las 12:00, spreads más estrechos, y el
  **49,7 % de las operaciones del sistema YA son a las 09:xx**.
- En el papel cortar la tarde cuesta (−10.978 $ desde las 13h), pero **la pregunta correcta es si
  sigue costando cuando cuentas que por la tarde te rechazan y no te llenan**. Si la tarde es
  puro coste, cortarla no es una renuncia: es quitarse el problema gratis.
- Variantes `w_no12/13/14` en `barrido_ejecucion_real.py`, con ejecución real activa.
- **Ventaja sobre A y B:** no depende de IBKR ni de datos nuevos. Es una decisión nuestra.

---

## LA OPCIÓN QUE ATACA LA CAUSA MAYOR — SIN EXPLORAR

### D. Arreglar la SALIDA  ⚠️ NADIE LA HA TOCADO
Es la causa que **dispara el drawdown ella sola: 21,1 % → 36,9 %**, y cuesta 23.673 $.
**El dato duro: 139 de 139 ventas del día 20 acabaron FORZADAS a mercado.** Ni una llenó al límite.
- La causa está identificada en el código: el sistema cierra con `cerrar_todo(espera=8)`, que es
  una **función de EMERGENCIA** — si no llena al mid en 8 s, va a mercado.
- **No toca la estrategia: es ejecución pura.** No cambia ninguna señal.
- Ideas sin probar: escalones más finos, empezar a vender antes del cierre por giro, usar el
  libro del combo (que está DESPLAZADO respecto a la suma de patas) en vez del mid de las patas.
- **Es la de mejor relación esfuerzo/retorno y la única que nadie ha intentado.**

---

## IDEAS NUEVAS DEL USUARIO (2026-08-20 noche)

### E. El HUECO DE LA NOCHE (overnight)  ⚠️ hay que separar DOS cosas
> **Corrección (el usuario me señaló que lo había planteado mal):** yo había marcado esto como
> "inviable" mezclando dos ideas distintas. Solo una lo es.

**E1. COMPRAR opciones en premarket → ❌ INVIABLE, y no por falta de datos:**
```
barras del SPY ....... 04:00 - 20:59   (160.133 barras antes de 09:30)  <- SÍ hay premarket
opciones capturadas .. 09:30 - 16:14   (0 filas antes de 09:30)
massive, 2 años ...... 09:30 - 16:14
```
**El mercado de opciones de EE. UU. no abre en premarket.** Puedes ver moverse el SPY a las
07:00, pero no hay dónde comprar el contrato. Esto no cambia con más datos.

**E2. ANALIZAR el cierre de un contrato y su apertura al día siguiente → ✅ SÍ SE PUEDE (idea
del usuario), pero necesita los datos que está descargando.**
La razón por la que hoy no se puede es sutil y conviene tenerla clara: **un 0DTE no sobrevive a
la noche** — vence ese mismo día, así que no hay "apertura siguiente" que cruzar, y por eso en
`massive_premium.db` (100 % 0DTE) no existe el dato. Un contrato de **1DTE o más SÍ sobrevive**:
tiene cierre el día X y apertura el día X+1.
**Qué se podría medir con esos datos, y hoy no mide NADA:**
 - cuánto salta el precio de un contrato por el hueco de la noche (a favor y en contra)
 - si mantener una posición al cierre compensa o destruye
 - si el gap del SUBYACENTE (que SÍ tenemos: 160.133 barras de premarket) predice el gap de la
   OPCIÓN, que es lo que decidiría si vale la pena dejar algo corriendo
**Ojo con el sesgo:** el sistema actual cierra TODO antes de las 16:00 por diseño (evitar
asignación, §12). Medir el overnight es explorar un modo de operar que hoy NO EXISTE, no afinar
el actual. Es una vía nueva, no una mejora.

**E3. ¿SE REPITE EL PATRÓN? (formulación exacta del usuario)**
> *"ver cómo reaccionó el contrato en cierto premarket después de cierto cierre, y ver si se
> repite el patrón"*

O sea: **condicionar** la reacción del premarket al TIPO de cierre del día anterior, y comprobar
si es recurrente. No es "¿hay gap?" sino "¿el gap depende de cómo cerró el día?".

**LA MITAD SE PUEDE MEDIR HOY, GRATIS**, y conviene hacerlo en este orden:
1. **Primero el SUBYACENTE** — tenemos 160.133 barras de premarket sobre 485 sesiones. Se puede
   medir ya: *tras un cierre del tipo X (cerca del máximo/mínimo del día, con el ST-3 alcista o
   bajista, con la línea plana o activa, tras día verde o rojo), ¿cómo se comporta el SPY en el
   premarket y en la apertura?* — con desglose AÑO 1 / AÑO 2, como todo lo demás.
2. **Solo si (1) muestra algo**, buscar el efecto en las OPCIONES (necesita los datos multi-DTE).

**POR QUÉ ESE ORDEN:** la opción deriva del subyacente. Si el SPY no muestra patrón condicionado
al cierre, la opción tampoco lo mostrará — y esa comprobación es gratis y no espera a ningún
dato. Es el mismo criterio que hizo bien el barrido de mañana: **la prueba barata que puede matar
la idea, antes que la cara que la confirmaría.**

**⚠️ TRAMPA CONOCIDA:** el sistema YA tiene reglas de este tipo (`gap_fade`, `pm_rev`,
`ayer_rev`, `dia_anterior`) y aportan 217+323+209 señales. Antes de medir nada hay que ver qué
capturan ya, o se acabará redescubriendo algo que lleva meses en el código (regla 9).

**Y lo que ya está disponible hoy:** usar la INFORMACIÓN del premarket para decidir mejor en la
apertura — donde el sistema hace la mitad de sus operaciones. Ya lo hace en parte (`ORB`,
`gap_fade`, `pm_rev` se calculan con premarket). Explotarlo más NO está explorado.

### F. Usar otros DTE para encontrar más flips  ⚠️ MATIZ IMPORTANTE
Los flips del ST-3 salen del **precio del SPY**, no de las opciones: otro vencimiento **no genera
flips nuevos**, el ST-3 es exactamente el mismo.

### F2. Detectar FLIPS FALSOS comparando 0DTE contra 1DTE  ⭐ LA MÁS PROMETEDORA SIN MEDIR
**Idea del usuario (2026-08-20 noche).** Y tiene el mejor fundamento de todas las pendientes,
porque **es exactamente la forma de la única señal que de verdad funcionó**.

**Por qué encaja tan bien.** El hallazgo del 2026-08-19 fue el filtro por cadena de opciones
(+12.000 $, p = 0,0000). Todo lo demás fallaba porque exigía ESPERAR velas y el retraso se comía
la señal; la cadena funcionó porque **en el minuto del flip ya existe, con coste de tiempo CERO**.
Pues bien: **en el minuto del flip también existe la cadena del 1DTE.** Misma virtud, información
nueva, cero retraso.

**El mecanismo económico (HIPÓTESIS, no medido).** Comparar el 0DTE con el 1DTE es leer la
ESTRUCTURA TEMPORAL de la volatilidad:
 - si la IV del 0DTE se dispara y la del 1DTE **no** → el mercado paga movimiento **solo para
   hoy, para las próximas horas**: ruido intradía, gamma, un flip que probablemente sea falso.
 - si suben **las dos** → hay convicción de que el movimiento continúa más allá del cierre:
   el flip tiene más probabilidad de ser real.
Es información que **el filtro actual no puede ver**: solo mira la cadena 0DTE (costv, IV, skew),
así que es ciego a si el movimiento esperado es de hoy o estructural.

**Qué haría falta:** los datos multi-DTE que el usuario está descargando. Con ellos se mediría
igual que el score actual (`fase3_modelo.py`): umbrales aprendidos SOLO en el AÑO 1, validados
en el AÑO 2 que nunca se mira.

**Techo a batir:** `reb2` con visión completa (look-ahead A PROPÓSITO) vale RETRASA +12.763 $ /
INVIERTE +13.640 $ / DESCARTA +3.904 $. Si esto detecta flips falsos SIN mirar el futuro, sería
un sustituto honesto de parte de ese techo — que es justo lo que se lleva buscando desde el 18.

**⚠️ Trampa a evitar (ya costó una sesión el 19):** el objetivo NO puede definirse con `reb2`, que
DEFINE "falso" como *"la mecha tocó la línea a ≤1,0·ATR"*. Si el predictor y el objetivo comparten
criterio, la señal se infla sola (+28,6 → +15,2 pts al usar un objetivo independiente). El
objetivo tiene que ser el **P&L neto** medido con el motor real.

### G. El TAPE del subyacente  🔬 CAPTURADOR LISTO, DATOS DESDE MAÑANA
Pregunta original: ¿hay relación entre órdenes entrantes, ST-3 y movimiento del precio?
- **VERIFICADO: solo existen 3 días de tape** (12, 13 y 14 ago, del sistema anterior), auditadas
  las 52 bases de datos del repo. `sys2` no capturaba nada: la tabla existía y `cr_schema` pasaba
  en VERDE porque comprobaba que EXISTE, no que tenga datos. **6 sesiones perdidas.**
- Capturador implementado, con fallback a RTVolume y cold run `cr_tape` VERDE.
- **Con 3 días no se puede concluir nada** (la compresión se validó con 56.205 buckets de 485
  sesiones). Hay que acumular. Por eso el capturador era urgente.

---

## DESCARTADO (medido, no repetir)

| idea | resultado |
|---|---|
| filtro OTM desde las 14h | −4.410 $ y **premisa falsa**: los OTM no llegan al mínimo de 20 $ de débito |
| "no abrir desde las 14h" | −5.466 $, casi igual que el OTM → **da igual lo que hagas por la tarde** |
| tope fijo de moneyness (mny≤2) | **−53,7 %** |
| SALIR cuando la línea se aplana | **destruye**: 430-46.676 $ (misma familia que "tiempo máximo" = 464 $) |
| descartar flips con línea activa | −4.264 a −18.449 $, monótono a peor |
| ruptura de la planitud → impulso | nada: ni en media ni en colas (32,7 %/30,1 % en todos los grupos) |
| "impulso vivo = línea moviéndose" | sale AL REVÉS (el máximo está con la línea congelada) |

**SIGUE EN PIE:** la **compresión d8** del usuario (+13.826 $, 6,20 sigmas, aporta en los 3
regímenes de la envolvente donde el sistema vive). Es el uso de la planitud que SÍ funciona.
⚠️ Pero con ejecución real **empeora la supervivencia**: 4 de 8 semillas mueren frente a 3 de 8
(3 vs 4 sobre 8 NO es significativo: hace falta más muestra).

---

## ORDEN SUGERIDO

1. **D (la salida)** — causa mayor del drawdown, no depende de nadie, nadie la ha tocado.
2. **C (primeras horas)** — decisión nuestra, no depende de IBKR ni de datos nuevos.
3. **A y B** — se prueban gratis mañana en la misma sesión; pueden morir en una tarde.
4. **G (tape)** — ya está capturando; hay que dejar pasar semanas antes de mirarlo.
5. **E y F** — exploratorias, sin coste de oportunidad.

`Nota:` A y B atacan **la causa más pequeña** (13.488 $ de 42.683). Aunque salgan bien, el
grueso del problema sigue siendo el fill y la salida.
