# -*- coding: utf-8 -*-
"""Parámetros CONGELADOS de la configuración validada (+71.396$ base / +61.999$ operable).
Fuente: motor real del sistema validado (agente dueño del análisis, 2026-08-16). Verbatim.
Estos valores producen las cifras titulares; NO tocar sin revalidar el motor (cr_motor).

Supertrend: per=7, mult=3.0 (ST-3 sobre buckets de 3 min, ST-1 sobre 1 min).
"""

# ── Supertrend ──
ST_PER = 7
ST_MULT = 3.0

# ── Entradas ──
ORB_ANCLAS = ("09:40", "11:00")
ORB_RANGO_MIN = 0.40
APERTURAS_ORDEN = ("pm_rev", "v1", "gap_fade", "ayer_rev")   # ORDEN IMPORTA (Sen)
DESCARTE_MIN = 5                      # descarte de aperturas: abs(dif) > 5 (estricto)

# ── Rebote (reb2) ──
REB_ESPERA = 12
REB_CERCA = 1.0
REB_SEP = 1.5
REB_PEGADO = 2

# ── Descarte ST-1 ──
ST1_ON = True                         # aplica el descarte por giro del ST-1 (False = off)
ST1_VENTANA = 5                       # giros del ST-1 en [m0, m0+5)

# ── Ratio call/put OTM ──
RUMB = 0.3                            # veto direccional por flujo OTM (None = off)

# ── Skew sobre RETRASA ──
RETMOD = "invierte"                  # 'invierte' | 'quita' | None
RETSK = 0.04

# ── Día bueno (dobla unidades) ──
DIABUENO = True
E60B = 0.187                          # eficiencia 60 min <
MDB = 1.23                            # mov DIA >
MTB = 1.225                           # mov TLT <

# ── Instrumento ──
ANCHO = 4.0                           # ancho del vertical de débito (pts); None = single
TOPE = 320.0                          # débito máx por operación (80% de 400$)
DEBITO_MIN = 20.0                     # débito mínimo del vertical

# ── Gestión ──
PIR = True                            # piramidar activo
PIR_DELTA = 0.03                      # delta sube +0.03 sobre inicial
PIR_ESPERA_MIN = 10                   # tras 10 min mínimo
PIR_HASTA = "15:20"
ROD_DELTA = 0.35                      # rodar si delta < 0.35
ROD_MAX = 3
ROD_HASTA = "15:30"

# ── Salida / límites ──
MAX_TRADES = 4
ABRIR_HASTA = "15:40"
APLANADO = "15:59"                    # base (+71.396$); operable = "15:53" (+61.999$)
COMISION = 1.72                       # ida y vuelta por contrato

# ── Greeks (convención del motor) ──
GREEKS_R = 0.0                        # el motor invierte IV con r=0, q=0
GREEKS_Q = 0.0

# ── VIVO / PAPER (tiempos OPERABLES §12.4, NUNCA 15:59 en vivo) ──
APLANADO_VIVO = "15:50"               # aplanar (cerrar) — operable (backtest = APLANADO 15:59)
MERCADO_VIVO = "15:55"                # si sigue abierta, orden a MERCADO
VERIF_PLANA = "15:59"                 # verificar posición plana antes de 16:00 (asignación §12)

# ── IBKR (paper) ──
IBKR_HOST = "127.0.0.1"
IBKR_PORT = 4002                      # IB Gateway paper (live=4001; TWS 7497/7496)
IBKR_CLIENT_ID = 17                   # propio, NO 7/24/25 (los usa el bot viejo/otros)
SYMBOL = "SPY"
ETFS = ("DIA", "TLT")                 # para la regla del día bueno
BACKFILL_DUR = "2 D"                  # reqHistoricalData useRTH=False -> premarket 04:00→arranque
N_STRIKES_LADO = 20                   # cadena: strikes por lado a CAPTURAR (ITM+OTM, C y P).
#   Se guardan TODOS en `premium` cada minuto con sus griegas -> registro del movimiento de las
#   griegas de toda la cadena. 20/lado = 82 contratos (<100 líneas de IBKR; se cancelan tras leer).
