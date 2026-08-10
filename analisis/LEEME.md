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
python analisis\barrido_total.py
```

## Aviso

Los resultados publicados salen de **UN SOLO DÍA** (2026-08-10, 265 minutos). Son hipótesis y
descartes, no reglas. Con 3-5 sesiones limpias habrá que **volver a correrlos todos** — y
controlando por hora del día y por régimen de GEX.
