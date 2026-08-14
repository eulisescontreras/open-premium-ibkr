# PROMPT PARA EL SIGUIENTE AGENTE — 2026-08-13 ~10:20 ET, SESIÓN EN CURSO

Proyecto: `C:\Users\eulis\proyectos\open-premium-ibkr` — scalping SPY 0DTE por flujo de opciones.
Capital: **SIEMPRE 400 $ o menos**. El usuario reinicia la paper cada día; las pérdidas NO se
arrastran. Tope por contrato = `acct_avail × 0.80` = **320 $**.
Es **PAPER**: hoy importa recolectar datos limpios, no el resultado.

Empieza saludando y **comprobando el estado real** (proceso, git, tablas, posición). No asumas
que sigue vivo lo que pone aquí.

---

## 1. LO QUE MÁS FÁCIL SE MALINTERPRETA: la "inversión" NO invierte, y es DELIBERADO

`INVERTIR_SENAL=True` se aplica en **dos** sitios (`_senal_media()` y `_lado_del_estado()`) y
las dos inversiones **se anulan**. Efecto neto: el sistema compra **lo mismo que la regla
original**.

```
09:30 (antes de invertir)  dist +1.165  senal PUT   estado DOWN  -> compra PUT
09:56 (ya "invertido")     dist +0.241  senal CALL  estado UP    -> compra PUT
```
Misma situación (precio ARRIBA de la media), misma compra. Lo único que cambió es la **etiqueta
`UP`/`DOWN` del panel**, que ahora sale al revés de lo que significaba.

**El usuario lo sabe y decidió dejarlo así** (~10:15) para no reiniciar a mitad de sesión.
Disco y proceso están **sincronizados**; hay un comentario largo en `_senal_media()` que lo
explica. **NO lo "arregles" sin hablarlo con él**: cambia lo que compra el sistema.
Si algún día se quiere invertir de verdad → quitar la inversión de `_senal_media()` (NO la de
`_lado_del_estado()`) y reiniciar; entonces precio-arriba → estado DOWN → **CALL**.

⚠️ **Para analizar el día:** los datos del 08-13 **no son los de un sistema invertido** pese al
flag. Son la regla normal con las etiquetas del estado cambiadas.

---

## 2. ESTADO EN VIVO (a las 10:19)

```
App: PID 13728 desde 09:55:43. ARMADA. Código y proceso coinciden.
Trades:
  #13  09:31:36 -> 09:39:53  PUT  777  2.78 -> 1.52  -126.00  (tiempo)
  #14  09:54:52 -> 09:56:47  CALL 775  2.52 -> 2.70   +18.00  (giro)
  #15  09:56:52 -> 10:17:19  PUT  777  0.94 -> 0.66   -28.00  (giro)
  #16  10:18:18 -> ABIERTA   CALL 776  2.72
Realizado: -136.00$   |   media_minute 46 filas   |   tape SPY 4.905 filas
```
La #13 salió por `tiempo` porque se abrió cuando `MINUTOS_POS` aún valía 8.

**Configuración activa:**
```
USAR_MEDIA=True  MEDIA_DIST=0.20  MINUTOS_POS=0  INVERTIR_SENAL=True (ver punto 1)
EJECUCION_ITM=True  TAPE_SPY=True  USAR_M1=True (solo registra, NO decide)
```

**Quién da la señal:** `_senal_media()` — distancia del SPY a su media de 5 velas. Cuando
`|SPY − media| >= 0.20`, `_update_signal()` cambia `self.state` (el `UP`/`DOWN` del panel), y
ese estado dispara el giro de contratos. `MINUTOS_POS=0` = no se vende por reloj: se aguanta
hasta que el estado cambie de lado y ahí se gira (vender + comprar el contrario).

⚠️ **`ta_vals["vwap"]` NO ES UN VWAP.** Es `((high+low+close)/3).rolling(5).mean()`
(`spy_direction.py:541`): media simple de 5 velas, SIN volumen. Nombre heredado del bot
original. **Probar el VWAP de verdad** (`bars_minute.volume` existe) sigue pendiente y es la
mejora más barata que queda.

M1/M2/CLÁSICO/CONFIRMACIÓN se calculan y guardan en sus 4 tablas: **ninguno decide**.

---

## 3. SIN COMMITEAR — nada de hoy está subido

`git log -1` = `19fced4` (datos del 08-12). Modificados: `spy_direction.py`,
`coldruns/m1m2_coldrun.py`, `coldruns/media_coldrun.py`, `coldruns/tape_coldrun.py`.
**25/25 cold runs en verde** a las 10:17.

**Lo que se hizo hoy:**
- **Tape del SUBYACENTE** (`TAPE_SPY=True`): el SPY se suscribía sin RTVolume(233) — mismo bug
  que la banda el 08-12 — y `_read_price` cancelaba su suscripción. Ahora hay suscripción
  permanente y una rama **separada** en `_on_ticks()` que va ANTES del filtro y acaba en
  `continue`: el SPY NO toca `accum`/`net_call`/`net_put` (su premium es `last*dvol` SIN el
  ×100, y no tiene expiry/strike/right). Va con `grupo='SPY'`. Verificado en vivo: ~100
  filas/min, la señal sigue limpia.
- **La media decide y el ESTADO dispara el giro** (antes decidía la señal instantánea, que se
  apagaba dentro de la banda y dejaba el sistema FLAT).
- **Cold runs actualizadas** para que cada una fije la config que dice probar
  (`S.USAR_MEDIA`, `S.INVERTIR_SENAL`, `S.MINUTOS_POS`).

---

## 4. PROBLEMA DE EJECUCIÓN SIN RESOLVER

En la apertura hicieron falta **4 intentos y 96 segundos** para llenar la primera orden.
`REPRICE_SECS=4` cancela si el mid se mueve y el cooldown del GAP 19 bloquea 10 s → ~26 s por
intento. **Medir al cierre**: intentos por fill y segundos perdidos. No se tocó en caliente.

---

## 5. ⚠️ LA BD VA A ROMPER EL PUSH

`spy_history.db` pesa ya **73,9 MB** (ayer 53). GitHub avisa a partir de 50 y el **límite duro
son 100 MB**. Con el tape del SPY crece más rápido. **Puede fallar el push de HOY MISMO.**
Hay que decidir: Git LFS, comprimir, o dejar de versionarla y guardar solo backups locales.

---

## 6. QUÉ LEER, EN ESTE ORDEN

1. `investigacion/INVESTIGACION_MEDIA_CORTA.md` — todo lo probado el 08-12 con la prueba que
   mató cada línea. **8 líneas cerradas: no las re-propongas.**
2. `ANTI_COMPACT_CONTEXT.md`, bloque verde del 08-12 (arriba del todo).
3. `investigacion/INVESTIGACION_M1_M2.md` §3 y §5.

Ficheros de análisis generados hoy (raíz, no versionados): `TABLA_COMPLETA.txt`,
`acumulado_por_tramo.txt`, `metodos_M1_M2_CLASICO.txt`.

---

## 7. PROBADO HOY Y DESCARTADO — no repetir

El usuario propuso medir el **% de cambio del premium** (lo que entra ese minuto sobre el
acumulado previo) en los giros. **Cuatro variantes, las cuatro caen:**

| variante | resultado |
|---|---|
| en el instante del giro | acierta **1 de 4** |
| suma de todo el tramo | **3 de 6** (una moneda) |
| nivel acumulado al girar | rango **230x-358x** entre tramos: no existe un "nivel" |
| normalizado por punto recorrido | rango **11x-65x** |

Causa común: **el denominador se reinicia** con cada recentrado de banda (62 el 08-12, 0 el
08-11). Y el indicador mide un **sesgo del día**, no la dirección del tramo: el 08-11 ganan las
CALLS en los 3 tramos (incluso en las caídas) y el 08-12 las PUTS en los 3 (incluso en la
subida). Mientras el acumulado no sea continuo, cualquier métrica normalizada arrastra el fallo.

---

## 8. LO QUE SÍ APARECIÓ HOY — corrige una conclusión de ayer

Buscando movimientos **sostenidos** (>=20 min) en vez de oscilaciones salen **3-4 al día**, no
38. Y ahí **M1 acierta la dirección de 5 de los 7** de los dos días.

⚠️ Ayer se midió el lift de M1 a 5/10/15/30 min, salió ~0 y se concluyó que no predecía nada.
**Pero los movimientos que importan duran 69, 74, 130, 181 y 269 minutos**, y M1 cambia ~5 veces
al día con 20 min de retardo: **se medía un indicador LENTO contra un objetivo RÁPIDO**. En su
escala natural parece funcionar. Con n=7 es HIPÓTESIS, no resultado — pero es la línea más
prometedora que queda, y sugiere que M1 (dirección de fondo) y la media (entrada corta) podrían
ser **capas distintas**, no rivales.

Nota metodológica: el ZigZag por **amplitud** no sirve para esto — con umbral 0.90 salen CERO
giros en los dos días, y el 08-11 se queda en cero ya con 0.50 (cayó −2,73 sin rebotar medio
punto). Los movimientos hay que buscarlos por **duración sostenida**, no por tamaño.

---

## 9. METODOLOGÍA OBLIGATORIA (en este orden)

1. **TEST DEL CRONÓMETRO PRIMERO**: `|rho(variable, minuto del día)| >= 0.30` → muerta. Tres
   líneas; ha matado 28 variables y dos hipótesis que parecían sólidas.
2. **T2: quitar la mejor operación.** Si el resultado se da la vuelta, es una historia.
3. **Mirar el nº de OPERACIONES antes que el P&L.**
4. **Nula por desplazamiento circular, y mirar su MEDIANA** (si la nula ya gana, hay sesgo).
5. **Control de azar con la MISMA exposición** (300 semillas, un segundo).
6. **Leer la REGIÓN de la rejilla, nunca la celda máxima.**

Más las reglas del `CLAUDE.md`: corrida en frío diferencial con las **funciones reales** antes
de tocar producción, comparar **salidas completas** (nunca `grep FAIL`: la única coincidencia
legítima es la línea `FALLOS: 0` de m1m2), y nada por arreglado sin ejecutarlo.

**Cómo trabaja el usuario:** manda ideas en mensajes cortos y encadenados — júntalas antes de
actuar. Quiere resultados **en ficheros .txt**, no volcados por pantalla, y con las columnas
estables (no cambiar el formato en cada iteración). Habla en **dinero**, no en teoría. Si dice
"deja el sistema en paz", no comentes la operativa en vivo.

---

## 10. PENDIENTE, POR ORDEN

1. **La BD y el push** (punto 5) — puede bloquear todo lo demás.
2. **Commit + push** de lo de hoy (nada subido).
3. Al cierre: parar la app, medir el día con `razon_salida`, subir BD y log **con la app parada**.
4. Medir el problema de fills (punto 4).
5. Probar el **VWAP de verdad** frente a la SMA(5) actual.
6. `trades.mfe/mae` se corrompen con los reinicios → fuente de verdad: `posicion_minuto`.
