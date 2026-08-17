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

## ===== RESUELTO: día bueno + señales_apertura (motor VERDE +72.375, +1.4%) =====
## ===== PENDIENTE NUEVO (DECISIÓN DEL USUARIO): piramidar — medición del agente 2026-08-16 =====
opción                          AÑO1     AÑO2    TOTAL   rojos racha drawdown disparos
A · delta espuria (ACTUAL)    +31.569 +39.827 +71.396   140    4    -1.140    626
B · delta REAL del spread     +30.483 +32.145 +62.628   187    7    -2.897    817
C · sin piramidar             +16.741 +19.583 +36.325   188    7    -1.276      0

- B (delta real spread): -12.3% P&L, MÁS rojos, racha 7, drawdown 2.5x peor, dispara MÁS (817).
  => la delta del spread NO es la variable que importa.
- C (sin piramidar): mitad del sistema. Piramidar aporta ~49% del P&L incluso bien medido.
- A (espuria, actual): mejor P&L Y mejor perfil de riesgo (140 rojos/racha 4 vs 187/7).

RECOMENDACIÓN DEL AGENTE (honesta): NINGUNA de las 3 tal cual. Replantear piramidar antes del paper.
  A funciona "por accidente": la condición real = "el débito subió respecto al intrínseco de la
  larga" = "el extrínseco del spread se expande". Puede tener sentido económico pero no está
  validado como tal. Operar una regla que no se entiende = perder cuentas.
  PLAN (≈2 días): (1) formular la métrica explícita: (débito_actual − intrínseco_largo) −
  (débito_entrada − intrínseco_entrada) > umbral; validar con los 4 tests §2.1. (2) barrer el
  umbral (el +0.03 se ajustó sobre la delta espuria; el óptimo real está en otro sitio).
  (3) MIENTRAS TANTO para el paper: opción A tal cual, PERO marcada pendiente en el código +
  guardar `senales.piramidar_metrica` en la BD para auditarla en vivo.
  El agente se OFRECIÓ a correr AHORA el barrido de la métrica reformulada. => DECISIÓN DEL USUARIO.

## ===== RESUELTO: piramidar (agente, medición de la métrica reformulada, 2026-08-16) =====
El agente barrió la métrica reformulada (expansión del extrínseco) y NO reproduce:
  expansión >0.02: +65.434 (170 rojos, racha 6)  |  >0.05: +64.901  |  >0.10: +65.098
  => insensible al umbral => NO es lo que captura la "delta espuria".
CONCLUSIÓN (agente): la condición real NO es continua, es un FILTRO BINARIO DE ESTADO.
  iv() devuelve None cuando el débito < intrínseco de la pata larga (67% del tiempo), y ese
  None BLOQUEA piramidar y rodar. Piramidar solo actúa en el 33% de minutos donde el spread
  está en cierta config; ese filtro produce el perfil de 140 rojos / racha 4.
RECOMENDACIÓN FINAL: DEJAR OPCIÓN A tal cual (mi motor ya la reproduce, +72.375). Documentarla
  como filtro binario. Equivalente EXPLÍCITO sin BS (determinista, auditable en vivo):
     piramidar_permitido = pos['mid'] > max(0.0, (Sx-pos['k']) if rt=='C' else (pos['k']-Sx))
  Sugerencia: sustituir la inversión BS por esa comparación y verificar que reproduce los 626
  disparos. En paper: guardar en BD la métrica que dispara Y la delta real del spread.
  (El agente aclaró que su reco previa de reformular era prematura; la regla actual es mejor.)
=> DECISIÓN: piramidar se queda (A). Mejora opcional: comparación explícita (pendiente, no bloquea).
