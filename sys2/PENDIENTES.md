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
- **`backtest/motor.py` (SIS70)** — **cr_motor VERDE**: TOTAL **+72.375$ (+1.4%)** vs +71.396;
  A1 +0.7%, A2 +3.6% (tol. titular 2%, año 5% por completitud de datos massive). Reproduce el
  sistema validado. Fixes clave: continue incondicional, día bueno nq (solo principal+rodado),
  señales_apertura verbatim (aperturas solo 09:30-10:00).

## 🔧 PENDIENTE INMEDIATO
- [ ] **Limpiar la instrumentación `STATS`** de `backtest/motor.py` (diagnóstico temporal).

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
- ✅ `vivo/log.py` — logging exhaustivo (archivo diario) + notificaciones (sin dashboard).
- ✅ `iniciar.sh` (toggle arranca/apaga) + `subir.sh` (push a git). Ejecutables.
- [ ] **MAÑANA en paper** (lo único que falta, requiere mercado + IB Gateway 4002): validar conexión,
      backfill real (≥390 barras 0 huecos), captura con greeks reales, órdenes BAG (fills de ambas patas,
      <5% parciales si no → single), aplanado 15:50→mercado 15:55→plana <16:00. Buscar los "cabos sueltos"
      de integración (gates, auth, multi-thread) que el smoke NO revela.

## ⏳ FALTA — Fase 3 (real, capital mínimo)
- [ ] Autocalibración desde saldo real (arranque ~320$ operativos), regla de parada 12 días rojos.
- [ ] (Futuro) migración a XSP — revalidar las reglas.

## Notas
- `sys2.db` se regenera con `python -m sys2.db.migrar` (gitignored, NO commitear, 145MB).
- Los cold runs corren con `python -m sys2.cold_runs.<nombre>`.
- Verbatim del motor real del agente en `_agente_verbatim/` (persistido; el scratchpad muere con /clear).
