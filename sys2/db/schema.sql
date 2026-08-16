-- Esquema del sistema SPY 0DTE nuevo (sys2). Base: sys2.db
-- Fuente: MANUAL_TRASPASO_AGENTE §4.1 + campos extra del plan aprobado.
-- Todo idempotente (CREATE TABLE IF NOT EXISTS). Fechas TEXT 'YYYY-MM-DD', horas TEXT 'HH:MM'.
-- OBLIGATORIO: antes de modificar, leer los 2 PDFs de la investigacion y el plan aprobado.

-- ═══════════════════════════════ MERCADO ═══════════════════════════════
CREATE TABLE IF NOT EXISTS bars (          -- SPY, 1 minuto, DESDE LAS 04:00 (premarket)
  fecha TEXT, hora TEXT,                   -- 'YYYY-MM-DD', 'HH:MM' (ET)
  open REAL, high REAL, low REAL, close REAL,
  volume REAL, vwap REAL,
  fuente TEXT DEFAULT 'hist',              -- 'hist' | 'backfill' | 'live'
  PRIMARY KEY (fecha, hora)
);

CREATE TABLE IF NOT EXISTS bars_etf (      -- DIA y TLT (regla 5: dia bueno), 09:25-10:05
  ticker TEXT, fecha TEXT, hora TEXT, close REAL,
  PRIMARY KEY (ticker, fecha, hora)
);

CREATE TABLE IF NOT EXISTS dia_anterior (  -- para ayer_rev y gap_fade
  fecha TEXT PRIMARY KEY,                  -- la fecha CUYO cierre/max/min se guarda
  cierre REAL, maximo REAL, minimo REAL
);

-- ═══════════════════════════ CADENA DE OPCIONES ════════════════════════
CREATE TABLE IF NOT EXISTS premium (       -- 0DTE (y 1DTE via expiry), TODOS los strikes, cada minuto
  fecha TEXT, hora TEXT, expiry TEXT,      -- expiry en la PK: nunca mezclar vencimientos
  strike REAL, right TEXT,                 -- 'C' | 'P'
  bid REAL, ask REAL, mid REAL, last REAL,
  day_vol REAL,                            -- CRITICO para la regla 3 (ratio call/put OTM)
  open_interest REAL,
  iv REAL, delta REAL, gamma REAL, theta REAL, vega REAL,
  fuente TEXT DEFAULT 'bs',                -- 'live' (greeks reales IBKR) | 'bs' (Black-Scholes sobre massive)
  PRIMARY KEY (fecha, hora, expiry, strike, right)
);
CREATE INDEX IF NOT EXISTS ix_prem ON premium(fecha, hora);

-- ═══════════════════════════ DECISIONES DEL SISTEMA ════════════════════
CREATE TABLE IF NOT EXISTS senales (       -- TODA senal generada, se opere o no
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT, hora TEXT,
  origen TEXT,                             -- 'ST'|'ORB'|'pm_rev'|'gap_fade'|'v1'|'ayer_rev'
  direccion TEXT,                          -- 'C'|'P' ORIGINAL, antes de reglas
  -- clasificacion de la regla del rebote (SOLO origen='ST')
  grupo TEXT,                              -- 'NORMAL'|'RETRASA'|'INVIERTE'|'DESCARTA'
  hora_efectiva TEXT,                      -- tras el retraso, si lo hubo
  direccion_final TEXT,                    -- tras rebote y skew
  -- que regla la toco
  descartada_por TEXT,                     -- NULL|'ST1'|'RATIO'|'sin_contrato'|...
  invertida_por TEXT,                      -- NULL|'REBOTE'|'SKEW'
  -- contexto en el instante de la senal
  spy REAL, atr3 REAL,
  dist_linea REAL,                         -- |close - linea ST| / ATR
  skew REAL,                               -- orientado al lado de la senal
  ratio_otm REAL,                          -- orientado al lado de la senal
  iv_atm REAL,
  giros_st1_5m INTEGER,
  -- resultado (se calcula AL CIERRE del dia)
  flip_falso INTEGER                       -- 1 si avance < 1 ATR antes del siguiente flip
);

CREATE TABLE IF NOT EXISTS contexto_dia (  -- una fila por sesion, calculada a las 10:30
  fecha TEXT PRIMARY KEY,
  gap REAL, rango_pm REAL, mov_pm REAL, atr_pm REAL,
  efic15 REAL, efic30 REAL, efic60 REAL,
  mov15 REAL, mov30 REAL, mov60 REAL,
  mov_DIA REAL, mov_TLT REAL,
  iv10 REAL, skew10 REAL,
  dia_bueno INTEGER,                       -- 1 si se activo la regla 5
  unidades INTEGER,                        -- 1 o 2 (dia bueno dobla)
  -- al cierre
  pnl_dia REAL, n_ops INTEGER, regimen TEXT
);

CREATE TABLE IF NOT EXISTS operaciones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT, senal_id INTEGER,
  n_op_dia INTEGER,                        -- 1..4  (el 95% del beneficio esta en la ULTIMA)
  -- estructura
  tipo TEXT,                               -- 'vertical'|'single'
  right TEXT, strike_largo REAL, strike_corto REAL, ancho REAL,
  qty INTEGER,
  -- autocalibracion usada (MANUAL §13.6)
  nivel INTEGER, modo TEXT, tope REAL, unidades INTEGER,
  -- entrada
  hora_entrada TEXT, spy_entrada REAL,
  precio_largo_pagado REAL, precio_corto_cobrado REAL, debito_neto REAL,
  bid_largo REAL, ask_largo REAL, bid_corto REAL, ask_corto REAL,
  delta_entrada REAL, iv_entrada REAL, moneyness REAL,
  -- salida
  hora_salida TEXT, spy_salida REAL,
  precio_largo_venta REAL, precio_corto_recompra REAL, credito_neto REAL,
  razon_salida TEXT,                       -- 'flip'|'cierre'|'manual'
  duracion_min INTEGER,
  -- resultado
  pnl REAL, comision REAL, mfe REAL, mae REAL
);

CREATE TABLE IF NOT EXISTS fills (         -- una fila POR PATA (hipotesis critica abierta: verticales)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  operacion_id INTEGER, fecha TEXT, hora TEXT,
  strike REAL, right TEXT, accion TEXT,    -- 'BUY'|'SELL'
  precio_ordenado REAL, precio_lleno REAL,
  bid_momento REAL, ask_momento REAL,
  segundos_hasta_fill REAL,
  lleno INTEGER,                           -- 0 si NO se lleno
  parcial INTEGER                          -- 1 si solo se lleno una pata del vertical
);

CREATE TABLE IF NOT EXISTS movimientos (   -- ingresos/retiros de capital (MANUAL §13.6)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT, tipo TEXT,                    -- 'ingreso'|'retiro'
  importe REAL, saldo_antes REAL, saldo_despues REAL
);

-- ═════════════════════ RESCATE / INVESTIGACION FUTURA ═════════════════
CREATE TABLE IF NOT EXISTS tape_und (      -- tape firmado del subyacente (spy_tape_und.db) -> signo del flujo
  fecha TEXT, ts TEXT, price REAL, size REAL, exch TEXT, signo TEXT,
  PRIMARY KEY (fecha, ts, price, size, exch)
);

CREATE TABLE IF NOT EXISTS premium_mix (   -- bid/ask reconstruido (spy_prem_mix_*/synth) por dia
  fecha TEXT, hora TEXT, expiry TEXT, strike REAL, right TEXT,
  bid REAL, ask REAL,
  PRIMARY KEY (fecha, hora, expiry, strike, right)
);

-- Control de migracion (para el cold run cr_migracion)
CREATE TABLE IF NOT EXISTS migracion_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cuando TEXT, origen TEXT, destino TEXT, filas INTEGER
);
