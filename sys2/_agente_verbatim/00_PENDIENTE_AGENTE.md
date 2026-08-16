# PENDIENTE — preguntas al agente dueño del análisis (motor real)

Agente: conversación claude.ai `https://claude.ai/chat/de266178-0585-4f6a-8a6a-53c75012b935`
(máquina del agente: `C:\Users\eulis\proyectos\open-premium-ibkr`, archivos `reopt25.py`,
`diabueno3.py`, `g2v.py`, `prem100`, etc.). El agente SE CAYÓ el 2026-08-16 tras varias
consultas seguidas (error "Authentication service was unavailable"). Reintentar cuando vuelva.

## ESTADO del motor al momento de preguntar
- `cr_motor` da **+81.088$** (target +71.396$, +13.6% alto).
- Residual AISLADO al **día bueno**: mi base sin día bueno +61.998 (≈ agente +64.963); pero
  día bueno me aporta **+19.090 en vez de +6.433** (3x), sobre los MISMOS 58 días.
- El fix del `continue` incondicional (ya aplicado) bajó de +97.762 a +81.088.

## LA PREGUNTA PENDIENTE (texto exacto que le mandé, quedó sin responder):
> Enorme, el fix del continue me bajó de +97.762 a +81.088. Diagnostiqué el resto y aislé el
> problema al DÍA BUENO: mi base sin día bueno da +61.998 (vs tu +64.963, cerca) pero día bueno
> me aporta +19.090 en vez de +6.433 (3x), sobre los MISMOS 58 días. No quiero tunear a ojo
> para pegarle al número, así que necesito el código VERBATIM (texto plano) de dos cosas de
> diabueno3.py:
> (1) el CIERRE de posición con día bueno: cómo se aplica exactamente nq al cerrar — ¿solo a la
>     pata principal g, o también al contrato EXTRA de piramidar y al cierre por RODADO? Pegame
>     las líneas exactas del 'if gira or h>=aplanado' y del 'elif rodar' en la versión con día
>     bueno (yo ahora hago tot += (main+extra)*nq y el rodado sin nq; sospecho que sobre-doblo
>     el extra).
> (2) señales_apertura(bars,ph,pl,pc,ex) VERBATIM (las 4: pm_rev, v1, gap_fade, ayer_rev) — mis
>     versiones son [DEC] reconstruidas y abro 1.115 posiciones vs tus 1.056, esos 59 de
>     diferencia y el -4.6% del base vienen de ahí.

## QUÉ FALTA para cerrar el motor exacto (+71.396$)
1. **día bueno** (bug gordo, +12.6k de exceso): código verbatim del cierre con `nq` en
   diabueno3.py — determinar si nq multiplica solo la pata principal o también extra/rodado.
   HIPÓTESIS (a validar con verbatim, NO tunear): sobre-doblo el contrato extra de piramidar.
2. **señales_apertura** verbatim (base -4.6%, 1115 vs 1056 posiciones): las 4 aperturas reales
   (mis `core/entradas.py` pm_rev/gap_fade/v1/ayer_rev son [DEC] reconstruidas).

Con esas dos → re-correr `cr_motor` → debe dar ~+71.396$ (VERDE).

## DESPUÉS (ROADMAP restante, ver ESTADO.md)
- Marcar **piramidar como PENDIENTE DE REVISIÓN**: su +56% del P&L se apoya en un delta ESPURIO
  (invierte el débito del vertical como single en el strike largo; dl=None 67% del tiempo).
  Antes del paper: calcular delta real del spread (delta_larga − delta_corta) y re-medir, o
  eliminar. El agente ofreció medir "cuánto da con la delta correcta del vertical" — PEDÍRSELO.
- `backtest/validacion.py` (4 tests §2.1), `core/autocalibra.py`, `core/salida.py`.
- Fase 2 (paper): `data/ibkr.py` órdenes combinadas BAG + fills por pata; `data/captura.py`
  (debe guardar los MISMOS campos que el backtest: greeks reales IBKR, day_vol, 8+ strikes/lado).
- Limpiar la instrumentación STATS de `backtest/motor.py` cuando el motor quede verde.
