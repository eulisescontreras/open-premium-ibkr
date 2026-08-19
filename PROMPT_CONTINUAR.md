# PROMPT PARA RETOMAR (pegar tal cual tras /clear)

Trabajamos en `C:\Users\eulis\proyectos\open-premium-ibkr` (sistema SPY 0DTE, carpeta `sys2/`).

**LEE PRIMERO, EN ESTE ORDEN:**
1. `ANTI_COMPACT_CONTEXT.md` — las secciones del **2026-08-18 y 2026-08-19** (están al principio,
   marcadas 🔴/🟢). Ahí está TODO lo medido, lo arreglado y lo descartado, con las cifras.
2. `sys2/PENDIENTES.md` y `sys2/ESTADO.md` si necesitas contexto del sistema.

**REGLAS:** las 16 de `CLAUDE.md` (verificar contra código puro, corrida en frío con la función
real, separar VERIFICADO/HIPÓTESIS, conectar-no-duplicar, minimizar radio de cambio).
Todo cambio pasa por **los 12 cold runs** (`sys2/cold_runs/`) antes de darse por bueno.

---

## ESTADO EN UNA FRASE

El sistema funciona y está validado (12/12 cold runs, motor +72.497$), pero se descubrió que
**el backtest ve el futuro** al clasificar los giros del ST-3: el rendimiento realista en vivo es
**~+36.500$/2 años con drawdown -3.500$**, no +71.396$ con -1.140$.

## LO QUE ESTÁ HECHO (13 fixes aplicados, subidos y validados)

Cierre garantizado con verificación contra IBKR (`ibkr.cerrar_todo`: BAG al mid -> patas al mid,
cortas primero -> patas a mercado), sincronización periódica IBKR↔`self.pos`, recuperación de
posición al arrancar, valoración de la pirámide, P&L con fills reales, margen +1$ sobre el tope,
fix del flotante, reintento del backfill ETF, recalibración intradía, persistencia de pirámide/
`senal_id`/`iv_entrada`, panel con cambio en $ y todas las patas.

## 🟢 EL HALLAZGO GRANDE (2026-08-19) — YA MEDIDO, FALTA APLICARLO

**Idea del usuario mirando el gráfico:** *"veo clarísimo cómo las velas se van acercando al
soporte/resistencia del ST — no hace falta saber el futuro"*. Es la señal más fuerte encontrada.

**REGLA:** tras un flip del ST-3, mirar las **k velas siguientes** (ya formadas, NO es look-ahead).
Si la mecha del lado de la línea se acerca a **<= U ATR**, el flip es sospechoso -> **no entrar**.

**MEDIDO sobre las 485 sesiones (base = `ap_base`, el sistema REAL con visión honesta):**
```
variante          TOTAL     vs VIVO    verdes rojos RACHA drawdown   T1      p      PASA
VIVO (sin filtro) +35.878      +0        273   202    5    -3.779     --      --     --
ENT k3 u1.0       +43.631   +7.754       291   181    5    -2.268   OK 4/4  0.000    SI
ENT k4 u1.0       +49.309  +13.431       298   172    4    -1.755   OK 4/4  0.000    SI
ENT k4 u1.5       +53.355  +17.477       303   162    5    -1.825   OK 4/4  0.002    SI  <-- mejor
```
- **+17.477$**: recupera MÁS DE LA MITAD de los -28.864$ de la brecha.
- **Pasa los 4 tests §2.1**, T1 **4/4** (mejora en los 4 bloques cronológicos), p=0.000-0.002.
- **Aporta en LOS DOS años** (A1 +10.298 / A2 +7.179), no depende de un período.
- **Drawdown a menos de la mitad**: -3.779 -> -1.825. Rojos 202->162, verdes 273->303.
- **u1.5 (acercarse) SUPERA a u1.0 (tocar)**: no hay que esperar al toque, la aproximación YA
  es la señal — exactamente lo que decía el usuario.

Evidencia previa (`scratchpad/test_aprox_post.py`, 1552 flips): con k=4, el que toca la línea es
falso el **49.1%** (n=269) vs **21.4%** si no toca (base 26.2%). Separación 0.54-0.67 frente al
0.33 máximo de todo lo demás probado.

**COMO SALIDA NO SIRVE** (misma señal, cerrando posiciones abiertas):
```
SALIDA k3 u1.0   +32.662   -3.216   racha 5  dd -1.103   T1 NO 2/4  p=0.530  NO
SALIDA k4 u1.0   +31.757   -4.121   racha 4  dd -1.153   T1 NO 2/4  p=0.528  NO
```
Restan 3-4k$ y no pasan (p~0.53 = azar). Coherente con TODO lo medido estos dos días: **cortar
posiciones abiertas siempre destruye valor**; lo que funciona es **NO ENTRAR**. (Curiosidad: como
salida bajan mucho el drawdown -1.103, el mejor medido, pero a costa del beneficio.)

**DÓNDE ESTÁ TODO (copiado al repo, no depende del scratchpad):**
`investigacion/2026-08-19_aproximacion/` -> scripts (`barrido_aprox.py`, `test_aprox_post.py`,
`test_secuencias.py`, `barrido_brecha.py`, `test_predecir_falso.py`, `_dump_D.py`) y
`D/ap_*.json` con el P&L día a día de cada variante.
Para reanalizar sin recomputar: cargar los JSON y usar `sys2.backtest.validacion.valida_regla`.

**FALTA:** (a) 1-2 variantes de salida que quedaron corriendo (`ap_sal_k4ben`, `ap_sal_k2u10`) —
si aparecen en `D/`, analizarlas; no cambian la conclusión; (b) pasar la regla de ENTRADA por los
**12 cold runs**, sobre todo `cr_lookahead` (verificar que solo usa velas YA formadas);
(c) decidir si se aplica al vivo y al motor.

## LO QUE HAY QUE HACER (por prioridad)

1. **Cerrar el punto anterior**: variantes de salida + cold runs + aplicar.
2. **Medir las 2 fuentes de brecha SIN MEDIR**: (a) descarte de aperturas por ORB futuro
   (`pipeline.py:38-41`); (b) `dia_bueno` aplicado desde el minuto 1 (`motor.py:127-129`).
3. **Juez de salida** (idea del usuario, ya medido: +857$, pasa los 4 tests §2.1 con racha y
   drawdown intactos): falta pasarlo por `cr_lookahead` y remedirlo sobre el sistema honesto.
4. **Panel**: muestra el estado de AYER hasta las 09:30 (volcar estado también al arrancar).
5. **Tape**: solo hay 2 sesiones (12 y 13 de agosto, con `fecha` ya escrita). Insuficiente. Es la
   única fuente de información INDEPENDIENTE del precio que queda sin explorar.

## NO REPETIR (ya medido y descartado sobre 485 sesiones)

Toma de beneficio por toques · más MAX_TRADES · soportes/resistencias por pivotes en 5
temporalidades · no-entrar-en-mercado-plano (el `atr_pct -0.83` era del sistema VIEJO, que
compraba singles; sys2 compra verticales y la pata corta vende theta) · trailing · esperar antes
de entrar (5 tiempos) · filtrar giros por cuerpo/dist/hora · secuencias de velas previas.
**Patrón: toda regla que corte ganancias antes de tiempo destruye el sistema.**

## CRITERIO DEL USUARIO PARA ACEPTAR UN CAMBIO

Racha ≤4, drawdown ≥-1.140, peor día ≥-648 y TOTAL ≥ el de la base. Si falla cualquiera, se
descarta. Y siempre sobre **las 485 sesiones (2 años)**, con desglose AÑO 1 / AÑO 2.
