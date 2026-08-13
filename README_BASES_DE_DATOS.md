# BASES DE DATOS DEL REPOSITORIO

## Por qué la BD está separada por día

`spy_history.db` es la **base de datos de producción**: una sola, con todos los días, y es
la que la aplicación abre y escribe en vivo (`spy_direction.py:844`).

El 2026-08-13 alcanzó **151,6 MB**. GitHub tiene un **límite duro de 100 MB por archivo**:
cualquier push que la incluya es rechazado por el servidor, no por configuración local.

Por eso **no se sube entera**. En su lugar se suben copias **partidas por día**:

```
spy_history_20260810.db     2,2 MB     20.991 filas
spy_history_20260811.db     8,3 MB     58.004 filas
spy_history_20260812.db    40,5 MB    236.397 filas
spy_history_20260813.db    93,5 MB    540.437 filas
```

**La separación es SOLO para poder versionarlas en GitHub.** No es un cambio de
arquitectura: la aplicación sigue usando una única `spy_history.db` local, exactamente
igual que antes. Nada del código lee estos ficheros por día.

## Qué contiene cada una

Las **17 tablas** que tienen columna `fecha`, filtradas por ese día, con su DDL original y
sus índices:

```
bars_minute · clasico_minute · confirmacion_minute · entrada_minute · estado_intradia
m1_minute · m2_minute · media_minute · posicion_minuto · premium_minute · sesion_config
strike_daily · ta_minute · tape · trades · transitions · walls_snapshot
```

## Lo que NO está: strike_accum

La tabla **`strike_accum` no tiene columna `fecha`** y por eso **queda fuera de las cuatro
BD por día**. Es un acumulado global por `(expiry, strike, right)`, no por sesión.

No se reparte por días a ojo: no hay forma de saber qué parte de cada acumulado
corresponde a cada día sin inventárselo. Si la necesitas, sale de la `spy_history.db`
local.

## Aviso de tamaño

`spy_history_20260813.db` son **93,5 MB**, muy cerca del límite de 100 MB. GitHub ya avisa
a partir de 50 MB.

**Si el tape del subyacente sigue creciendo al ritmo del 08-13, el día siguiente no
cabrá en un solo fichero.** Cuando llegue ese punto habrá que:

- partir además por tabla (el `tape` es el 90 % del peso), o
- dejar de versionar el `tape` y guardarlo aparte, o
- pasar a Git LFS.

## Si algún día se quiere partir la BD de producción

**Ojo, no es un cambio trivial.** Hay consultas que **no filtran por día** y que se
romperían al separar:

```
spy_direction.py:1505   SELECT ... FROM strike_accum          <- acumulado global, sin fecha
spy_direction.py:1144   SELECT ... FROM transitions
spy_direction.py:1561   SELECT ... FROM trades
```

Antes de tocarlo hay que revisar cada una y decidir qué pasa con los datos que cruzan
sesiones. **No se ha hecho ningún cambio en producción.**

## Cómo regenerar las BD por día

```
python investigacion/scripts/partir_bd.py
```

Abre `spy_history.db` en **solo lectura**, crea una BD nueva por cada fecha encontrada y
hace `VACUUM`. No modifica la de producción. Si un fichero de destino ya existe, lo omite
en vez de pisarlo.

## Otras bases de datos del repositorio

```
spy_tape_ayer.db        380.778 ticks del 08-12 descargados de IBKR (reqHistoricalTicks)
spy_tape_20260813.db     31.161 ticks del 08-13 exportados del tape en vivo
spy_velas.db            copia de trabajo de las velas, para análisis
```

Ninguna es de producción: son derivadas, generadas para la investigación del tape del
subyacente (ver `investigacion/INVESTIGACION_TAPE_SUBYACENTE.md`).
