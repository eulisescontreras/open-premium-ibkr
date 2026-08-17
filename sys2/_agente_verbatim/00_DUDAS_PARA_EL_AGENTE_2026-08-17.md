# DUDAS PARA EL AGENTE DUEÑO DEL ANÁLISIS — 2026-08-17
Surgidas en la **primera sesión en paper** del sistema `sys2/` (máquina `C:\Users\eulis`).
Cada duda va con la evidencia medida, para que se pueda responder sin adivinar.

---

## ✅ RESUELTAS SOLAS (1 y 2) — no hace falta preguntarlas, se dejan como registro
**Cuál `massive_premium.db` usar, y cuántos días opera el motor.** El repo trae dos archivos:

| | `massive_premium.db` (suelta, 62 MB) | `massive_premium.db.gz` (→ 344 MB) |
|---|---|---|
| `aggs` | 458.355 filas | **2.616.094 filas** |
| tickers distintos | 1.268 | **6.881** |
| contratos/día | mediana **3**, máx 4 | mediana **14**, máx 16 |
| `cr_motor` | **+4.517$** · 24 días operados (19V/5R) | **+72.375$** · 485 días (333V/**139R**) ✅ |

→ **La correcta es la del `.gz`.** Reproduce las 3 cifras al dólar (+72.375 / A1 +32.289 /
A2 +40.086 = exactamente lo que dice `ESTADO.md`) y los 139 rojos cuadran con el "140 rojos"
documentado. La `.db` suelta de 62 MB es **parcial** y con ella el motor casi no opera.
**Conclusión operativa: descomprimir el `.gz` sobre `massive_premium.db`.** Además queda claro
que la advertencia del cold run sobre "la completitud de contratos difiere entre máquinas" no era
ruido inevitable: era esta base parcial. Con la buena, el motor es determinista y portable.

---

## 3. ¿La descarga de contratos está terminada?
El commit `a0b44c7` dice "Premium REAL: **588 contratos descargados (46%)**" y existe
`massive_plan_contratos.json` con el plan. Incluso la base completa tiene **mediana 14
contratos/día**.
**¿Los +71.396$ se obtuvieron con esos 14/día, o requieren terminar el 54% restante?**

---

## 4. ⚠️ CRÍTICO — las 4 entradas de apertura NO se ejecutan en vivo
**Demostrado hoy con corrida en frío diferencial sobre datos reales:**
- `construir_sen` con el día completo → **3 señales**: 09:32 `pm_rev` C, 09:39 `v1` C, 09:46 `ayer_rev` C.
- `construir_sen` con datos ≤ minuto (como hace `paso()`) → **0 ejecutables**.
- Las 3 se hacen visibles a las **09:49** (+17 / +10 / +3 min): su hora ya pasó.

Causa: `entradas.py:70-72` no devuelve nada hasta tener **20 barras RTH** (~09:49), pero la hora
que devuelve es la barra que rompió el rango, **siempre anterior**; y `sistema.py:145` abre solo
si `hora in Sen` con `hora` = minuto **actual**. `pipeline.py` no aplica ningún desfase.
Afecta a **pm_rev, v1, gap_fade, ayer_rev** (4 de las 6 entradas). ORB y ST-3 sí funcionan.

Medido: los **513 días** del histórico tienen **30 barras** en 09:30-10:00, así que la guarda de
20 **nunca se activa en el backtest** (parece un filtro de completitud, no parte de la mecánica).

**¿La guarda de 20 es intencional? ¿Cómo se supone que se ejecutan estas 4 entradas en vivo:
se relaja la guarda al mínimo real de cada mecánica (pm_rev/ayer_rev=1, gap_fade=4, v1=5), se
acepta la señal con retraso al precio del momento, o hay otro mecanismo que no vimos?**

### 4-bis. Descarte cruzado con el ORB: no replicable en vivo
`pipeline.py:40` descarta una apertura si cae a <5 min de una señal del ORB. En el backtest eso
se evalúa conociendo todo el día; **en vivo, a las 09:32 el ORB de la ancla 09:40 aún no existe**,
así que el vivo TOMARÍA una operación que el backtest DESCARTA. **¿Cómo lo manejás?**

---

## 5. `dia_anterior`: ¿qué semántica manda? (riesgo de look-ahead)
Tres sitios, dos semánticas incompatibles:
- `schema.sql:21` + `migrar.py:96` → `fecha` = **la fecha cuyos** cierre/máx/mín se guardan.
- `backfill.py:68` → `fecha` = **HOY**, con los valores de **AYER**.
- `sistema.py:84` → lee `where fecha = HOY` (espera la de `backfill`).

Ambas conviven en la BD. **Peligro concreto:** re-correr `python -m sys2.db.migrar` (documentado
como regenerable) sobrescribe `dia_anterior[HOY]` con el máx/mín de **HOY** → el vivo los leería
como de ayer = **look-ahead** (trampa del MANUAL §2.3).
**¿Cuál es la correcta, y debería `derivar_dia_anterior` excluir la fecha en curso?**

---

## 6. ¿Cómo obtiene el motor el `prev` (máx/mín/cierre de ayer)?
Mis conteos de aperturas sobre 513 días: `pm_rev` **266**, `v1` **428**, `gap_fade` **447**,
`ayer_rev` **277**. `ESTADO.md:42` dice: pm **418**, gap **446**, v1 **459**, ayer **449**.
`gap_fade` casi cuadra (447 vs 446) pero `pm_rev` y `ayer_rev` se van mucho.
**¿De dónde saca el motor el día anterior de cada sesión?** Sospechamos que ahí está la diferencia.

---

## 7. `dia_anterior_spy()` devuelve ANTEAYER si se arranca en premarket
`ibkr.py:87` toma `bars[-2]` de las barras diarias. En premarket la serie **no incluye hoy**, así
que `[-1]`=ayer y `[-2]`=**anteayer**. Verificado hoy: los arranques de 08:53–09:05 cargaron
`max=779.37 min=774.11` (= jueves 13, anteayer) y el de 09:52 `max=778.80` (= viernes 14, correcto).
Afecta a `ayer_rev` y `gap_fade`. **¿Lo tenías identificado? ¿Fix preferido: elegir la última
barra diaria con `fecha < hoy` en vez de `[-2]` posicional?**

---

## 8. La tabla `senales` no se escribe nunca
`schema.sql:39` la define como "TODA senal generada, se opere o no" y `cr_schema.py:12` la valida,
pero **ningún módulo la escribe** (grep en todo `sys2/`: solo un `L.log(...,"SENAL")` en
`sistema.py:257` para el veto del ratio). Por eso el bug del punto 4 fue invisible: el log de hoy
tiene 0 errores y 0 órdenes, y parecía "no hubo señales" cuando hubo 3.
**¿Estaba previsto poblarla en el vivo? ¿Con qué columnas exactamente para que el backtest y el
vivo sean comparables?**

---

## Contexto de la sesión de hoy (para referencia)
- IB Gateway paper 4002, clientId 17. Conexión, backfill y captura: **impecables, 0 errores**.
- Cadena 0DTE real: **82 contratos/minuto**, bid/ask **100%** en strikes a ≤2 pts del spot,
  greeks reales de IBKR. (Contraste: el backtest tiene 3-14 contratos/**día**.)
- Autocalibración: con 200$ → tope 35$; con 400$ → 75$; con 600$ → 110$. Medido con la cadena
  real de hoy, el débito mínimo de un vertical de 2 pts oscila **73-99$**, así que con 400$ solo
  el **5,3%** de los minutos permitía abrir y con 600$ el **100%**. Operando hoy con 600$.
- Aún **NO VALIDADO** en paper: órdenes BAG, fills por pata, aplanado 15:50→15:55→plana <16:00
  (no hubo ninguna operación por el bug del punto 4).
