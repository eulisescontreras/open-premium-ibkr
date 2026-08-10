# SPY Direction — Guía completa (para otro agente / instalador)

> App **independiente** (no tiene relación con ningún trading bot). Un solo propósito:
> mirar el flujo de opciones de **SPY** al abrir y mostrar en pantalla **UP / DOWN**
> para apoyar **scalping** de SPY.

---

## 1) Qué hace (en una frase)
Se conecta a **IBKR (IB Gateway)**, toma el **vencimiento de opciones más cercano** (0DTE)
y los strikes **ATM/ITM** (call con strike ≤ precio, put con strike ≥ precio; nunca OTM),
mide el **neto de premium comprado en calls vs en puts** desde la apertura, y muestra:
- **UP** (verde) → el flujo de calls domina → sesgo alcista.
- **DOWN** (rojo) → el flujo de puts domina → sesgo bajista.
- **–** (gris) → aún sin señal / dentro del umbral.

Además avisa **antes del giro** (banner naranja, heurística de momentum) y en el
**giro confirmado** (banner rojo). Guarda todo en un **SQLite** que viaja con la app.

## 2) Cómo funciona (lógica interna)
1. Conecta a IB Gateway (`ib_insync`), puerto **4002** (paper).
2. Precio de SPY con fallback: **LIVE → FROZEN → DELAYED** (para que siempre lea algo).
3. `reqSecDefOptParams` → elige la entrada SMART con **tradingClass == 'SPY'**
   (OJO: la '2SPY' es parcial), toma la **expiración más cercana** y los **strikes válidos**.
4. Elige **CALL = strike más cercano ≤ precio** y **PUT = strike más cercano ≥ precio** (ATM/ITM).
5. Suscribe `reqMktData(contract, "233")` (RTVolume). Por cada aumento de **volumen**:
   `premium = precio_último × Δvolumen × 100`; **compra** si el último pega en el ask,
   **venta** si pega en el bid. Acumula `net_call` y `net_put`.
   (NO se usa `reqTickByTickData`: IBKR devuelve **error 10189** para opciones.)
6. **Señal:** `UP` si `net_call − net_put > umbral`; `DOWN` si `< −umbral`; si está dentro
   del umbral, **mantiene** el estado (no parpadea).
7. **Aviso anticipado:** si el neto va cayendo con fuerza hacia cero (momentum) → banner naranja.

## 3) Requisitos
- **IB Gateway** instalado, **abierto y logueado** (cuenta **paper**).
- API habilitada en IB Gateway: *Configure → Settings → API → Settings*:
  - ✅ Enable ActiveX and Socket Clients
  - **Socket port: 4002** (paper). Live = 4001.
  - ✅ Allow connections from localhost (o Trusted IP `127.0.0.1`).
- **Datos de opciones en tiempo real (OPRA)** en la cuenta para el flujo real
  (add-on "US Equity and Options Add-On Streaming Bundle"). Sin eso corre en DELAYED (15 min).
- Para correr desde código: **Python 3.11** + `ib_insync` (`pip install ib_insync`).
  Para el `.exe` no hace falta Python.

## 4) Cómo instalar (en una máquina nueva)
**Opción A — automática (recomendada):**
1. Copiar toda la carpeta `open-premium-ibkr`.
2. Doble clic en **`install.bat`** (instala Python si falta vía winget, instala
   dependencias y construye `dist\spy_direction.exe`).

**Opción B — manual:**
```
pip install ib_insync pyinstaller
pyinstaller --onefile --windowed --name spy_direction spy_direction.py
```

## 5) Cómo ejecutar
- **Ejecutable:** doble clic en `dist\spy_direction.exe` (con IB Gateway abierto).
- **Con Python:**
  - Normal (real):   `python spy_direction.py`
  - **Demo** (sin mercado, entradas simuladas para ver la pantalla): `python spy_direction.py --demo`
  - **Self-test** (diagnóstico de conexión + strikes, sin ventana): `python spy_direction.py --selftest`

## 6) Archivos del proyecto
| Archivo | Qué es |
|---|---|
| `spy_direction.py` | La app completa (conexión, lógica, GUI, SQLite) |
| `install.bat` | Instalador de un clic (Python + deps + build exe) |
| `build_exe.bat` | Solo empaqueta el .exe |
| `README.txt` | Guía corta de uso |
| `GUIA_AGENTE.md` | Este documento |
| `dist/spy_direction.exe` | Ejecutable autónomo (se genera al construir) |
| `spy_history.db` | Historial SQLite (modo real) — se crea solo |
| `spy_history_demo.db` | Historial del modo demo |

## 7) Configuración (arriba de `spy_direction.py`)
| Constante | Default | Qué hace |
|---|---|---|
| `PORT` | 4002 | Puerto API (4002 paper IBGW / 4001 live / 7497-7496 TWS) |
| `CLIENT_ID` | 7 | ID de cliente API (cambiar si choca) |
| `SIGNAL_THRESHOLD` | 5000 | US$ de neto para cambiar de estado (anti-parpadeo) |
| `WARN_BAND_FRAC` | 0.6 | Banda para el aviso anticipado |
| `MOMENTUM_WIN` / `MOMENTUM_MIN` | 8 / 3000 | Sensibilidad del aviso de giro |
| `ENABLE_SOUND` | False | Solo banner visual (sin sonido) |

## 8) Historial (SQLite)
- Archivo `spy_history.db` **junto al .exe** → viaja con la carpeta; se ve en cualquier máquina.
- Tabla `transitions(fecha, hora, estado, tipo, spy, net_call, net_put, modo)`.
  `tipo` = `WARN` (aviso) o `FLIP` (giro confirmado).

## 9) Notas honestas (importante)
- El "Open Premium" aquí es **casero** (neto de premium call vs put por lado agresor).
  **No** es idéntico al de MarketSnack (fórmula propietaria), pero es el **mismo concepto** direccional.
- Es una **señal de apoyo**, no una garantía. La relación flujo→precio en la apertura
  quedó **validada solo parcialmente** (muestra chica); conviene registrar varios días.
- El flujo por-trade real necesita **OPRA en vivo**; si la app muestra `[DELAYED]`,
  los datos llegan con retraso (15 min) y no sirven para scalping.

## 10) Problemas comunes
- **"SIN CONEXION"** → IB Gateway cerrado / API no habilitada / puerto ≠ 4002.
- **`[DELAYED]` o `[FROZEN]`** → falta suscripción OPRA en vivo, o mercado cerrado.
- **`net_call/net_put = 0`** → mercado cerrado (sin trades) o fuera de la ventana de apertura.
- **Precio NaN al abrir en finde** → normal, el dato en vivo aparece con el mercado abierto.
