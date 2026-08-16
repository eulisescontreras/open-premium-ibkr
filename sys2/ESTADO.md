# ESTADO DE IMPLEMENTACIÓN — Sistema SPY 0DTE nuevo (sys2/)

> LEER ESTO PRIMERO al retomar, junto con el plan aprobado y los 2 PDFs.
> Última actualización: 2026-08-16.

## Documentos maestros (leer antes de tocar código)
1. `C:\Users\17862\Downloads\SISTEMA_VALIDADO_PREMIUM_REAL.pdf` (210 pág) — el sistema validado completo, con código exacto del ST-3, ORB, rebote.
2. `C:\Users\17862\Downloads\MANUAL_TRASPASO_AGENTE.pdf` (77 pág) — cómo construirlo, esquema BD (§4.1), 4 tests de validación (§2.1), 6 trampas de look-ahead (§2.3), autocalibración (§13), riesgo de asignación (§12).
   - Leer PDFs con: `python -c "import fitz,sys; sys.stdout.reconfigure(encoding='utf-8',errors='replace'); d=fitz.open(RUTA); [print(p.get_text()) for p in d]"` (fitz=PyMuPDF está instalado).
3. Plan aprobado: `C:\Users\17862\.claude\plans\c-users-17862-downloads-sistema-validado-velvet-manatee.md`

## Qué es el sistema (resumen)
SPY 0DTE, **verticales de débito de 4 puntos**. **6 entradas** (A ST-3, B ORB, C pm_rev, D gap_fade, E v1, F ayer_rev) + **5 reglas** (1 rebote con clasificación NORMAL/RETRASA/INVIERTE/DESCARTA, 2 descarte ST-1, 3 ratio call/put OTM, 4 skew sobre RETRASA, 5 día bueno→doblar) + rodado por delta. Salida: flip del ST-3. **Aplanar 15:50** (riesgo de asignación §12). Autocalibración por capital (tope 3 contratos). Validado **+71.396$/2 años**, ~+31.000$/año operable.

## ⚠️ DECISIONES CRÍTICAS DEL USUARIO (no violar)
- **Construir DESDE CERO** en `sys2/` (NO heredar el monolito `spy_direction.py` de 5.596 líneas, arrastra 3 bugs). Rescatar la data eso sí.
- **Trabajar en `main`** directo (el usuario lo pidió; no crear ramas).
- **FRONTERA DE DATOS:** el sistema EN VIVO obtiene TODO de **IBKR** (barras + cadena + greeks/IV reales). **Massive = SOLO histórico del backtest**, FUERA del sistema. La tabla `premium` de sys2.db se llena solo con IBKR (`fuente='live'`). Los greeks Black-Scholes van en el lado del BACKTEST, sobre massive, nunca en vivo.
- **PREMARKET (restricción del usuario):** el sistema NO puede estar activo desde las 4am. Al arrancar (a la hora que sea) hace DOS cosas: (1) **backfill de golpe** `reqHistoricalData(useRTH=False, "2 D")` = 04:00→arranque persistido en `bars`; (2) **keepUpToDate** minuto a minuto = arranque→cierre. Sin huecos. AMBAS son obligatorias.
- **Instrumento de arranque:** SPY + aplanado 15:50 (migrar a XSP más adelante).
- **Motor de backtest y vivo COMPARTEN núcleo** de reglas.
- Cada componente con su **cold run** verde antes de seguir (R23). Reutilizar funciones validadas (R9), NO duplicar.

## ⚠️ TRAMPA verificada: el código viejo tiene parámetros SUPERADOS
`analisis/orb_senal.py` = versión de premium SINTÉTICO (1 ancla 09:40, amplitud 0.75). El sistema validado (premium real) usa **2 anclas (09:40, 11:00) y 0.40** (PDF §10.4, §20). NO copiar el código viejo como si fuera el sistema. El sistema real está en los PDFs.

## Reutilizables verificados (file:line)
- `analisis/year_backtest.py:27 st_dir(hi,lo,cl,per=7,mult=3.0)` — Supertrend (ya copiado limpio a sys2/core/supertrend.py).
- `analisis/backtest_st3_orb.py:65 sen_principal(bars)` — ST-3 completo (referencia de equivalencia).
- `analisis/orb_senal.py:40 orb_senal(bars,rango_min)` — mecánica ORB (params viejos).
- `analisis/simulador_st.py:151 simular(...)` — motor de simulación (1 pata ITM al ASK; el nuevo necesita verticales).
- `analisis/synth_premium.py:33 calibra / :51 extr / spy_min` — premium sintético (para comparar).
- `analisis/exp_timing_realista.py:31 shift_sen`, `exp_st_flip.py:32 sen_Nmin`.
- Patrón cold run: `coldruns/st3_signal_coldrun.py`.
- Bot vivo (referencia, NO heredar): `spy_direction.py` (ib_insync, clientId 7, órdenes single-leg LimitOrder al MID, NO combos; `_st3_dir` 3046, `_orb_check` 2945).

## HECHO Y VERDE (cold runs pasan)
- `sys2/db/schema.sql` — esquema completo (MANUAL §4.1) + fuente/nivel/tape_und/premium_mix.
- `sys2/db/repo.py` — abrir (aplica schema), insertar OR REPLACE idempotente.
- `sys2/db/migrar.py` — CORRIDO. Migró: `bars` 2 años 1-min continuos (2024-07-31→2026-08-13, **158.483 barras premarket**), `bars_etf` (DIA+TLT), `dia_anterior` (511), `operaciones` (41), `premium` live (los 4 días IBKR reales). `sys2.db` regenerable con `python -m sys2.db.migrar` (está en .gitignore, NO commitear).
- `sys2/core/supertrend.py` — st_dir + buckets3 + flips_st3. **cr_supertrend VERDE**: idéntico a year_backtest.st_dir y sen_principal en 21 días reales.
- `sys2/core/entradas.py` — 6 entradas (A ST-3, B ORB §10.4, C pm_rev, D gap_fade, E v1, F ayer_rev) + descartar_cerca_orb. Bug `ap = next(...)` en gap_fade ELIMINADO. **cr_entradas VERDE**: ORB == orb_senal(0.75/ancla 09:40) EXACTO en **511/511 días** (0 difs, 0 excepciones); cada señal cumple su mecánica (reversión pm/v1/ayer/orb, fade en gap) contra barras reales; las 4 aperturas disparan (pm 418, gap 446, v1 459, ayer 449 días); descarte <5min del ORB respetado. Aportes [DEC] al P&L los juzgará el motor de backtest.
- `sys2/backtest/greeks.py` — Black-Scholes-Merton (math.erf, sin scipy) SOLO backtest. `parse_occ` (ticker OCC→expiry/right/strike), `t_years` (zoneinfo ET, no offset fijo §2.3), `bs_price`, `implied_vol` (bisección, suelo intrínseco §2.3), `greeks`, `desde_precio`. **Invierte el precio REAL de massive→IV→greeks (preserva la sonrisa); NUNCA fija precios** (§57: BS-IV-plana=60% error). **cr_greeks_bs VERDE** (muestra [::12]=41 días/2208 obs + verificación global 485 días): round-trip 1e-6, delta analítica=fin-dif 2e-5, 0 fuera de rango, 0 paridad (invariante a misma sigma `|dC|+|dP|=e^{-qT}`), delta comprables p5 0.518/mediana 0.710/p95 0.936 ≈ H3. Banda IV realista `0.005<iv<5.0` (0DTE va de ~1% ATM barato a >300% deep-ITM día crash como 2025-04-09; la banda vieja `[0.02,3.0]` daba 8 falsos rojos, greeks correctos). r=0.045 q=0.013 (constantes backtest; irán a config.py). Insight: las diferencias de IV call/put del mismo strike SON la sonrisa (skew), no un error.
- `sys2/core/rebote.py` — REGLA 1 (rebote, +33k). Transcripción **VERBATIM** del código real del sistema validado (`st_lin_p` + `sen_p` + `reb2` + clasificación), obtenida del agente dueño del análisis (claude.ai, 2026-08-16) porque el **PDF §10.5 estaba DESACTUALIZADO** (ventana 8 vs 12, cierre vs mecha). **cr_rebote VERDE — MATCH EXACTO bit a bit**: 1.411 flips, 479 días, grupos 675/393/243/100, split A1/A2 y falsos% TODOS idénticos al validado. ⚠️ Usa su PROPIA ST (`st_lin_p`), distinta de `st_dir` (ATR corrida desde i=0, d=-1 init, prev en premarket) → **la ST base del sistema validado (premium real) es `st_lin_p`, NO `st_dir`** (que era del backtest SINTÉTICO superado).
- Cold runs verdes: `cr_schema.py`, `cr_migracion.py`, `cr_supertrend.py`, `cr_entradas.py`, `cr_greeks_bs.py`, `cr_rebote.py`.

## ⚠️ PENDIENTES DE RECONCILIACIÓN (hallazgos del agente, verificar con evidencia antes de tocar)
1. **ST base**: entrada A (ST-3) y `core/supertrend.py`/`flips_st3` usan `st_dir` (backtest SINTÉTICO). El sistema validado usa `st_lin_p/sen_p`. Reconciliar entrada A a `sen_p` cuando se arme el motor (comparar flips sen_p vs flips_st3; probable que difieran en el primer flip RTH).
2. **entradas.py descarte**: el real descarta aperturas a ≤5 min de **TODAS** las señales ya en `S` (no solo ORB), orden de llenado ORB→pm_rev→**v1→gap_fade**→ayer_rev (v1 antes que gap_fade), umbral `>5` (descarta en =5). Ajustar al armar la unión de señales del motor.
3. **greeks.py**: el motor validado usa T=`max(1e-6,(960-mm(h))/(60*24*252))` (año 252 días) y **clampea** el precio al suelo intrínseco `max(precio,intrínseco)` antes de invertir (yo uso 365 y devuelvo None sub-intrínseco). Ajustar en el motor/greeks para reproducir cifras (corrección B_suelo, +70.769$).

Nota: `reb2` etc. transcritos verbatim del agente (otra máquina, `C:\Users\eulis\proyectos\open-premium-ibkr`); scratchpad `rebote_agente_verificado.md` guarda el código y la revisión.

## ⚠️ REQUISITO DURO (orden usuario 2026-08-16): espejo backtest↔captura
El backtest corre sobre massive (con greeks BS), PERO `captura.py` (vivo, IBKR) DEBE guardar
en `premium` EXACTAMENTE los mismos campos con que se validó el backtest: bid/ask/mid/last,
day_vol, open_interest, iv/delta/gamma/theta/vega (reales de IBKR), 8+ strikes/lado. Hoy los
4 días `live` tienen greeks NULL → captura.py los llenará y ahí cr_greeks_bs comparará BS vs real.

## WIP SIN VALIDAR (arreglar al retomar)
- (vacío — entradas.py y greeks.py validados; siguiente es el ROADMAP)

## ROADMAP (build por fases, lo que falta)
- **Fase 0 resto:** `sys2/backtest/greeks.py` (Black-Scholes + IV, sobre massive, solo backtest); `sys2/data/backfill.py` + `captura.py` (IBKR; se prueban en paper); cold runs cr_backfill.
- **Fase 1:** validar entradas (cr_entradas); `core/rebote.py` (REGLA 1: toque a la línea con la MECHA, ventana 12 buckets, clasifica 4 grupos — código exacto PDF §10.5/§21); `core/st1.py` (REGLA 2); `core/reglas.py` (REGLA 3 ratio, 4 skew, 5 día bueno + rodado); `core/instrumento.py` (vertical 4pts + single fallback); `core/autocalibra.py` (§13.1-bis); `core/salida.py` (flip + aplanado 15:50). Luego `backtest/motor.py` (corre las 6 entradas + 5 reglas + verticales sobre massive con greeks BS) + `backtest/validacion.py` (4 tests). Cold run CLAVE: `cr_backtest_cifras.py` debe reproducir **+71.396$/2 años** ± tolerancia y los aportes por regla. `cr_nucleo_equivale.py` (vivo↔backtest señal a señal). `cr_flips_grupos.py` (675/393/243/100).
- **Fase 2 (paper):** `data/ibkr.py` órdenes **combinadas BAG** (capacidad nueva, el bot viejo no la tiene) + `fills` por pata. cr_pone_ordenes, cr_guarda_estadisticas, cr_aplanado_asignacion. Si >5% fills parciales → single.
- **Fase 3 (real):** autocalibración desde saldo real, parada 12 días rojos.

## Cosas EN PARALELO (mueren con el /clear — re-armar si hace falta)
- Descargas: **massive 1DTE** (`analisis/massive_premium_real.py estado 1dte`, ~14% al momento) y **tape del subyacente** (`analisis/descarga_tape_und.py estado`, 42/137 días). Ambas resumibles. Supervisor idempotente en `C:\Users\17862\massive_auto\` + Scheduled Task `MassiveAutoResume` (cada 15 min, reanuda tras reboot). Estas son de DATOS históricos, NO del sistema sys2.
- IB Gateway paper puerto 4002 se cayó una vez (~3h45m); si el tape no avanza, reabrir IB Gateway paper.

## Reglas de trabajo (CLAUDE.md 1-23, las más relevantes aquí)
R2 honestidad total · R3 cold run real (nunca scripts aislados) · R8 diferencial · R9 conectar no duplicar · R13 no inventar (marcar [DEC] y validar) · R23 espejo prod↔cold run · <1000 líneas/archivo · commits frecuentes --no-verify · NUNCA push sin autorización.
