# PENDIENTES — Sistema SPY 0DTE (sys2/)

> Estado a 2026-08-16. Fuente de verdad del roadmap. Leer junto con `ESTADO.md`,
> `_agente_verbatim/00_PENDIENTE_AGENTE.md` y el plan (`_docs/plan_aprobado.md`).

## ✅ HECHO Y VERDE (cold run pasa)
- `db/schema.sql` + `db/repo.py` + `db/migrar.py` — cr_schema, cr_migracion.
- `core/supertrend.py` — cr_supertrend (idéntico al backtest validado).
- `core/entradas.py` (6 entradas: ST-3, ORB, pm_rev, gap_fade, v1, ayer_rev) — cr_entradas
  (ORB == orb_senal exacto 511/511 días).
- `backtest/greeks.py` (Black-Scholes, solo backtest) — cr_greeks_bs (round-trip 1e-6, 485 días).
- `core/rebote.py` (REGLA 1) — **cr_rebote MATCH EXACTO bit a bit** (1.411 flips, 675/393/243/100).
- `config.py` + `core/st1.py` (descarte ST-1) + `core/reglas.py` (ratio/skew/día bueno) +
  `core/instrumento.py` (vertical/single) — verbatim del agente.
- **`vivo/sistema.py` persistencia de FILLS por pata** (`_persistir_fills`) — vertical Y single —
  **cr_fills VERDE**: lleno (2 patas) / parcial (1 pata → parcial=1 + alerta) / single / trade=None.
  Ejercita el chain REAL `_abrir`→`ib.comprar_*`→`_persistir_operacion`→`_persistir_fills`.
- **`backtest/motor.py` (SIS70)** — **cr_motor VERDE**: TOTAL **+72.375$ (+1.4%)** vs +71.396;
  A1 +0.7%, A2 +3.6% (tol. titular 2%, año 5% por completitud de datos massive). Reproduce el
  sistema validado. Fixes clave: continue incondicional, día bueno nq (solo principal+rodado),
  señales_apertura verbatim (aperturas solo 09:30-10:00).

## ✅ RESUELTO Y CERTIFICADO (2026-08-17) — el parche de la guarda de las aperturas
`entradas.py senales_apertura`: la guarda fija `len(rth) < 20` se sustituyó por el mínimo real de
cada mecánica → `{'pm_rev':1, 'ayer_rev':1, 'gap_fade':4, 'v1':5}.get(modo, 20)`.
**Confirmado por el agente dueño del análisis** (era un filtro de completitud del histórico, no
parte de la mecánica) y **certificado con corridas reales**:
- diferencial de `senales_apertura` sobre **513 días**: **0 diferencias**.
- `cr_motor` (con la massive COMPLETA) **antes y después**: **+72.375$ / A1 +32.289 / A2 +40.086
  / 485 días / 333V-139R — IDÉNTICO** en las 3 corridas.
- `cr_entradas`: VERDE. Ejecutabilidad con datos reales de hoy: **0 → 3 señales, desfase +0 min**.
⚠️ Aplicado en disco; **el sistema en marcha sigue con el código viejo** (módulos en `sys.modules`,
no hay `importlib.reload`): toma efecto en el próximo reinicio.

## ⚠️ DATO SOBRE LA BASE DE DATOS DEL BACKTEST (2026-08-17)
`massive_premium.db` suelta (62 MB) es **PARCIAL**: 1.268 contratos, mediana **3/día** → `cr_motor`
da **+4.517$** y solo 24 días operados de 485. La buena es **`massive_premium.db.gz`** (→344 MB):
6.881 contratos, mediana **14/día** → **+72.375$**. `motor.py:29` apunta a la suelta.
**Hay que descomprimir el `.gz` sobre `massive_premium.db`.** El agente lo confirma: la suelta es
un residuo de una descarga al 20%, y es la trampa C del MANUAL §2.3 (menú de contratos).
Descarga real: 6.881 de 6.945 = **99,1%** (el "46%" del commit es de una fase intermedia).

## ⚠️ CIFRAS NO CONFIABLES EN `ESTADO.md`
`ESTADO.md:42` dice que las aperturas disparan "pm 418, gap 446, v1 459, ayer 449". El agente
dueño del análisis **NO reconoce esos números**. Los medidos con el motor real son
**pm_rev 265-266 · v1 427-428 · gap_fade 446-447 · ayer_rev 292-293**. No usar `ESTADO.md` como
fuente de verdad numérica (R1: verificar contra código, nunca contra docs).

## 🔴 CRÍTICO (hallazgo 2026-08-17, primera sesión en paper) — 4 de las 6 entradas NO se ejecutan en vivo
**DEMOSTRADO por corrida en frío diferencial con la función real y datos reales de hoy.**
Fallo **SILENCIOSO**: 0 ERROR / 0 WARN en 181 líneas de log, captura de 82 contratos/minuto
impecable… y **ninguna operación**. Parece "no hubo señales" y en realidad hubo 3.
- A) `construir_sen` con TODO el día → **3 señales**: 09:32 pm_rev C, 09:39 v1 C, 09:46 ayer_rev C.
- B) `construir_sen` con datos ≤ minuto (como `paso()`) → **0 ejecutables**.
- C) desfase: 09:32 visible a las 09:49 (**+17 min**), 09:39 → 09:49 (+10), 09:46 → 09:49 (+3).
**Causa raíz (código puro):** `entradas.py:70-72` no devuelve nada hasta tener 20 barras RTH
(~09:49) pero la hora que devuelve es la barra que rompió el rango, **siempre anterior**;
`sistema.py:145` abre solo si `hora in Sen` con `hora` = minuto ACTUAL; `pipeline.py` NO aplica
ningún shift; `salida.py:39 puede_abrir()` no rescata señales pasadas.
**Alcance:** pm_rev, v1, gap_fade, ayer_rev inejecutables. SÍ funcionan ORB y ST-3.
**Impacto estimado (NO verificado, cifras del docstring `entradas.py:14`):** ~28.800$ de
+72.375$ ≈ **40% del P&L**. Opciones: (1) ventana de tolerancia para señales recién pasadas
—cambia el precio de entrada, hay que medirlo—; (2) reformular las aperturas para decidir con
la barra en curso —cambia la señal, revalidar motor—; (3) asumir que en vivo solo operan
ORB+ST-3 y recalcular la expectativa. Decidir con el usuario (R11), validar con R3/R8.

## 🔧 PENDIENTE INMEDIATO
- [ ] **Limpiar la instrumentación `STATS`** de `backtest/motor.py` (diagnóstico temporal).
- [ ] **`vivo/sistema.py` NO persiste la tabla `senales`** (hallazgo 2026-08-17, VERIFICADO por grep):
      `schema.sql:39` la define como "TODA senal generada, se opere o no" y `cr_schema.py:12` la
      valida, pero **nadie la escribe**. El único rastro en vivo es `L.log(...,"SENAL")` cuando
      `ratio_otm` veta una apertura (`sistema.py:257`). Consecuencia: si una sesión no operó, no
      queda registro auditable de qué señales hubo ni por qué se descartaron.
      - Implementar: en `paso()`, tras `pipeline.construir_sen()`, insertar en `senales` con
        `repo.insertar` (reutilizar, no duplicar). Es lógica que corre EN VIVO → cuidar el radio.
      - Reconstruir sesiones pasadas: ⚠️ **NO se puede desde el log** (no las contiene). La vía
        fiel es correr la función real `pipeline.construir_sen()` sobre lo que sí quedó en
        `sys2.db` (`bars` con premarket + `premium` con la cadena real minuto a minuto).
      - Exige corrida en frío real + diferencial (R3/R8): el motor debe seguir dando +72.375$.
- [ ] **BUG `dia_anterior_spy()` trae ANTEAYER en premarket** (2026-08-17, VERIFICADO con datos):
      `ibkr.py:87` toma `bars[-2]` de las barras diarias. En premarket la serie NO incluye hoy →
      `[-1]`=ayer y `[-2]`=**anteayer**. Con mercado abierto `[-1]`=hoy(parcial) y `[-2]`=ayer (ok).
      EVIDENCIA: arranque 08:53 cargó max=779.37/min=774.11 = jueves 13 (anteayer); arranque 09:52
      cargó max=778.80 = viernes 14 (correcto). **Afecta `ayer_rev` y `gap_fade`** (2 de las 6
      entradas). Fix: elegir la última barra diaria con `fecha < hoy`, no `[-2]` posicional.
- [ ] **`dia_anterior` tiene DOS semánticas contradictorias → riesgo de LOOK-AHEAD**:
      `schema.sql:21` y `migrar.py:96` = "fecha es la fecha cuyos datos se guardan";
      `backfill.py:68` = "fecha es HOY con los valores de AYER"; `sistema.py:84` lee `fecha=HOY`
      (espera la de backfill). Ambas conviven en la BD.
      ⚠️ **PELIGRO: re-correr `python -m sys2.db.migrar`** (documentado como regenerable)
      sobrescribe `dia_anterior[HOY]` con el max/min de HOY → el vivo los lee como de AYER =
      look-ahead (trampa del MANUAL §2.3). Unificar semántica + guard en `derivar_dia_anterior`
      para no escribir la fecha en curso. Cubrir con `cr_lookahead.py`.

## ⚠️ DECISIÓN ANTES DEL PAPER — piramidar
Hallazgo del agente (VERIFICADO): piramidar aporta el **+56% del P&L** apoyado en un **delta
ESPURIO** (invierte el débito del vertical como single en el strike largo; `dl=None` el 67% del
tiempo). Artefacto de implementación, no mecanismo económico. El backtest es válido (precios
reales, P&L bien contabilizado) pero la cifra depende fuerte de una condición arbitraria.
- [ ] Pedir al agente: medir el sistema con la **delta real del spread** (delta_larga − delta_corta).
- [ ] Decidir con el usuario: recalcular delta real y re-medir, o **eliminar piramidar**.

## ⏳ FALTA — BACKTEST / validación (Fase 1)
- [ ] `backtest/validacion.py` — los **4 tests del §2.1** (bloques temporales / T2 / permutación
      no-solapada / % de días positivos). MANUAL §2.1 / §5-6.
- [ ] `cold_runs/cr_lookahead.py` — guardas contra las 6 trampas de look-ahead (§2.3):
      pos=None sin contabilizar, resultado con otro nombre, menú de contratos, desfase horario
      fijo (usar zoneinfo), extrínseco negativo (suelo intrínseco), contrato que deja de cotizar.
- [ ] `cold_runs/cr_nucleo_equivale.py` — el motor en vivo replica señal a señal al de backtest
      sobre los mismos días (diferencial, R8). (Requiere el lado vivo.)
- [ ] `cold_runs/cr_flips_grupos.py` — ya cubierto por cr_rebote (675/393/243/100); formalizar si hace falta.

## ✅ LADO VIVO / PAPER — CONSTRUIDO (validar en paper mañana)
Todo el sistema en vivo con IBKR, TODO ACTIVO. Núcleo COMPARTIDO con el backtest (`core/pipeline`,
verificado: el motor sigue +72.375 tras usarlo). Grafo de decisión validado con smoke sobre día real
(2025-04-09): 0 crashes, abre verticales, gestiona piramidar/rodar, cierra por flip/aplanado, plana al final.
- ✅ `data/ibkr.py` — ib_insync (clientId 17, puerto 4002 paper), backfill, cadena con greeks reales,
      **órdenes combinadas BAG** (vertical) + single + cierres.
- ✅ `data/backfill.py` — premarket SPY (useRTH=False "2 D") + DIA/TLT + día anterior → `bars`/`bars_etf`/`dia_anterior`.
- ✅ `data/captura.py` — barra minuto a minuto + cadena 8+ strikes/lado con day_vol + greeks reales → `premium` (fuente='live').
- ✅ `core/autocalibra.py` — configuracion(saldo) tabla §13.1, tope 3 · **cr_autocalibra VERDE**.
- ✅ `core/salida.py` — flip + aplanar 15:50 + mercado 15:55 + verif plana <16:00 · **cr_salida VERDE**.
- ✅ `core/pipeline.py` — Sen compartido (backtest+vivo), única fuente de verdad.
- ✅ `vivo/sistema.py` — orquestador (arranque→backfill→captura→señales→reglas→ejecución→BD), logs exhaustivos.
      Fills por pata persistidos en apertura de vertical y single (cr_fills). ⚠️ PENDIENTE menor: los
      singles de **piramidar/rodar** NO persisten fills (no tienen fila `operaciones` a la que colgarlos;
      requeriría guardar op_id en `pos` — cambio mayor, fuera de radio). No bloqueante para mañana.
- ✅ `vivo/log.py` — logging exhaustivo (archivo diario) + notificaciones (sin dashboard).
- ✅ `iniciar.sh` (toggle arranca/apaga) + `subir.sh` (push a git). Ejecutables.
- [ ] **MAÑANA en paper** (lo único que falta, requiere mercado + IB Gateway 4002): validar conexión,
      backfill real (≥390 barras 0 huecos), captura con greeks reales, órdenes BAG (fills de ambas patas,
      <5% parciales si no → single), aplanado 15:50→mercado 15:55→plana <16:00. Buscar los "cabos sueltos"
      de integración (gates, auth, multi-thread) que el smoke NO revela.
      NOTA: que ib_insync reporte los fills POR PATA está CONFIRMADO contra su source (Trade.filled: el
      combo trae un Fill 'BAG' agregado + un Fill por pata; `_persistir_fills` salta el BAG). La incógnita
      de mañana se reduce a si ambas patas efectivamente SE LLENAN (liquidez), no a cómo se reportan.

## ⏳ FALTA — Fase 3 (real, capital mínimo)
- [ ] Autocalibración desde saldo real (arranque ~320$ operativos), regla de parada 12 días rojos.
- [ ] (Futuro) migración a XSP — revalidar las reglas.

## Notas
- `sys2.db` se regenera con `python -m sys2.db.migrar` (gitignored, NO commitear, 145MB).
- Los cold runs corren con `python -m sys2.cold_runs.<nombre>`.
- Verbatim del motor real del agente en `_agente_verbatim/` (persistido; el scratchpad muere con /clear).
