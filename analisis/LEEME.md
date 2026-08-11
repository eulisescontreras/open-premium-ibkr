# Scripts de análisis (READ-ONLY)

Todos abren `spy_history.db` en **modo solo lectura** (`file:...?mode=ro`): se pueden correr
con la app en marcha sin riesgo. Ninguno modifica nada.

Los resultados y su interpretación están en **`../ANALISIS_ENTRADA_SALIDA.md`**. Léelo antes de
sacar conclusiones: incluye las **trampas metodológicas ya identificadas** (tasa base, sesgo de
selección, correlación con el reloj, medir sobre la prima y no sobre el subyacente).

| Script | Qué responde |
|---|---|
| `verifica_vivo.py` | ¿Se está llenando cada tabla? Estado rápido de la instrumentación |
| `auditoria_datos.py` | Calidad y congruencia: cruza `ta_minute.spy` contra `walls_snapshot.spot`, huecos, reinicios, valores imposibles |
| `lead_lag.py` | **¿El flujo de premium anticipa el movimiento o lo sigue?** Correlación cruzada por lags |
| `barrido_total.py` | **El más completo.** 40+ variables (niveles y deltas) contra movimiento brusco / gradual / plano |
| `barrido.py` | Versión previa, solo niveles, contra movimientos grandes |
| `compresion.py` | Prueba (y descarta) la hipótesis del ancho de Bollinger, con tasa base |
| `ta_vs_movimiento.py` | ¿El TA anticipa? TA vs premium en acierto direccional |
| `vida_del_giro.py` | Qué hace el SPY después de cada giro: MFE, MAE, lo dejado sobre la mesa |
| `tesis_acumulado.py` | Cuánto cuesta girar según avanza el día (el umbral crece con el acumulado) |
| `explican_movimientos.py` | Los mayores movimientos del día y qué decían los datos en ese momento |

## Cómo correrlos

```powershell
cd C:\Users\eulis\proyectos\open-premium-ibkr
python analisis\barrido_total.py                # la ULTIMA fecha con datos en la BD
python analisis\barrido_total.py 2026-08-10     # una fecha concreta
python analisis\barrido_total.py ayer           # la fecha anterior a la ultima
```

**Todos anuncian en su primera línea qué fecha están analizando.** No es adorno:

> El 2026-08-11, con el mercado abierto, se corrió `auditoria_datos.py` para revisar los datos
> **de hoy** y devolvió tan tranquilo el informe **de ayer** — 323 minutos de TA, 7 huecos,
> 6 reinicios: todo correcto y todo del día equivocado. Los 9 scripts tenían
> `F = "2026-08-10"` escrito a mano. Solo se detectó porque el hueco 13:24→14:00 era la firma
> del GAP 17 del día anterior.

La fecha la resuelve `_fecha.py` (compartido). El defecto es *la última fecha con datos* y **no**
*hoy*, a propósito: así sirve también en fin de semana, de madrugada o antes de la apertura. Si se
pide una fecha sin datos, **aborta con código 2** en vez de analizar el vacío.

*(`verifica_vivo.py` no lleva fecha: comprueba el estado actual de la instrumentación.)*

## Aviso

Los resultados publicados salen de **UN SOLO DÍA** (2026-08-10, 265 minutos). Son hipótesis y
descartes, no reglas. Con 3-5 sesiones limpias habrá que **volver a correrlos todos** — y
controlando por hora del día y por régimen de GEX.
