# PARCHE M1/M2 — registro en tablas + cambio del disparador de flips

Fecha: 2026-08-11. Pedido explícito del usuario.
**NO probado contra la app** (no hay conexión a IB desde el entorno donde se escribió).
Requiere corrida en frío diferencial antes de arrancar en vivo.

---

## PARTE 1 — Crear las tablas (sin riesgo, no toca la lógica)

```
sqlite3 spy_history.db < analisis\crear_tablas_m1_m2.sql
```

Dos tablas, una por método, cada una con las columnas de **su propio cálculo**:

- `m1_minute`: `abs_call`, `abs_put`, `dif`, `senal_min`, **`n_up`, `n_down`, `marcador`**, `m1`, `racha`
- `m2_minute`: `abs_call`, `abs_put`, `dif`, `senal_min`, **`usd_up`, `usd_down`, `acumulado`**, `m2`, `racha`

Ambas llevan `recentrado` (1 si hubo re-centrado de strike ese minuto) para poder
excluir después los minutos contaminados por GAP D.

---

## PARTE 2 — Registrar cada minuto

### 2a. Estado en `__init__` (junto a `self.net_call = 0.0`, ~línea 493)

```python
        # --- M1 / M2: contadores de la investigacion (2026-08-11) ---
        self.m1_up = 0; self.m1_down = 0        # contador de MINUTOS
        self.m2_up = 0.0; self.m2_down = 0.0    # contador de DOLARES
        self.m1_estado = None; self.m2_estado = None
        self.m1_racha = 0; self.m2_racha = 0
        self.m_recentrado = 0                   # lo pone a 1 refresh_strikes
```

### 2b. Reset en `reset_day()` (junto al `self.net_call = 0.0`, ~línea 940)

```python
        self.m1_up = 0; self.m1_down = 0
        self.m2_up = 0.0; self.m2_down = 0.0
        self.m1_estado = None; self.m2_estado = None
        self.m1_racha = 0; self.m2_racha = 0
        self.m_recentrado = 0
```

### 2c. Marcar el re-centrado

En `refresh_strikes`, donde ya se emite `SENAL call/put re-centrada`, añadir:

```python
        self.m_recentrado = 1
```

### 2d. Escritura, en `ta_poll` justo DESPUÉS del `INSERT ... ta_minute` (~línea 3140)

```python
            # --- M1 / M2 (2026-08-11): se REGISTRAN, y M1 ademas decide (ver PARTE 3) ---
            _ac = abs(self.net_call); _ap = abs(self.net_put)
            _dif = _ac - _ap
            _sen = "UP" if _dif > 0 else "DOWN"
            if _dif > 0: self.m1_up += 1; self.m2_up += _dif
            else:        self.m1_down += 1; self.m2_down += -_dif
            _m1 = "UP" if self.m1_up > self.m1_down else "DOWN" if self.m1_down > self.m1_up else "NEUTRAL"
            _m2 = "UP" if self.m2_up > self.m2_down else "DOWN" if self.m2_down > self.m2_up else "NEUTRAL"
            self.m1_racha = self.m1_racha + 1 if _m1 == self.m1_estado else 1
            self.m2_racha = self.m2_racha + 1 if _m2 == self.m2_estado else 1
            self.m1_estado = _m1; self.m2_estado = _m2
            self.db.execute(
                "INSERT OR REPLACE INTO m1_minute(fecha,hora,spy,net_call,net_put,abs_call,"
                "abs_put,dif,senal_min,n_up,n_down,marcador,m1,racha,recentrado) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, v.get("close", self.spy_price), self.net_call, self.net_put,
                 _ac, _ap, _dif, _sen, self.m1_up, self.m1_down, self.m1_up - self.m1_down,
                 _m1, self.m1_racha, self.m_recentrado))
            self.db.execute(
                "INSERT OR REPLACE INTO m2_minute(fecha,hora,spy,net_call,net_put,abs_call,"
                "abs_put,dif,senal_min,usd_up,usd_down,acumulado,m2,racha,recentrado) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, v.get("close", self.spy_price), self.net_call, self.net_put,
                 _ac, _ap, _dif, _sen, self.m2_up, self.m2_down, self.m2_up - self.m2_down,
                 _m2, self.m2_racha, self.m_recentrado))
            self.m_recentrado = 0
```

---

## PARTE 3 — Cambiar el disparador de flips a M1

En `_update_signal`, sustituir SOLO el bloque de decisión (~línea 2003):

**ANTES:**
```python
        new = self.state
        if diff > thr:
            new = "UP"
        elif diff < -thr:
            new = "DOWN"
```

**DESPUÉS:**
```python
        # 2026-08-11: el disparador pasa a M1 (dominancia en VALOR ABSOLUTO acumulada
        # en minutos), por peticion del usuario. El calculo del diff/thr/momentum se
        # mantiene intacto: sigue alimentando el WARN, el log y ta_minute.
        # Para volver al criterio anterior, poner USAR_M1 = False.
        new = self.state
        if USAR_M1:
            if self.m1_estado in ("UP", "DOWN"):
                new = self.m1_estado
        else:
            if diff > thr:
                new = "UP"
            elif diff < -thr:
                new = "DOWN"
```

Y arriba con las constantes (~línea 90):
```python
USAR_M1 = True              # 2026-08-11: disparador de flips = M1. False -> criterio diff/thr.
```

### ⚠️ Ojo con esto

`_update_signal` corre cada segundo, pero `m1_up`/`m1_down` **solo se actualizan una vez
por minuto** en `ta_poll`. Es intencionado: M1 es un contador de minutos y no debe avanzar
1 por segundo. Efecto práctico: **M1 solo puede girar en el cambio de minuto**, no dentro.
Eso también elimina de golpe los flips en ráfaga (54 el 08-10, 16 entre 09:30 y 09:52).

Si `m1_estado` es `None` (antes del primer minuto) o `NEUTRAL` (empate), no se toca el
estado: se mantiene el anterior en vez de inventar una dirección.

---

## PARTE 4 — Antes de arrancar (protocolo del propio usuario)

1. `copy spy_history.db spy_history_backup_pre-m1.db`
2. Corrida en frío **diferencial** contra `git show HEAD` (patrón `coldruns/gapD_coldrun.py`).
   Comprobar como mínimo: que `m1_minute`/`m2_minute` se llenan un minuto por fila, que
   `n_up + n_down` = número de filas, que `acumulado == usd_up - usd_down`, y que con
   `USAR_M1 = False` el comportamiento es **idéntico** al de HEAD.
3. Diferencial de las 21 suites previas: conteos idénticos, 0 FAIL.
4. **Arrancar primero con `TRADING_ENABLED = False`** una sesión, para ver los flips que
   M1 habría dado sin arriesgar. Es un día de espera y da la evidencia que hoy no existe.
5. Cerrar el trade abierto si lo hay, SIN inventar precio de salida (`exit_price`,
   `profit`, `pct` a NULL).

## Cómo revertir

`USAR_M1 = False`. Las tablas se siguen llenando; solo deja de decidir.
