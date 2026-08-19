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

# ═══════════════════════════════════════════════════════════════════════════════════════
# SISTEMA HONESTO (2026-08-19) — ver investigacion/2026-08-19_sistema_real/README.md
# Todo lo de aquí es CONFIGURABLE: poniéndolo a False/None se vuelve al comportamiento viejo.
# Medido sobre 485 sesiones sin look-ahead: 600$ -> 89.638$ (149,4x), racha 3, drawdown -21,1%.
# ═══════════════════════════════════════════════════════════════════════════════════════

# ── FIXES ANTI-LOOK-AHEAD (hacen BAJAR el backtest; es el precio de la honestidad) ──
VISION_HONESTA = True                 # reb2 con 1 bucket = lo que ve el vivo. 72.497 -> 35.878$
DIABUENO_DESDE = "10:31"              # `dia_bueno` necesita 60 barras (reglas.py:60): antes de
                                      # esa hora el dato NO existe. Sin esto: -1.132$ inflados.
                                      # "00:00" = comportamiento viejo (doblar desde el minuto 1)

# ── FILTRO POR CADENA DE OPCIONES (+9.606$) — coste de tiempo CERO ──
# Cuenta condiciones adversas EN EL MINUTO DEL FLIP. Umbrales del percentil 25 del AÑO 1
# (el año 2 nunca se miró al elegirlos). Validación out-of-sample: score 0 -> 51,0% pierden,
# 1 -> 59,1%, 2 -> 74,1%, 3 -> 89,3%. p=0,0000 contra muestras aleatorias.
SCORE_OPCIONES = 2                    # descartar el flip con >= N señales adversas (0 = off)
SCORE_COSTV = 0.195                   # vertical ATM barato -> el mercado no paga el movimiento
SCORE_IV = 0.150                      # IV muerta -> sin recorrido esperado
SCORE_SKEW = 0.031                    # pagan protección CONTRA la dirección del flip

# ── SALIDA POR OBJETIVO (+9.010$) ──
# El vertical NO puede valer más que su ancho: al 95% ya capturó casi todo y lo que queda es
# riesgo sin recompensa. Atado al ANCHO (techo físico), no al débito (que varía con la entrada).
TP_ANCHO = 0.95                       # cerrar si mid >= TP_ANCHO * ancho (None = off)

# ── CONTROL DE RIESGO ──
PAUSA_ROJOS = 3                       # no operar tras N días rojos seguidos (0 = off).
                                      # Corta la racha de 7 a 3 Y GANA MÁS (+665$): tres días
                                      # rojos seguidos son un régimen malo, no mala suerte.
STOP_DIARIO = 0.15                    # dejar de ABRIR si el día ya perdió este % del saldo

# ── SIZING POR FRACCIÓN DEL SALDO (sustituye la tabla de autocalibra) ──
# La tabla bajaba de nivel al perder -> con tope 75$ no cabe ningún vertical (cuestan 88-135$)
# -> el sistema se AUTOAPAGABA (6 días operados de 485 con 600$).
SIZING_FRAC = 0.18                    # tope = 18% del saldo (medido óptimo; 25% y 50% son PEORES)
SIZING_SUELO = 140.0                  # suelo del tope. Con 110 el drawdown pasa de -21% a -32%;
                                      # con 90 la cuenta llega a saldo NEGATIVO.
SIZING_KSUP = 3.5                     # REGLA DE SUPERVIVENCIA: no operar si saldo < K * suelo.
                                      # Riesgo de ruina 33% -> 0% y NO cuesta profit (los
                                      # arranques sanos dan el mismo número al céntimo).
                                      # Fija el CAPITAL MÍNIMO: 3,5 x 140 = 490$.

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
