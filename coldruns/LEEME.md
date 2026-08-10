# Cold runs — suites de verificación

**Las 14 suites deben salir VERDES antes de cualquier reinicio de la app.** Es la regla dura
del proyecto (regla 3: nada se da por bueno sin ejecutar la función real; regla 8: diferencial
contra el baseline).

Todas ejercitan **métodos REALES** de `SpyDirection` con un `FakeIB`, no reimplementaciones,
y usan BD en memoria o ficheros temporales: **ninguna toca `spy_history.db`**.

## Cómo correrlas

Desde la raíz del repo (necesitan `spy_direction.py` en el path):

```powershell
$env:PYTHONPATH = "C:\Users\eulis\proyectos\open-premium-ibkr"
Get-ChildItem coldruns\*.py, spy_walls_coldrun.py, posicion_coldrun.py, gapsA_coldrun.py |
  ForEach-Object { python $_.FullName > $null 2>&1; "{0,-24} {1}" -f $_.Name, $(if($LASTEXITCODE -eq 0){"VERDE"}else{"ROJO"}) }
```

Exit 0 = verde. Cada suite imprime `OK`/`FAIL` por comprobación.

## Qué cubre cada una

| Suite | Cubre |
|---|---|
| `fase1_coldrun.py` | Conexión, reconexión, cooldown de reintentos |
| `gaps_coldrun.py` | Batería general de gaps (incluye el GAP 5, ya invertido tras arreglarlo) |
| `gap3_coldrun.py` | Los strikes siguen al precio (señal, ejecución, banda) |
| `gap7_coldrun.py` | `_log_minute` con `ON CONFLICT` (no borra OI/gamma) |
| `gap9_coldrun.py` | Órdenes fantasma: `Cancelled` con `filled>0` se procesa como FILL |
| `gap11_coldrun.py` | Precio del SPY en vivo desde las barras |
| `gap12_coldrun.py` | Contrato en cartera sin cotización (`_ensure_mkt`) |
| `gap13_coldrun.py` | Fills perdidos vía `execDetailsEvent` |
| `gap14_coldrun.py` | Límite duro de 1 contrato contando lo que va en vuelo |
| `gap15_coldrun.py` | Estado intradía sobrevive al reinicio (+ GAP 16, restauración completa) |
| `cuenta_coldrun.py` | Lectura de cuenta y P&L |
| `spy_walls_coldrun.py` *(raíz)* | Walls / GEX / gamma flip / Ladder |
| `posicion_coldrun.py` *(raíz)* | `trades`, `posicion_minuto`, griegas del contrato, `cum_net`, ventanas, GAP 17 |
| `gapsA_coldrun.py` *(raíz)* | GAP 2, GAP 4, GAP 5, M2, M12, premium por vela, panel, `sesion_config` |

## Nota histórica

`gap15_coldrun.py` y `gaps_coldrun.py` se **actualizaron el 2026-08-10** porque comprobaban
cosas que dejaron de existir al arreglar el GAP 5 (`diff_hist`, `MOMENTUM_WIN`). No eran
regresiones: un test que documenta un bug tiene que cambiar cuando el bug se arregla.
