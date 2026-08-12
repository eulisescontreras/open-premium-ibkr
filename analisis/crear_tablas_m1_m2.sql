-- ============================================================================
-- TABLAS DE REGISTRO M1 y M2  -- aplicar sobre spy_history.db
-- Cada tabla lleva las columnas del calculo REAL de su metodo.
-- ============================================================================

-- M1: contador de MINUTOS. Se compara #UP contra #DOWN.
CREATE TABLE IF NOT EXISTS m1_minute (
    fecha        TEXT,
    hora         TEXT,
    spy          REAL,
    net_call     REAL,      -- crudo, con signo
    net_put      REAL,
    abs_call     REAL,      -- |net_call|
    abs_put      REAL,      -- |net_put|
    dif          REAL,      -- abs_call - abs_put
    senal_min    TEXT,      -- UP / DOWN  (lectura de ESTE minuto)
    n_up         INTEGER,   -- contador acumulado de minutos UP
    n_down       INTEGER,   -- contador acumulado de minutos DOWN
    marcador     INTEGER,   -- n_up - n_down
    m1           TEXT,      -- UP / DOWN / NEUTRAL  <- la lectura del metodo
    racha        INTEGER,   -- minutos seguidos con la misma m1
    recentrado   INTEGER,   -- 1 si hubo re-centrado de strike en este minuto (GAP D)
    PRIMARY KEY (fecha, hora)
);

-- M2: contador de DOLARES. Se compara $UP contra $DOWN.
CREATE TABLE IF NOT EXISTS m2_minute (
    fecha        TEXT,
    hora         TEXT,
    spy          REAL,
    net_call     REAL,
    net_put      REAL,
    abs_call     REAL,
    abs_put      REAL,
    dif          REAL,      -- abs_call - abs_put  (lo que se acumula)
    senal_min    TEXT,      -- UP / DOWN
    usd_up       REAL,      -- suma de dif en los minutos UP
    usd_down     REAL,      -- suma de |dif| en los minutos DOWN
    acumulado    REAL,      -- usd_up - usd_down  (= suma corrida de dif con signo)
    m2           TEXT,      -- UP / DOWN / NEUTRAL  <- la lectura del metodo
    racha        INTEGER,
    recentrado   INTEGER,
    PRIMARY KEY (fecha, hora)
);
