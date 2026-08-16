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
  `core/instrumento.py` (vertical/single) — construidos, verbatim del agente.

## 🔧 EN AJUSTE FINO — `backtest/motor.py` (SIS70)
Corre end-to-end (485 días). **cr_motor = +81.088$ vs target +71.396$ (+13.6% alto).**
Bloqueado esperando 2 piezas verbatim del agente (ver `_agente_verbatim/00_PENDIENTE_AGENTE.md`):
- [ ] **día bueno**: cómo aplica `nq` al cerrar (¿solo pata principal, o también extra/rodado?).
      Mío aporta +19.090 vs +6.433 documentado (sobre-doblo, probablemente, el extra de piramidar).
- [ ] **señales_apertura** verbatim (pm_rev/v1/gap_fade/ayer_rev). Mías son [DEC] → 1.115 pos vs 1.056.
- [ ] Re-correr cr_motor → debe dar ~+71.396$ (VERDE) + A1 +32.071 / A2 +38.698.
- [ ] Limpiar la instrumentación `STATS` de motor.py cuando quede verde.

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

## ⏳ FALTA — LADO VIVO / PAPER (Fase 0 resto + Fase 2) — NADA EMPEZADO
Todo el sistema en vivo con IBKR. Hasta ahora el trabajo fue backtest.
- [ ] `data/ibkr.py` — conexión ib_insync (clientId propio, NO 7/24/25), reqHistoricalData,
      **placeOrder combo BAG** (capacidad NUEVA, el bot viejo solo hacía single-leg) + fills por pata.
- [ ] `data/backfill.py` — premarket 04:00→arranque (`reqHistoricalData useRTH=False "2 D"`) +
      DIA/TLT 09:25-10:05 + dia_anterior → persiste en `bars`. + `cr_backfill` (≥390 barras, 0 huecos).
- [ ] `data/captura.py` — loop minuto a minuto (`keepUpToDate`) + cadena 8+ strikes/lado con
      **day_vol y greeks REALES de IBKR** (espejo backtest↔captura — requisito del usuario).
- [ ] `core/autocalibra.py` — `configuracion(cuenta)`: modo/ancho/tope/unidades, tope duro 3
      contratos, peor día ≤35% de la cuenta, solo al inicio de sesión. + cr_autocalibra (§13).
- [ ] `core/salida.py` — flip del ST-3 + **aplanar 15:50/15:53** + orden a mercado 15:55 +
      verificación explícita posición plana <16:00 (bloqueante de asignación §12).
- [ ] `vivo/sistema.py` — orquestador: arranque → backfill → captura → señales → reglas →
      ejecución → BD. Escribe TODA señal en `senales` (con grupo), operaciones, fills por pata.
- [ ] Cold runs de paper: `cr_pone_ordenes` (envía combo BAG, detecta fill de ambas patas),
      `cr_guarda_estadisticas` (todas las tablas pobladas), `cr_aplanado_asignacion` (15:50→mercado
      15:55→plana <16:00). Criterio: <5% fills parciales del vertical, si no → single.

## ⏳ FALTA — Fase 3 (real, capital mínimo)
- [ ] Autocalibración desde saldo real (arranque ~320$ operativos), regla de parada 12 días rojos.
- [ ] (Futuro) migración a XSP — revalidar las reglas.

## Notas
- `sys2.db` se regenera con `python -m sys2.db.migrar` (gitignored, NO commitear, 145MB).
- Los cold runs corren con `python -m sys2.cold_runs.<nombre>`.
- Verbatim del motor real del agente en `_agente_verbatim/` (persistido; el scratchpad muere con /clear).
