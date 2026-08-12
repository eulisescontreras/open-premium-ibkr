# -*- coding: utf-8 -*-
"""
SPY Direction — Open-Premium casero via IBKR (proyecto INDEPENDIENTE, no toca el bot)
------------------------------------------------------------------------------------
Para SCALPING de SPY. Dos partes:

1) SEÑAL EN VIVO (pantalla UP/DOWN): usa el vencimiento MAS CERCANO (el proximo a
   expirar; puede ser 0DTE o a pocos dias) y los strikes ATM/ITM (call<=precio,
   put>=precio, nunca OTM). Mide el NETO de premium call vs put desde la apertura.

2) LINEA BASE (fechas posteriores): acumula el premium ATM/ITM de VARIAS
   expiraciones FUTURAS, guardando un ACUMULADO en la BD desde el primer dia de uso.
   Sirve para, al abrir el dia siguiente, ver si ese valor cambia fuerte (señal temprana).

Persistencia en SQLite (viaja con la app). Requiere IB Gateway abierto+logueado con
API habilitada (puerto 4002 paper). El flujo por-trade real necesita datos de
opciones OPRA en tiempo real; si solo hay 'delayed', la app lo indica.
"""

import math
import os
import sys
import time
import sqlite3
import subprocess
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime, timezone, timedelta

try:
    import pandas as pd
    HAVE_PD = True
except Exception:
    HAVE_PD = False

try:
    import winsound
    HAVE_SOUND = True
except Exception:
    HAVE_SOUND = False

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = None  # fallback: EDT (UTC-4) mas abajo

from ib_insync import IB, Stock, Option, LimitOrder, util


def now_et():
    """Hora actual en ET. Usa zoneinfo; si no hay tzdata, cae a EDT (UTC-4)."""
    if _ET is not None:
        return datetime.now(_ET)
    return datetime.now(timezone.utc) + timedelta(hours=-4)

# ----------------------- CONFIG (editable) -----------------------
HOST = "127.0.0.1"
PORT = 4002          # IB Gateway paper. Live=4001. TWS: 7497 paper / 7496 live.
CLIENT_ID = 7
SYMBOL = "SPY"
SIGNAL_THRESHOLD = 5000.0   # US$ de premium neto para cambiar de estado (anti-parpadeo)
REFRESH_SECS = 1.0
# Aviso anticipado de "posible giro" (heuristica de momentum):
WARN_BAND_FRAC = 0.6
MOMENTUM_SECS = 30.0        # GAP 5: el momentum se mide en SEGUNDOS, no en numero de muestras.
                            # Antes era MOMENTUM_WIN=8 EVENTOS: en una rafaga esas 8 muestras se
                            # llenan en milisegundos y en calma son identicas -> el valor era
                            # bimodal (0 o enorme) y nunca media una tendencia. Efecto medido el
                            # 2026-08-10: el aviso WARN y el FLIP salieron en el MISMO milisegundo
                            # (09:30:13,650 y 12:20:37,624), o sea que no anticipaba nada.
MOMENTUM_MIN = 3000.0
ENABLE_SOUND = False        # SOLO banner visual (sin sonido)
ENABLE_TOAST = True         # notificacion nativa de Windows (esquina inferior derecha)
# Linea base (fechas posteriores):
ITM_DEPTH = 3               # ademas del ATM, cuantos strikes ITM por lado
BASELINE_EXPIRIES = 3       # cuantas expiraciones FUTURAS seguir (posteriores a la cercana)
SNAPSHOT_SECS = 120         # cada cuanto persistir el acumulado en la BD
OPEN_JUMP_FACTOR = 1.5      # si hoy supera prev*este factor -> marca "cambio fuerte"
# --- Umbrales ADAPTATIVOS (auto-ajuste a la magnitud real) ---
ADAPTIVE = True
ADAPT_FRAC = 0.15           # umbral = ADAPT_FRAC * (|net_call|+|net_put|)
MOM_FRAC = 0.6             # momentum minimo = MOM_FRAC * umbral
# --- EJECUCION AUTOMATICA (rotar 1 opcion) ---
TRADING_ENABLED = True      # ARRANCA ARMADO (2026-08-10, orden del usuario). Boton = DESARMAR.
QTY = 1                     # contratos por señal (cuenta pequeña)
# --- QUE STRIKE SE OPERA (2026-08-12) -----------------------------------------------------
# EL PROBLEMA, MEDIDO CON PRECIOS REALES DE HOY: el sistema compraba el ATM, que es casi todo
# valor TEMPORAL, asi que se evapora aunque la direccion acierte. Con el SPY QUIETO 5 horas
# (773.53 -> 773.56):
#     765C ITM  8.57 -> 8.59   -0.1%     <- no pierde practicamente nada
#     770C ITM  3.91 -> 3.57   -8.7%
#     773C ATM  1.71 -> 0.82  -51.8%     <- lo que se compraba
#     775C OTM  0.79 -> 0.12  -85.4%
# Y la MISMA operacion #12 (misma entrada 10:25, misma salida), solo cambiando el strike:
#     769C ITM  +53.00 (capital 406$)    770C ITM  +39.00 (capital 318$)
#     773C ATM  -27.00 (capital 110$)    775C OTM  -27.00 (capital  38$)
# Con 400$ de cuenta, el 770C CABE y convierte -27.00 en +39.00.
# El ITM tiene valor INTRINSECO, que no se evapora: es lo que hace viable AGUANTAR una
# tendencia larga en un 0DTE en vez de tener que cobrar rapido.
# Se compra el ITM MAS PROFUNDO QUE QUEPA en el capital. Si no hay precio o no hay capital
# conocido, se cae al ATM de siempre (regla 13: no inventar).
EJECUCION_ITM = True        # False -> ATM, el comportamiento anterior
CAPITAL_FRAC_MAX = 0.80     # fraccion maxima del capital disponible en UN contrato
REPRICE_SECS = 4.0          # re-precia al mid si no llena en este tiempo
MAX_FILL_SECS = 60.0        # tiempo maximo intentando llenar una entrada
USAR_M1 = True              # 2026-08-11: disparador de flips = M1. False -> criterio diff/thr.
# --- DISPARADOR POR DISTANCIA A LA MEDIA CORTA (2026-08-12) --------------------------------
# QUIEN DECIDE A PARTIR DE AHORA. M1/M2/CLASICO/CONFIRMACION siguen calculandose y guardandose
# en sus 5 tablas EXACTAMENTE igual; solo dejan de decidir, como el 08-11 dejo de decidir
# diff/thr. Con USAR_MEDIA=False el comportamiento vuelve a ser el de M1 (interruptor A/B).
#
# POR QUE SE CAMBIA, medido: M1 no predice a la escala en que se opera. Lift sobre la tasa base
# del dia = +0.6 / -0.1 / +1.8 / +1.6 a 5/10/15/30 min (n~320 minutos): ruido. Y el 08-12 dijo
# UP en 353 de 383 minutos SIN GIRAR NUNCA, con el SPY cerrando -2.26: una sola posicion de
# 5h20m mientras pasaban 15 movimientos fuertes. Ademas RETARDO_M1_MIN=20 es mayor que la
# duracion MEDIANA de un tramo (10 min): llegar tarde no es mala suerte, es aritmetica.
#
# LA REGLA. Es CONTRAINTUITIVA, leerla dos veces:
#     SPY - media >= +MEDIA_DIST  ->  el precio esta ALTO  ->  PUT  (estado DOWN)
#     SPY - media <= -MEDIA_DIST  ->  el precio esta BAJO  ->  CALL (estado UP)
# Se compra HACIA la media, no a favor del movimiento. Seguir el movimiento esta MEDIDO y
# MUERTO: breakout 0% de 27 combinaciones positivas, zigzag 7%, perdiendo -321 a -398$.
# Revertir sale 6x mejor (reversor 41%, extremo 44%). Encaja con la reversion a la media ya
# medida en dos series independientes (r=-0.35 en dia lateral).
#
# ⚠️ `ta_vals["vwap"]` NO ES UN VWAP. Es ((high+low+close)/3).rolling(5).mean() -- una SMA de 5
# periodos del precio tipico, SIN volumen (ver TAEngine.compute). El nombre viene del bot
# original. Lo que funciona es la MEDIA CORTA; queda pendiente probar el VWAP de verdad.
#
# RESULTADO con ejecucion realista (señal de la vela cerrada, se compra al minuto siguiente):
#     08-11 +109.20$ | 08-12 +222.66$ | 2 dias +331.86$ en 37 operaciones
#     (el sistema real hizo -76.44$ el 08-12; el techo de ese dia era +947$)
# Entrar en el mismo minuto daria +468$, pero eso es look-ahead: en vivo el dato de la vela X
# se conoce en X+1. Se planifica con el suelo, no con el techo.
#
# CONTROLES PASADOS (los mismos que mataron a los otros 5 candidatos):
#   - Tautologia: +6.8/+6.5 contra `extremo del rango 30` +5.3/+4.5, `SMA30` +2.5/+4.5 y
#     `distancia al medio del dia` +2.3/+1.6. Gana a las 4 lineas base tontas en los DOS dias.
#   - Nula por desplazamiento circular: 0 de 10 la superan, mediana -4 (sin sesgo estructural).
#   - AZAR con la MISMA exposicion al mercado: 300 semillas, mediana -127$, solo 25% positivas.
#     3 de 300 igualan o superan a la señal -> p = 0.0100.
#   - Direccional: siempre-CALL -360$, siempre-PUT -3$. Ninguna direccion fija gana.
#   - Robustez (§7): con salida a 8 min, los umbrales 0.20-0.28 son positivos en LOS DOS dias.
#     Los umbrales bajos (0.12/0.16) dan mas suma pero FALLAN el 08-11: no se cogen.
#
# ⚠️ MUESTRA: 2 dias (08-12 completo, 08-11 solo desde las 11:48) y 37 operaciones. p=0.01 es
# significativo pero NO es una validacion. La confirmacion es la primera sesion nueva.
USAR_MEDIA = True           # False -> decide M1 (comportamiento anterior, A/B limpio)
MEDIA_DIST = 0.20           # |SPY - media| que dispara. Region medida valida: 0.20-0.28
MINUTOS_POS = 8             # minutos en posicion antes de vender. t8 es la UNICA columna que
                            # aguanta con ejecucion realista (t6/t10/t12/t15 se vuelven erraticas)
CONFIRMACION_MIN = 5        # 2026-08-12: filtro de confirmacion (SOLO REGISTRO, no decide): la SEÑAL
                            # del minuto debe aguantar N min seguidos para "confirmar". D=5 mata las
                            # rotaciones de <=4 min medidas. HIPOTESIS ajustable con mas datos.
# --- ENTRADA POR RETROCESO segun REGIMEN (2026-08-12) -------------------------------------
# POR QUE: medido este dia, los maximos a favor llegan ENSEGUIDA (trades #9/#10/#11 tocaron su
# MFE a los 88s, 62s y 545s de entrar; la CALL #12 al minuto siguiente). Entrar en el impulso es
# comprar el maximo local. Y la reversion a la media es REAL -- aparece con la misma magnitud en
# las barras del SPY y en el precio implicito por paridad, o sea que no es rebote bid-ask -- pero
# depende del REGIMEN: r=-0.35 el 08-12 (dia lateral) frente a r=-0.06 el 08-11 (con tendencia).
# Por eso NINGUN parametro fijo de espera sirve: lo que hay que hacer dinamico es leer el regimen.
#
# ⚠️ NO VERIFICADO que mejore el sistema REAL. La medicion es sobre 138 entradas/dia simuladas
# con un disparador de momentum, NO sobre los flips de M1 (n=4 el 08-12; el 08-11 tiene 7 flips
# pero todos antes de las 11:48 y ese dia no hay precios de opcion hasta las 11:48). Se activa en
# cuenta PAPER por decision explicita del usuario para medirlo en vivo.
#
# INVARIANTES: solo RETRASA. Nunca cancela (al llegar al tope entra igual), nunca cambia de
# direccion, nunca anade operaciones. Con ENTRADA_RETROCESO=False el comportamiento es el de antes.
# --- OBJETIVO DE BENEFICIO (2026-08-12) ---------------------------------------------------
# EL PROBLEMA, EN DINERO: hasta hoy solo se vendia al girar M1, asi que el beneficio disponible
# se devolvia entero. Medido sobre las 4 operaciones REALES del 2026-08-12, con el mid real
# minuto a minuto y SIN cambiar ni una entrada:
#     MFE alcanzado por cada una:  +42.00  +11.00  +37.00  +21.50
#     dia REAL (como se opero) .....................  -44.50
#     con objetivo +5$  -> +20.00     +10$ -> +28.00     +15$ -> +43.00     +20$ -> +58.00
#     con objetivo +25$ -> -3.50  (se cae: la 4a operacion nunca llego a +25)
# Se elige 10 y NO el que mas da: 10 es el objetivo mas alto que TODAS alcanzaron (el MFE
# minimo fue +11). Por encima, el resultado depende de que una operacion concreta llegue o no,
# que es ajustar al dia que se esta usando para juzgarlo (INVESTIGACION_M1_M2 §7).
# 0 o None lo desactiva y el comportamiento vuelve a ser el anterior.
#
# ⚠️ 2026-08-12, MISMO DIA: el objetivo fijo queda a 0 (DESACTIVADO) y NO se sustituye por
# nada. El objetivo fijo PONE TECHO: el 08-11 una sola operacion llego a +122.36 y con
# objetivo +10 se habrian cobrado 10.
TAKE_PROFIT_USD = 0.0

# --- SALIDA POR OBJETIVO / TRAILING: MEDIDO Y **NO IMPLEMENTADO** --------------------------
# Aqui vivian TRAIL_ACTIVAR_USD=10.0 y TRAIL_DEVOLVER_USD=5.0. Se eliminan el 2026-08-12
# porque NINGUN punto del codigo las leia: no habia trailing, solo dos numeros que hacian
# creer que lo habia. Un parametro que nadie consume es peor que no tenerlo -- se lee como
# configuracion vigente y las decisiones que salen de leerlo salen torcidas.
# COMPROBADO ese mismo dia: las 3 operaciones cerradas salieron las tres con
# razon_salida='giro'. La UNICA salida que existe hoy es el giro de la senal (mas el EOD).
#
# LO QUE SE MIDIO (se conserva: costo medirlo, y es el punto de partida si algun dia se
# implementa). Sobre un recorrido que sube a +122 y devuelve la mitad:
#     fijo+10 -> +10.00  |  aguantar -> +61.00  |  trailing(10,5) -> +115.00
# Y en las 4 operaciones REALES del 08-12: trailing +37.50 vs fijo +28.00. Las variantes
# (10,5), (10,10) y (15,8) daban las tres +37.50 -> el resultado no dependia de acertar el
# numero exacto, que es la propiedad que se buscaba (INVESTIGACION_M1_M2 §7).
#
# POR QUE NO ESTA PUESTO, decision explicita del usuario: con opciones el trailing salta con
# el RUIDO del mid (un spread de 0.01 es 1$ por tick). Lo que se quiere es salir cuando la
# tendencia se ACABA, no cuando el mid tiembla. Si se implementa algun dia, reutilizar
# `self.mfe`, que ya se sigue a 1 Hz: no hace falta estado nuevo.

# ⚠️ 2026-08-12, MISMO DIA: se APAGA. El discriminador que la gobierna (ER_UMBRAL sobre el
# efficiency ratio) NO separa regimen: medido, no distingue el dia lateral del dia con tendencia,
# asi que la compuerta se abria y se cerraba sin relacion con lo que hacia el precio. Al no
# cancelar nunca (tope de RETRO_MAX_MIN), no hacia dano -- solo retrasaba hasta 10 min -- pero
# tampoco aportaba, y un parametro que no aporta es ruido que estorba al juzgar el resto.
# La tabla `entrada_minute` SIGUE registrando er/regimen/impulso con activo=0: se conserva la
# medicion del "que habria hecho" sin dejar que actue.
ENTRADA_RETROCESO = False   # APAGADO. True -> compuerta de retroceso activa (ver arriba).
RETRO_FRAC = 0.50           # retroceso exigido, como fraccion del impulso previo
RETRO_MAX_MIN = 10          # TOPE de espera en minutos: si no llega el retroceso, SE ENTRA IGUAL
ER_UMBRAL = 0.30            # efficiency ratio: < umbral = REVERSION (esperar); >= = TENDENCIA
ER_VENTANA = 30             # minutos de la ventana del efficiency ratio
IMPULSO_VENTANA = 5         # minutos sobre los que se mide el impulso previo al giro

RETARDO_M1_MIN = 20         # 2026-08-11: minutos de RETARDO al aplicar M1. El sistema se
                            # posiciona segun lo que M1 decia hace RETARDO_M1_MIN minutos, en
                            # entrada Y en salida. 0 = sin retardo (aplicar al instante).
                            # OJO (medido, investigacion/INVESTIGACION_M1_M2.md §7): con n=7
                            # operaciones el 20 fue el mejor de 12 valores probados, y la mejora
                            # viene de comprar puts mas arriba en dos dias BAJISTAS, no de
                            # anticipacion. Es una hipotesis a comprobar, no un resultado.
FLATTEN_HHMM = "15:45"      # ET: cerrar cualquier opcion abierta
STOP_NEW_HHMM = "15:40"     # ET: no abrir nuevas cerca del cierre
START_TRADE_HHMM = "09:30"  # ET: NO abrir posiciones antes de esta hora. 2026-08-12: el usuario
                            # QUITA el retardo (estaba en 09:35) -> se puede abrir desde la
                            # apertura. Lo que motivo el retardo ya no aplica igual: los 5 giros
                            # en 90 s del 2026-08-10 venian del umbral adaptativo con el acumulado
                            # vacio, y desde el 2026-08-11 el disparador es M1 (USAR_M1=True), que
                            # solo puede girar en el cambio de MINUTO y ademas usa el estado de
                            # hace RETARDO_M1_MIN. Ese retardo de 20 min sigue vigente y es OTRO:
                            # en la practica la primera entrada no llega hasta que M1 tiene 20 min
                            # de historia. Historico del motivo original (2026-08-11, peticion del
                            # usuario). Motivo con datos del 2026-08-10: en los primeros 90 s hubo
                            # 5 GIROS (09:30:06 UP, :13 DOWN, :30 UP, :37 DOWN, 09:31:14 UP). El
                            # umbral es adaptativo -thr = ADAPT_FRAC*(|net_call|+|net_put|)- y con
                            # el acumulado casi vacio cae al piso SIGNAL_THRESHOLD=5000, ~100x
                            # menor que el umbral maduro del dia (llego a 1,2 M): cualquier tick lo
                            # cruza y con 0DTE cada rotacion paga el spread.
                            # Es el gap M6 de MEJORAS.md atacado por la via barata: en vez de
                            # rediseñar el umbral, no operar mientras no sea fiable.
                            # OJO - solo frena ABRIR: las VENTAS no pasan por stop_new, asi que una
                            # posicion heredada se puede cerrar igual durante la espera. Y la SEÑAL
                            # se sigue acumulando desde las 09:30 (_on_ticks es independiente de
                            # trade_poll): la idea es justamente VER como se forma el acumulado.
OPEN_HHMM = "09:30"         # desde que hora se RECOLECTA.
                            # 2026-08-11 09:00-09:07: se PROBO bajarlo a "09:00" para ver si el
                            # pre-market daba algo guardable. MEDIDO CON DATOS REALES -> NO:
                            #   de 68 filas de premium_minute, day_vol>0 en 0, day_prem>0 en 0,
                            #   gamma!=0 en 0 (griegas None). Solo llegaba OI, que es de AYER (EOD).
                            #   walls_snapshot salia con GEX=0, regime=FLAT y spot=773.07 (cierre
                            #   de ayer) pese a que _read_price(SPY) SI daba 774.23: el spot de
                            #   walls viene de ta_poll (barras useRTH=True), que no existen antes
                            #   de las 09:30 -> ta_minute se quedaba en 0 filas.
                            # Conclusion: las opciones de SPY no cotizan hasta las 09:30 (OPRA) y
                            # dejarlo en 09:00 solo METIA BASURA en la BD (filas en cero con
                            # spot_stale=0, es decir marcadas como validas). Revertido.
                            # Si algun dia se reintenta, hace falta ANTES: barras con useRTH=False
                            # y marcar esas filas como pre-market para poder excluirlas.
RTH_OPEN_HHMM = "09:30"     # apertura REAL del mercado. Gobierna (a) cuando se puede OPERAR y
                            # (b) desde cuando exigirle frescura al stream de barras: con
                            # useRTH=True las barras NO avanzan antes de esta hora, asi que
                            # vigilarlas en pre-market daria un GAP 17 falso y repediria el
                            # stream cada BARS_RETRY_SECS -> riesgo de pacing violation (162/420).
CLOSE_HHMM = "16:15"        # hasta que hora se RECOLECTA (no se opera: eso acaba a las 15:45).
                            # 2026-08-10: se subio de 16:00 a 16:15 para MEDIR si las opciones
                            # de SPY siguen negociandose esos 15 min. Es una PRUEBA: si el
                            # volumen no avanza entre 16:00 y 16:15, se vuelve a 16:00.
CROSS_HHMM = "15:55"        # GAP 4: ULTIMO RECURSO. Solo en los ultimos 5 minutos las VENTAS
                            # cruzan el spread (van al BID). Antes de esa hora se insiste al MID
                            # recotizando rapido: ir al BID es regalar el spread y el usuario NO
                            # lo quiere salvo cuando ya no queda tiempo. A las 16:00 end_session
                            # cancela y desconecta: una 0DTE sin vender EXPIRA valiendo 0.
EOD_REPRICE_SECS = 12.0     # de FLATTEN_HHMM en adelante: recotizar al MID hasta que llene.
                            # CORREGIDO 2026-08-10 (era 1.5 y provoco el GAP 19): "rapido" NO
                            # puede significar mas rapido que la latencia del broker. Medido:
                            # latencia de fill mediana 1 s con cola de 25 s, y hoy una
                            # cancelacion tardo 21 s en resolverse (15:45:01 -> 15:45:22).
                            # Recotizar antes NO acelera el llenado: solo multiplica ordenes
                            # en vuelo. Con el cruce a las 15:55 quedan 10 min = ~50 intentos.
CANCEL_SETTLE_SECS = 10.0   # GAP 19: tras CANCELAR, no colocar NADA nuevo durante este tiempo,
                            # AUNQUE IBKR diga que la orden ya esta cancelada. El 2026-08-10 a
                            # las 15:45 IBKR reporto `Cancelled` (estado FINAL), la orden
                            # desaparecio de openTrades()... y se ejecuto 16 s despues. En ese
                            # instante NO habia ningun estado que consultar que lo evitara:
                            # la unica defensa posible es el reloj. Mismo principio que
                            # BUY_SETTLE_SECS, que ya cubria las COMPRAS pero no las ventas.
                            # NO CALIBRADO: con la latencia real de varias sesiones se ajusta.
RECONNECT_SECS = 15.0       # espera entre reintentos si se cae el socket (no saturar el Gateway)
SYNC_POS_SECS = 20.0        # cada cuanto re-sincronizar la posicion CONTRA IBKR (la realidad manda)
STRIKE_REFRESH_SECS = 20.0  # cada cuanto re-centrar senal/ejecucion/banda al precio actual
BUY_SETTLE_SECS = 25.0      # margen para que aterricen fills tardios antes de liberar el cupo
                            # de compra (medido 2026-08-10: IBKR lleno una orden 22 s DESPUES
                            # de reportarla como cancelada)
# --- registro del recorrido de la posicion (tabla posicion_minuto) ---
POS_LOG_SECS = 60.0         # muestreo del contrato mientras la posicion esta viva. La entrada y
                            # la salida se graban SIEMPRE aparte: con permanencia mediana de 47 s
                            # el 60% de las operaciones no llegan a generar una fila de minuto.
# --- GAP 17: salud del stream de barras (fuente de spy_price y del TA) ---
BARS_STALE_SECS = 120.0     # sin avance de bars[-1].date -> stream muerto. El doble de la barra
                            # (1 min) para no dar falso positivo en un minuto sin trades.
BARS_RETRY_SECS = 30.0      # espera entre intentos de reponer. Repedir sin freno provoca pacing
                            # violations de IBKR (162/420), que es peor que el fallo original.
TAPE_ENABLED = True         # 2026-08-11: guardar UNA FILA POR OPERACION en la tabla `tape`.
                            # Motivo: el agregado por minuto hacia indistinguible un print
                            # institucional de 3.038 contratos de 50 operaciones de retail de 60
                            # (mismo dvol, mismo premium), y borraba por promediado cualquier
                            # señal mas rapida que 1 minuto. tk.lastSize SI trae el tamaño de la
                            # operacion (verificado en vivo: last=0.9 lastSize=2.0).
                            # SOLO REGISTRO: no toca la señal ni la ejecucion. Ponerlo a False
                            # desactiva la escritura sin afectar a nada mas.
TAPE_FLUSH_N = 400          # volcado por lotes: _on_ticks corre en el hilo de Tkinter y a alta
                            # frecuencia, asi que un INSERT por tick bloquearia la GUI. Se
                            # acumula en memoria y se vuelca con executemany al llegar a este
                            # tamaño o en el registro del minuto, lo que ocurra antes.
BARS_DURATION = "2 D"       # historia que se pide en cada reqHistoricalData de 1 min.
                            # 2026-08-11: era "1 D". Se sube a "2 D" (orden del usuario) para que
                            # la SMA200 exista DESDE EL PRIMER MINUTO de sesion; con "1 D" no
                            # habia 200 barras hasta ~12:50 y la columna quedaba NULL media
                            # sesion. Medido contra IBKR con keepUpToDate=True:
                            #   "1 D"->52 barras (a las 10:21) · "2 D"->442 · "3 D"->832 · "1 W"->1612
                            # ⚠️ CORTE DE COMPARABILIDAD: los indicadores que ARRASTRAN desde el
                            # inicio de la serie cambian de valor respecto a los ya guardados:
                            #   - ema8 / ema21 / ema50 (ewm recorre toda la serie)
                            #   - obv_trend (acumulado desde la 1a barra)
                            # NO cambian los de ventana fija una vez hay N barras: rsi(14),
                            # atr(14), bollinger(20), vwap(5), sma20/50/200.
                            # Al analizar, tratar los datos anteriores al 2026-08-11 10:30 como
                            # un tramo distinto para esas columnas (ver sesion_config).
# --- Walls / GEX / Gamma Flip (informativo, "como el TA": se guarda y se analiza vs la grafica) ---
WALLS_ENABLED = True        # calcular walls/GEX/flip. NO toca la senal UP/DOWN ni la ejecucion.
WALLS_BAND = 10             # strikes a CADA lado del precio a escanear (banda). Bajo por limite de lineas IBKR.
WALLS_RECALC_SECS = 180.0   # cada 3 min: snapshot de la banda (no satura el gateway; MarketSnack usa 5 min)
# Convencion de signo del GEX (dealers +gamma calls / -gamma puts). HIPOTESIS estandar: validar vs precio real.
GEX_CALL_SIGN = 1.0
GEX_PUT_SIGN = -1.0
# ----------------------------------------------------------------


def _fmt(x):
    """Formato None-safe para logs/pantalla."""
    return f"{x:.2f}" if isinstance(x, (int, float)) else "-"


def _money(v):
    """Formato compacto de dinero: 1.2M / 34k / 120."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{v / 1e3:.0f}k"
    return f"{v:.0f}"


def _max_pain(call_oi, put_oi):
    """Strike de Max Pain (minimiza el pago total) a partir del OI. Funcion pura.
    call_oi/put_oi: dict strike->OI. Devuelve el strike o None. NO usa el spot."""
    strikes = sorted(set(call_oi) | set(put_oi))
    if not strikes:
        return None
    best_k, best_pay = None, None
    for K in strikes:
        pay = (sum(call_oi.get(s, 0) * max(0.0, K - s) for s in strikes)
               + sum(put_oi.get(s, 0) * max(0.0, s - K) for s in strikes))
        if best_pay is None or pay < best_pay:
            best_pay, best_k = pay, K
    return best_k


def compute_walls_from_oi(call_oi, put_oi, spot, call_gamma=None, put_gamma=None):
    """Funcion pura y testeable. call_oi/put_oi: dict strike->OI. Devuelve walls + max pain.

    Si se pasan los gamma, las walls se ponderan por EXPOSICION GAMMA (gamma*OI) en vez de
    por OI puro. Motivo (verificado con datos reales 2026-08-10): el OI que da IBKR es de
    CIERRE del dia anterior y no se mueve intradia, mientras que el gamma SI es en vivo.
    Con OI puro la wall se quedaba clavada en el strike con mas contratos aunque estuviera
    lejos del precio (780, OI=13144, gamma=0.025 -> 19.744 M) en vez del que realmente
    manda (775, OI=10945, gamma=0.1726 -> 113.346 M). Es el criterio que usa MarketSnack."""
    strikes = sorted(set(call_oi) | set(put_oi))
    if not strikes:
        return None

    def _peso(oi_map, g_map):
        """gamma*OI si hay gamma utilizable; si no, OI puro (compatibilidad)."""
        if not g_map:
            return dict(oi_map)
        out = {}
        for k, oi in oi_map.items():
            g = g_map.get(k)
            if g is None or (isinstance(g, float) and math.isnan(g)):
                return dict(oi_map)      # gamma incompleto -> no mezclar criterios
            out[k] = oi * g
        return out

    pw_map = _peso(put_oi, put_gamma)
    cw_map = _peso(call_oi, call_gamma)
    put_wall = max(pw_map, key=lambda k: pw_map.get(k, 0)) if pw_map else None
    call_wall = max(cw_map, key=lambda k: cw_map.get(k, 0)) if cw_map else None
    return {"put_wall": put_wall, "call_wall": call_wall,
            "max_pain": _max_pain(call_oi, put_oi), "spot": spot}


def compute_prem_center(weight_by_strike):
    """Centro de masa (strike) ponderado por la MAGNITUD de dinero por strike = 'hacia donde
    hay mas peso'. weight_by_strike: dict strike->$ (se usa |valor|). Funcion pura."""
    num = den = 0.0
    for K, w in weight_by_strike.items():
        a = abs(w)
        num += K * a
        den += a
    return (num / den) if den > 0 else None


def compute_gex_from_greeks(call_oi, put_oi, call_gamma, put_gamma, spot,
                            call_sign=1.0, put_sign=-1.0):
    """GEX (Gamma Exposure) neto y Gamma Flip. Funcion pura y testeable.
    - GEX por strike = 100 * spot^2 * (call_sign*gamma_c*OI_c + put_sign*gamma_p*OI_p)
    - gex_total>0 -> dealers LONG gamma (mean-reverting) ; <0 -> SHORT gamma (tendencial)
    - gamma_flip (PROXY): strike donde la suma ACUMULADA por strike del GEX neto cruza cero
      (interpolado). Aprox: no repreciamos gamma por cada S (no hay BS aqui). Documentado.
    Devuelve dict o None si no hay datos."""
    strikes = sorted(set(call_oi) | set(put_oi) | set(call_gamma) | set(put_gamma))
    if not strikes:
        return None
    factor = 100.0 * spot * spot
    per = {}
    gex_total = 0.0
    for K in strikes:
        g = 0.0
        cg = call_gamma.get(K)
        pg = put_gamma.get(K)
        if cg is not None and not math.isnan(cg):
            g += call_sign * cg * call_oi.get(K, 0)
        if pg is not None and not math.isnan(pg):
            g += put_sign * pg * put_oi.get(K, 0)
        per[K] = g * factor
        gex_total += per[K]
    regime = "LONG" if gex_total > 0 else ("SHORT" if gex_total < 0 else "FLAT")
    # gamma flip (proxy): cruce por cero de la acumulada por strike
    flip = None
    cum = 0.0
    cum_vals = []
    for K in strikes:
        cum += per[K]
        cum_vals.append((K, cum))
    for i in range(1, len(cum_vals)):
        k0, c0 = cum_vals[i - 1]
        k1, c1 = cum_vals[i]
        if (c0 <= 0.0 <= c1) or (c0 >= 0.0 >= c1):
            flip = k0 + (0.0 - c0) / (c1 - c0) * (k1 - k0) if c1 != c0 else k1
            break
    return {"gex_total": gex_total, "regime": regime, "gamma_flip": flip,
            "spot": spot, "gex_by_strike": per}


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class _RotacionTolerante(TimedRotatingFileHandler):
    """TimedRotatingFileHandler que NO se queda mudo si la rotacion falla.

    Por que existe (2026-08-11, medido en vivo): en Windows, renombrar un fichero que otro
    proceso tiene ABIERTO lanza PermissionError. Basta un `tail`, un editor o un script de
    monitorizacion leyendolo para que `doRollover()` reviente. El handler estandar deja
    entonces el stream cerrado y **todos los registros posteriores se pierden en silencio**:
    la app parece funcionar, la BD se llena, y el log no vuelve a escribir una linea.
    Ocurrio hoy entre las 09:00 y las 09:32 (32 minutos de traza perdidos) porque el monitor
    tenia abierto spy_activity.log.

    Aqui, si la rotacion falla: se avisa EN EL PROPIO LOG, se reabre el fichero actual y se
    sigue escribiendo. Se pierde la rotacion de ese dia (el fichero crece de mas), que es un
    problema muchisimo menor que quedarse ciego. Se reintentara en el proximo rollover.
    """

    def doRollover(self):
        try:
            super().doRollover()
        except Exception as e:
            # reabrir el fichero actual: sin esto el stream queda cerrado y no se escribe mas
            try:
                if self.stream:
                    self.stream.close()
            except Exception:
                pass
            self.stream = self._open()
            # calcular el proximo intento para no reintentar en cada linea
            try:
                self.rolloverAt = self.computeRollover(int(time.time()))
            except Exception:
                pass
            try:
                self.stream.write(
                    "%s WARNING ROTACION DEL LOG FALLIDA (%s: %s). Alguien tiene el fichero "
                    "ABIERTO (tail/editor/monitor). Se SIGUE escribiendo en el fichero actual; "
                    "el log de ayer no se archivo. Cierra ese proceso.\n"
                    % (datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3],
                       type(e).__name__, e))
                self.stream.flush()
            except Exception:
                pass


def _make_logger(name, filename):
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    lg.propagate = False
    try:
        h = _RotacionTolerante(os.path.join(_app_dir(), filename),
                               when="midnight", backupCount=120, encoding="utf-8")
    except Exception:
        h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    lg.addHandler(h)
    return lg


# LOG = errores/excepciones ; ACT = actividad exhaustiva del dia (que hizo el sistema)
LOG = _make_logger("spyd", "spy_direction.log")
ACT = _make_logger("spyd.act", "spy_activity.log")


def _excepthook(exctype, value, tb):
    LOG.error("EXCEPCION NO CAPTURADA", exc_info=(exctype, value, tb))


sys.excepthook = _excepthook


class TAEngine:
    """Replica del TA del bot (src/ta/indicators.py) aplicado a barras de 1 min:
    RSI(14), EMA(8/21/50), MACD(12/26/9), Bollinger(20,2), ATR(14), VWAP aprox, OBV."""

    def compute(self, df):
        if not HAVE_PD or df is None or len(df) < 26:
            return None
        close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = float((100.0 - 100.0 / (1.0 + rs)).iloc[-1])
        ema8 = float(close.ewm(span=8, adjust=False).mean().iloc[-1])
        ema21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        e12 = close.ewm(span=12, adjust=False).mean()
        e26 = close.ewm(span=26, adjust=False).mean()
        macd_line = e12 - e26
        macd_sig = macd_line.ewm(span=9, adjust=False).mean()
        ml = float(macd_line.iloc[-1]); ms = float(macd_sig.iloc[-1]); mh = ml - ms
        # --- SMA 20/50/200 (2026-08-11, peticion del usuario). Solo se REGISTRAN. ---
        # rolling() y NO ewm(): con menos de N barras devuelve NaN, y aqui se convierte a None
        # -> la columna queda NULL, que es la verdad. Con ewm(span=200) sobre 52 barras saldria
        # un numero que PARECE valido y contaminaria la BD en silencio.
        # Con "1 D" (max 390 barras de RTH) la SMA200 no existe hasta ~12:50; es correcto que
        # falte. Para tenerla desde el minuto 1 habria que pedir "2 D", pero eso cambiaria los
        # valores de ema8/21/50 y obv (arrastran desde el inicio de la serie) y rompe la
        # comparabilidad con lo ya guardado. Decision: preferir NULL a un dato incomparable.
        def _sma(n):
            v = close.rolling(n).mean().iloc[-1]
            return None if pd.isna(v) else float(v)

        sma20, sma50, sma200 = _sma(20), _sma(50), _sma(200)
        sma = close.rolling(20).mean(); sd = close.rolling(20).std()
        bb_up = float((sma + 2 * sd).iloc[-1]); bb_mid = float(sma.iloc[-1])
        bb_low = float((sma - 2 * sd).iloc[-1])
        tr = pd.concat([high - low, (high - close.shift()).abs(),
                        (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        price = float(close.iloc[-1])
        atr_pct = (atr / price) * 100.0 if price else 0.0
        vwap = float(((high + low + close) / 3.0).rolling(5).mean().iloc[-1])
        obv = [0.0]
        cl = close.values; vv = vol.values
        for i in range(1, len(cl)):
            if cl[i] > cl[i - 1]:
                obv.append(obv[-1] + vv[i])
            elif cl[i] < cl[i - 1]:
                obv.append(obv[-1] - vv[i])
            else:
                obv.append(obv[-1])
        obv_s = pd.Series(obv)
        ma_obv = float(obv_s.rolling(20).mean().iloc[-1]); cur = float(obv_s.iloc[-1])
        if ma_obv and cur > ma_obv * 1.05:
            obv_trend = "bullish"
        elif ma_obv and cur < ma_obv * 0.95:
            obv_trend = "bearish"
        else:
            obv_trend = "neutral"
        # scores (identicos al bot)
        r = rsi
        s_rsi = 3 if r < 25 else 2 if r < 35 else 1 if r < 45 else 0 if r <= 55 else -1 if r <= 65 else -2 if r <= 75 else -3
        rng = bb_up - bb_low
        s_bb = 2 if (rng > 0 and price <= bb_low + rng * 0.2) else (-2 if (rng > 0 and price >= bb_up - rng * 0.2) else 0)
        sc = {
            "rsi": s_rsi,
            "ema": 2 if ema8 > ema21 else -2,
            "macd": 2 if mh > 0 else -2,
            "bb": s_bb,
            "atr": 1 if atr_pct > 1.0 else (-1 if atr_pct < 0.3 else 0),
            "vwap": 1 if price > vwap else -1,
            "obv": 1 if obv_trend == "bullish" else (-1 if obv_trend == "bearish" else 0),
        }
        total = sum(sc.values())
        bull = sum(1 for v in sc.values() if v > 0)
        bear = sum(1 for v in sc.values() if v < 0)
        dirn = "BULL" if total > 0 else ("BEAR" if total < 0 else "NEUTRAL")
        return {"close": price, "rsi": rsi, "ema8": ema8, "ema21": ema21, "ema50": ema50,
                # SMA 20/50/200: SOLO se registran, NO entran en `sc` ni en el score/dir. La
                # decision de compra/venta sigue siendo unicamente el premium.
                "sma20": sma20, "sma50": sma50, "sma200": sma200,
                "macd_line": ml, "macd_signal": ms, "macd_hist": mh,
                "bb_up": bb_up, "bb_mid": bb_mid, "bb_low": bb_low,
                "atr": atr, "atr_pct": atr_pct, "vwap": vwap, "obv_trend": obv_trend,
                "score": total, "dir": dirn, "bull": bull, "bear": bear}


class SpyDirection:
    def __init__(self, demo=False):
        self.ib = IB()
        self.demo = demo
        self.demo_i = 0
        self.mode = "DEMO" if demo else "?"
        self.spy_price = float("nan")
        self.expiry = None            # vencimiento mas cercano (para la señal)
        self.call = None              # ATM/ITM call (señal)
        self.put = None               # ATM/ITM put (señal)
        self.net_call = 0.0
        self.net_put = 0.0
        # --- M1 / M2: contadores de la investigacion (2026-08-11) ---
        self.m1_up = 0; self.m1_down = 0        # contador de MINUTOS
        self.m2_up = 0.0; self.m2_down = 0.0    # contador de DOLARES
        self.m1_estado = None; self.m2_estado = None
        self.m1_racha = 0; self.m2_racha = 0
        self.m_recentrado = 0                   # 1 si hubo re-centrado en el minuto en curso
        self.cl_estado = None; self.cl_racha = 0   # metodo ANTIGUO (diff/thr), solo registro
        self.sen_estado = None; self.sen_racha = 0   # SEÑAL del minuto (para la confirmacion)
        self.conf_estado = None                      # SEÑAL CONFIRMADA (aguanto CONFIRMACION_MIN), solo registro
        self.conf_hist = []; self.conf_efectivo = None
        self.m1_hist = []             # [(monotonic, estado)] para aplicar M1 con RETARDO_M1_MIN
        self.m1_efectivo = None       # lo que M1 decia hace RETARDO_M1_MIN minutos
        self.m2_hist = []; self.m2_efectivo = None   # igual para M2 (solo registro)
        self.cl_hist = []; self.cl_efectivo = None   # igual para el CLASICO (solo registro)
        self.prev_vol = {}            # conId -> volumen acumulado previo (delta)
        self.state = "-"
        self.transitions = []
        self.status = "Iniciando..."
        # alertas
        self.alert_text = ""
        self.alert_kind = ""
        self.alert_until = 0.0
        self.pending_sound = None
        self.last_warn_side = None
        # --- linea base (fechas posteriores) ---
        self.info_base = {}           # conId -> (expiry, strike, right)
        self._base_ct = {}            # conId -> contrato de la linea base (hace falta el
                                      # OBJETO para poder soltar su market data despues)
        self.accum = {}               # (expiry,strike,right) -> premium acumulado (persistente, desde dia 1)
        self.today_prem = {}          # (expiry,strike,right) -> premium de HOY
        # NETO firmado, en PARALELO al bruto de arriba (que solo suma y nunca resta).
        # El bruto es actividad (hecho); el neto lleva el signo del agresor (INFERENCIA).
        self.accum_net = {}           # (expiry,strike,right) -> neto firmado acumulado (persistente)
        self.today_net = {}           # (expiry,strike,right) -> neto firmado de HOY
        self.base_prev = {}           # (expiry,strike,right) -> premium del dia previo
        self.base_expiries = []       # lista de expiraciones futuras seguidas
        self.last_snapshot = 0.0
        # --- Walls / GEX / Gamma Flip (informativo, "como el TA": se guarda por 3 min y se analiza) ---
        self.band_contracts = []      # contratos de la banda (expiracion CERCANA) para snapshot
                                      # NOTA: las greeks del contrato que se OPERA se leen del
                                      # ticker de la banda (ver _greeks_de). La banda pide
                                      # "100,101,106" (trae modelGreeks); los contratos de
                                      # EJECUCION piden "" (NO traen greeks), y ib_insync indexa
                                      # los tickers por id(OBJETO), no por conId, asi que el
                                      # ticker de buy_call/buy_put NUNCA tiene modelGreeks
                                      # aunque sea el mismo contrato de IBKR.
        self._tape_buf = []           # TAPE: filas pendientes de volcar (ver _flush_tape)
        self._tape_n = 0              # total de operaciones registradas hoy
        self._tape_err = 0            # capturas del tape que fallaron (se reportan por minuto)
        self._tape_err_last = ""      # ultimo error de captura, para el log del minuto
        self.band_prev_vol = {}       # conId -> volumen previo (delta entre lecturas de 3 min)
        self._tick_prem_ids = set()   # conIds cuyo premium YA acumulo _on_ticks al menos una vez.
                                      # La ruta de walls (_persist_walls) los salta para no contar
                                      # el mismo premium dos veces. Es DINAMICO a proposito: un
                                      # contrato que nunca llega a _on_ticks debe seguir contandose
                                      # alli en vez de quedarse a cero. No se limpia al re-suscribir
                                      # (_soltar_mkt): re-contarlo seria inflar, perder un tramo no.
        self.prev_gamma = {}          # conId -> gamma previo (detectar dato estancado/viejo)
        self.today_vol = {}           # (expiry,strike,right) -> volumen del dia (banda)
        self.net_prem = {}            # (expiry,strike,right) -> premium neto firmado ('peso' de dinero)
        self.walls = None             # dict: put_wall/call_wall/max_pain_static/max_pain_dyn/prem_center
        self.gex = None               # dict: gex_total/regime/gamma_flip
        self.last_walls_calc = 0.0
        # --- ejecucion automatica (rotar 1 opcion) ---
        self.trading = TRADING_ENABLED   # ON/OFF (boton en la GUI)
        self.buy_call = None             # contrato de EJECUCION call (ATM lado OTM: strike > precio)
        self.buy_put = None              # contrato de EJECUCION put  (ATM lado OTM: strike < precio)
        self.pos = "FLAT"                # FLAT / CALL / PUT (lo que tenemos)
        self.pos_qty = 0.0               # cantidad REAL en cartera segun IBKR (no se asume)
        self.last_sync = 0.0             # ultimo _sync_pos (la realidad de IBKR manda sobre self.pos)
        self.strikes = []                # cadena de strikes viva (para re-centrar al precio)
        self.last_strikes = 0.0          # ultimo refresh_strikes()
        # COMPRAS COMPROMETIDAS: ordenes de compra enviadas cuyo destino aun no se conoce.
        # IBKR puede llenar una orden que ya reporto como CANCELADA hasta 22 s despues
        # (medido 2026-08-10), asi que mirar solo la posicion confirmada NO basta para
        # garantizar "1 solo contrato": hay que contar tambien lo que va en vuelo.
        self.buys_pend = 0               # compras enviadas y sin resolver
        self.last_buy_ts = 0.0           # cuando se envio la ultima compra
        self.last_cancel_ts = 0.0        # GAP 19: cuando se pidio la ultima cancelacion. Hasta
                                         # que pasen CANCEL_SETTLE_SECS no se coloca nada nuevo,
                                         # aunque IBKR diga que la orden ya esta cancelada.
        self._last_order_status = None   # ultimo estado visto (para loguear los cambios)
        self.target = "FLAT"             # lado deseado segun ultima señal
        self.order = None                # Trade activo (ib_insync)
        self.order_action = None         # BUY / SELL
        self.order_side = None           # CALL / PUT
        self.order_deadline = 0.0        # monotonic: re-precia al vencer
        self.order_giveup = 0.0          # (sin uso) compatibilidad
        self.order_aggr = 0              # (sin uso) compatibilidad
        self.open_deadline = 0.0         # limite de tiempo para llenar una COMPRA (BUY)
        self.min_tick = {}               # conId -> minTick
        self._mkt_subs = set()           # conIds con market data ya pedido (evita re-suscribir)
        self._eventos_ok = False         # handlers de IBKR suscritos (una sola vez por proceso)
        self._intradia_ok = False        # ya se intento restaurar el estado del dia. Hasta que
                                         # sea True NO se persiste: si setup_contracts fallara
                                         # antes de _load_accum, se guardarian CEROS encima
                                         # del estado bueno y se perderia el acumulado.
        # --- estado de CUENTA y P&L acumulado (para la vista) ---
        self.acct_net = None             # NetLiquidation actual (IBKR manda)
        self.acct_avail = None           # AvailableFunds actual
        self.acct_net_open = None        # NetLiquidation de la 1a lectura del dia (base)
        self.last_acct = 0.0             # ultimo refresco de cuenta
        self.pnl_realizado = 0.0         # suma de profits de las VENTAS llenadas hoy (interno)
        self.pnl_ibkr = None             # M2: realizado SEGUN IBKR (manda este si existe)
        self.pnl_ibkr_unreal = None      # no realizado segun IBKR
        self._pnl_avisado = False        # ya se aviso de que IBKR no da el dato
        self._pnl_dev_avisada = 0.0      # ultima desviacion avisada (evita spam en el log)
        self.n_trades = 0                # operaciones cerradas hoy
        self.n_wins = 0                  # de esas, cuantas en positivo
        # Estado inicial COHERENTE con la realidad. Antes ponia siempre "trading OFF" aunque
        # TRADING_ENABLED fuese True: como trade_poll solo escribe trade_msg cuando HACE algo,
        # con la posicion ya en el objetivo el panel se quedaba diciendo "trading OFF" durante
        # horas mientras operaba con normalidad. Un panel que miente sobre si esta armado es
        # peor que no tener panel.
        self.trade_msg = ("TRADING ARMADO - esperando senal" if TRADING_ENABLED
                          else "TRADING OFF (desarmado)")
        self.entry_price = None          # precio de entrada del contrato comprado (para la linea)
        self.contract_price = None       # precio ACTUAL del contrato comprado (tiempo real, P&L)
        self.last_diff = 0.0             # ultimos valores de la senal (para log exhaustivo)
        self.last_thr = 0.0
        self.last_momentum = 0.0
        self._last_trade_log = ""        # dedupe del log de decision de trading
        self.eod_flat = False            # ya se aplano hoy
        self.reconciled = False
        # --- TA de 1 min + registro por minuto ---
        self.ta = TAEngine()
        self.bars = None                 # BarDataList (reqHistoricalData keepUpToDate)
        self.ta_vals = None              # dict con ultimos indicadores
        self.last_bar_time = None        # detectar cierre de minuto
        # --- GAP 17: salud del stream de barras ---
        # El stream muere SIN que el socket se caiga (2026-08-10 13:26: code 10182; las granjas
        # se repusieron solas, el stream no). Como spy_price sale de las barras, queda congelado
        # y walls_snapshot se sigue escribiendo con un spot falso. ib.isConnected() dice la
        # verdad -> la unica deteccion valida es la FRESCURA del dato, no el estado de conexion.
        self.spy_stock = None            # contrato SPY (hace falta para REPEDIR las barras)
        self.bars_last_advance = 0.0     # monotonic del ultimo avance real de bars[-1].date
        self._bars_ult_date = None       # ultima fecha de barra vista (detectar si avanza)
        self.bars_stale = False          # el stream no avanza -> spy_price NO es de fiar
        self.bars_retry_ts = 0.0         # ultimo intento de reponer (backoff: pacing violations)
        self.bars_retries = 0            # intentos acumulados (para el log)
        # --- registro de OPERACIONES (tabla trades / posicion_minuto) ---
        self.trade_id = None             # id de la operacion ABIERTA (None si FLAT)
        self.trade_open = None           # dict con los datos de la entrada (hora, spy, greeks)
        self.mfe = None                  # maximo a favor alcanzado (mid), seguido a 1 Hz
        self.mae = None                  # peor momento (mid)
        self.hora_mfe = None             # CUANDO se alcanzo el maximo (el dato que faltaba:
        self.spy_mfe = None              # el PUT del 12:20 hizo +130$ y se vendio en +45$)
        self.last_pos_log = 0.0          # ultimo muestreo por minuto del recorrido
        self._prem_snap = None           # totales call/put de la vela anterior (premium POR VELA)
        self._sello_arranque = None      # hora de este arranque en sesion_config (PK del sello)
        # --- ENTRADA POR RETROCESO (2026-08-12). SOLO se llenan en ta_poll; None = "no lo se"
        self.er_actual = None            # efficiency ratio de ER_VENTANA min: <ER_UMBRAL = reversion
        self.impulso_actual = None       # recorrido del SPY en IMPULSO_VENTANA min
        self.retro_ancla = None          # dict del giro: t, spy, imp, objetivo, er, lado
        self.retro_espero_min = None     # minutos que se acabo esperando (para el registro)
        self._com_entrada = None         # comision de la pata de COMPRA, hasta que la venta
                                         # cierre la fila y se guarde el coste de las dos juntas
        self.exit_reason = None          # por que se vende: giro / eod / exceso. Se fija donde
                                         # se DECIDE (target=FLAT), no se infiere en _on_filled:
                                         # inferirla por la hora daria 'eod' a un giro legitimo
                                         # ocurrido a las 15:44.
        # --- instrumentacion de la senal (ventanas moviles, NO deciden nada) ---
        self.flow_hist = []              # [(monotonic, net_call, net_put)] purgado a 15 min.
                                         # Unica historia de flujo: alimenta el momentum (GAP 5)
                                         # y las ventanas moviles. Sustituye a diff_hist, que
                                         # contaba EVENTOS y quedo sin uso al medir por tiempo.
        # --- SQLite ---
        self.db = sqlite3.connect(
            os.path.join(_app_dir(), "spy_history_demo.db" if demo else "spy_history.db"))
        self._init_db()

    def _init_db(self):
        c = self.db
        c.execute("CREATE TABLE IF NOT EXISTS transitions ("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, hora TEXT, "
                  "estado TEXT, tipo TEXT, spy REAL, net_call REAL, net_put REAL, modo TEXT)")
        # Acumulado persistente (desde el primer dia de uso)
        c.execute("CREATE TABLE IF NOT EXISTS strike_accum ("
                  "expiry TEXT, strike REAL, right TEXT, cum_prem REAL, updated TEXT, "
                  "PRIMARY KEY(expiry,strike,right))")
        # Premium por dia (para comparar apertura vs dia previo)
        c.execute("CREATE TABLE IF NOT EXISTS strike_daily ("
                  "fecha TEXT, expiry TEXT, strike REAL, right TEXT, day_prem REAL, "
                  "PRIMARY KEY(fecha,expiry,strike,right))")
        # Registro POR MINUTO: TA del SPY + precio + estado de premium
        c.execute("CREATE TABLE IF NOT EXISTS ta_minute ("
                  "fecha TEXT, hora TEXT, spy REAL, rsi REAL, ema8 REAL, ema21 REAL, ema50 REAL, "
                  "macd_line REAL, macd_signal REAL, macd_hist REAL, bb_up REAL, bb_mid REAL, "
                  "bb_low REAL, atr REAL, atr_pct REAL, vwap REAL, obv_trend TEXT, "
                  "ta_score REAL, ta_dir TEXT, net_call REAL, net_put REAL, prem_state TEXT, "
                  "PRIMARY KEY(fecha,hora))")
        # Registro POR MINUTO: premium call/put por strike seguido
        # (+ net_prem/open_interest/gamma por strike de la banda de walls, cada 3 min)
        c.execute("CREATE TABLE IF NOT EXISTS premium_minute ("
                  "fecha TEXT, hora TEXT, expiry TEXT, strike REAL, right TEXT, "
                  "cum_prem REAL, day_prem REAL, net_prem REAL, open_interest REAL, gamma REAL, "
                  "PRIMARY KEY(fecha,hora,expiry,strike,right))")
        # M1 / M2 (2026-08-11): una tabla por metodo, con las columnas de SU calculo
        c.execute("CREATE TABLE IF NOT EXISTS m1_minute ("
                  "fecha TEXT, hora TEXT, spy REAL, net_call REAL, net_put REAL, "
                  "abs_call REAL, abs_put REAL, dif REAL, senal_min TEXT, "
                  "n_up INTEGER, n_down INTEGER, marcador INTEGER, m1 TEXT, racha INTEGER, "
                  "m1_efectivo TEXT, retardo_min INTEGER, "
                  "recentrado INTEGER, PRIMARY KEY(fecha,hora))")
        # MEDIA CORTA (2026-08-12): el metodo que DECIDE desde hoy. Se registra minuto a minuto
        # igual que los otros, y CON SUS PARAMETROS en cada fila: si manana se cambia el umbral
        # o los minutos, las filas viejas siguen siendo interpretables (mismo criterio que
        # `entrada_minute`, que guarda er_umbral/retro_frac/retro_max_min).
        # `dist` va CON SIGNO ademas de en valor absoluto: el hallazgo aparecio justamente al
        # dejar de mirar el signo, y hace falta el crudo para poder re-analizarlo despues.
        c.execute("CREATE TABLE IF NOT EXISTS media_minute ("
                  "fecha TEXT, hora TEXT, spy REAL, media REAL, dist REAL, dist_abs REAL, "
                  "senal TEXT, estado TEXT, target TEXT, pos TEXT, seg_en_pos REAL, "
                  "activo INTEGER, media_dist REAL, minutos_pos INTEGER, "
                  "decide TEXT, origen TEXT, PRIMARY KEY(fecha,hora))")
        # METODO ANTIGUO (diff/thr): se sigue calculando y registrando aunque NO decida,
        # para poder comparar los tres metodos por tipo de mercado (bull/bear/lateral).
        c.execute("CREATE TABLE IF NOT EXISTS clasico_minute ("
                  "fecha TEXT, hora TEXT, spy REAL, net_call REAL, net_put REAL, "
                  "diff REAL, thr REAL, banda REAL, momentum REAL, mom_min REAL, "
                  "clasico TEXT, estado_real TEXT, warn_side TEXT, racha INTEGER, "
                  "clasico_efectivo TEXT, retardo_min INTEGER, "
                  "recentrado INTEGER, PRIMARY KEY(fecha,hora))")
        c.execute("CREATE TABLE IF NOT EXISTS m2_minute ("
                  "fecha TEXT, hora TEXT, spy REAL, net_call REAL, net_put REAL, "
                  "abs_call REAL, abs_put REAL, dif REAL, senal_min TEXT, "
                  "usd_up REAL, usd_down REAL, acumulado REAL, m2 TEXT, racha INTEGER, "
                  "m2_efectivo TEXT, retardo_min INTEGER, "
                  "recentrado INTEGER, PRIMARY KEY(fecha,hora))")
        # CONFIRMACION (2026-08-12): SEÑAL del minuto que aguanto CONFIRMACION_MIN min. SOLO REGISTRO.
        c.execute("CREATE TABLE IF NOT EXISTS confirmacion_minute ("
                  "fecha TEXT, hora TEXT, spy REAL, net_call REAL, net_put REAL, "
                  "abs_call REAL, abs_put REAL, dif REAL, senal_min TEXT, racha INTEGER, "
                  "confirmado TEXT, confirmado_efectivo TEXT, confirmacion_min INTEGER, "
                  "retardo_min INTEGER, recentrado INTEGER, PRIMARY KEY(fecha,hora))")
        # VELAS DE 1 MINUTO (2026-08-12). La app pide BARS_DURATION="2 D" de barras en CADA
        # arranque (medido en los comentarios de :193: "2 D" -> 442 barras) y hasta hoy las
        # TIRABA: no habia ni una tabla ni un INSERT de barras en todo el fichero. `ta_minute`
        # solo guardaba el cierre, asi que NO se podian formar velas ni buscar patrones.
        # Al volcarse con INSERT OR REPLACE toda la ventana en cada ta_poll, el arranque
        # RELLENA HACIA ATRAS los 2 dias sin ninguna logica extra.
        c.execute("CREATE TABLE IF NOT EXISTS bars_minute ("
                  "fecha TEXT, hora TEXT, open REAL, high REAL, low REAL, close REAL, "
                  "volume REAL, PRIMARY KEY(fecha,hora))")
        # REGIMEN Y COMPUERTA DE ENTRADA (2026-08-12). Una fila por minuto con lo que la regla
        # VE y lo que HACE, para poder juzgarla despues con datos en vez de con opiniones:
        # el efficiency ratio, el regimen que implica, el impulso, el objetivo de retroceso y
        # si en ese minuto se estaba esperando. Es lo que permitira comparar "lo que hizo" con
        # "lo que habria hecho" sin volver a simular nada.
        c.execute("CREATE TABLE IF NOT EXISTS entrada_minute ("
                  "fecha TEXT, hora TEXT, spy REAL, er REAL, regimen TEXT, impulso REAL, "
                  "objetivo REAL, esperando INTEGER, min_esperando REAL, target TEXT, "
                  "pos TEXT, activo INTEGER, er_umbral REAL, retro_frac REAL, "
                  "retro_max_min INTEGER, PRIMARY KEY(fecha,hora))")
        # migracion para BD existentes: agregar columnas nuevas si faltan
        for col in ("net_prem REAL", "open_interest REAL", "gamma REAL"):
            try:
                c.execute("ALTER TABLE premium_minute ADD COLUMN " + col)
            except Exception:
                pass  # ya existe
        # ESTADO INTRADIA: net_call/net_put y contadores del dia, para que un REINICIO a
        # media sesion NO empiece de cero. Sin esto el umbral adaptativo vuelve al piso
        # (max(5000, 0.15*0) = 5000, cien veces menor que el maduro) y la app se pone a
        # picotear: 4 giros en 34 s tras el reinicio de las 11:50 del 2026-08-10, cerrando
        # una posicion que la senal real habria mantenido.
        c.execute("CREATE TABLE IF NOT EXISTS estado_intradia ("
                  "fecha TEXT PRIMARY KEY, hora TEXT, net_call REAL, net_put REAL, "
                  "pnl_realizado REAL, n_trades INTEGER, n_wins INTEGER, "
                  "acct_net_open REAL, estado TEXT)")
        # migracion para BD ya creadas con la version anterior de la tabla
        for col in ("acct_net_open REAL", "estado TEXT"):
            try:
                c.execute("ALTER TABLE estado_intradia ADD COLUMN " + col)
            except Exception:
                pass  # ya existe
        # day_vol en premium_minute: alimenta max_pain_dyn (el magneto dinamico), que sin
        # el volumen del dia se quedaria en el magneto estatico tras cada reinicio.
        try:
            c.execute("ALTER TABLE premium_minute ADD COLUMN day_vol REAL")
        except Exception:
            pass
        # PRECIO del contrato por minuto (2026-08-11, peticion del usuario). Hasta ahora se
        # guardaba cuanto DINERO pasa por cada strike (cum_prem/day_prem/net_prem) pero NO cuanto
        # VALE el contrato: el unico precio en toda la BD era el del contrato comprado, en
        # posicion_minuto, y solo mientras la posicion estaba abierta.
        # No cuesta ni una linea de market data: los 68 contratos ya estan suscritos y sus
        # tickers traen bid/ask/last; compute_walls ya los leia para clasificar el agresor y
        # despues los tiraba.
        # spread se guarda CALCULADO (ask-bid) porque es la magnitud que se va a consultar:
        # distingue un strike liquido de uno donde el precio existe pero no es operable.
        for col in ("bid REAL", "ask REAL", "mid REAL", "last REAL", "spread REAL"):
            try:
                c.execute("ALTER TABLE premium_minute ADD COLUMN " + col)
            except Exception:
                pass
        # TAPE: una fila por ACTUALIZACION de ticker con operacion nueva (2026-08-11).
        # POR QUE (peticion del usuario): hasta ahora el flujo se agregaba al minuto, asi que un
        # print institucional de 3.038 contratos y 50 operaciones de retail de 60 quedaban
        # IDENTICOS: mismo dvol, mismo premium. Ademas, cualquier señal mas rapida que 1 minuto
        # se promediaba hasta borrarla, y el resultado "lag 0" que salio el 10-ago es compatible
        # tanto con "no anticipa" como con "anticipa 30 segundos".
        # `size` viene de tk.lastSize (RTVolume SI lo trae; se verifico en vivo el 2026-08-11:
        # last=0.9 lastSize=2.0). `dvol` es el delta de volumen acumulado, que es lo que se venia
        # usando: se guardan LOS DOS para poder comparar la atribucion exacta con la agregada.
        c.execute("CREATE TABLE IF NOT EXISTS tape ("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                  "fecha TEXT, hora TEXT, ts REAL, "          # hora HH:MM:SS.mmm y epoch
                  "expiry TEXT, strike REAL, right TEXT, "
                  "last REAL, size REAL, dvol REAL, "         # size = ESTA operacion; dvol = delta
                  "bid REAL, ask REAL, "
                  "agresor TEXT, "                            # COMPRA / VENTA / MID (no atribuible)
                  "premium REAL, "                            # last * size * 100
                  "premium_dvol REAL, "                       # last * dvol * 100 (lo que usa la señal)
                  "grupo TEXT)")                              # SENAL / BASELINE
        for _ix in ("CREATE INDEX IF NOT EXISTS ix_tape_fh ON tape(fecha,hora)",
                    "CREATE INDEX IF NOT EXISTS ix_tape_k ON tape(fecha,expiry,strike,right)",
                    "CREATE INDEX IF NOT EXISTS ix_tape_size ON tape(fecha,size)"):
            try:
                c.execute(_ix)
            except Exception:
                pass
        # SELLO DE CONFIGURACION: que version del codigo y que parametros generaron los datos.
        # Sin esto, filas creadas con criterios distintos (p.ej. walls por OI vs por gamma,
        # o strikes OTM vs ATM) se mezclan en la misma tabla y el analisis saca conclusiones
        # falsas creyendo que la serie es homogenea.
        c.execute("CREATE TABLE IF NOT EXISTS sesion_config ("
                  "fecha TEXT, hora TEXT, arranque TEXT, qty INTEGER, "
                  "signal_threshold REAL, adapt_frac REAL, mom_frac REAL, momentum_win INTEGER, "
                  "reprice_secs REAL, max_fill_secs REAL, walls_band INTEGER, "
                  "walls_recalc_secs REAL, itm_depth INTEGER, baseline_expiries INTEGER, "
                  "strike_exec TEXT, walls_criterio TEXT, trading INTEGER, notas TEXT, "
                  "PRIMARY KEY(fecha,arranque))")
        # Constancia de QUE arreglos estaban vivos en cada arranque. Es lo que de verdad
        # distingue un tramo de otro: el 2026-08-10 la misma tabla mezcla datos de antes y
        # despues del GAP 2 (premium de senal inflado) y del GAP 17 (spot congelado).
        for _col in ("cross_hhmm TEXT", "bars_stale_secs REAL", "pos_log_secs REAL",
                     "gaps_activos TEXT",
                     # 2026-08-11: la duracion de las barras cambia el VALOR de ema8/21/50 y obv
                     # (arrastran desde el inicio de la serie). Sin dejarla registrada, un tramo
                     # con "1 D" y otro con "2 D" son incomparables y nada lo delata.
                     "bars_duration TEXT", "start_trade_hhmm TEXT", "open_hhmm TEXT"):
            try:
                c.execute("ALTER TABLE sesion_config ADD COLUMN " + _col)
            except Exception:
                pass
        # Registro cada 3 min: walls/GEX/flip agregados (para analizar vs la grafica del precio)
        c.execute("CREATE TABLE IF NOT EXISTS walls_snapshot ("
                  "fecha TEXT, hora TEXT, expiry TEXT, spot REAL, "
                  "put_wall REAL, call_wall REAL, "
                  "max_pain_static REAL, max_pain_dyn REAL, prem_center REAL, "
                  "gex_total REAL, regime TEXT, gamma_flip REAL, "
                  "PRIMARY KEY(fecha,hora,expiry))")
        # spot_stale: el spot viene de las barras (ta_poll). Si el stream de barras muere,
        # spy_price queda CONGELADO y estas filas se siguen escribiendo con un precio falso
        # (2026-08-10 13:26: spot clavado en 773.03 tres snapshots seguidos). Marcarlas es la
        # unica forma de que el analisis las excluya en vez de creerlas buenas.
        try:
            c.execute("ALTER TABLE walls_snapshot ADD COLUMN spot_stale INTEGER")
        except Exception:
            pass

        # OPERACIONES: una fila por posicion abierta+cerrada. Hasta ahora la app instrumentaba
        # el MERCADO exhaustivamente pero NO lo que ella misma hacia: el recorrido del contrato
        # solo existia como texto en spy_activity.log, 1 linea por minuto, y se perdia.
        c.execute("CREATE TABLE IF NOT EXISTS trades ("
                  "trade_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                  "fecha TEXT, expiry TEXT, strike REAL, right TEXT, side TEXT, "
                  "hora_entrada TEXT, hora_salida TEXT, segundos REAL, "
                  "entry_price REAL, exit_price REAL, qty REAL, "
                  "profit REAL, pct REAL, "
                  "spy_entrada REAL, spy_salida REAL, "
                  "delta_entrada REAL, gamma_entrada REAL, theta_entrada REAL, "
                  "vega_entrada REAL, iv_entrada REAL, "
                  "mfe REAL, mae REAL, hora_mfe TEXT, spy_mfe REAL, "
                  "razon_salida TEXT)")
        # CONTEXTO DE MERCADO EN LA ENTRADA. Sin esto solo se puede responder "cuanto gano cada
        # operacion", no "QUE tenian en comun las que ganaron". Es lo que permite, en unas
        # sesiones, filtrar las compras que no van a ningun lado: el riesgo del scalping 0DTE
        # es que el theta corre siempre y el movimiento a veces no llega.
        # Las candidatas salen de M7 (rango comprimido + precio desplazado de su equilibrio).
        for _col in ("rsi_entrada REAL", "ta_score_entrada REAL", "ta_dir_entrada TEXT",
                     "atr_pct_entrada REAL", "bb_ancho_entrada REAL", "dist_vwap_entrada REAL",
                     "gex_entrada REAL", "regime_entrada TEXT", "dist_flip_entrada REAL",
                     "dist_prem_center_entrada REAL", "dist_call_wall_entrada REAL",
                     "dist_put_wall_entrada REAL", "diff_entrada REAL", "thr_entrada REAL",
                     "momentum_entrada REAL", "minuto_sesion_entrada INTEGER",
                     # COMISION real de las DOS patas (2026-08-12). `profit` es BRUTO: se
                     # comprobo que (exit-entry)*qty*100 reproduce el valor guardado con
                     # diferencia 0.00 en las 3 operaciones cerradas de ese dia. Sin este dato
                     # no se puede saber si un +7.00 bruto es en realidad positivo o negativo,
                     # y con permanencias medianas de decenas de segundos la comision pesa.
                     # NULL cuando IBKR no ha entregado el commissionReport (llega asincrono):
                     # NULL es la verdad, un 0 seria mentira.
                     "comision REAL"):
            try:
                c.execute("ALTER TABLE trades ADD COLUMN " + _col)
            except Exception:
                pass
        # RECORRIDO del contrato mientras la posicion esta viva (1 fila/min + entrada + salida).
        # 'tipo' distingue los puntos obligatorios de los del muestreo: con permanencia mediana
        # de 47 s, el 60% de las operaciones no llegan a generar ni una fila de minuto.
        c.execute("CREATE TABLE IF NOT EXISTS posicion_minuto ("
                  "trade_id INTEGER, fecha TEXT, hora TEXT, seg_desde_entrada REAL, "
                  "expiry TEXT, strike REAL, right TEXT, "
                  "spy REAL, bid REAL, ask REAL, mid REAL, "
                  "entry_price REAL, pnl REAL, pnl_pct REAL, "
                  "delta REAL, gamma REAL, theta REAL, vega REAL, iv REAL, und_price REAL, "
                  "tipo TEXT, "
                  "PRIMARY KEY(trade_id,hora,tipo))")

        # ACUMULADO NETO por strike, EN PARALELO al bruto (cum_prem/day_prem NO se tocan).
        # El bruto solo suma (es actividad, un hecho); el neto lleva el signo del agresor
        # (last>=ask compra / last<=bid venta), que es una INFERENCIA, no un dato de IBKR.
        for _t, _col in (("strike_accum", "cum_net REAL"), ("strike_daily", "day_net REAL")):
            try:
                c.execute("ALTER TABLE %s ADD COLUMN %s" % (_t, _col))
            except Exception:
                pass
        # INSTRUMENTACION DE LA SENAL: lo que decide hoy (diff/thr/momentum, acumulados desde
        # las 09:30) junto a las mismas magnitudes en VENTANA MOVIL. Se GUARDAN las variantes,
        # la decision UP/DOWN sigue usando EXCLUSIVAMENTE el acumulado. Sin esto no hay forma
        # de saber si una ventana movil habria girado antes: girar cuesta |diff|+thr y el thr
        # CRECE con el dia (medido 2026-08-10: 17->20->12->3 giros por hora).
        # PREMIUM POR VELA: lo que entro en ESE minuto, call y put por separado. El acumulado
        # crece monotonamente con la hora del dia (M10), asi que correlacionarlo con nada da
        # falsos positivos; el flujo POR MINUTO si es estacionario y se puede cruzar con la
        # vela del SPY. Bruto (actividad) y neto firmado (direccion) por separado.
        for _col in ("diff REAL", "thr REAL", "momentum REAL",
                     "prem_call_min REAL", "prem_put_min REAL",
                     "net_call_min REAL", "net_put_min REAL",
                     "net_call_1m REAL", "net_put_1m REAL",
                     "net_call_5m REAL", "net_put_5m REAL",
                     "net_call_15m REAL", "net_put_15m REAL",
                     # SMA 20/50/200 (2026-08-11): SOLO registro, NO deciden nada. La 200 queda
                     # NULL hasta que haya 200 barras (~12:50 con "1 D"), que es la verdad.
                     "sma20 REAL", "sma50 REAL", "sma200 REAL",
                     # MAXIMO y MINIMO de la vela (2026-08-12). SOLO registro.
                     # Hasta hoy `ta_minute` guardaba una sola columna de precio, `spy`, que es el
                     # CIERRE del minuto. Con solo cierres no se puede calcular el MFE/MAE de una
                     # entrada contrafactual: no se sabe si un stop o un take-profit habrian
                     # saltado, y el maximo de los cierres es un SUELO del recorrido real. Toda
                     # conclusion del tipo "con stop en X habria ganado Y" era, como mucho, una
                     # cota inferior. Las barras ya traen high/low (ta_poll:3229): solo habia que
                     # guardarlos. Filas anteriores quedan en NULL, que es la verdad.
                     "spy_high REAL", "spy_low REAL"):
            try:
                c.execute("ALTER TABLE ta_minute ADD COLUMN " + _col)
            except Exception:
                pass
        c.commit()

    # ---------------- historial de giros ----------------
    def _save(self, estado, tipo):
        try:
            now = datetime.now()
            self.db.execute(
                "INSERT INTO transitions(fecha,hora,estado,tipo,spy,net_call,net_put,modo)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), estado, tipo,
                 self.spy_price, self.net_call, self.net_put, self.mode))
            self.db.commit()
        except Exception:
            pass

    def recent(self, n=10):
        try:
            return self.db.execute(
                "SELECT fecha,hora,estado,tipo,spy FROM transitions "
                "ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        except Exception:
            return []

    # ---------------- conexion ----------------
    def connect(self):
        self.ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=8)
        self.ib.reqMarketDataType(1)
        # Suscribir los handlers UNA sola vez: con la reconexion automatica, connect()
        # se llama varias veces por sesion y los handlers se acumularian (logs duplicados
        # y _update_signal corriendo dos veces por evento).
        if not self._eventos_ok:
            self.ib.errorEvent += self._on_error
            self.ib.pendingTickersEvent += self._on_ticks
            self.ib.execDetailsEvent += self._on_exec
            self._eventos_ok = True
        ACT.info("Conectado a IB Gateway %s:%s (clientId=%s)", HOST, PORT, CLIENT_ID)

    def _on_exec(self, trade, fill):
        """EVENTO REAL de ejecucion de IBKR. Llega SIEMPRE que hay un fill, aunque
        self.order ya no apunte a esa orden. El sondeo de estado de trade_poll puede
        PERDERSE un fill: el 2026-08-10 la SELL CALL (reqId 450) se lleno, la app no se
        entero y siguio colocando ventas que habrian sido SHORTS DESCUBIERTOS; solo el
        control de margen de IBKR las freno. Aqui se deja constancia y se fuerza la
        re-sincronizacion inmediata contra la posicion real."""
        try:
            ex = fill.execution
            c = fill.contract
            ACT.info("EXEC REAL %s %s x%g @ %.2f (orderId=%s)",
                     getattr(ex, "side", "?"), getattr(c, "localSymbol", "?"),
                     getattr(ex, "shares", 0), getattr(ex, "price", 0.0),
                     getattr(trade.order, "orderId", "?"))
            self.last_sync = 0.0   # la posicion real acaba de cambiar -> resync ya
        except Exception:
            LOG.exception("Error en _on_exec")

    def _on_error(self, reqId, code, msg, contract):
        sym = getattr(contract, "localSymbol", "") or getattr(contract, "symbol", "") if contract else ""
        ACT.info("IBKR code=%s reqId=%s %s%s", code, reqId, msg, (f" [{sym}]" if sym else ""))
        if code in (354, 10167, 10168, 10197, 10089, 10091):
            if self.mode not in ("DELAYED", "DEMO"):
                self.mode = "DELAYED"
                self.status = "Datos DELAYED (sin OPRA live) - sin flujo por-trade real"
                try:
                    self.ib.reqMarketDataType(3)
                except Exception:
                    pass
        # GAP 17, deteccion A (por evento): IBKR avisa de que el stream de barras se rompio.
        # Es la via RAPIDA, pero NO se puede depender de ella: el 2026-08-10 el stream murio
        # y el TA quedo congelado sin que nada mas lo notara. La via que de verdad protege es
        # la B (frescura del dato, en ta_poll), porque no exige que IBKR diga nada.
        if code == 10182 and not self.bars_stale:
            self.bars_stale = True
            ACT.info("BARRAS: stream roto segun IBKR (code=10182) -> se repondra en <=%.0fs",
                     BARS_RETRY_SECS)

    def is_market_open(self):
        """RECOLECCION: dia habil (Lun-Vie) y OPEN_HHMM <= hora ET < CLOSE_HHMM. (Sin festivos.)

        OJO - esto NO es la ventana de TRADING, es la de RECOLECCION. Operar ya esta acotado
        aparte: FLATTEN_HHMM (15:45) fuerza target=FLAT y `in_session`/STOP_NEW_HHMM impiden
        abrir nuevas. Pasadas las 16:00 la app solo MIRA y GUARDA.

        2026-08-11: OPEN_HHMM bajo a 09:00 (era el literal "09:30"). Desde entonces esta ventana
        es MAS ANCHA que la de RTH, asi que todo lo que dependa de "el mercado esta de verdad
        abierto" (trading, frescura de barras) debe usar is_rth(), NO esta funcion."""
        et = now_et()
        return et.weekday() < 5 and OPEN_HHMM <= et.strftime("%H:%M") < CLOSE_HHMM

    def is_rth(self):
        """MERCADO REAL abierto (Regular Trading Hours): RTH_OPEN_HHMM <= ET < CLOSE_HHMM.

        Es lo que is_market_open() significaba ANTES de adelantar la recoleccion a las 09:00.
        Usarla para lo que solo tiene sentido con el mercado de verdad abierto: exigirle
        frescura al stream de barras (useRTH=True no produce barras en pre-market)."""
        et = now_et()
        return et.weekday() < 5 and RTH_OPEN_HHMM <= et.strftime("%H:%M") < CLOSE_HHMM

    def reset_day(self):
        """Nuevo dia de mercado: limpiar acumuladores intradia (la senal arranca en 0)."""
        self.net_call = 0.0; self.net_put = 0.0
        self.m1_up = 0; self.m1_down = 0
        self.m2_up = 0.0; self.m2_down = 0.0
        self.m1_estado = None; self.m2_estado = None
        self.m1_racha = 0; self.m2_racha = 0
        self.m_recentrado = 0
        self.cl_estado = None; self.cl_racha = 0
        self.sen_estado = None; self.sen_racha = 0
        self.conf_estado = None; self.conf_hist = []; self.conf_efectivo = None
        self.m1_hist = []; self.m1_efectivo = None
        self.m2_hist = []; self.m2_efectivo = None
        self.cl_hist = []; self.cl_efectivo = None
        self.today_prem = {}; self.net_prem = {}; self.today_vol = {}
        self.today_net = {}          # el NETO del dia se reinicia; accum_net NO (es persistente)
        self.prev_vol = {}; self.band_prev_vol = {}; self.prev_gamma = {}
        self._tick_prem_ids = set()   # dia nuevo: nadie ha contado nada todavia
        self.transitions = []; self.state = "-"
        # TAPE: el contador es del DIA. El buffer se vuelca antes de vaciarlo para no perder
        # las operaciones que quedaran pendientes del dia anterior.
        try:
            self._flush_tape(forzar=True)
        except Exception:
            pass
        self._tape_buf = []; self._tape_n = 0
        self._tape_err = 0; self._tape_err_last = ""
        self.flow_hist = []          # ventanas moviles: historia de AYER no vale para hoy
        self._prem_snap = None       # premium por vela: sin referencia del dia anterior
        self.entry_price = None; self.contract_price = None
        # operacion en curso: un dia nuevo jamas hereda un trade abierto del anterior
        self.trade_id = None; self.trade_open = None
        self.mfe = self.mae = self.hora_mfe = self.spy_mfe = None
        self.exit_reason = None
        # contadores de cuenta/P&L del dia (la base se recaptura en la 1a lectura)
        self.acct_net_open = None
        self.pnl_realizado = 0.0; self.n_trades = 0; self.n_wins = 0
        self.buys_pend = 0; self.last_buy_ts = 0.0
        ACT.info("NUEVO DIA - acumuladores intradia reiniciados (senal en 0)")

    def end_session(self):
        """Mercado cerrado: persistir, cancelar ordenes vivas y desconectar (reconecta al reabrir)."""
        # GAP 4: si se llega aqui CON POSICION, el aplanado de las 15:45 y el cruce de spread
        # de las 15:50 no consiguieron cerrar. Con 0DTE eso significa que EXPIRA. Se deja
        # constancia explicita en el log: es dinero perdido y tiene que ser rastreable.
        if self.pos in ("CALL", "PUT") or self.pos_qty > 0:
            ACT.info("ALERTA EOD: la sesion CIERRA con posicion ABIERTA (%s x%g). Si es 0DTE "
                     "EXPIRA sin valor. Revisar por que no llenaron ni el MID (15:45) ni el "
                     "cruce al BID (%s)", self.pos, self.pos_qty, CROSS_HHMM)
            if self.trade_id is not None:
                self._trade_cerrar(None, None, None, "expirada")
        try:
            self._persist_accum()
        except Exception:
            pass
        # TAPE: volcar lo que quede en el buffer o se pierden las ultimas operaciones del dia
        # (el volcado normal es por lotes de TAPE_FLUSH_N o por minuto, y al cerrar puede haber
        # un lote a medias).
        if TAPE_ENABLED:
            try:
                _n = self._flush_tape(forzar=True)
                ACT.info("TAPE cerrado: %d operaciones en el ultimo volcado, %d en total hoy",
                         _n, self._tape_n)
            except Exception:
                pass
        # cerrar el sello: sin la hora de cierre no se sabe si un tramo duro 3 minutos o 3 horas
        try:
            if getattr(self, "_sello_arranque", None):
                self.db.execute(
                    "UPDATE sesion_config SET notas = notas || ? WHERE fecha=? AND arranque=?",
                    (" | cierre %s" % datetime.now().strftime("%H:%M:%S"),
                     datetime.now().strftime("%Y-%m-%d"), self._sello_arranque))
                self.db.commit()
        except Exception:
            LOG.exception("Error cerrando el sello de sesion")
        try:
            if self.ib.isConnected():
                self._cancel_working()
                self.ib.disconnect()
        except Exception:
            LOG.exception("Error al cerrar sesion de mercado")
        self.reconciled = False
        self.mode = "?"
        ACT.info("MERCADO CERRADO - sesion detenida y desconectada (recoleccion se reanuda al abrir)")

    # ---------------- seleccion de contratos ----------------
    def _read_price(self, spy):
        price = float("nan")
        for mdt, label in [(1, "LIVE"), (2, "FROZEN"), (3, "DELAYED"), (4, "DELAYED")]:
            self.ib.reqMarketDataType(mdt)
            t = self.ib.reqMktData(spy, "", False, False)
            self.ib.sleep(2.5)
            p = t.marketPrice()
            if p is None or math.isnan(p):
                p = t.last if (t.last and not math.isnan(t.last)) else t.close
            self.ib.cancelMktData(spy)
            if p and not math.isnan(p):
                self.mode = label
                return float(p)
        return price

    def _band(self, strikes, price):
        """Devuelve (call_strikes, put_strikes) ATM+ITM (nunca OTM)."""
        below = [s for s in strikes if s <= price]
        above = [s for s in strikes if s >= price]
        call_strikes = below[-(1 + ITM_DEPTH):] if below else []
        put_strikes = above[:(1 + ITM_DEPTH)] if above else []
        return call_strikes, put_strikes

    def _subscribe_bars(self):
        """UNICO punto donde se pide el stream de barras de 1 min (fuente del TA y, desde el
        GAP 11, de spy_price). Lo llaman setup_contracts y el recuperador del GAP 17.

        GAP 17 (2026-08-10 13:26): IBKR mando `10182 Failed to request live updates` y el
        stream murio. Las granjas se repusieron solas; este NO, y nadie lo repedia: ta_minute
        se congelo 20+ minutos y walls_snapshot siguio escribiendo con spy_price CONGELADO
        (spot clavado en 773.03). El socket seguia vivo, asi que ib.isConnected() no ayudaba."""
        if self.spy_stock is None or not self.ib.isConnected():
            return False
        # soltar la suscripcion vieja antes de repedir: si no, se acumulan streams muertos
        # en el Gateway y se acaba en pacing violation.
        if self.bars is not None:
            try:
                self.ib.cancelHistoricalData(self.bars)
            except Exception:
                pass
        try:
            self.bars = self.ib.reqHistoricalData(
                self.spy_stock, "", BARS_DURATION, "1 min", "TRADES",
                useRTH=True, keepUpToDate=True)
        except Exception:
            self.bars = None
            LOG.exception("Error pidiendo el stream de barras")
            return False
        # OJO: NO se toca self.last_bar_time. El objeto bars es nuevo, pero la continuidad del
        # registro depende de esa variable: ponerla a None haria que ta_poll se saltara un
        # minuto entero (hace `return` la primera vez que la ve vacia).
        self.bars_last_advance = time.monotonic()   # reloj del backoff, NO bandera de fiabilidad
        # GAP 17-bis: AQUI NO se limpia bars_stale. Pedir el stream no es lo mismo que tenerlo:
        # el 2026-08-10 a las 16:01 se repidio "con exito" fuera de RTH, la bandera se limpio,
        # IBKR no mando ni una barra, y walls_snapshot escribio spot_stale=0 sobre un spot
        # CONGELADO en 773.07 - justo lo que esa columna existe para evitar.
        # La bandera la limpia LA EVIDENCIA (_chequear_barras, cuando ve avanzar bars[-1].date),
        # nunca la INTENCION de haber pedido el stream.
        return True

    def setup_contracts(self):
        spy = Stock(SYMBOL, "SMART", "USD")
        self.ib.qualifyContracts(spy)
        self.spy_stock = spy          # hace falta guardarlo para poder REPEDIR las barras
        price = self._read_price(spy)
        if math.isnan(price):
            self.status = "No pude leer precio de SPY (revisa suscripcion de datos)"
            return False
        self.spy_price = price

        chains = self.ib.reqSecDefOptParams(spy.symbol, "", spy.secType, spy.conId)
        chain = next((c for c in chains
                      if c.exchange == "SMART" and c.tradingClass == SYMBOL), None) \
            or next((c for c in chains if c.exchange == "SMART"), None)
        if chain is None or not chain.strikes or not chain.expirations:
            self.status = "No obtuve la cadena de opciones de SPY"
            return False

        today = datetime.now().strftime("%Y%m%d")
        exps = sorted(chain.expirations)
        self.expiry = next((e for e in exps if e >= today), exps[0])  # mas cercano
        strikes = sorted(chain.strikes)
        self.strikes = strikes        # cadena viva: la necesita refresh_exec_strikes()

        # --- señal: ATM call/put del vencimiento mas cercano ---
        below = [s for s in strikes if s <= self.spy_price]
        above = [s for s in strikes if s >= self.spy_price]
        if not below or not above:
            self.status = "No hay strikes ATM/ITM alrededor del precio"
            return False
        call_strike, put_strike = max(below), min(above)
        self.call = Option(SYMBOL, self.expiry, call_strike, "C", "SMART", tradingClass=SYMBOL)
        self.put = Option(SYMBOL, self.expiry, put_strike, "P", "SMART", tradingClass=SYMBOL)
        self.ib.qualifyContracts(self.call, self.put)
        self.ib.reqMktData(self.call, "233", False, False)
        self.ib.reqMktData(self.put, "233", False, False)

        # --- EJECUCION: ATM del lado OTM (call strike > precio, put strike < precio) ---
        above_otm = [s for s in strikes if s > self.spy_price]
        below_otm = [s for s in strikes if s < self.spy_price]
        bc = min(above_otm) if above_otm else call_strike
        bp = max(below_otm) if below_otm else put_strike
        self.buy_call = Option(SYMBOL, self.expiry, bc, "C", "SMART", tradingClass=SYMBOL)
        self.buy_put = Option(SYMBOL, self.expiry, bp, "P", "SMART", tradingClass=SYMBOL)
        self.ib.qualifyContracts(self.buy_call, self.buy_put)
        self.ib.reqMktData(self.buy_call, "", False, False)   # bid/ask para el MID
        self.ib.reqMktData(self.buy_put, "", False, False)

        # --- linea base: ATM/ITM de las siguientes expiraciones FUTURAS ---
        self.base_expiries = [e for e in exps if e > self.expiry][:BASELINE_EXPIRIES]
        base_contracts = []
        for exp in self.base_expiries:
            cs, ps = self._band(strikes, self.spy_price)
            for s in cs:
                base_contracts.append(Option(SYMBOL, exp, s, "C", "SMART", tradingClass=SYMBOL))
            for s in ps:
                base_contracts.append(Option(SYMBOL, exp, s, "P", "SMART", tradingClass=SYMBOL))
        if base_contracts:
            self.ib.qualifyContracts(*base_contracts)
            for c in base_contracts:
                if not c.conId:
                    continue
                self.info_base[c.conId] = (c.lastTradeDateOrContractMonth, c.strike, c.right)
                self._base_ct[c.conId] = c   # sin esto, los 24 del arranque nunca se soltarian
                self.ib.reqMktData(c, "233", False, False)

        # --- WALLS/GEX: contratos de la banda (expiracion CERCANA). Se piden por SNAPSHOT cada 3 min ---
        self.band_contracts = []
        if WALLS_ENABLED:
            below = [s for s in strikes if s <= self.spy_price][-WALLS_BAND:]
            above = [s for s in strikes if s > self.spy_price][:WALLS_BAND]
            wc = []
            for s in (below + above):
                wc.append(Option(SYMBOL, self.expiry, s, "C", "SMART", tradingClass=SYMBOL))
                wc.append(Option(SYMBOL, self.expiry, s, "P", "SMART", tradingClass=SYMBOL))
            try:
                self.ib.qualifyContracts(*wc)
                self.band_contracts = [c for c in wc if c.conId]
                # STREAMING persistente: una suscripcion por contrato (NO repite requests -> no satura).
                # OI(101)+volumen(100)+greeks(106/modelGreeks). Se RECALCULA/guarda cada 3 min.
                # 233 (RTVolume) 2026-08-12: sin el, la banda NO trae `last`/`lastSize` por
                # operacion y `tk.volume` solo se refresca por el tick 100 (periodico). Medido ese
                # dia: el `tape` veia 290.319 de 1.916.463 contratos del 0DTE = 15,1%, con 32 de 40
                # strikes a CERO operaciones, y el poll de walls leyo volumen OBSOLETO en los
                # strikes de senal (612.615$ de premium no contabilizados entre 09:48 y 09:51).
                # Anadir un tick generico a un contrato YA suscrito no consume una linea de
                # mercado nueva: la linea es por contrato.
                for c in self.band_contracts:
                    self.ib.reqMktData(c, "100,101,106,233", False, False)
                ACT.info("WALLS banda lista (streaming): %d contratos (%d strikes, +-%d por lado)",
                         len(self.band_contracts), len(below + above), WALLS_BAND)
            except Exception:
                LOG.exception("Error suscribiendo banda de walls")

        self._load_accum()
        # SELLO: se escribe DESPUES de _load_accum (que decide si es dia nuevo o reinicio) y
        # una sola vez por arranque. Deja en la BD que codigo genero los datos de este tramo.
        self._sellar_sesion()

        # barras de 1 min en vivo (fuente del TA y de spy_price)
        self._subscribe_bars()

        self.status = (f"OK  SPY={self.spy_price:.2f}  cercano={self.expiry}  "
                       f"senal C{call_strike:g}/P{put_strike:g} (ATM/ITM)  "
                       f"opera C{bc:g}/P{bp:g} (OTM)  "
                       f"| baseline exps={len(self.base_expiries)}  [{self.mode}]")
        print(self.status)
        ACT.info("SETUP %s", self.status)
        return True

    # ---------------- acumulado persistente ----------------
    def _load_accum(self):
        """Carga el acumulado historico y el premium del dia previo desde la BD."""
        try:
            for exp, strike, right, cp, cn in self.db.execute(
                    "SELECT expiry,strike,right,cum_prem,cum_net FROM strike_accum").fetchall():
                self.accum[(exp, strike, right)] = cp
                # cum_net es NULL en las filas escritas antes de que existiera la columna:
                # se deja en 0 y a partir de ahora acumula. NO se infiere del bruto.
                if cn is not None:
                    self.accum_net[(exp, strike, right)] = cn
            hoy = datetime.now().strftime("%Y-%m-%d")
            rows = self.db.execute(
                "SELECT expiry,strike,right,day_prem FROM strike_daily WHERE fecha=("
                "SELECT MAX(fecha) FROM strike_daily WHERE fecha < ?)", (hoy,)).fetchall()
            for exp, strike, right, dp in rows:
                self.base_prev[(exp, strike, right)] = dp
        except Exception:
            pass
        # Se llama DESPUES de reset_day(): resetear y luego restaurar lo de HOY si lo hay.
        self._load_intradia()
        self._load_estado_dia()

    def _load_estado_dia(self):
        """Repuebla lo que YA estaba en la BD para que un reinicio no deje la pantalla en
        blanco: premium del dia por strike (barras de la Gamma Ladder), premium neto,
        volumen del dia (magneto dinamico) y la lista de giros.

        OJO - lo que NO se toca a proposito: prev_vol, band_prev_vol, buys_pend y
        last_buy_ts. Son lineas base de volumen y ordenes en vuelo; restaurarlas generaria
        un PREMIUM FANTASMA (el volumen que da IBKR es acumulado del dia y se compararia
        contra una base vieja) o bloquearia compras legitimas."""
        try:
            hoy = datetime.now().strftime("%Y-%m-%d")
            # 1) premium del dia por strike -> barras de la Ladder desde el primer dibujo
            for exp, strike, right, dp, dn in self.db.execute(
                    "SELECT expiry,strike,right,day_prem,day_net FROM strike_daily WHERE fecha=?",
                    (hoy,)).fetchall():
                if dp:
                    self.today_prem[(exp, strike, right)] = dp
                if dn:
                    self.today_net[(exp, strike, right)] = dn
            # 2) net_prem y volumen del dia de la ULTIMA foto de hoy
            ult = self.db.execute(
                "SELECT MAX(hora) FROM premium_minute WHERE fecha=?", (hoy,)).fetchone()[0]
            n_np = n_vol = 0
            if ult:
                for exp, strike, right, npm, dv in self.db.execute(
                        "SELECT expiry,strike,right,net_prem,day_vol FROM premium_minute "
                        "WHERE fecha=? AND hora=?", (hoy, ult)).fetchall():
                    if npm:
                        self.net_prem[(exp, strike, right)] = npm
                        n_np += 1
                    if dv:
                        self.today_vol[(exp, strike, right)] = dv
                        n_vol += 1
            # 2-bis) OPERACION ABIERTA: si la sesion se reinicio con posicion viva, readoptar
            # su trade_id para que el recorrido CONTINUE en la misma fila en vez de perderse.
            # Sin esto, tras un reinicio la operacion nunca se cerraria en 'trades' y su MFE
            # quedaria a medias. Si resulta que ya no hay posicion real, _sync_pos la cierra.
            r = self.db.execute(
                "SELECT trade_id,hora_entrada,mfe,mae,hora_mfe,spy_mfe,entry_price FROM trades "
                "WHERE fecha=? AND hora_salida IS NULL ORDER BY trade_id DESC LIMIT 1",
                (hoy,)).fetchone()
            if r:
                self.trade_id = r[0]
                self.trade_open = {"hora": r[1]}
                self.mfe, self.mae, self.hora_mfe, self.spy_mfe = r[2], r[3], r[4], r[5]
                # PRECIO DE ENTRADA: el de la fila es el avgFillPrice REAL de la compra, que es
                # lo que _on_filled guardo. Sin reponerlo aqui, _adoptar_posicion lo recupera de
                # avgCost, y avgCost INCLUYE LA COMISION.
                # VERIFICADO el 2026-08-12 con el trade #12 cerrado en el FLATTEN:
                #   trades.entry_price 1.13 | profit guardado -83.44 | recalculado desde la
                #   fila (0.31-1.13)x100 = -82.00 | entry_price implicito 1.144395 = avgCost.
                # La fila se CONTRADICE A SI MISMA en 1.44$: quien recalcule el dia desde
                # `trades` no obtiene el profit que la propia tabla guarda. Y el significado de
                # `profit` pasa a depender de si hubo reinicio (con -> neto de la comision de
                # compra; sin -> bruto), que es lo que hace incomparables dos dias.
                # RIESGO ADICIONAL, NO VERIFICADO: si la columna `comision` trae las DOS patas,
                # restarla al profit descuenta la comision de compra por segunda vez. En la #12
                # NO llego a pasar porque el reinicio perdio `_com_entrada` y solo se guardo la
                # pata de venta ("COMISION PARCIAL ... entrada=- salida=0.86"). Hace falta una
                # operacion con las dos patas y un reinicio de por medio para comprobarlo.
                # avgCost sigue siendo el ultimo recurso en _adoptar_posicion (guard
                # `if not self.entry_price`) para una posicion huerfana que no tiene fila.
                if r[6]:
                    self.entry_price = r[6]
                ACT.info("TRADE #%s readoptado tras el reinicio (entrada %s, MFE=%s, "
                         "entry_price=%s)", r[0], r[1], _fmt(r[2]), _fmt(r[6]))
            # 3) lista de giros en memoria (la pantalla usa recent(), pero se deja coherente)
            for hora, estado in self.db.execute(
                    "SELECT hora,estado FROM transitions WHERE fecha=? AND tipo='FLIP' "
                    "ORDER BY id DESC LIMIT 8", (hoy,)).fetchall():
                self.transitions.append((hora, estado))
            self.transitions.reverse()
            # 3-bis) LOS CUATRO METODOS: sin esto un reinicio les borra la memoria del dia.
            self._load_metodos(hoy)
            if self.today_prem or n_np or self.transitions:
                ACT.info("ESTADO DEL DIA repuesto: %d strikes con premium, %d con net_prem, "
                         "%d con volumen, %d giros | prev_vol/band_prev_vol/buys_pend "
                         "vacios a proposito",
                         len(self.today_prem), n_np, n_vol, len(self.transitions))
        except Exception:
            LOG.exception("Error repoblando el estado del dia")

    def _load_metodos(self, hoy):
        """Repone en memoria el estado de los CUATRO metodos (M1, M2, CLASICO, CONFIRMACION)
        cuando la sesion se reinicia a mitad del dia.

        POR QUE HACE FALTA: las cuatro tablas del minuto se escriben desde el 2026-08-11 pero
        NUNCA se leian (verificado con grep: cero SELECT sobre ellas). `_load_intradia` solo
        repone net_call/net_put/pnl/estado, asi que tras un reinicio los contadores arrancaban
        en CERO. Medido el 2026-08-12: el marcador de M1 iba por +75 tras 141 minutos y un
        reinicio lo dejaba en 0. Peor aun, `m1_hist` quedaba vacia, con lo que M1 no podia
        aplicar el retardo hasta juntar RETARDO_M1_MIN minutos NUEVOS (~20 min sin poder
        girar) y despues decidia con contadores desde cero: bastaban 1-2 minutos de dominancia
        contraria para invertir la direccion. Un reinicio no puede cambiar lo que el sistema
        opina; eso no es recuperarse, es empezar otra sesion distinta con la misma posicion.

        LAS HISTORIAS Y EL RELOJ: `m1_hist`/`m2_hist`/`cl_hist`/`conf_hist` llevan sellos de
        `time.monotonic()`, que se reinicia con el proceso y NO sirve entre arranques. Se
        reconstruyen desplazando el reloj: a la fila de las HH:MM le corresponde
        `monotonic_ahora - (minutos transcurridos desde HH:MM) * 60`. Asi `_efec` sigue
        comparando contra RETARDO_M1_MIN exactamente igual que si no se hubiera reiniciado.

        Si no hay filas de HOY no se toca nada: es el primer arranque del dia y los contadores
        en cero son la verdad (regla 13).

        `m1_efectivo` NO se calcula aqui: lo recalcula `_log_minute` en el primer minuto, y
        hasta entonces `_update_signal` mantiene `self.state`, que `_load_intradia` ya repuso.
        La ventana ciega pasa de ~20 minutos a como mucho 1.
        """
        try:
            ahora = datetime.now()
            t_now = time.monotonic()
            ahora_min = ahora.hour * 60 + ahora.minute

            def _ts(hhmm):
                """monotonic sintetico para una hora HH:MM de hoy. None si no es utilizable."""
                try:
                    mins = ahora_min - (int(hhmm[:2]) * 60 + int(hhmm[3:5]))
                except Exception:
                    return None
                return (t_now - mins * 60.0) if mins >= 0 else None

            def _hist(filas):
                """[(ts, estado)] en orden cronologico, FIEL a lo que hace el codigo vivo.

                OJO: se conservan las entradas con estado None. `conf_hist` las tiene a
                proposito (`:3603` appendea `self.conf_estado` SIEMPRE, y vale None hasta que
                la senal aguanta CONFIRMACION_MIN minutos). Saltarlas desplazaria la historia
                y `_efec` devolveria un estado anterior donde el sistema vivo dice None.
                Lo unico que se descarta es la fila cuyo sello de tiempo no se puede
                reconstruir (hora futura respecto a ahora: cruce de medianoche).
                """
                out = []
                for h, est in filas:
                    ts = _ts(h)
                    if ts is not None:
                        out.append((ts, est))
                return out

            n1 = n2 = ncl = nco = 0

            f1 = self.db.execute(
                "SELECT hora,n_up,n_down,m1,racha,senal_min FROM m1_minute "
                "WHERE fecha=? ORDER BY hora", (hoy,)).fetchall()
            if f1:
                self.m1_hist = _hist([(r[0], r[3]) for r in f1])
                _u, _d, _m, _r, _s = f1[-1][1], f1[-1][2], f1[-1][3], f1[-1][4], f1[-1][5]
                self.m1_up = int(_u or 0)
                self.m1_down = int(_d or 0)
                self.m1_estado = _m or None
                self.m1_racha = int(_r or 0)
                self.sen_estado = _s or None
                n1 = len(f1)

            f2 = self.db.execute(
                "SELECT hora,usd_up,usd_down,m2,racha FROM m2_minute "
                "WHERE fecha=? ORDER BY hora", (hoy,)).fetchall()
            if f2:
                self.m2_hist = _hist([(r[0], r[3]) for r in f2])
                self.m2_up = float(f2[-1][1] or 0.0)
                self.m2_down = float(f2[-1][2] or 0.0)
                self.m2_estado = f2[-1][3] or None
                self.m2_racha = int(f2[-1][4] or 0)
                n2 = len(f2)

            fcl = self.db.execute(
                "SELECT hora,clasico,racha FROM clasico_minute "
                "WHERE fecha=? ORDER BY hora", (hoy,)).fetchall()
            if fcl:
                self.cl_hist = _hist([(r[0], r[1]) for r in fcl])
                self.cl_estado = fcl[-1][1] or None
                self.cl_racha = int(fcl[-1][2] or 0)
                ncl = len(fcl)

            fco = self.db.execute(
                "SELECT hora,confirmado,racha FROM confirmacion_minute "
                "WHERE fecha=? ORDER BY hora", (hoy,)).fetchall()
            if fco:
                self.conf_hist = _hist([(r[0], r[1]) for r in fco])
                self.conf_estado = fco[-1][1] or None
                self.sen_racha = int(fco[-1][2] or 0)
                nco = len(fco)

            if n1 or n2 or ncl or nco:
                ACT.info("METODOS repuestos tras el reinicio: M1 up=%d down=%d marcador=%+d "
                         "estado=%s racha=%d hist=%d | M2 acum=%+.0f estado=%s | CLASICO=%s "
                         "r=%d | CONFIRMA=%s r=%d | filas leidas %d/%d/%d/%d",
                         self.m1_up, self.m1_down, self.m1_up - self.m1_down,
                         self.m1_estado or "-", self.m1_racha, len(self.m1_hist),
                         self.m2_up - self.m2_down, self.m2_estado or "-",
                         self.cl_estado or "-", self.cl_racha,
                         self.conf_estado or "-", self.sen_racha,
                         n1, n2, ncl, nco)
            else:
                ACT.info("METODOS: no hay filas de hoy -> primer arranque del dia, "
                         "los contadores se quedan en cero (correcto)")
        except Exception:
            # nunca puede impedir el arranque: sin reponer se opera como hasta ahora
            LOG.exception("Error reponiendo el estado de los metodos")

    def _sellar_sesion(self):
        """SELLO DE CONFIGURACION: deja constancia de QUE codigo y QUE parametros generaron
        los datos de este arranque. Una fila por arranque (PK fecha+arranque), asi que un dia
        con varios reinicios queda troceado y se puede saber que tramo produjo cada dato.

        Por que hace falta: la tabla existia desde el 2026-08-10 pero NADIE escribia en ella
        (0 sentencias INSERT en todo el archivo) - un CREATE TABLE huerfano, indistinguible de
        una tabla que 'aun no tiene datos'. Ese mismo dia la BD acabo mezclando tres criterios
        distintos sin ninguna marca: walls por OI vs por gamma, ejecucion OTM vs ATM real, y
        premium de los strikes de senal inflado por el GAP 2. Quien analice la serie completa
        sin esto concluira en falso creyendo que es homogenea.

        NO puede tumbar el arranque: es informativo, va entero en try/except."""
        try:
            now = datetime.now()
            # gaps/arreglos VIVOS en esta version. Es el dato que de verdad separa un tramo de
            # otro; los parametros numericos por si solos no dicen que bugs estaban activos.
            gaps = "GAP1,GAP3,GAP7,GAP8,GAP9,GAP11,GAP12,GAP13,GAP14,GAP15,GAP16,GAP17," \
                   "GAP2,GAP4,GAP5,M2,M12," \
                   "GAP18,GAP19,GAP17bis,GAP20,GAP21,SMA20-50-200,BARS2D," \
                   "PRECIO-CONTRATOS" + (",TAPE" if TAPE_ENABLED else "")
            # QUIEN DECIDE y CON QUE PARAMETROS. Sin esto, dos sesiones con disparadores
            # distintos son INDISTINGUIBLES en la BD: el 2026-08-12 los arranques posteriores
            # al commit del ITM quedaron marcados igual que los anteriores y no hubo forma de
            # atribuir nada. Va en `notas` (columna que ya existe) para no tocar el esquema.
            _dec = ("MEDIA(dist>=%.2f, %dmin)" % (MEDIA_DIST, MINUTOS_POS) if USAR_MEDIA
                    else ("M1(retardo=%d)" % RETARDO_M1_MIN if USAR_M1 else "CLASICO diff/thr"))
            notas = ("DECIDE=%s | EJECUCION_ITM=%s cap_frac=%.2f | USAR_M1=%s retardo=%d | "
                     "TAKE_PROFIT_USD=%s | ENTRADA_RETROCESO=%s || "
                     "momentum_win guarda SEGUNDOS (MOMENTUM_SECS), no numero de muestras: "
                     "el GAP 5 cambio la ventana de eventos a tiempo. "
                     "Registra: trades/posicion_minuto, cum_net, premium por vela, "
                     "ventanas moviles 1/5/15m, contexto de entrada."
                     % (_dec, EJECUCION_ITM, CAPITAL_FRAC_MAX, USAR_M1, RETARDO_M1_MIN,
                        TAKE_PROFIT_USD, ENTRADA_RETROCESO))
            self.db.execute(
                "INSERT OR REPLACE INTO sesion_config(fecha,hora,arranque,qty,"
                "signal_threshold,adapt_frac,mom_frac,momentum_win,reprice_secs,max_fill_secs,"
                "walls_band,walls_recalc_secs,itm_depth,baseline_expiries,strike_exec,"
                "walls_criterio,trading,notas,cross_hhmm,bars_stale_secs,pos_log_secs,"
                "gaps_activos,bars_duration,start_trade_hhmm,open_hhmm) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), now.strftime("%H:%M:%S"),
                 QTY, SIGNAL_THRESHOLD, ADAPT_FRAC, MOM_FRAC, MOMENTUM_SECS,
                 REPRICE_SECS, MAX_FILL_SECS, WALLS_BAND, WALLS_RECALC_SECS,
                 ITM_DEPTH, BASELINE_EXPIRIES,
                 # 2026-08-12: ANTES era el literal "ATM real", escrito a fuego, que NO leia
                 # EJECUCION_ITM. Las 17 filas de la tabla decian lo mismo aunque el criterio
                 # hubiera cambiado -- justo el rastro que esta columna existe para guardar.
                 ("ITM mas profundo que quepa" if EJECUCION_ITM else "ATM real"), "gamma",
                 1 if self.trading else 0, notas,
                 CROSS_HHMM, BARS_STALE_SECS, POS_LOG_SECS, gaps,
                 BARS_DURATION, START_TRADE_HHMM, OPEN_HHMM))
            self.db.commit()
            ACT.info("SELLO DE SESION %s: DECIDE=%s | QTY=%d thr=%.0f adapt=%.2f mom=%.2f/%.0fs "
                     "reprice=%.0fs banda=%d/%.0fs exec=%s walls=gamma trading=%s "
                     "cross=%s barras=%s recoleccion>=%s opera>=%s | gaps: %s",
                     now.strftime("%H:%M:%S"), _dec, QTY, SIGNAL_THRESHOLD, ADAPT_FRAC, MOM_FRAC,
                     MOMENTUM_SECS, REPRICE_SECS, WALLS_BAND, WALLS_RECALC_SECS,
                     "ITM" if EJECUCION_ITM else "ATM-real",
                     "ON" if self.trading else "OFF", CROSS_HHMM,
                     BARS_DURATION, OPEN_HHMM, START_TRADE_HHMM, gaps)
            self._sello_arranque = now.strftime("%H:%M:%S")
        except Exception:
            LOG.exception("Error escribiendo el sello de sesion (no bloquea el arranque)")

    def _persist_accum(self):
        """Guarda el acumulado (persistente) y el premium de HOY en la BD."""
        try:
            now = datetime.now()
            hoy = now.strftime("%Y-%m-%d")
            ts = now.strftime("%H:%M:%S")
            for key, cp in self.accum.items():
                exp, strike, right = key
                self.db.execute(
                    "INSERT INTO strike_accum(expiry,strike,right,cum_prem,cum_net,updated) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(expiry,strike,right) "
                    "DO UPDATE SET cum_prem=excluded.cum_prem, cum_net=excluded.cum_net, "
                    "updated=excluded.updated",
                    (exp, strike, right, cp, self.accum_net.get(key, 0.0), ts))
            for key, dp in self.today_prem.items():
                exp, strike, right = key
                self.db.execute(
                    "INSERT INTO strike_daily(fecha,expiry,strike,right,day_prem,day_net) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(fecha,expiry,strike,right) "
                    "DO UPDATE SET day_prem=excluded.day_prem, day_net=excluded.day_net",
                    (hoy, exp, strike, right, dp, self.today_net.get(key, 0.0)))
            # ESTADO INTRADIA: para que un reinicio a media sesion no empiece de cero.
            # Solo si ya se intento restaurar; si no, se escribirian ceros encima del bueno.
            if self._intradia_ok:
                self.db.execute(
                    "INSERT INTO estado_intradia(fecha,hora,net_call,net_put,pnl_realizado,"
                    "n_trades,n_wins,acct_net_open,estado) VALUES(?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(fecha) "
                    "DO UPDATE SET hora=excluded.hora, net_call=excluded.net_call, "
                    "net_put=excluded.net_put, pnl_realizado=excluded.pnl_realizado, "
                    "n_trades=excluded.n_trades, n_wins=excluded.n_wins, "
                    "acct_net_open=excluded.acct_net_open, estado=excluded.estado",
                    (hoy, ts, self.net_call, self.net_put, self.pnl_realizado,
                     self.n_trades, self.n_wins, self.acct_net_open, self.state))
            self.db.commit()
            # 2026-08-12 (peticion del usuario: TODO tiene que quedar en el log).
            # Estas 3 tablas eran las unicas que se escribian sin dejar traza. No es
            # cosmetico: `estado_intradia` es lo que evita que un reinicio a media sesion
            # empiece de cero, y si dejara de escribirse solo se notaria AL REINICIAR
            # -restaurando valores viejos-, que es el peor momento para enterarse.
            ACT.info("PERSIST accum=%d strikes (cum) | daily=%d strikes (hoy) | "
                     "intradia=%s netC=%.0f netP=%.0f estado=%s pnl=%.2f ops=%d/%d",
                     len(self.accum), len(self.today_prem),
                     "SI" if self._intradia_ok else "NO (aun sin restaurar)",
                     self.net_call, self.net_put, self.state,
                     self.pnl_realizado, self.n_wins, self.n_trades)
        except Exception:
            # ANTES: `pass` a secas. Un fallo aqui era INVISIBLE: ni log, ni excepcion,
            # ni fila en la BD. Se sigue sin propagar (persistir no debe tumbar la sesion)
            # pero ahora deja constancia.
            LOG.exception("PERSIST FALLO: no se pudo guardar accum/daily/intradia")
            ACT.warning("PERSIST FALLO: no se guardo el acumulado ni el estado intradia "
                        "(ver spy_direction.log). Un reinicio ahora empezaria con datos viejos")

    def _load_intradia(self):
        """Restaura el estado del dia tras un REINICIO a media sesion.
        reset_day() pone net_call/net_put a cero porque en un proceso nuevo no hay forma de
        saber si es un dia nuevo o un reinicio. Aqui se recupera lo que ya se habia medido
        HOY: sin esto el umbral adaptativo vuelve al piso de SIGNAL_THRESHOLD y la app
        empieza a girar con cualquier ruido (verificado 2026-08-10: 4 giros en 34 s tras
        reiniciar, cerrando una posicion que la senal madura habria mantenido).
        Se llama DESPUES de reset_day(), desde setup_contracts -> _load_accum()."""
        try:
            hoy = datetime.now().strftime("%Y-%m-%d")
            r = self.db.execute(
                "SELECT hora,net_call,net_put,pnl_realizado,n_trades,n_wins,"
                "acct_net_open,estado FROM estado_intradia WHERE fecha=?", (hoy,)).fetchone()
            self._intradia_ok = True        # ya se consulto: a partir de aqui SI se persiste
            if not r:
                return                      # primer arranque del dia: se queda en 0, correcto
            self.net_call = float(r[1] or 0.0)
            self.net_put = float(r[2] or 0.0)
            self.pnl_realizado = float(r[3] or 0.0)
            self.n_trades = int(r[4] or 0)
            self.n_wins = int(r[5] or 0)
            # base del dia para el "DIA +/-" del panel: sin esto la variacion se mide desde
            # el REINICIO en vez de desde la apertura.
            if r[6] is not None:
                self.acct_net_open = float(r[6])
            # estado UP/DOWN: se restaura, pero flow_hist queda VACIO a proposito. Sin historia
            # el momentum vale 0 y las condiciones de aviso de _update_signal no se cumplen, asi
            # que no se dispara ninguna alerta espuria en el primer tick tras el reinicio.
            if r[7] in ("UP", "DOWN"):
                self.state = r[7]
            thr = max(SIGNAL_THRESHOLD, ADAPT_FRAC * (abs(self.net_call) + abs(self.net_put)))
            ACT.info("ESTADO INTRADIA restaurado (guardado %s): netC=%.0f netP=%.0f -> "
                     "umbral %.0f (sin restaurar habria sido %.0f) | realizado %.2f "
                     "ops %d (%d ganadoras) | estado=%s | base del dia=%s",
                     r[0], self.net_call, self.net_put, thr, SIGNAL_THRESHOLD,
                     self.pnl_realizado, self.n_trades, self.n_wins, self.state,
                     ("%.2f" % self.acct_net_open) if self.acct_net_open else "-")
        except Exception:
            LOG.exception("Error restaurando el estado intradia")

    # ---------------- Walls / GEX / Gamma Flip (informativo) ----------------
    def compute_walls(self):
        """Snapshot de la banda (cada WALLS_RECALC_SECS, no satura el gateway) -> walls/GEX/flip.
        INFORMATIVO: NO toca la senal UP/DOWN ni la ejecucion. Guarda TODO en la BD
        (walls_snapshot agregado + premium_minute por strike) y en el log, para acumular datos
        y luego analizar la precision de los cambios de direccion vs la grafica del precio."""
        if not WALLS_ENABLED or not self.band_contracts or not self.ib.isConnected():
            return
        # Leer los tickers YA vivos (streaming persistente). NO se piden snapshots.
        # IBKR actualiza cada campo a SU ritmo (OI=EOD; gamma/vol/precio=en vivo); detectamos
        # 'staleness' comparando gamma con el recalculo anterior + hora del ultimo tick.
        tks = [self.ib.ticker(c) for c in self.band_contracts]

        # GAP 2: conIds cuyo premium ya cuenta _on_ticks por tick. Aqui NO se vuelven a sumar.
        signal_ids = {c.conId for c in (self.call, self.put) if c is not None}
        # 2026-08-12: desde que la BANDA tambien entra en _on_ticks (RTVolume 233) hay que
        # excluirla de aqui o su premium se contaria DOS veces (GAP 2 repitiendose sobre 40
        # strikes). Pero la exclusion NO puede ser estatica: si un contrato de la banda no
        # llegara nunca a _on_ticks (RTVolume rechazado, strike sin una sola operacion,
        # re-suscripcion en curso), excluirlo por lista dejaria su premium en CERO en vez de
        # aproximado — se pierde el dato en silencio. Medido con la cold run: `prem_center` se
        # quedaba en '-' y `strike 780 tiene premium>0` fallaba.
        # Por eso se excluye lo que _on_ticks ha contado DE VERDAD (`_tick_prem_ids`), no lo que
        # deberia contar. Sin solapamiento posible: cada ruta lleva su propio `prev_vol`, asi que
        # el tramo anterior al primer tick lo cuenta walls y el posterior _on_ticks.
        tick_ids = set(signal_ids) | set(self._tick_prem_ids)
        call_oi = {}; put_oi = {}; call_g = {}; put_g = {}
        oi_est_c = {}; oi_est_p = {}; gross = {}
        miss_oi = miss_g = 0
        g_changed = 0
        last_tick_time = None
        detail = []
        for c, tk in zip(self.band_contracts, tks):
            s = c.strike; right = c.right
            key = (self.expiry, s, right)
            oi = tk.callOpenInterest if right == "C" else tk.putOpenInterest
            g = tk.modelGreeks.gamma if tk.modelGreeks else None
            oi = None if (oi is None or (isinstance(oi, float) and math.isnan(oi))) else float(oi)
            g = None if (g is None or (isinstance(g, float) and math.isnan(g))) else float(g)
            if oi is None:
                miss_oi += 1
            if g is None:
                miss_g += 1
            # staleness: contar cuantos gamma cambiaron vs el recalculo anterior + hora del ult. tick
            if g is not None:
                if self.prev_gamma.get(c.conId) != g:
                    g_changed += 1
                self.prev_gamma[c.conId] = g
            tt = getattr(tk, "time", None)
            if tt is not None and (last_tick_time is None or tt > last_tick_time):
                last_tick_time = tt
            # delta de volumen entre lecturas (3 min) -> premium neto firmado por strike ('peso')
            vol = tk.volume; last = tk.last
            if (vol is not None and not math.isnan(vol)
                    and last is not None and not math.isnan(last)):
                prev = self.band_prev_vol.get(c.conId)
                self.band_prev_vol[c.conId] = vol
                if prev is not None and vol - prev > 0:
                    dvol = vol - prev
                    prem = float(last) * dvol * 100.0
                    self.today_vol[key] = self.today_vol.get(key, 0.0) + dvol
                    # GAP 2 - DOBLE CONTEO. Los 2 strikes de SENAL estan tambien dentro de la
                    # banda (misma expiry), asi que su clave (expiry,strike,right) la escribian
                    # DOS funciones con deltas de volumen independientes: _on_ticks (por tick)
                    # y esta (cada 3 min). Resultado: su premium salia inflado, y son
                    # justamente los strikes que alimentan la senal.
                    # Manda _on_ticks: mide por TICK, con bid/ask alineados al trade, mientras
                    # aqui un unico `last` clasifica 3 minutos enteros de volumen.
                    # OJO: today_vol y net_prem SI se siguen contando aqui; a esos dicts no
                    # los escribe nadie mas, no hay colision.
                    # 2026-08-12: la exclusion pasa de `signal_ids` a `tick_ids` porque la banda
                    # entera la mide ya _on_ticks. Con `signal_ids` los 40 strikes se contarian
                    # DOS veces: es el mismo GAP 2 repitiendose, ahora sobre toda la banda.
                    if c.conId not in tick_ids:
                        self.today_prem[key] = self.today_prem.get(key, 0.0) + prem
                    bid = tk.bid if (tk.bid and not math.isnan(tk.bid)) else None
                    ask = tk.ask if (tk.ask and not math.isnan(tk.ask)) else None
                    signed = 0.0
                    if ask is not None and last >= ask:
                        signed = prem
                    elif bid is not None and last <= bid:
                        signed = -prem
                    self.net_prem[key] = self.net_prem.get(key, 0.0) + signed
            gv = self.today_vol.get(key, 0.0)
            if right == "C":
                if oi is not None:
                    call_oi[s] = oi
                if g is not None:
                    call_g[s] = g
                oi_est_c[s] = (oi or 0.0) + gv
            else:
                if oi is not None:
                    put_oi[s] = oi
                if g is not None:
                    put_g[s] = g
                oi_est_p[s] = (oi or 0.0) + gv
            gross[s] = gross.get(s, 0.0) + self.today_prem.get(key, 0.0)
            detail.append(f"{s:g}{right}:OI={_fmt(oi)},g={_fmt(g)},"
                          f"net={self.net_prem.get(key, 0.0):+.0f}")

        spot = self.spy_price
        # walls ponderadas por gamma (el OI es EOD y no se mueve; el gamma si es en vivo)
        w = compute_walls_from_oi(call_oi, put_oi, spot, call_g, put_g)
        self.walls = {
            "put_wall": w["put_wall"] if w else None,
            "call_wall": w["call_wall"] if w else None,
            "max_pain_static": w["max_pain"] if w else None,
            "max_pain_dyn": _max_pain(oi_est_c, oi_est_p),
            "prem_center": compute_prem_center(gross),
            "spot": spot,
        }
        self.gex = compute_gex_from_greeks(call_oi, put_oi, call_g, put_g, spot,
                                           GEX_CALL_SIGN, GEX_PUT_SIGN)
        self._persist_walls(call_oi, put_oi, call_g, put_g)
        g = self.gex or {}
        gxt = g.get("gex_total")
        n_g = len(self.band_contracts) - miss_g   # cuantos strikes trajeron gamma
        ACT.info("WALLS spot=%.2f PW=%s CW=%s magneto est=%s/din=%s peso=%s | "
                 "GEX=%s regime=%s flip=%s | faltan OI=%d greeks=%d de %d | "
                 "frescura: gamma cambiaron=%d/%d ult_tick=%s",
                 spot, _fmt(self.walls["put_wall"]), _fmt(self.walls["call_wall"]),
                 _fmt(self.walls["max_pain_static"]), _fmt(self.walls["max_pain_dyn"]),
                 _fmt(self.walls["prem_center"]),
                 (f"{gxt/1e9:+.3f}Bn" if isinstance(gxt, (int, float)) else "-"),
                 g.get("regime", "-"), _fmt(g.get("gamma_flip")),
                 miss_oi, miss_g, len(self.band_contracts),
                 g_changed, n_g, (str(last_tick_time) if last_tick_time else "-"))
        if n_g > 0 and g_changed == 0:
            ACT.info("WALLS AVISO: ningun gamma cambio desde el ultimo recalculo -> posible dato "
                     "ESTANCADO/viejo (revisar suscripcion OPRA o fuera de RTH)")
        ACT.info("WALLS detalle por strike: %s", " | ".join(detail))
        # GAP 2: dejar constancia de que estos strikes NO se sumaron aqui (los cuenta _on_ticks
        # por tick). Sin este log el arreglo seria invisible y nadie sabria si sigue activo.
        if signal_ids:
            _sig = [f"{c.strike:g}{c.right}" for c in (self.call, self.put) if c is not None]
            ACT.info("WALLS GAP2: premium de los strikes de SENAL (%s) NO sumado aqui para "
                     "evitar el doble conteo (lo lleva _on_ticks, por tick)", ", ".join(_sig))

    def _persist_walls(self, call_oi, put_oi, call_g, put_g):
        """Guarda walls_snapshot (agregado) + premium_minute por strike de la banda."""
        try:
            now = datetime.now()
            fecha = now.strftime("%Y-%m-%d"); hora = now.strftime("%H:%M")
            g = self.gex or {}
            self.db.execute(
                "INSERT OR REPLACE INTO walls_snapshot(fecha,hora,expiry,spot,put_wall,call_wall,"
                "max_pain_static,max_pain_dyn,prem_center,gex_total,regime,gamma_flip,spot_stale) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, self.expiry, self.walls.get("spot"),
                 self.walls.get("put_wall"), self.walls.get("call_wall"),
                 self.walls.get("max_pain_static"), self.walls.get("max_pain_dyn"),
                 self.walls.get("prem_center"), g.get("gex_total"), g.get("regime"),
                 g.get("gamma_flip"),
                 # 1 = el spot venia de un stream de barras congelado -> gex_total (factor
                 # spot^2) y gamma_flip NO son fiables en esta fila. Marcarlo es la unica
                 # forma de que el analisis las excluya en vez de creerlas buenas.
                 1 if self.bars_stale else 0))
            strikes = sorted(set(call_oi) | set(put_oi) | set(call_g) | set(put_g))
            for s in strikes:
                for right, oimap, gmap in (("C", call_oi, call_g), ("P", put_oi, put_g)):
                    key = (self.expiry, s, right)
                    # PRECIO (2026-08-11): hay que incluirlo AQUI tambien. Este INSERT OR REPLACE
                    # reescribe la fila ENTERA, asi que si _log_minute ya habia guardado
                    # bid/ask/mid/last/spread en este mismo minuto y aqui no se nombraran, el
                    # REPLACE los dejaria en NULL. Es el mismo fallo que el comentario de
                    # _log_minute advierte en sentido contrario.
                    px = self._precio_de(self.expiry, s, right)
                    self.db.execute(
                        "INSERT OR REPLACE INTO premium_minute(fecha,hora,expiry,strike,right,"
                        "cum_prem,day_prem,net_prem,open_interest,gamma,day_vol,"
                        "bid,ask,mid,last,spread) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (fecha, hora, self.expiry, s, right,
                         self.accum.get(key, 0.0), self.today_prem.get(key, 0.0),
                         self.net_prem.get(key, 0.0), oimap.get(s), gmap.get(s),
                         self.today_vol.get(key, 0.0),
                         px["bid"], px["ask"], px["mid"], px["last"], px["spread"]))
            self.db.commit()
        except Exception:
            LOG.exception("Error guardando walls_snapshot/premium_minute (banda)")

    # ---------------- registro de OPERACIONES (que hizo la app, no el mercado) ----------------
    @staticmethod
    def _segs_desde(hhmmss):
        """Segundos transcurridos desde una hora 'HH:MM:SS' de HOY. Se usa reloj de PARED y no
        time.monotonic() a proposito: monotonic se reinicia con el proceso, y una posicion
        puede sobrevivir a un reinicio (paso el 2026-08-10 a las 12:09)."""
        if not hhmmss:
            return None
        try:
            p = [int(x) for x in str(hhmmss).split(":")]
            ini = p[0] * 3600 + p[1] * 60 + (p[2] if len(p) > 2 else 0)
            n = datetime.now()
            return float(n.hour * 3600 + n.minute * 60 + n.second - ini)
        except Exception:
            return None

    def _contexto_entrada(self):
        """Foto del MERCADO en el instante de comprar. Todo en DISTANCIAS al precio (no valores
        absolutos): 'GEX=250Bn' crece con la hora del dia y correlaciona con el reloj (M10),
        pero 'estoy 0.6 por encima del centro de peso' es comparable entre dias y horas.

        Sirve para responder, en unas sesiones: que tenian en comun las compras que SI
        recorrieron, y cuales se quedaron quietas pagando theta. Ninguno de estos valores
        decide nada hoy: se guardan y punto. Lo que falte va a NULL, no se rellena (regla 13)."""
        v = self.ta_vals or {}
        w = self.walls or {}
        gx = self.gex or {}
        spy = self.spy_price

        def dist(x):
            """Distancia con signo del precio a un nivel (positivo = precio por encima)."""
            if x is None or spy is None or (isinstance(spy, float) and math.isnan(spy)):
                return None
            try:
                return float(spy) - float(x)
            except (TypeError, ValueError):
                return None

        bb_up, bb_low, bb_mid = v.get("bb_up"), v.get("bb_low"), v.get("bb_mid")
        # ancho de Bollinger en % del precio: el precursor candidato de M7 (rango comprimido)
        bb_ancho = None
        if bb_up is not None and bb_low is not None and bb_mid:
            try:
                bb_ancho = (float(bb_up) - float(bb_low)) / float(bb_mid) * 100.0
            except (TypeError, ValueError, ZeroDivisionError):
                bb_ancho = None
        et = now_et()
        return {
            "rsi": v.get("rsi"), "ta_score": v.get("score"), "ta_dir": v.get("dir"),
            "atr_pct": v.get("atr_pct"), "bb_ancho": bb_ancho,
            "dist_vwap": dist(v.get("vwap")),
            "gex": gx.get("gex_total"), "regime": gx.get("regime"),
            "dist_flip": dist(gx.get("gamma_flip")),
            "dist_prem_center": dist(w.get("prem_center")),
            "dist_call_wall": dist(w.get("call_wall")),
            "dist_put_wall": dist(w.get("put_wall")),
            # minuto de sesion: el theta y la liquidez no se comportan igual a las 09:35 que a
            # las 15:30. Sin esto no se puede controlar por hora del dia.
            "minuto_sesion": (et.hour * 60 + et.minute) - (9 * 60 + 30),
        }

    def _trade_abrir(self, contract, px, qty):
        """Abre una fila en 'trades' al llenarse una COMPRA. Devuelve el trade_id."""
        try:
            now = datetime.now()
            g = self._greeks_de(contract)
            ctx = self._contexto_entrada()
            self.db.execute(
                "INSERT INTO trades(fecha,expiry,strike,right,side,hora_entrada,"
                "entry_price,qty,spy_entrada,delta_entrada,gamma_entrada,theta_entrada,"
                "vega_entrada,iv_entrada,"
                "rsi_entrada,ta_score_entrada,ta_dir_entrada,atr_pct_entrada,bb_ancho_entrada,"
                "dist_vwap_entrada,gex_entrada,regime_entrada,dist_flip_entrada,"
                "dist_prem_center_entrada,dist_call_wall_entrada,dist_put_wall_entrada,"
                "diff_entrada,thr_entrada,momentum_entrada,minuto_sesion_entrada) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now.strftime("%Y-%m-%d"), contract.lastTradeDateOrContractMonth,
                 contract.strike, contract.right, self.pos, now.strftime("%H:%M:%S"),
                 px, qty, self.spy_price,
                 g["delta"], g["gamma"], g["theta"], g["vega"], g["iv"],
                 ctx["rsi"], ctx["ta_score"], ctx["ta_dir"], ctx["atr_pct"], ctx["bb_ancho"],
                 ctx["dist_vwap"], ctx["gex"], ctx["regime"], ctx["dist_flip"],
                 ctx["dist_prem_center"], ctx["dist_call_wall"], ctx["dist_put_wall"],
                 self.last_diff, self.last_thr, self.last_momentum, ctx["minuto_sesion"]))
            self.db.commit()
            self.trade_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
            self.trade_open = {"ts": time.monotonic(), "hora": now.strftime("%H:%M:%S")}
            # el recorrido arranca en la entrada: mfe/mae parten del propio precio de compra
            self.mfe = self.mae = px
            self.hora_mfe = now.strftime("%H:%M:%S")
            self.spy_mfe = self.spy_price
            self.last_pos_log = time.monotonic()
            self._pos_snapshot("entrada")
            ACT.info("TRADE #%s ABIERTO %s %g%s @ %.2f | greeks delta=%s gamma=%s theta=%s iv=%s",
                     self.trade_id, self.pos, contract.strike, contract.right, px,
                     _fmt(g["delta"]), _fmt(g["gamma"]), _fmt(g["theta"]), _fmt(g["iv"]))
            # CONTEXTO de la compra: con esto se podra separar despues las entradas que
            # recorrieron de las que solo pagaron theta.
            ACT.info("TRADE #%s CONTEXTO | min_sesion=%s | TA %s score=%s rsi=%s atr=%s%% "
                     "bb_ancho=%s%% | dist: vwap=%s peso=%s flip=%s CW=%s PW=%s | "
                     "GEX=%s %s | diff=%s thr=%s mom=%s",
                     self.trade_id, ctx["minuto_sesion"], ctx["ta_dir"], _fmt(ctx["ta_score"]),
                     _fmt(ctx["rsi"]), _fmt(ctx["atr_pct"]), _fmt(ctx["bb_ancho"]),
                     _fmt(ctx["dist_vwap"]), _fmt(ctx["dist_prem_center"]),
                     _fmt(ctx["dist_flip"]), _fmt(ctx["dist_call_wall"]),
                     _fmt(ctx["dist_put_wall"]),
                     (f"{ctx['gex']/1e9:+.1f}Bn" if isinstance(ctx["gex"], (int, float)) else "-"),
                     ctx["regime"] or "-",
                     _fmt(self.last_diff), _fmt(self.last_thr), _fmt(self.last_momentum))
        except Exception:
            LOG.exception("Error abriendo trade en la BD")

    def _trade_cerrar(self, px, profit, pct, razon, comision=None):
        """Cierra la fila de 'trades' al llenarse una VENTA. Vuelca MFE/MAE, que es el dato
        que responde 'cuanto deje sobre la mesa': el 2026-08-10 un PUT comprado a 0.80 llego
        a 2.10 (+130$) y se vendio a 1.25 (+45$), 18 min despues del maximo."""
        if self.trade_id is None:
            return
        try:
            self._pos_snapshot("salida")
            now = datetime.now()
            segs = self._segs_desde(self.trade_open.get("hora")) if self.trade_open else None
            self.db.execute(
                "UPDATE trades SET hora_salida=?, segundos=?, exit_price=?, profit=?, pct=?, "
                "spy_salida=?, mfe=?, mae=?, hora_mfe=?, spy_mfe=?, razon_salida=?, "
                "comision=? WHERE trade_id=?",
                (now.strftime("%H:%M:%S"), segs, px, profit, pct, self.spy_price,
                 self.mfe, self.mae, self.hora_mfe, self.spy_mfe, razon,
                 comision, self.trade_id))
            self.db.commit()
            ACT.info("TRADE #%s CERRADO @ %s (%s) | dur=%ss | MFE=%s (a las %s) MAE=%s "
                     "| dejado sobre la mesa=%s",
                     self.trade_id, ("%.2f" % px) if px is not None else "?", razon,
                     ("%.0f" % segs) if segs is not None else "?",
                     _fmt(self.mfe), self.hora_mfe or "-", _fmt(self.mae),
                     _fmt((self.mfe - px) * 100.0)
                     if (self.mfe is not None and px is not None) else "-")
        except Exception:
            LOG.exception("Error cerrando trade en la BD")
        finally:
            self.trade_id = None
            self.trade_open = None
            self.mfe = self.mae = self.hora_mfe = self.spy_mfe = None

    def _pos_snapshot(self, tipo):
        """Una fila del RECORRIDO del contrato en cartera. tipo: entrada|minuto|salida.
        'entrada' y 'salida' se graban SIEMPRE; 'minuto' cada POS_LOG_SECS. Sin los dos
        primeros, el 60% de las operaciones (mediana 47 s) no tendrian ni un solo punto."""
        if self.trade_id is None or self.pos not in ("CALL", "PUT"):
            return
        contract = self.buy_call if self.pos == "CALL" else self.buy_put
        if contract is None:
            return
        try:
            now = datetime.now()
            bid, ask = self._bid_ask(contract)
            mid = self._mid(contract)
            en = self.entry_price
            pnl = ((mid - en) * 100.0) if (mid is not None and en) else None
            pct = ((mid / en - 1.0) * 100.0) if (mid is not None and en) else None
            g = self._greeks_de(contract)
            segs = self._segs_desde(self.trade_open.get("hora")) if self.trade_open else None
            self.db.execute(
                "INSERT OR REPLACE INTO posicion_minuto(trade_id,fecha,hora,seg_desde_entrada,"
                "expiry,strike,right,spy,bid,ask,mid,entry_price,pnl,pnl_pct,"
                "delta,gamma,theta,vega,iv,und_price,tipo) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.trade_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), segs,
                 contract.lastTradeDateOrContractMonth, contract.strike, contract.right,
                 self.spy_price, bid, ask, mid, en, pnl, pct,
                 g["delta"], g["gamma"], g["theta"], g["vega"], g["iv"], g["und_price"],
                 tipo))
            self.db.commit()
            # LOG del recorrido: respaldo en texto por si la BD falla, y permite seguir la
            # evolucion del contrato sin abrir SQLite. Incluye el spread real pagado.
            ACT.info("POS #%s %-7s %g%s | SPY=%s mid=%s (bid=%s ask=%s spread=%s) | "
                     "entrada=%s pnl=%s$ (%s%%) | delta=%s gamma=%s theta=%s vega=%s iv=%s | "
                     "%.0fs en posicion",
                     self.trade_id, tipo, contract.strike, contract.right,
                     _fmt(self.spy_price), _fmt(mid), _fmt(bid), _fmt(ask),
                     _fmt((ask - bid) if (bid is not None and ask is not None) else None),
                     _fmt(en), _fmt(pnl), _fmt(pct),
                     _fmt(g["delta"]), _fmt(g["gamma"]), _fmt(g["theta"]),
                     _fmt(g["vega"]), _fmt(g["iv"]), segs or 0.0)
        except Exception:
            LOG.exception("Error guardando el recorrido de la posicion")

    def _seguir_extremos(self, mid):
        """MFE/MAE a 1 Hz (cada tick), SIN escribir en la BD. Asi toda operacion tiene su
        recorrido real aunque el muestreo sea por minuto y dure 10 segundos.

        Y desde 2026-08-12, el OBJETIVO DE BENEFICIO: es el unico sitio que ve el precio de la
        posicion a 1 Hz, asi que es donde se puede cobrar antes de que se devuelva.
        """
        if mid is None or self.trade_id is None:
            return
        if self.mfe is None or mid > self.mfe:
            self.mfe = mid
            self.hora_mfe = datetime.now().strftime("%H:%M:%S")
            self.spy_mfe = self.spy_price
        if self.mae is None or mid < self.mae:
            self.mae = mid
        # ---- OBJETIVO DE BENEFICIO (2026-08-12) ----
        # POR QUE: medido sobre las 4 operaciones REALES de hoy, con el mid real minuto a
        # minuto. El dia acabo en -44.50 y las cuatro tuvieron beneficio disponible que se
        # devolvio entero, porque hasta ahora SOLO se vendia al girar M1:
        #     MFE alcanzado: +42.00 / +11.00 / +37.00 / +21.50
        #     con objetivo +5  -> +20.00   con +10 -> +28.00   con +15 -> +43.00
        # Se elige +10 y NO el que mas da (+20 -> +58.00) a proposito: 10 es el objetivo mas
        # alto que TODAS las operaciones alcanzaron (el MFE minimo fue +11). Por encima, el
        # resultado depende de que una operacion concreta llegue o no -> eso es ajustar al dia
        # de hoy (INVESTIGACION_M1_M2 §7) y manana falla.
        # NO cambia la direccion ni abre nada: solo pide FLAT, y la venta la hace `trade_poll`
        # por el camino de siempre (LimitOrder al MID, con sus guardas contra descubierto).
        if not TAKE_PROFIT_USD or self.entry_price in (None, 0):
            return
        try:
            if (mid - self.entry_price) * 100.0 >= TAKE_PROFIT_USD and self.target != "FLAT":
                self.target = "FLAT"
                self.exit_reason = "objetivo"
                ACT.info("OBJETIVO alcanzado: mid=%.2f entrada=%.2f -> +%.2f$ >= %.2f$. "
                         "Se pide FLAT (la venta la hace trade_poll al MID)",
                         mid, self.entry_price, (mid - self.entry_price) * 100.0,
                         TAKE_PROFIT_USD)
        except Exception:
            LOG.exception("Error evaluando el objetivo de beneficio")

    def baseline_summary(self):
        """Por cada expiracion futura: (exp, call_hoy, call_prev, put_hoy, put_prev)."""
        out = []
        for exp in self.base_expiries:
            ch = cp = ph = pp = 0.0
            for (e, s, r), v in self.today_prem.items():
                if e != exp:
                    continue
                if r == "C":
                    ch += v
                else:
                    ph += v
            for (e, s, r), v in self.base_prev.items():
                if e != exp:
                    continue
                if r == "C":
                    cp += v
                else:
                    pp += v
            out.append((exp, ch, cp, ph, pp))
        return out

    def ladder_rows(self):
        """Datos para la Gamma Ladder (SOLO lectura, estilo MarketSnack). Barras = premium $ por
        strike de la banda (call+put), coloreadas por lado del precio. Marca CW/PW/precio/flip.
        Devuelve dict {rows:[(strike,prem,side,tag)], price, flip, magnet, state, max_prem}."""
        strikes = sorted({c.strike for c in self.band_contracts}, reverse=True)
        w = self.walls or {}
        cw = w.get("call_wall"); pw = w.get("put_wall")
        magnet = w.get("max_pain_dyn") if w.get("max_pain_dyn") is not None else w.get("max_pain_static")
        flip = (self.gex or {}).get("gamma_flip")
        price = self.spy_price
        rows = []
        max_prem = 0.0
        for s in strikes:
            prem = (self.today_prem.get((self.expiry, s, "C"), 0.0)
                    + self.today_prem.get((self.expiry, s, "P"), 0.0))
            side = "call" if (price is None or math.isnan(price) or s >= price) else "put"
            tag = "CW" if (cw is not None and s == cw) else ("PW" if (pw is not None and s == pw) else "")
            if magnet is not None and s == magnet:      # magneto como marca, estilo PW/CW
                tag = (tag + "M") if tag else "MAG"
            rows.append((s, prem, side, tag))
            if prem > max_prem:
                max_prem = prem
        # contrato comprado (solo si hay posicion real): strike + entrada + precio ACTUAL (P&L)
        contract = None
        if self.pos == "CALL" and self.buy_call is not None:
            contract = {"strike": self.buy_call.strike, "side": "CALL",
                        "entry": self.entry_price, "price": self.contract_price}
        elif self.pos == "PUT" and self.buy_put is not None:
            contract = {"strike": self.buy_put.strike, "side": "PUT",
                        "entry": self.entry_price, "price": self.contract_price}
        return {"rows": rows, "price": price, "flip": flip, "magnet": magnet,
                "state": self.state, "max_prem": max_prem, "contract": contract}

    # ---------------- procesamiento de trades ----------------
    def _on_ticks(self, tickers):
        signal_ids = {c.conId for c in (self.call, self.put) if c is not None}
        # BANDA (2026-08-12): hasta hoy se descartaba aqui, asi que el `tape` solo veia los 2
        # strikes rotatorios de senal + el baseline = 15,1% del volumen 0DTE, con 32 de 40
        # strikes a cero. Se recalcula por llamada, igual que `signal_ids`, para no desincronizarse
        # con `refresh_strikes`, que re-centra la banda en vivo.
        band_ids = {c.conId for c in (self.band_contracts or []) if c.conId}
        for tk in tickers:
            c = tk.contract
            is_signal = c.conId in signal_ids
            is_base = c.conId in self.info_base
            is_band = c.conId in band_ids
            if not (is_signal or is_base or is_band):
                continue
            vol = tk.volume
            last = tk.last
            if vol is None or math.isnan(vol) or last is None or math.isnan(last):
                continue
            prev = self.prev_vol.get(c.conId)
            self.prev_vol[c.conId] = vol
            if prev is None:
                continue
            dvol = vol - prev
            if dvol <= 0:
                continue
            premium = float(last) * float(dvol) * 100.0
            # premium BRUTO por strike (señal + baseline) para historial/estadisticas
            key = (c.lastTradeDateOrContractMonth, c.strike, c.right)
            self.accum[key] = self.accum.get(key, 0.0) + premium
            self.today_prem[key] = self.today_prem.get(key, 0.0) + premium
            # a partir de aqui, la ruta de walls NO debe volver a sumar el premium de este
            # contrato: ya lo mide esta funcion, por tick y con bid/ask alineados al trade.
            self._tick_prem_ids.add(c.conId)
            # SIGNO DEL AGRESOR: quien cruzo el spread. Es una INFERENCIA (regla del agresor),
            # no un dato de IBKR: toda opcion negociada tiene comprador Y vendedor. El flujo
            # que se ejecuta DENTRO del spread no se puede atribuir y se descarta (signed=0).
            # Se calcula para TODOS los strikes (senal + baseline) para poder acumular el neto
            # por strike; antes solo se computaba para los 2 de senal.
            bid = tk.bid if (tk.bid and not math.isnan(tk.bid)) else None
            ask = tk.ask if (tk.ask and not math.isnan(tk.ask)) else None
            signed = 0.0
            if ask is not None and last >= ask:
                signed = premium
            elif bid is not None and last <= bid:
                signed = -premium
            # acumulado NETO por strike, en paralelo al bruto (columnas cum_net/day_net)
            self.accum_net[key] = self.accum_net.get(key, 0.0) + signed
            self.today_net[key] = self.today_net.get(key, 0.0) + signed
            # --- TAPE (2026-08-11): una fila por operacion, SOLO REGISTRO ---
            # No toca la señal: se anota lo mismo que ya se calculo arriba, mas el TAMAÑO de la
            # operacion (tk.lastSize), que hasta ahora se tiraba. Con el agregado por minuto un
            # print de 3.038 contratos y 50 de 60 eran indistinguibles.
            # Va a un buffer en MEMORIA: _on_ticks corre en el hilo de Tkinter y a alta
            # frecuencia; un INSERT por tick bloquearia la GUI. El volcado es por lotes.
            if TAPE_ENABLED:
                try:
                    _ls = getattr(tk, "lastSize", None)
                    _ls = None if (_ls is None or math.isnan(_ls) or _ls <= 0) else float(_ls)
                    _now = datetime.now()
                    self._tape_buf.append((
                        _now.strftime("%Y-%m-%d"), _now.strftime("%H:%M:%S.") +
                        f"{_now.microsecond // 1000:03d}", time.time(),
                        key[0], key[1], key[2],
                        float(last), _ls, float(dvol), bid, ask,
                        ("COMPRA" if signed > 0 else ("VENTA" if signed < 0 else "MID")),
                        # premium de ESTA operacion (atribucion exacta) vs el del delta de
                        # volumen (lo que usa la señal): guardar ambos permite medir cuanto
                        # distorsiona la agregacion, sobre todo cuando el mercado va rapido.
                        (float(last) * _ls * 100.0) if _ls else None,
                        premium,
                        # 2026-08-12: tercer valor BANDA. Sin el, las operaciones de la banda
                        # entrarian como BASELINE y falsearian todos los analisis que filtran por
                        # `grupo` (analisis/premium_por_minuto.py, neto_por_strike.py, cobertura).
                        "SENAL" if is_signal else ("BASELINE" if is_base else "BANDA")))
                except Exception as _e:
                    # el tape JAMAS puede romper el procesamiento de la señal, asi que NO se
                    # propaga. Pero antes era `pass` a secas y una captura fallida se perdia
                    # en silencio: podia estar tirando operaciones sistematicamente sin que
                    # nada lo indicara. 2026-08-12: se CUENTAN y se reportan una vez por
                    # minuto en la linea de TAPE. No se loguea aqui a proposito: _on_ticks
                    # corre a alta frecuencia en el hilo de Tkinter y una linea por tick
                    # colgaria la GUI y llenaria el fichero.
                    self._tape_err = getattr(self, "_tape_err", 0) + 1
                    self._tape_err_last = "%s: %s" % (type(_e).__name__, _e)
                if len(self._tape_buf) >= TAPE_FLUSH_N:
                    self._flush_tape()
            # LA SENAL NO CAMBIA: net_call/net_put siguen sumando SOLO los strikes de senal.
            if is_signal:
                if c.right == "C":
                    self.net_call += signed
                else:
                    self.net_put += signed
        self._update_signal()

    def _prem_totales(self):
        """Totales acumulados HOY de la expiracion en curso, separados call/put:
        (bruto_call, bruto_put, neto_call, neto_put)."""
        bc = bp = nc = np_ = 0.0
        for (exp, _s, right), v in self.today_prem.items():
            if exp != self.expiry:
                continue                      # solo la expiry que se opera (la 0DTE)
            if right == "C":
                bc += v
            else:
                bp += v
        for (exp, _s, right), v in self.today_net.items():
            if exp != self.expiry:
                continue
            if right == "C":
                nc += v
            else:
                np_ += v
        return bc, bp, nc, np_

    def _prem_de_la_vela(self):
        """Premium que entro en ESTE minuto (la vela que acaba de cerrar), call y put por
        separado: total actual menos el de la vela anterior.

        Por que hace falta: `cum_prem`/`day_prem` solo crecen, asi que "premium alto" acaba
        significando "mas tarde en el dia" (M10) y cualquier correlacion contra el precio sale
        falsa. El flujo POR VELA no arrastra historia y se puede cruzar directamente con lo que
        hizo el SPY en ese mismo minuto.

        Devuelve (bruto_call, bruto_put, neto_call, neto_put), o None en el primer minuto y
        tras un reinicio: sin referencia anterior NO se inventa un delta (regla 13)."""
        bc, bp, nc, np_ = self._prem_totales()
        prev = self._prem_snap
        self._prem_snap = (bc, bp, nc, np_)
        if prev is None:
            return None, None, None, None
        d = (bc - prev[0], bp - prev[1], nc - prev[2], np_ - prev[3])
        # un delta bruto negativo es imposible (el bruto solo suma): significa que la referencia
        # es de otra sesion/expiry. Se descarta en vez de guardar un numero sin sentido.
        if d[0] < 0 or d[1] < 0:
            return None, None, None, None
        return d

    def _flujo_ventana(self, secs):
        """(net_call, net_put) del flujo de los ultimos `secs` segundos = acumulado actual
        menos el de hace `secs`. SOLO se GUARDA (ta_minute): NO decide nada.

        Para que existe: la decision usa el acumulado DESDE LA APERTURA, que nunca olvida.
        Girar cuesta |diff| + thr, y thr crece con el propio acumulado, asi que la barrera
        se ensancha sola con el dia (medido 2026-08-10: 17 -> 20 -> 12 -> 3 giros por hora;
        a las 12:36 hacian falta 2,81 M de flujo nuevo, mas del que habia dado el dia entero).
        Guardando las ventanas en paralelo se podra comprobar CON DATOS, en unas sesiones,
        si una ventana movil habria girado antes -y solo entonces decidir si se cambia."""
        if not self.flow_hist:
            return None, None
        limite = time.monotonic() - secs
        # Si la historia NO cubre la ventana entera, se devuelve None y se guarda NULL.
        # Usar el punto mas viejo disponible seria etiquetar 10 min de flujo como "15 min":
        # un dato falso es peor que un hueco (regla 13).
        if self.flow_hist[0][0] > limite:
            return None, None
        # punto MAS CERCANO al instante t-secs (no "el ultimo anterior a el": con historia
        # dispersa ese podria ser de hace el doble de tiempo y falsear la ventana).
        base = min(self.flow_hist, key=lambda r: abs(r[0] - limite))
        return self.net_call - base[1], self.net_put - base[2]

    def _senal_media(self):
        """Lado a COMPRAR segun la distancia a la media corta. None = no hay señal, estar FLAT.

        UNICO sitio donde vive esta regla (regla 9): la usan `_update_signal` para el estado y
        `trade_poll` para saber si hay que estar fuera. Si se duplicara, una copia acabaria
        diciendo lo contrario que la otra.

        OJO, es CONTRAINTUITIVA: se compra HACIA la media, no a favor del movimiento.
        Ante CUALQUIER duda (sin media, sin precio, excepcion) devuelve None -> no se opera.
        Nunca se inventa una direccion (regla 13)."""
        if not USAR_MEDIA:
            return None
        try:
            m = (self.ta_vals or {}).get("vwap")
            p = self.spy_price
            if not m or p is None or math.isnan(p):
                return None
            d = p - m
            if d >= MEDIA_DIST:
                return "PUT"        # precio ALTO respecto a la media -> deberia volver ABAJO
            if d <= -MEDIA_DIST:
                return "CALL"       # precio BAJO respecto a la media -> deberia volver ARRIBA
            return None             # dentro de la banda: no hay nada que capturar
        except Exception:
            return None

    def _update_signal(self):
        # GAP 18: NO evaluar la senal hasta haber intentado restaurar el estado del dia.
        # setup_contracts suscribe el market data de la senal ANTES de _load_intradia, asi que
        # durante ~4 s net_call/net_put valen 0 y el umbral cae al piso (5.000): cualquier
        # flujo minimo dispara un GIRO ESPURIO. Medido el 2026-08-10 a las 14:52:29
        # (`GIRO -> DOWN net_call=-10640 thr=5000`, corregido 4 s despues al restaurar), y con
        # dano real por la manana: 4 giros en 34 s tras el reinicio de las 11:50, cerrando una
        # posicion que la senal real habria mantenido. Ademas ensuciaba `transitions`.
        # Se reutiliza _intradia_ok, que _load_intradia pone a True JUSTO ANTES de restaurar
        # (misma bandera que ya usa _persist_accum para no escribir ceros sobre el estado bueno).
        # En DEMO no hay estado que restaurar (no se toca la BD real): el guard no aplica, o la
        # simulacion se quedaria congelada sin girar nunca.
        if not self._intradia_ok and not self.demo:
            return
        diff = self.net_call - self.net_put
        hhmmss = datetime.now().strftime("%H:%M:%S")
        # historia con SELLO DE TIEMPO: alimenta el momentum (GAP 5) y las ventanas moviles.
        ahora = time.monotonic()
        self.flow_hist.append((ahora, self.net_call, self.net_put))
        if self.flow_hist and self.flow_hist[0][0] < ahora - 900.0:
            corte = ahora - 900.0
            self.flow_hist[:] = [r for r in self.flow_hist if r[0] >= corte]

        # GAP 5: momentum = cuanto se ha movido el diff en los ultimos MOMENTUM_SECS.
        # Se REUSA _flujo_ventana en vez de una segunda historia (regla 9): la ventana devuelve
        # (net_call - nc0, net_put - np0), y su resta es exactamente (diff - diff0).
        # Sin historia suficiente -> 0.0: preferimos NO avisar antes que avisar con un dato que
        # no existe (con momentum 0 las condiciones de WARN no se cumplen).
        _mv = self._flujo_ventana(MOMENTUM_SECS)
        momentum = (_mv[0] - _mv[1]) if _mv[0] is not None else 0.0

        # umbral ADAPTATIVO: escala con la magnitud real del flujo (miles->millones)
        if ADAPTIVE:
            thr = max(SIGNAL_THRESHOLD, ADAPT_FRAC * (abs(self.net_call) + abs(self.net_put)))
        else:
            thr = SIGNAL_THRESHOLD
        mom_min = MOM_FRAC * thr
        self.last_diff = diff; self.last_thr = thr; self.last_momentum = momentum  # para log exhaustivo

        band = thr * WARN_BAND_FRAC
        if self.state == "UP" and diff < band and momentum <= -mom_min:
            if self.last_warn_side != "DOWN":
                self._raise_alert("WARN", f"posible GIRO a DOWN ({hhmmss})", "warn")
                self._save("DOWN", "WARN")
                self.last_warn_side = "DOWN"
        elif self.state == "DOWN" and diff > -band and momentum >= mom_min:
            if self.last_warn_side != "UP":
                self._raise_alert("WARN", f"posible GIRO a UP ({hhmmss})", "warn")
                self._save("UP", "WARN")
                self.last_warn_side = "UP"

        new = self.state
        # M1 EFECTIVO: se calcula SIEMPRE, decida o no. Alimenta `m1_efectivo`, que va a
        # `m1_minute` y al panel. Si esto colgara del `if USAR_M1` (como antes), activar otro
        # disparador dejaria la columna en NULL y se perderia la serie con la que comparar.
        # 2026-08-11: dominancia en VALOR ABSOLUTO, contador de MINUTOS. `m1_estado` lo
        # actualiza ta_poll una vez por minuto, asi que M1 solo puede girar en el cambio de
        # minuto: eso elimina los flips en rafaga. RETARDO: se usa lo que M1 decia hace
        # RETARDO_M1_MIN minutos, no lo de ahora. NEUTRAL o None -> no se inventa direccion.
        limite = ahora - RETARDO_M1_MIN * 60.0
        efec = None
        for _ts, _st in self.m1_hist:
            if _ts <= limite:
                efec = _st
            else:
                break
        self.m1_efectivo = efec

        if USAR_MEDIA:
            # DISPARADOR VIGENTE (2026-08-12): distancia a la media corta. Se compra HACIA la
            # media. Ver el bloque de constantes para los numeros y los controles pasados.
            # Sin media o sin precio NO se toca el estado: no se inventa direccion (regla 13).
            _lado = self._senal_media()
            if _lado == "CALL":
                new = "UP"
            elif _lado == "PUT":
                new = "DOWN"
        elif USAR_M1:
            if efec in ("UP", "DOWN"):
                new = efec
        elif diff > thr:
            new = "UP"
        elif diff < -thr:
            new = "DOWN"
        if new != self.state and new in ("UP", "DOWN"):
            self.state = new
            self.transitions.append((hhmmss, new))
            self.transitions[:] = self.transitions[-8:]
            self.last_warn_side = None
            self._raise_alert("FLIP", f"CAMBIO -> {new}  ({hhmmss})", "flip")
            self._save(new, "FLIP")
            # objetivo de posicion segun la nueva direccion
            self.target = "CALL" if new == "UP" else "PUT"
            # ANCLA DEL RETROCESO: se fija AQUI, en el instante del giro, porque es el unico
            # momento en que se sabe cual fue el impulso que precedio a la senal. Guarda el
            # reloj, el precio y el objetivo al que tiene que retroceder para poder entrar.
            # Si no hay impulso medible se deja en None -> la compuerta no espera (entra ya).
            self.retro_ancla = None
            try:
                _imp = self.impulso_actual
                if (ENTRADA_RETROCESO and _imp is not None and abs(_imp) > 1e-9
                        and self.spy_price is not None and not math.isnan(self.spy_price)):
                    self.retro_ancla = {
                        "t": time.monotonic(), "spy": self.spy_price, "imp": _imp,
                        "objetivo": self.spy_price - _imp * RETRO_FRAC,
                        "er": self.er_actual, "lado": self.target}
            except Exception:
                self.retro_ancla = None
            self.exit_reason = "giro"    # la venta que provoque este giro se marca como tal
            # 2026-08-12: decir POR QUE giro. Antes imprimia `thr` siempre, y con USAR_M1
            # el umbral ya NO interviene en la decision: al releer el log parecia que el
            # giro venia del umbral cuando lo disparo M1 con RETARDO_M1_MIN de retraso.
            if USAR_M1:
                ACT.info("GIRO -> %s por M1 (efectivo de hace %d min; M1 ahora=%s) "
                         "| net_call=%.0f net_put=%.0f abs C=%.0f P=%.0f | thr=%.0f NO decide",
                         new, RETARDO_M1_MIN, self.m1_estado or "-",
                         self.net_call, self.net_put,
                         abs(self.net_call), abs(self.net_put), thr)
            else:
                ACT.info("GIRO -> %s por CLASICO diff/thr (net_call=%.0f net_put=%.0f "
                         "diff=%.0f thr=%.0f)",
                         new, self.net_call, self.net_put, diff, thr)

    def _raise_alert(self, kind, text, sound):
        self.alert_kind = kind
        self.alert_text = text
        self.alert_until = time.monotonic() + 6.0
        ACT.info("ALERTA %s: %s", kind, text)
        if ENABLE_SOUND:
            self.pending_sound = sound
        if ENABLE_TOAST and kind == "FLIP":
            self._toast("SPY: CAMBIO DE DIRECCION", text)

    def _toast(self, title, msg):
        title = str(title).replace("'", " ").replace('"', " ")
        msg = str(msg).replace("'", " ").replace('"', " ")
        ps = (
            "$ErrorActionPreference='SilentlyContinue';"
            "[void][Windows.UI.Notifications.ToastNotificationManager,"
            "Windows.UI.Notifications,ContentType=WindowsRuntime];"
            "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            "$x=$t.GetElementsByTagName('text');"
            f"[void]$x.Item(0).AppendChild($t.CreateTextNode('{title}'));"
            f"[void]$x.Item(1).AppendChild($t.CreateTextNode('{msg}'));"
            "$toast=[Windows.UI.Notifications.ToastNotification]::new($t);"
            "$n=[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('SPY Direction');"
            "$n.Show($toast)")
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def simulate_step(self):
        t = self.demo_i
        self.demo_i += 1
        diff = 12000.0 * math.sin(t / 6.0)
        self.net_call = 2000.0 + max(0.0, diff) + t * 8
        self.net_put = 2000.0 + max(0.0, -diff) + t * 4
        self.spy_price = 773.0 + math.sin(t / 6.0) * 0.8
        self.status = "MODO DEMO - entradas simuladas (no es dato real)"
        # demo: en vivo m1_hist lo puebla ta_poll cada minuto; aqui lo alimentamos con el estado
        # sintetico y un timestamp que YA cumplio el retardo, para VER la rotacion sin esperar 20 min.
        if USAR_M1:
            self.m1_estado = "UP" if self.net_call >= self.net_put else "DOWN"
            self.m1_hist = [(time.monotonic() - (RETARDO_M1_MIN * 60.0 + 5.0), self.m1_estado)]
        self._update_signal()
        self._demo_walls(t)

    def _demo_walls(self, t):
        """SOLO --demo: genera datos de prueba SINTETICOS (no reales) para VER moverse la
        Gamma Ladder, walls/GEX/flip y la linea de contrato comprado. No toca IBKR ni la BD real."""
        self.expiry = "DEMO"
        center = round(self.spy_price)
        if not self.band_contracts:
            strikes = [center - 5 + i for i in range(11)]     # 11 strikes alrededor del precio
            self.band_contracts = []
            for s in strikes:
                self.band_contracts.append(Option(SYMBOL, self.expiry, s, "C", "SMART", tradingClass=SYMBOL))
                self.band_contracts.append(Option(SYMBOL, self.expiry, s, "P", "SMART", tradingClass=SYMBOL))
        # strike "caliente" que se desplaza -> el pico de premium se mueve (barras respiran)
        hot = self.spy_price + 2.0 * math.sin(t / 10.0)
        for c in self.band_contracts:
            s = c.strike
            bump = math.exp(-((s - hot) ** 2) / 6.0)          # gaussiana movil
            wobble = 1.0 + 0.35 * math.sin(t / 3.0 + s)
            base = 1_200_000.0 if c.right == "C" else 900_000.0
            self.today_prem[(self.expiry, s, c.right)] = base * bump * wobble
        # walls sinteticos: CW arriba, PW abajo, magnetos y centro de peso
        cw = center + 2
        pw = center - 2
        self.walls = {
            "put_wall": float(pw), "call_wall": float(cw),
            "max_pain_static": float(center),
            "max_pain_dyn": float(center + round(math.sin(t / 8.0))),
            "prem_center": hot, "spot": self.spy_price,
        }
        gex_total = 3.0e9 * math.sin(t / 7.0)                  # cambia de signo -> LONG/SHORT alterna
        self.gex = {
            "gex_total": gex_total,
            "regime": "LONG" if gex_total > 0 else ("SHORT" if gex_total < 0 else "FLAT"),
            "gamma_flip": self.spy_price - 1.0 + 0.6 * math.sin(t / 5.0),
            "spot": self.spy_price,
        }
        # contrato comprado SIMULADO: sigue la señal; cada ~18 ticks queda FLAT 3 ticks (para ver
        # que la linea DESAPARECE al vender y reaparece al recomprar)
        prev_pos = self.pos
        prev_entry = self.entry_price
        prev_price = self.contract_price
        if (t % 18) < 3:
            self.pos = "FLAT"; self.entry_price = None; self.contract_price = None
        elif self.state == "UP":
            self.pos = "CALL"
            self.buy_call = Option(SYMBOL, self.expiry, center + 1, "C", "SMART", tradingClass=SYMBOL)
            self.entry_price = 1.05
            self.contract_price = round(1.05 + 0.45 * math.sin(t / 4.0), 2)   # precio en vivo (oscila)
        elif self.state == "DOWN":
            self.pos = "PUT"
            self.buy_put = Option(SYMBOL, self.expiry, center - 1, "P", "SMART", tradingClass=SYMBOL)
            self.entry_price = 2.05
            self.contract_price = round(2.05 + 0.55 * math.sin(t / 4.0), 2)
        # notificacion DEMO de compra/venta al cambiar la posicion (con profit al vender)
        if ENABLE_TOAST and self.pos != prev_pos:
            if prev_pos in ("CALL", "PUT"):
                prof = ((prev_price if prev_price is not None else prev_entry or 0.0)
                        - (prev_entry or 0.0)) * 100.0 * QTY
                self._toast("SPY: VENTA (demo) LLENADA", f"SPY {prev_pos} vendida  Profit {prof:+.0f}$")
            if self.pos in ("CALL", "PUT"):
                bc = self.buy_call if self.pos == "CALL" else self.buy_put
                rl = "C" if self.pos == "CALL" else "P"
                self._toast("SPY: COMPRA (demo) LLENADA", f"SPY {bc.strike:g}{rl} @ {self.entry_price:.2f}")

    # ================= EJECUCION AUTOMATICA (rotar 1 opcion) =================
    def _minTick(self, contract):
        if contract.conId in self.min_tick:
            return self.min_tick[contract.conId]
        mt = 0.01
        try:
            cds = self.ib.reqContractDetails(contract)
            if cds and cds[0].minTick:
                mt = cds[0].minTick
        except Exception:
            pass
        self.min_tick[contract.conId] = mt
        return mt

    def _mid(self, contract):
        """SIEMPRE el MID (bid+ask)/2 redondeado al minTick. NUNCA bid/ask/market.
        Devuelve None si no hay bid/ask (entonces NO se coloca; se espera cotizacion)."""
        tk = self.ib.ticker(contract)
        bid = tk.bid if (tk and tk.bid and not math.isnan(tk.bid) and tk.bid > 0) else None
        ask = tk.ask if (tk and tk.ask and not math.isnan(tk.ask) and tk.ask > 0) else None
        if bid is None or ask is None or ask < bid:
            return None
        mt = self._minTick(contract)
        mid = (bid + ask) / 2.0
        return round(round(mid / mt) * mt, 2)

    def _bid_ask(self, contract):
        """(bid, ask) crudos del contrato, o (None, None). Para registrar el spread real que
        se pago, no solo el MID: la friccion es la mitad del problema del scalping 0DTE."""
        tk = self.ib.ticker(contract)
        if tk is None:
            return None, None
        bid = tk.bid if (tk.bid and not math.isnan(tk.bid) and tk.bid > 0) else None
        ask = tk.ask if (tk.ask and not math.isnan(tk.ask) and tk.ask > 0) else None
        return bid, ask

    def _greeks_de(self, contract):
        """Greeks (delta/gamma/theta/vega/iv/undPrice) del contrato que se OPERA.

        POR QUE NO SE LEEN DE SU PROPIO TICKER: los contratos de ejecucion se suscriben con
        genericTickList="" (solo bid/ask para el MID), asi que su modelGreeks es SIEMPRE None.
        Y no basta con que la banda pida "106" sobre el MISMO contrato de IBKR: ib_insync
        indexa los tickers por id(OBJETO) (wrapper.py: self.tickers[id(contract)]), no por
        conId, de modo que el objeto de ejecucion y el de la banda tienen tickers DISTINTOS.

        Solucion sin gastar una sola linea de market data (van 68 de ~100): buscar en la banda
        el contrato del mismo strike/right -y misma expiry- y leer SU ticker, que si trae greeks.

        Devuelve dict con None en los campos que falten. NUNCA inventa un valor (regla 13):
        si el strike no esta en la banda, todo va a None y se guarda NULL en la BD."""
        vacio = {"delta": None, "gamma": None, "theta": None, "vega": None,
                 "iv": None, "und_price": None}
        if contract is None or not self.band_contracts:
            return vacio
        # busqueda directa sobre la banda (40 contratos): evita mantener un indice paralelo
        # sincronizado en los 3 sitios donde band_contracts se reasigna. Un indice viejo
        # devolveria greeks del strike EQUIVOCADO sin que nada avisara.
        bc = next((c for c in self.band_contracts
                   if c.strike == contract.strike
                   and c.right == contract.right
                   and c.lastTradeDateOrContractMonth == contract.lastTradeDateOrContractMonth),
                  None)
        if bc is None:
            return vacio
        tk = self.ib.ticker(bc)
        g = getattr(tk, "modelGreeks", None) if tk is not None else None
        if g is None:
            return vacio

        def _v(x):
            if x is None:
                return None
            try:
                x = float(x)
            except (TypeError, ValueError):
                return None
            return None if math.isnan(x) else x

        return {"delta": _v(getattr(g, "delta", None)),
                "gamma": _v(getattr(g, "gamma", None)),
                "theta": _v(getattr(g, "theta", None)),
                "vega": _v(getattr(g, "vega", None)),
                "iv": _v(getattr(g, "impliedVol", None)),
                "und_price": _v(getattr(g, "undPrice", None))}

    def _flush_tape(self, forzar=False):
        """Vuelca a la BD el buffer del TAPE, por lotes.

        Se llama desde _on_ticks (cuando el buffer llega a TAPE_FLUSH_N) y desde _log_minute
        (una vez por minuto, con forzar=True). Nunca desde ambos a la vez porque el bucle de la
        app es de un solo hilo.

        NUNCA propaga una excepcion: el tape es SOLO registro y no puede tumbar ni la señal ni
        el ciclo principal. Si falla, se pierde ese lote y se avisa en el log de errores."""
        if not self._tape_buf:
            return 0
        if not forzar and len(self._tape_buf) < TAPE_FLUSH_N:
            return 0
        lote, self._tape_buf = self._tape_buf, []
        try:
            self.db.executemany(
                "INSERT INTO tape(fecha,hora,ts,expiry,strike,right,last,size,dvol,bid,ask,"
                "agresor,premium,premium_dvol,grupo) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", lote)
            self.db.commit()
            self._tape_n += len(lote)
            return len(lote)
        except Exception:
            LOG.exception("Error volcando el TAPE (se pierde este lote, la señal NO se afecta)")
            return 0

    _PRECIO_VACIO = {"bid": None, "ask": None, "mid": None, "last": None, "spread": None}

    def _precio_de(self, expiry, strike, right):
        """Precio VIVO de un contrato seguido: bid/ask/mid/last/spread. Solo para REGISTRO.

        Mismo patron que _greeks_de y por los mismos motivos:
          - ib_insync indexa los tickers por id(OBJETO), no por conId, asi que hay que usar el
            MISMO objeto que se paso a reqMktData. Un Option() equivalente NO sirve.
          - Busqueda directa sobre las listas vivas, sin indice paralelo: band_contracts se
            reasigna en 3 sitios y _base_ct en 2; un indice desincronizado devolveria el precio
            del strike EQUIVOCADO sin que nada avisara.

        Orden: banda -> baseline -> senal. La banda va primero porque su ticker es el mas
        completo (se pide con "100,101,106").

        NUNCA inventa (regla 13): si el contrato no esta suscrito -por ejemplo una expiry YA
        VENCIDA que sigue viva en self.accum- devuelve todo None y en la BD queda NULL.
        mid/spread solo existen con bid Y ask; con uno solo, None."""
        cont = None
        # 1) banda (expiracion cercana, 40 contratos)
        # getattr y no acceso directo: un contrato sin lastTradeDateOrContractMonth lanzaria
        # AttributeError, y como esta funcion se llama DENTRO del try de _persist_walls, ese
        # error abortaria el bucle entero y dejaria walls SIN persistir (0 filas), sin que
        # nada avisara salvo una linea en spy_direction.log. Lo detecto el diferencial:
        # spy_walls_coldrun paso de 58 a 56 checks. Si falta la expiry se compara solo por
        # strike/right, que dentro de la banda (una sola expiracion) es identificacion
        # suficiente; si sobra, el filtro por expiry sigue aplicandose.
        for c in (self.band_contracts or []):
            if c.strike == strike and c.right == right:
                exp_c = getattr(c, "lastTradeDateOrContractMonth", None)
                if exp_c is None or exp_c == expiry:
                    cont = c
                    break
        # 2) baseline (expiraciones futuras). _base_ct guarda el OBJETO suscrito, que es lo que
        #    hace falta para que ib.ticker() lo encuentre.
        if cont is None:
            for cid, info in (self.info_base or {}).items():
                if info == (expiry, strike, right):
                    cont = self._base_ct.get(cid)
                    break
        # 3) strikes de SENAL (ATM/ITM de la expiry cercana)
        if cont is None:
            for c in (self.call, self.put):
                if c is None or c.strike != strike or c.right != right:
                    continue
                exp_c = getattr(c, "lastTradeDateOrContractMonth", None)   # ver nota de arriba
                if exp_c is None or exp_c == expiry:
                    cont = c
                    break
        if cont is None:
            return dict(self._PRECIO_VACIO)
        try:
            tk = self.ib.ticker(cont)
        except Exception:
            return dict(self._PRECIO_VACIO)
        if tk is None:
            return dict(self._PRECIO_VACIO)

        def _v(x):
            """IBKR manda NaN cuando no hay dato: se convierte a None para guardar NULL y no un
            0 falso. Tambien se descarta el 0 en bid/ask: un contrato no cotiza a cero, es
            'sin cotizacion' (mismo criterio que _mid)."""
            try:
                x = float(x)
            except (TypeError, ValueError):
                return None
            return None if (math.isnan(x) or x <= 0) else x

        bid, ask, last = _v(getattr(tk, "bid", None)), _v(getattr(tk, "ask", None)), \
            _v(getattr(tk, "last", None))
        mid = round((bid + ask) / 2.0, 4) if (bid is not None and ask is not None) else None
        spread = round(ask - bid, 4) if (bid is not None and ask is not None) else None
        return {"bid": bid, "ask": ask, "mid": mid, "last": last, "spread": spread}

    def _read_account(self):
        """Lee el estado de la cuenta de IBKR (la fuente de verdad) para la vista.
        Reutiliza accountSummary, que ib_insync ya mantiene cacheado tras la 1a llamada."""
        try:
            net = avail = None
            real = unreal = None
            for r in self.ib.accountSummary():
                if r.tag == "NetLiquidation":
                    net = float(r.value)
                elif r.tag == "AvailableFunds":
                    avail = float(r.value)
                # M2: el P&L lo lleva el BROKER. El calculo interno se desviaba (2026-08-10:
                # la app decia -98.11 y la cuenta real -54): un fill perdido no computo su
                # profit y un episodio de 3 contratos uso un unico entry_price cuando el coste
                # medio real era otro. Aqui se lee el dato de IBKR; el interno se conserva
                # SOLO para comparar y detectar cuando vuelve a desviarse.
                elif r.tag == "RealizedPnL":
                    try:
                        real = float(r.value)
                    except (TypeError, ValueError):
                        real = None
                elif r.tag == "UnrealizedPnL":
                    try:
                        unreal = float(r.value)
                    except (TypeError, ValueError):
                        unreal = None
            if net is not None:
                self.acct_net = net
                if self.acct_net_open is None:
                    self.acct_net_open = net     # base del dia: 1a lectura
                    ACT.info("CUENTA base del dia: NetLiquidation=%.2f", net)
            if avail is not None:
                self.acct_avail = avail
            self.pnl_ibkr = real
            self.pnl_ibkr_unreal = unreal
            if real is None and not self._pnl_avisado:
                self._pnl_avisado = True
                ACT.info("PNL: IBKR no expone RealizedPnL en accountSummary -> el panel sigue "
                         "usando el calculo interno (puede desviarse, ver M2)")
            elif real is not None:
                # avisar solo cuando la desviacion importa (>1 USD) y cambia
                dev = real - self.pnl_realizado
                if abs(dev) > 1.0 and abs(dev - self._pnl_dev_avisada) > 1.0:
                    self._pnl_dev_avisada = dev
                    ACT.info("PNL DESVIACION: IBKR realizado=%.2f vs interno=%.2f (dif %+.2f) "
                             "| manda IBKR", real, self.pnl_realizado, dev)
        except Exception:
            LOG.exception("Error leyendo el estado de la cuenta")

    def resumen_cuenta(self):
        """Texto para la vista: cuanto hay, cuanto se ha movido hoy y que se lleva acumulado."""
        if self.acct_net is None:
            return "Cuenta: (leyendo de IBKR...)"
        dia = (self.acct_net - self.acct_net_open) if self.acct_net_open else 0.0
        pct = (dia / self.acct_net_open * 100.0) if self.acct_net_open else 0.0
        # M2: manda el realizado de IBKR si lo da; si no, el interno (marcado como tal).
        if self.pnl_ibkr is not None:
            real_txt = f"realizado {self.pnl_ibkr:+,.2f} (IBKR)"
            if abs(self.pnl_ibkr - self.pnl_realizado) > 1.0:
                real_txt += f" [interno {self.pnl_realizado:+,.2f}]"
        else:
            real_txt = f"realizado {self.pnl_realizado:+,.2f} (interno)"
        txt = (f"Cuenta ${self.acct_net:,.2f}   disp ${self.acct_avail or 0:,.2f}   "
               f"|   DIA {dia:+,.2f} ({pct:+.1f}%)   "
               f"|   {real_txt}   "
               f"ops {self.n_trades}")
        if self.n_trades:
            txt += f" ({self.n_wins} ganadoras, {100.0 * self.n_wins / self.n_trades:.0f}%)"
        return txt

    def _can_afford(self, price):
        try:
            avail = None
            for r in self.ib.accountSummary():
                if r.tag in ("AvailableFunds", "BuyingPower"):
                    try:
                        v = float(r.value)
                    except Exception:
                        continue
                    if r.tag == "AvailableFunds":
                        avail = v
                        break
                    if avail is None:
                        avail = v
            if avail is None:
                return True  # si no se pudo leer, no bloquear (se vera en paper)
            return avail >= price * 100 * QTY
        except Exception:
            return True

    def _cancel_working(self):
        """Cancela CUALQUIER orden de opciones SPY viva (evita limits huerfanas)."""
        try:
            for tr in self.ib.openTrades():
                c = tr.contract
                if (c.symbol == SYMBOL and c.secType == "OPT"
                        and tr.orderStatus.status in ("PreSubmitted", "Submitted", "PendingSubmit")):
                    self.ib.cancelOrder(tr.order)
                    ACT.info("Cancelada orden huerfana %s", getattr(tr.order, "orderId", "?"))
        except Exception:
            LOG.exception("Error cancelando ordenes huerfanas")

    def _reconcile(self):
        self.reconciled = True
        try:
            self._cancel_working()   # limpiar limits colgadas de una corrida previa
            opts = [p for p in self.ib.positions()
                    if p.contract.symbol == SYMBOL and p.contract.secType == "OPT"
                    and p.position and p.position > 0]
            if len(opts) == 1:
                p = opts[0]
                self.pos = "CALL" if p.contract.right == "C" else "PUT"
                self.target = self.pos            # mantener hasta el proximo flip
                # El contrato a VENDER debe ser el que se POSEE, no el que recalculo
                # setup_contracts: si el precio se movio, el strike nuevo seria otro y
                # venderiamos algo que no tenemos (corto descubierto).
                # _adoptar_posicion ademas le asegura market data (sin ella _mid()=None y
                # la VENTA nunca se colocaria) y recupera la entrada desde avgCost.
                self.pos_qty = float(p.position)
                self._adoptar_posicion(p, self.pos)
                ACT.info("Reconcile: posicion real %s %s x%g -> contrato de salida reapuntado",
                         self.pos, getattr(p.contract, "localSymbol", "?"), self.pos_qty)
            elif len(opts) > 1:
                self.pos = "CALL" if opts[0].contract.right == "C" else "PUT"
                self.target = "FLAT"              # >1 posicion: aplanar todo al MID
                ACT.info("Reconcile: %d posiciones SPY -> aplanar", len(opts))
            else:
                self.pos = "FLAT"; self.target = "FLAT"
        except Exception:
            LOG.exception("Error en reconcile")

    def _live_orders(self):
        """Ordenes de opciones SPY VIVAS segun IBKR (no segun self.order)."""
        try:
            return [tr for tr in self.ib.openTrades()
                    if tr.contract.symbol == SYMBOL and tr.contract.secType == "OPT"
                    and tr.orderStatus.status in ("PreSubmitted", "Submitted",
                                                  "PendingSubmit", "PendingCancel")]
        except Exception:
            return []

    def _strike_ejecucion(self, right, px):
        """Strike que se OPERA: el ITM mas profundo que quepa en el capital disponible.

        POR QUE NO EL ATM. Medido el 2026-08-12 con precios reales. Con el SPY QUIETO 5 horas
        (773.53 -> 773.56), lo que perdio cada strike solo por el paso del tiempo:
            765C ITM  8.57 -> 8.59    -0.1%     773C ATM  1.71 -> 0.82   -51.8%
            770C ITM  3.91 -> 3.57    -8.7%     775C OTM  0.79 -> 0.12   -85.4%
        El ATM es casi todo valor TEMPORAL y se evapora aunque la direccion acierte. El ITM
        tiene valor INTRINSECO, que no se evapora: es lo que hace viable AGUANTAR una tendencia
        larga en un 0DTE en vez de tener que cobrar rapido.
        La MISMA operacion #12 (misma entrada 10:25, misma salida) daba:
            773C ATM  -27.00 (110$)      770C ITM  +39.00 (318$)      769C ITM  +53.00 (406$)
        Con 400$ de cuenta el 770C cabia y convertia -27.00 en +39.00.

        Devuelve (strike, motivo). CAE AL ATM -y lo dice en el motivo- si falta cualquier dato:
        sin capital conocido, sin precio del strike, o si ningun ITM cabe. Nunca inventa un
        precio ni asume capital (regla 13). El peor caso es el comportamiento anterior.
        """
        atm = min(self.strikes, key=lambda s: abs(s - px))
        try:
            if not EJECUCION_ITM:
                return atm, "ATM (EJECUCION_ITM=False)"
            cap = self.acct_avail
            if cap is None or cap <= 0:
                return atm, "ATM (capital disponible desconocido)"
            tope = cap * CAPITAL_FRAC_MAX
            # ITM: la call POR DEBAJO del precio, la put POR ENCIMA. Se prueba del mas profundo
            # (mas caro, mas intrinseco) al mas superficial, y se coge el primero que quepa.
            if right == "C":
                cands = sorted([s for s in self.strikes if s < px])
            else:
                cands = sorted([s for s in self.strikes if s > px], reverse=True)
            for s in cands:
                p = self._precio_de(self.expiry, s, right) or {}
                coste = p.get("ask") or p.get("mid")
                if coste and coste > 0:
                    total = coste * 100.0 * QTY
                    if total <= tope:
                        return s, (f"ITM {abs(s - px):.0f}pts dentro: cuesta {total:.0f}$ de "
                                   f"{tope:.0f}$ disponibles ({CAPITAL_FRAC_MAX:.0%} de "
                                   f"{cap:.0f}$)")
            return atm, f"ATM (ningun ITM cabe en {tope:.0f}$)"
        except Exception:
            LOG.exception("Error eligiendo el strike de ejecucion")
            return atm, "ATM (error al elegir)"

    def _nuevo_opt(self, strike, right):
        """Crea+califica un contrato de opcion de la expiracion en curso."""
        c = Option(SYMBOL, self.expiry, strike, right, "SMART", tradingClass=SYMBOL)
        self.ib.qualifyContracts(c)
        return c if getattr(c, "conId", None) else None

    def _soltar_mkt(self, contract):
        """Libera la suscripcion de market data de un contrato que ya no se sigue.

        GAP D (2026-08-11): al soltar hay que OLVIDAR tambien su volumen previo.
        `prev_vol`/`band_prev_vol` guardan el volumen ACUMULADO DEL DIA de cada conId.
        Si el contrato se vuelve a seguir mas tarde (el SPY se mueve y regresa), el
        primer tick calcularia dvol = volumen_de_ahora - volumen_de_cuando_se_solto,
        metiendo de golpe TODO lo que se negocio mientras no mirabamos: un premium
        FANTASMA de millones en un solo minuto.
        El bloque de la LINEA BASE ya lo hacia (`prev_vol.pop` mas abajo), pero las
        rutas de SENAL, EJECUCION y BANDA llamaban aqui sin olvidar nada. Se hace en
        este embudo porque es el punto por el que pasan las 6.
        Coste de olvidar: se pierde el delta de UN tick al re-suscribir (el primero
        solo siembra). Se prefiere perder un tick a inventar millones."""
        if contract is None:
            return
        # Olvidar PRIMERO, fuera del try: si `cancelMktData` lanza (IB caido) el
        # except se tragaria los pop y quedaria el volumen viejo — y es justo tras
        # una caida cuando se re-suscribe todo. Estas dos lineas no pueden fallar.
        cid = getattr(contract, "conId", None)
        if cid is not None:
            self.prev_vol.pop(cid, None)
            self.band_prev_vol.pop(cid, None)
        try:
            self.ib.cancelMktData(contract)
            self._mkt_subs.discard(cid)
        except Exception:
            pass

    def refresh_strikes(self):
        """TODO SIGUE AL PRECIO. setup_contracts solo corre 1 vez por sesion, asi que los
        strikes quedaban congelados al precio de apertura: la SENAL medira flujo en strikes
        que ya no son ATM, la EJECUCION compra el contrato equivocado y la banda de walls
        deja de estar centrada. Aqui se recalculan los tres con el precio actual.

        SEGURIDAD: los contratos de EJECUCION solo se mueven con la cuenta PLANA y sin orden
        viva; cambiarlos con posicion abierta haria que trade_poll vendiera algo que no se
        posee (corto descubierto)."""
        if not self.strikes or self.spy_price is None or math.isnan(self.spy_price):
            return
        px = self.spy_price
        try:
            # ---- 1) SENAL: ATM/ITM (call<=precio, put>=precio), nunca OTM ----
            below = [s for s in self.strikes if s <= px]
            above = [s for s in self.strikes if s >= px]
            if below and above:
                cs, ps = max(below), min(above)
                if self.call is None or self.call.strike != cs:
                    nc = self._nuevo_opt(cs, "C")
                    if nc is not None:
                        self._soltar_mkt(self.call)
                        self.call = nc
                        self.ib.reqMktData(nc, "233", False, False)
                        ACT.info("SENAL call re-centrada -> %gC (precio %.2f)", cs, px)
                        self.m_recentrado = 1   # GAP D: minuto contaminado
                if self.put is None or self.put.strike != ps:
                    np_ = self._nuevo_opt(ps, "P")
                    if np_ is not None:
                        self._soltar_mkt(self.put)
                        self.put = np_
                        self.ib.reqMktData(np_, "233", False, False)
                        ACT.info("SENAL put re-centrada -> %gP (precio %.2f)", ps, px)
                        self.m_recentrado = 1   # GAP D: minuto contaminado

            # ---- 2) EJECUCION: ATM REAL (strike mas cercano al precio) ----
            # Solo con la cuenta plana: con posicion abierta se venderia otro contrato.
            if self.pos == "FLAT" and self.order is None:
                # 2026-08-12: el strike ya NO es el ATM fijo. `_strike_ejecucion` elige el ITM
                # mas profundo que quepa en el capital (el ATM se evapora: -51.8% en 5 h con el
                # SPY quieto, frente a -0.1% del ITM profundo). Cae al ATM si falta cualquier
                # dato, asi que el peor caso es el comportamiento anterior.
                k_c, why_c = self._strike_ejecucion("C", px)
                k_p, why_p = self._strike_ejecucion("P", px)
                if self.buy_call is None or self.buy_call.strike != k_c:
                    bc = self._nuevo_opt(k_c, "C")
                    if bc is not None:
                        self._soltar_mkt(self.buy_call)
                        self.buy_call = bc
                        self.ib.reqMktData(bc, "", False, False)
                        self._mkt_subs.add(bc.conId)
                        ACT.info("EJECUCION call -> %gC (precio %.2f) | %s", k_c, px, why_c)
                if self.buy_put is None or self.buy_put.strike != k_p:
                    bp = self._nuevo_opt(k_p, "P")
                    if bp is not None:
                        self._soltar_mkt(self.buy_put)
                        self.buy_put = bp
                        self.ib.reqMktData(bp, "", False, False)
                        self._mkt_subs.add(bp.conId)
                        ACT.info("EJECUCION put -> %gP (precio %.2f) | %s", k_p, px, why_p)

            # ---- 2-bis) LINEA BASE: los strikes ATM/ITM de las expiraciones FUTURAS ----
            # Tambien tienen que seguir al precio: si no, se acumula premium de contratos
            # que ya son OTM, justo lo que el diseno dice evitar. Se suscriben los que
            # entran en rango y se SUELTAN los que salen (presupuesto de lineas constante).
            # Lo acumulado NO se pierde: self.accum esta indexado por (expiry,strike,right)
            # y persiste en strike_accum aunque se deje de seguir ese strike.
            if self.base_expiries:
                cs, ps = self._band(self.strikes, px)
                quiero = set()
                for exp in self.base_expiries:
                    for s in cs:
                        quiero.add((exp, s, "C"))
                    for s in ps:
                        quiero.add((exp, s, "P"))
                tengo = {v: k for k, v in self.info_base.items()}   # (exp,strike,right)->conId
                nuevos = quiero - set(tengo)
                sobran = set(tengo) - quiero
                if nuevos or sobran:
                    for k in sobran:
                        cid = tengo[k]
                        c = self._base_ct.get(cid)
                        if c is not None:
                            self._soltar_mkt(c)
                            self._base_ct.pop(cid, None)
                        self.info_base.pop(cid, None)
                        # CRITICO: sin esto, si ese contrato vuelve a seguirse mas tarde,
                        # su volumen (acumulado del dia) contra un prev_vol viejo generaria
                        # un delta enorme y un premium FANTASMA.
                        self.prev_vol.pop(cid, None)
                    for (exp, s, r) in sorted(nuevos):
                        o = Option(SYMBOL, exp, s, r, "SMART", tradingClass=SYMBOL)
                        try:
                            self.ib.qualifyContracts(o)
                        except Exception:
                            continue
                        if not getattr(o, "conId", None):
                            continue
                        self.info_base[o.conId] = (o.lastTradeDateOrContractMonth, o.strike, o.right)
                        self._base_ct[o.conId] = o
                        self.ib.reqMktData(o, "233", False, False)
                    ACT.info("LINEA BASE re-centrada en %.2f: +%d nuevos, -%d soltados "
                             "(siguiendo %d contratos de %d expiraciones)",
                             px, len(nuevos), len(sobran), len(self.info_base),
                             len(self.base_expiries))

            # ---- 3) BANDA DE WALLS: re-centrar si el precio se ha ido del medio ----
            # Cuesta 40 suscripciones, asi que solo cuando la deriva es real (>3 strikes).
            if WALLS_ENABLED and self.band_contracts:
                ban = sorted({c.strike for c in self.band_contracts})
                centro = ban[len(ban) // 2]
                idx_c = min(range(len(self.strikes)), key=lambda i: abs(self.strikes[i] - centro))
                idx_p = min(range(len(self.strikes)), key=lambda i: abs(self.strikes[i] - px))
                if abs(idx_p - idx_c) > 3:
                    nb = ([s for s in self.strikes if s <= px][-WALLS_BAND:]
                          + [s for s in self.strikes if s > px][:WALLS_BAND])
                    viejos = list(self.band_contracts)
                    nuevos = []
                    for s in nb:
                        for r in ("C", "P"):
                            o = self._nuevo_opt(s, r)
                            if o is not None:
                                nuevos.append(o)
                    if nuevos:
                        for c in viejos:
                            self._soltar_mkt(c)
                        self.band_contracts = nuevos
                        for c in nuevos:
                            # 233 OBLIGATORIO, igual que en setup_contracts (:1259). Sin el, en
                            # cuanto el precio deriva >3 strikes la banda se re-suscribe SIN
                            # RTVolume y el tape se queda ciego otra vez, EN SILENCIO: no hay
                            # error, simplemente dejan de llegar `last`/`lastSize` y esos 40
                            # contratos desaparecen del tape hasta el siguiente reinicio.
                            # Son DOS sitios de suscripcion de la banda: si se cambia uno hay
                            # que cambiar el otro.
                            self.ib.reqMktData(c, "100,101,106,233", False, False)
                        ACT.info("BANDA walls re-centrada en %.2f: %g-%g (%d contratos)",
                                 px, nb[0], nb[-1], len(nuevos))
        except Exception:
            LOG.exception("Error re-centrando strikes")

    def _ensure_mkt(self, contract):
        """Asegura bid/ask para un contrato en cartera.
        CRITICO: los contratos que devuelve ib.positions() vienen SIN market data (la
        suscripcion la tienen los creados en setup_contracts). Sin ticker, _mid() devuelve
        None -> no hay precio ni P&L en pantalla Y ADEMAS _place() no coloca la VENTA,
        con lo que la posicion se queda atrapada."""
        try:
            cid = getattr(contract, "conId", None)
            if not cid or cid in self._mkt_subs:
                return
            # ib.positions() devuelve el contrato SIN exchange y reqMktData lo exige:
            # IBKR responde 321 "Please enter exchange" y la suscripcion nunca llega.
            if not getattr(contract, "exchange", ""):
                contract.exchange = "SMART"
            self.ib.reqMktData(contract, "", False, False)
            self._mkt_subs.add(cid)
            ACT.info("Market data suscrito para el contrato en cartera %s",
                     getattr(contract, "localSymbol", cid))
        except Exception:
            LOG.exception("Error suscribiendo market data del contrato en cartera")

    def _adoptar_posicion(self, p, lado):
        """Toma el contrato REAL en cartera como contrato de salida: lo reapunta solo si
        cambia (no churn de objetos, o se pierde el ticker), le asegura cotizacion y
        recupera el precio de entrada desde avgCost si la app no lo sabe (tras reiniciar)."""
        con = p.contract
        actual = self.buy_call if lado == "CALL" else self.buy_put
        if actual is None or getattr(actual, "conId", None) != getattr(con, "conId", None):
            if lado == "CALL":
                self.buy_call = con
            else:
                self.buy_put = con
        self._ensure_mkt(self.buy_call if lado == "CALL" else self.buy_put)
        # avgCost de opciones viene por contrato con multiplicador 100 (95.05 -> 0.9505)
        if not self.entry_price:
            try:
                ac = float(getattr(p, "avgCost", 0) or 0)
                if ac > 0:
                    self.entry_price = ac / 100.0
                    ACT.info("Entrada recuperada de IBKR (avgCost=%.2f) -> %.4f",
                             ac, self.entry_price)
            except Exception:
                pass

    def _sync_pos(self):
        """RED DE SEGURIDAD: la posicion REAL de IBKR manda sobre self.pos.
        self.pos es una variable en memoria y puede DIVERGIR de la realidad (una orden
        'cancelada' puede haberse llenado igual). No toca self.target: eso lo decide la senal."""
        try:
            opts = [p for p in self.ib.positions()
                    if p.contract.symbol == SYMBOL and p.contract.secType == "OPT"
                    and p.position and p.position > 0]
            real, qty, pos_obj = "FLAT", 0.0, None
            if opts:
                p = opts[0]
                real = "CALL" if p.contract.right == "C" else "PUT"
                qty = float(p.position)
                pos_obj = p
            if real != self.pos or qty != self.pos_qty:
                ACT.info("SYNC posicion REAL de IBKR=%s x%g | la app creia %s x%g -> corregido",
                         real, qty, self.pos, self.pos_qty)
            if pos_obj is not None:
                # vender SIEMPRE el contrato que se POSEE, con cotizacion asegurada
                self._adoptar_posicion(pos_obj, real)
            self.pos = real
            self.pos_qty = qty
            if real in ("CALL", "PUT") and self.trade_id is None and pos_obj is not None:
                # GAP 20 (2026-08-11): posicion ADOPTADA de IBKR sin pasar por _on_filled -> nadie
                # abria su fila en 'trades' y la operacion entera quedaba sin registrar.
                # Ocurrio en vivo hoy: la orden 2134 se reporto Cancelled con filled=0 y se lleno
                # igual (09:35:12); _sync_pos corrigio la posicion pero el PUT 773 se compro a 1.11
                # y se vendio a 1.12 (+0.96) SIN dejar rastro en trades ni en posicion_minuto.
                # Es el simetrico exacto del cierre "externa" de abajo: si al desaparecer una
                # posicion se CIERRA el registro, al aparecer una hay que ABRIRLO.
                cont = self.buy_call if real == "CALL" else self.buy_put
                if cont is None:
                    cont = pos_obj.contract
                # entry_price lo acaba de recuperar _adoptar_posicion desde avgCost (dato REAL de
                # IBKR). Si no hubiera, se usa el MID; y si tampoco, NO se inventa: no se abre.
                px = self.entry_price or self._mid(cont)
                if px:
                    ACT.info("TRADE: posicion %s x%g adoptada de IBKR sin registro -> abriendo "
                             "fila en trades @ %.4f (GAP 20)", real, qty, px)
                    self._trade_abrir(cont, px, qty)
                else:
                    ACT.info("TRADE: posicion %s x%g adoptada pero SIN precio (ni avgCost ni MID) "
                             "-> no se abre fila, no se inventa un precio (GAP 20)", real, qty)
            if real == "FLAT":
                # La posicion desaparecio de IBKR sin pasar por _on_filled (venta llenada
                # mientras la app estaba parada, o cerrada a mano en TWS). Cerrar el trade
                # para que no quede abierto para siempre. Sin precio: no se INVENTA uno.
                if self.trade_id is not None:
                    self._trade_cerrar(None, None, None, "externa")
                self.entry_price = None
                self.contract_price = None
                # Liberar el cupo de compra SOLO cuando ya no puede llegar un fill tardio.
                # Si se libera antes, se vuelve a comprar y acabamos con 2-3 contratos.
                if (self.buys_pend and not self._live_orders()
                        and time.monotonic() - self.last_buy_ts > BUY_SETTLE_SECS):
                    ACT.info("Cupo de compra liberado (FLAT, sin ordenes vivas, %.0fs desde "
                             "la ultima compra)", time.monotonic() - self.last_buy_ts)
                    self.buys_pend = 0
        except Exception:
            LOG.exception("Error en _sync_pos")

    def _place(self, contract, action, side, qty=None):
        """Coloca SIEMPRE una LimitOrder al MID. Si no hay MID, NO coloca (espera).
        qty=None -> QTY (compras). En las VENTAS se pasa la cantidad REAL en cartera."""
        # GUARDA DURA: si IBKR reporta alguna orden viva, NO colocar otra (invariante
        # "jamas 2 limits vivas"). self.order puede estar en None y aun asi haber una viva.
        vivas = self._live_orders()
        if vivas:
            self.trade_msg = f"{len(vivas)} orden(es) viva(s) en IBKR - no coloco otra"
            return
        # GAP 19 - GUARDA POR TIEMPO. La de arriba consulta el ESTADO, y el estado puede mentir:
        # el 2026-08-10 a las 15:45 IBKR reporto la orden como `Cancelled` (estado FINAL), con
        # lo que salio de openTrades() y _live_orders() la dio por muerta... y se ejecuto 16 s
        # despues. Se colocaron 4 ventas encima y solo el control de margen de IBKR evito 4
        # shorts descubiertos. NO hay estado que consultar que lo evite: la unica defensa es
        # esperar a que el broker digiera la cancelacion.
        _desde_cancel = time.monotonic() - self.last_cancel_ts
        if self.last_cancel_ts and _desde_cancel < CANCEL_SETTLE_SECS:
            self.trade_msg = (f"esperando {CANCEL_SETTLE_SECS - _desde_cancel:.0f}s a que IBKR "
                              f"confirme la cancelacion anterior")
            ACT.info("ORDEN %s %s BLOQUEADA: solo han pasado %.1fs desde el cancel (minimo "
                     "%.0fs). IBKR puede llenar una orden que ya reporto como cancelada.",
                     action, side, _desde_cancel, CANCEL_SETTLE_SECS)
            return
        px = self._mid(contract)
        # GAP 4 - EOD: pasadas las CROSS_HHMM la VENTA cruza el spread (va al BID). Sin esto,
        # una venta al MID que no encuentre contraparte deja la 0DTE viva hasta las 16:00, y
        # end_session cancela y desconecta -> el contrato EXPIRA valiendo 0.
        cruzar = (action == "SELL" and now_et().weekday() < 5
                  and now_et().strftime("%H:%M") >= CROSS_HHMM)
        if cruzar:
            _bid, _ask = self._bid_ask(contract)
            if _bid is not None:
                mt = self._minTick(contract)
                px_cruce = round(round(_bid / mt) * mt, 2)
                ACT.info("EOD CRUCE DE SPREAD (%s>=%s): %s %s al BID %.2f en vez del MID %s "
                         "-> ULTIMO RECURSO tras 10 min insistiendo al MID; quedan <5 min y la "
                         "0DTE expira a las 16:00",
                         now_et().strftime("%H:%M"), CROSS_HHMM, action, side, px_cruce,
                         ("%.2f" % px) if px is not None else "sin MID")
                px = px_cruce
            elif px is None:
                ACT.info("EOD CRUCE: %s %s sin BID ni MID - no se puede colocar, se reintenta",
                         action, side)
        if px is None:
            self.trade_msg = f"esperando MID para {action} {side} (sin bid/ask)"
            return
        q = int(qty) if qty else QTY
        if q <= 0:
            return
        # LIMITE DURO DE 1 CONTRATO (hasta que el usuario decida cambiarlo).
        # No basta con mirar la posicion CONFIRMADA: IBKR puede llenar una orden que ya
        # reporto como cancelada hasta 22 s despues (medido 2026-08-10: 3 compras del mismo
        # strike por recotizar cada 4 s). Hay que contar tambien lo que va EN VUELO.
        if action == "BUY":
            comprometido = self.pos_qty + self.buys_pend
            if comprometido >= QTY:
                self.trade_msg = (f"{comprometido:g} contrato(s) comprometido(s) "
                                  f"(max {QTY}) - NO se compra mas")
                return
        try:
            # M12: tif explicito. Sin el, el Gateway aplica su preset y devuelve un aviso
            # `10349 Order TIF was set to DAY based on order preset` por CADA orden (54 en la
            # sesion del 2026-08-10). Fijarlo elimina el ruido y hace explicito el contrato.
            self.order = self.ib.placeOrder(contract, LimitOrder(action, q, px, tif="DAY"))
            self.order_action = action
            self.order_side = side
            self.order_contract = contract
            # EOD: recotizar MUCHO mas rapido. Colocar al MID, si no llena cancelar y volver a
            # colocar, una y otra vez, hasta que entre. Ir al BID regala el spread, asi que se
            # insiste al MID los primeros 10 min y el cruce queda como ultimo recurso (15:55).
            _eod = (action == "SELL" and now_et().weekday() < 5
                    and now_et().strftime("%H:%M") >= FLATTEN_HHMM)
            self.order_deadline = time.monotonic() + (EOD_REPRICE_SECS if _eod else REPRICE_SECS)
            if action == "BUY":
                self.buys_pend += q          # cupo ocupado hasta que se resuelva
                self.last_buy_ts = time.monotonic()
            self.trade_msg = f"{action} {side} x{q} LIMIT MID @ {px:.2f}"
            ACT.info("ORDEN %s %s x%d LIMIT MID @ %.2f (comprometido=%g)",
                     action, side, q, px, self.pos_qty + self.buys_pend)
        except Exception as e:
            self.trade_msg = f"error orden: {e}"
            self.order = None
            LOG.exception("Error colocando orden %s %s", action, side)

    def _comision_de_orden(self):
        """Comision REAL de la orden recien llenada, sumando sus fills. None si IBKR todavia
        no ha entregado el commissionReport (llega asincrono, puede tardar mas que el fill).

        None NO es 0: significa 'no lo se'. Devolver 0 haria que un P&L neto pareciera igual
        al bruto y esa es justo la confusion que esta columna viene a resolver."""
        try:
            tot = None
            for f in (getattr(self.order, "fills", None) or []):
                cr = getattr(f, "commissionReport", None)
                com = getattr(cr, "commission", None) if cr is not None else None
                if com is None or (isinstance(com, float) and math.isnan(com)):
                    continue
                tot = (tot or 0.0) + float(com)
            return tot
        except Exception:
            return None

    def _on_filled(self):
        act, side = self.order_action, self.order_side
        try:
            px = self.order.orderStatus.avgFillPrice
        except Exception:
            px = 0.0
        # comision de ESTA pata. La de la compra se guarda hasta que la venta cierre la fila:
        # la columna `comision` es el coste de las DOS patas, que es lo que hay que restar al
        # `profit` bruto para saber si la operacion gano dinero de verdad.
        _com = self._comision_de_orden()
        if act == "BUY":
            self._com_entrada = _com
            if _com is None:
                ACT.info("COMISION de la compra NO disponible todavia (commissionReport "
                         "asincrono) -> se guardara NULL si tampoco llega en la venta")
        # cantidad REALMENTE llenada (puede no ser QTY: fills parciales / venta de varios lotes)
        try:
            nq = float(self.order.orderStatus.filled) or float(QTY)
        except Exception:
            nq = float(QTY)
        # profit al VENDER (usa el precio de entrada ANTES de limpiarlo)
        profit = pct = None
        if act == "SELL" and self.entry_price:
            profit = (px - self.entry_price) * 100.0 * nq
            pct = (px / self.entry_price - 1.0) * 100.0
            # acumulado del dia (para la vista y el registro por minuto)
            self.pnl_realizado += profit
            self.n_trades += 1
            if profit > 0:
                self.n_wins += 1
        rl = "C" if side == "CALL" else "P"
        c = getattr(self, "order_contract", None)
        strike = f"{c.strike:g}{rl}" if c is not None else side
        self.trade_msg = (f"{act} {side} LLENADO @ {px:.2f}"
                          + (f"  Profit {profit:+.2f} ({pct:+.1f}%)" if profit is not None else ""))
        ACT.info("FILL %s %s @ %.2f -> pos=%s%s", act, side, px,
                 "FLAT" if act != "BUY" else side,
                 (f" | PROFIT {profit:+.2f} ({pct:+.1f}%)" if profit is not None else ""))
        # NOTIFICACION en el FILL REAL (cuando la orden se llena, NO al enviarla)
        if ENABLE_TOAST:
            if act == "BUY":
                self._toast(f"SPY: COMPRA {side} LLENADA", f"SPY {strike} @ {px:.2f}")
            else:
                body = f"SPY {strike} @ {px:.2f}"
                if profit is not None:
                    body += f"  |  Profit {profit:+.2f} ({pct:+.1f}%)"
                self._toast(f"SPY: VENTA {side} LLENADA", body)
        # CERRAR el registro de la operacion ANTES de limpiar pos/entry_price: _pos_snapshot
        # necesita los dos vivos para grabar la fila 'salida'.
        if act != "BUY":
            # coste de las DOS patas. Si solo se conoce una, se guarda esa y se DICE en el log
            # que es parcial: mejor un dato marcado como incompleto que un NULL que borra lo
            # unico que si se sabe. Si no se conoce ninguna -> None (no lo se), nunca 0.
            _ce = getattr(self, "_com_entrada", None)
            _com_tot = None
            if _ce is not None or _com is not None:
                _com_tot = (_ce or 0.0) + (_com or 0.0)
                if _ce is None or _com is None:
                    ACT.info("COMISION PARCIAL en el trade #%s: entrada=%s salida=%s -> se "
                             "guarda %.2f (falta una pata)", self.trade_id,
                             _fmt(_ce), _fmt(_com), _com_tot)
            self._trade_cerrar(px, profit, pct, self.exit_reason or "giro", _com_tot)
            self._com_entrada = None
            self.exit_reason = None
        # actualizar posicion/entrada DESPUES de calcular el profit
        # (valor PROVISIONAL: _sync_pos lo corrige contra IBKR, que es la fuente de verdad)
        self.pos = side if act == "BUY" else "FLAT"
        self.pos_qty = nq if act == "BUY" else 0.0
        self.entry_price = px if act == "BUY" else None
        if act != "BUY":
            self.contract_price = None
        self.order = None
        self.open_deadline = 0.0
        # ABRIR el registro DESPUES: _trade_abrir lee self.pos y _pos_snapshot lee entry_price.
        if act == "BUY" and c is not None:
            self._trade_abrir(c, px, nq)

    def trade_poll(self):
        """Motor de ejecucion, se llama en cada tick (no bloquea la GUI)."""
        if self.demo or not self.trading or not self.ib.isConnected():
            return
        if self.buy_call is None or self.buy_put is None:
            return
        if not self.reconciled:
            self._reconcile()

        # RED DE SEGURIDAD: la posicion REAL de IBKR manda sobre self.pos. Sin esto la app
        # puede creerse FLAT teniendo contratos (orden 'cancelada' que se llenó igual).
        if self.order is None and time.monotonic() - self.last_sync > SYNC_POS_SECS:
            self._sync_pos()
            self.last_sync = time.monotonic()

        # CAPITAL BAJO: NUNCA mas de QTY contrato(s). Si hay de mas, aplanar TODO.
        if self.pos_qty > QTY:
            if self.target != "FLAT":
                ACT.info("EXCESO de posicion: %g contratos (maximo %d) -> aplanar TODO",
                         self.pos_qty, QTY)
            self.target = "FLAT"
            self.exit_reason = "exceso"

        et = now_et()
        hhmm = et.strftime("%H:%M")
        weekday = et.weekday() < 5
        # RTH_OPEN_HHMM y NO el literal "09:30": desde 2026-08-11 la RECOLECCION empieza a las
        # 09:00, pero OPERAR sigue empezando a las 09:30. Antes de esa hora in_session es False
        # -> stop_new True -> no se abre ninguna posicion en pre-market.
        in_session = weekday and (RTH_OPEN_HHMM <= hhmm <= "16:00")
        if weekday and hhmm >= FLATTEN_HHMM:      # EOD: aplanar
            if self.target != "FLAT":
                self.exit_reason = "eod"
            self.target = "FLAT"
        elif USAR_MEDIA:
            # SALIDA POR PERMANENCIA Y ESTAR FUERA SIN SEÑAL (2026-08-12).
            # El disparador de la media NO mantiene la posicion hasta el proximo giro: vende a
            # los MINUTOS_POS minutos y se queda FLAT hasta que vuelva a haber señal. Medido:
            # con salida a 8 min +331.86$ en los 2 dias; aguantar hasta el giro es lo que hizo
            # el sistema el 08-12 (una posicion de 5h20m -> -83.44$ en esa sola operacion).
            # El reloj sale de trade_open["ts"] (monotonic, fijado en _trade_abrir): NO se usa
            # nada de la fila `trades`, cuyo mfe/mae se corrompe en cada reinicio.
            if self.pos in ("CALL", "PUT") and self.trade_open:
                _en_pos = time.monotonic() - self.trade_open.get("ts", time.monotonic())
                if _en_pos >= MINUTOS_POS * 60.0:
                    if self.target != "FLAT":
                        self.exit_reason = "tiempo"
                        ACT.info("SALIDA POR TIEMPO: %.1f min en %s (tope %d) -> FLAT",
                                 _en_pos / 60.0, self.pos, MINUTOS_POS)
                    self.target = "FLAT"
                else:
                    # MANTENER hasta cumplir el tiempo, AUNQUE la señal gire. Es lo que se
                    # midio; salir al invertirse la señal da PEOR resultado (+133/+117 frente
                    # a +154/+313). Sin esta linea, el flip de `_update_signal` sacaria antes
                    # y el comportamiento dejaria de ser el validado. Riesgo acotado: 8 min.
                    self.target = self.pos
            elif self.pos == "FLAT":
                # Sin posicion: el objetivo es lo que diga la señal, y FLAT si no dice nada.
                # Sin este `else` el target se quedaria pegado al ultimo lado y se recompraria
                # en cuanto se vendiera, ignorando que la señal ya no esta activa.
                self.target = self._senal_media() or "FLAT"
                # NO QUEDARSE MUDO EN SILENCIO. Con USAR_MEDIA, si falta la media el sistema no
                # opera NUNCA -- y sin este aviso pareceria "un dia sin señales". Es el mismo
                # fallo silencioso que el tape sin RTVolume: no fallaba, solo no veia. Se
                # distingue "dentro de la banda" (normal) de "no hay dato" (anormal).
                if in_session and not (self.ta_vals or {}).get("vwap"):
                    if not getattr(self, "_aviso_sin_media", False):
                        ACT.info("⚠️ USAR_MEDIA activo pero NO hay media disponible "
                                 "(ta_vals sin 'vwap'): NO se abrira ninguna posicion hasta "
                                 "que el TA tenga sus barras. Revisar backfill/GAP 17.")
                        self._aviso_sin_media = True
                elif getattr(self, "_aviso_sin_media", False):
                    ACT.info("media disponible de nuevo: el disparador vuelve a operar")
                    self._aviso_sin_media = False
        # 3 motivos para no ABRIR: fuera de sesion, cerca del cierre (EOD) o aun en los primeros
        # minutos de la apertura. Se separan para poder decirle al usuario CUAL es (ver trade_msg).
        # `in_session and hhmm < START_TRADE_HHMM` era INALCANZABLE desde el 2026-08-12 08:53:
        # ese commit bajo START_TRADE_HHMM de 09:35 a 09:30, y como in_session ya exige
        # hhmm >= RTH_OPEN_HHMM (09:30), la condicion pedia hhmm >= 09:30 Y hhmm < 09:30 a la
        # vez -> False SIEMPRE. Efecto real: a las 09:29 el panel decia "sin abrir nuevas (EOD)"
        # -- fin de dia a las nueve de la manana -- que es justo la mentira que esta variable
        # existe para evitar. Se quita el `in_session`: lo que importa es que aun no ha llegado
        # la hora de operar, no si el mercado ya abrio. No cambia NINGUNA decision de operar
        # (eso lo gobierna stop_new, que no se toca): cambia solo lo que se le dice al usuario.
        espera_apertura = weekday and hhmm < START_TRADE_HHMM
        stop_new = ((not in_session)
                    or (weekday and hhmm >= STOP_NEW_HHMM)
                    or (weekday and hhmm < START_TRADE_HHMM))

        now = time.monotonic()
        # ---- orden activa: gestionar fill / re-precio ----
        if self.order is not None:
            st = self.order.orderStatus.status
            # GAP 19 - TRAZA DE ESTADOS. El 2026-08-10 no se pudo reconstruir por que se
            # colocaron 4 ventas encima de una orden viva: el log no guardaba los estados
            # intermedios. Se registra cada CAMBIO (no cada tick, seria spam).
            if st != self._last_order_status:
                try:
                    _f = self.order.orderStatus.filled
                    _r = self.order.orderStatus.remaining
                    _oid = getattr(self.order.order, "orderId", "?")
                except Exception:
                    _f = _r = _oid = "?"
                ACT.info("ORDEN estado %s -> %s (id=%s filled=%s remaining=%s)",
                         self._last_order_status or "-", st, _oid, _f, _r)
                self._last_order_status = st
            if st == "Filled":
                self._on_filled()
                return
            if st in ("Cancelled", "ApiCancelled", "Inactive"):
                # OJO: 'Cancelado' NO significa 'no paso nada'. Entre el cancelOrder y su
                # confirmacion la orden SIGUE siendo ejecutable y puede haberse llenado
                # (total o parcialmente). Si se ignora, la app cree estar FLAT teniendo
                # contratos reales -> posiciones huerfanas que nadie cierra.
                try:
                    llenado = float(self.order.orderStatus.filled or 0)
                except Exception:
                    llenado = 0.0
                if llenado > 0:
                    ACT.info("ORDEN cancelada PERO llenada x%g -> se procesa como FILL", llenado)
                    self._on_filled()
                    return
                self.order = None
                self._last_order_status = None
            elif now >= self.order_deadline:
                # No lleno al MID: SOLO cancelar. La recotizacion al MID nuevo ocurre cuando
                # el cancel se confirme (order=None) -> jamas 2 limits vivas (no short).
                try:
                    self.ib.cancelOrder(self.order.order)
                    # GAP 19: marcar CUANDO se pidio la cancelacion. _place no colocara nada
                    # nuevo hasta CANCEL_SETTLE_SECS, aunque IBKR reporte la orden como
                    # cancelada: puede seguir viva y ejecutarse (medido: 16-22 s despues).
                    if not self.last_cancel_ts or now - self.last_cancel_ts > 1.0:
                        ACT.info("CANCEL solicitado (id=%s) - no se recoloca hasta %.0fs",
                                 getattr(self.order.order, "orderId", "?"), CANCEL_SETTLE_SECS)
                    self.last_cancel_ts = now
                except Exception:
                    pass
            return

        # ---- sin orden viva: mover posicion al objetivo (SIEMPRE LimitOrder al MID) ----
        # Estado en REPOSO: posicion ya en el objetivo, no hay nada que hacer. Hay que decirlo
        # explicitamente; si no, el panel se queda con el ultimo mensaje (o con el inicial) y
        # parece que el sistema esta parado cuando en realidad esta armado y vigilando.
        if self.pos == self.target and self.order is None:
            if self.pos in ("CALL", "PUT"):
                self.trade_msg = (f"ARMADO - en {self.pos} {self.pos_qty:g}, "
                                  f"esperando giro a {'DOWN' if self.pos == 'CALL' else 'UP'}")
            else:
                if espera_apertura:
                    # el motivo importa: a las 09:31 decir "(EOD)" era MENTIRA y cuesta tiempo de
                    # diagnostico (el 2026-08-10 el panel decia "trading OFF" estando ARMADO)
                    self.trade_msg = (f"ARMADO - FLAT, sin abrir hasta las {START_TRADE_HHMM} "
                                      f"(dejando que el acumulado se forme)")
                elif stop_new:
                    self.trade_msg = "ARMADO - FLAT, sin abrir nuevas (EOD)"
                else:
                    self.trade_msg = "ARMADO - FLAT, esperando senal"
        if self.pos != self.target:
            if self.pos in ("CALL", "PUT"):
                # GUARDA DURA ANTES DE VENDER: confirmar contra IBKR que la posicion SIGUE
                # existiendo. Si una venta anterior se lleno y el sondeo de estado no lo
                # detecto, volver a vender seria un SHORT DESCUBIERTO (2026-08-10: 4 intentos
                # seguidos; solo el control de margen de IBKR los freno, no el codigo).
                self._sync_pos()
                self.last_sync = time.monotonic()
                if self.pos not in ("CALL", "PUT") or self.pos_qty <= 0:
                    self.trade_msg = "sin posicion real en IBKR - NO se vende (evita descubierto)"
                    return
                # CERRAR: vender al MID, RELENTLESS (reintenta hasta llenar).
                # Se vende la cantidad REAL en cartera (si quedaron 3 lotes, se cierran los 3;
                # vender QTY=1 dejaria 2 huerfanos que nadie cerraria).
                contract = self.buy_call if self.pos == "CALL" else self.buy_put
                self._place(contract, "SELL", self.pos, qty=(self.pos_qty or QTY))
            elif self.target in ("CALL", "PUT") and not stop_new:
                # COMPUERTA DEL RETROCESO (2026-08-12): en regimen de REVERSION no se compra en
                # el impulso; se espera a que el precio devuelva RETRO_FRAC de lo recorrido.
                # VA ANTES de tocar `open_deadline` A PROPOSITO: si se fijara aqui, MAX_FILL_SECS
                # correria DURANTE la espera y la entrada se abandonaria sola. Solo retrasa: al
                # llegar a RETRO_MAX_MIN `_retroceso_pendiente` devuelve False y se compra igual.
                _esperar, _motivo = self._retroceso_pendiente()
                if _esperar:
                    self.trade_msg = f"ARMADO - {self.target} en espera: {_motivo}"
                    return
                if self.retro_ancla and self.retro_ancla.get("lado") == self.target:
                    self.retro_espero_min = (time.monotonic() - self.retro_ancla["t"]) / 60.0
                # ABRIR: comprar al MID, con limite de tiempo (si no llena, abandona -> FLAT)
                if not self.open_deadline:
                    self.open_deadline = now + MAX_FILL_SECS
                if now >= self.open_deadline:
                    self.trade_msg = f"BUY {self.target} no lleno al MID - abandonado"
                    self.target = "FLAT"
                    self.open_deadline = 0.0
                else:
                    # GUARDA DURA (capital bajo): 1 SOLA posicion, 1 SOLO contrato.
                    # Se comprueba contra IBKR, NO contra self.pos: una orden 'cancelada'
                    # pudo llenarse y dejarnos con contratos que la app no sabe que tiene.
                    self._sync_pos()
                    self.last_sync = time.monotonic()
                    if self.pos_qty > 0:
                        self.trade_msg = (f"ya hay {self.pos_qty:g} contrato(s) en cartera "
                                          f"- NO se compra hasta cerrarlos")
                        return
                    # RE-CENTRAR AHORA MISMO: hay que comprar el ATM de ESTE instante, no el
                    # de hace 20 s. Tras cerrar una posicion, _reconcile deja buy_call/buy_put
                    # apuntando al contrato que se acaba de vender; sin esto se recompraria
                    # el mismo strike viejo en vez del ATM actual.
                    self.refresh_strikes()
                    self.last_strikes = time.monotonic()
                    contract = self.buy_call if self.target == "CALL" else self.buy_put
                    px = self._mid(contract)
                    if px is None:
                        self.trade_msg = "esperando MID (sin bid/ask)"
                    elif self._can_afford(px):
                        self._place(contract, "BUY", self.target)
                    else:
                        self.trade_msg = f"sin buying power para {self.target}"

    def toggle_trading(self):
        self.trading = not self.trading
        self.trade_msg = "TRADING ARMADO" if self.trading else "TRADING OFF (desarmado)"
        ACT.info("TRADING %s por el usuario", "ARMADO" if self.trading else "DESARMADO")
        return self.trading

    # ================= TA 1 min + registro por minuto =================
    def _chequear_barras(self, rows):
        """GAP 17, deteccion B (por FRESCURA): la unica que detecta un stream muerto EN
        SILENCIO. No pregunta si hay conexion -mentiria, el socket sigue vivo- sino si el dato
        AVANZA. Mismo criterio que compute_walls usa para el gamma ('gamma cambiaron=N/40')."""
        if not rows:
            return
        ult = rows[-1]["date"]
        if ult != getattr(self, "_bars_ult_date", None):
            self._bars_ult_date = ult
            self.bars_last_advance = time.monotonic()
            if self.bars_stale:
                ACT.info("BARRAS: el stream volvio a avanzar (ultima barra %s)", ult)
                self.bars_stale = False
                self.bars_retries = 0
            return
        # no avanza: solo es un fallo si el mercado esta abierto (fuera de RTH es lo normal).
        # is_rth() y NO is_market_open(): desde 2026-08-11 la recoleccion empieza a las 09:00 y
        # con useRTH=True no hay barras nuevas hasta las 09:30 -> seria un GAP 17 falso.
        if (not self.bars_stale and self.is_rth()
                and self.bars_last_advance
                and time.monotonic() - self.bars_last_advance > BARS_STALE_SECS):
            self.bars_stale = True
            ACT.info("BARRAS ESTANCADAS: %.0fs sin avanzar (ultima %s). spy_price NO es de "
                     "fiar -> walls/GEX quedan marcados como stale hasta reponer el stream",
                     time.monotonic() - self.bars_last_advance, ult)

    def _guardar_barras(self, rows):
        """Persiste las velas de 1 min en `bars_minute`. SOLO REGISTRO: no decide nada.

        POR QUE: `reqHistoricalData(BARS_DURATION="2 D")` entrega ~442 barras en cada arranque y
        hasta hoy se TIRABAN (no habia ni tabla ni INSERT). `ta_minute` solo guardaba el cierre,
        asi que no se podian formar velas ni buscar patrones contra el premium que entra.

        La PRIMERA pasada vuelca la ventana ENTERA -> rellena hacia atras los 2 dias sin logica
        de backfill. Despues solo las 3 ultimas: la que se acaba de cerrar y la que se esta
        formando (INSERT OR REPLACE la va actualizando), que es barato y deja el dato en vivo.

        Nunca puede romper ta_poll: si falla, se cuenta y se sigue (el TA y la senal no dependen
        de esto). Se reporta una vez por minuto en la linea de BARRAS, no por tick.
        """
        if not rows:
            return
        try:
            primera = not getattr(self, "_bars_backfill_ok", False)
            # ESCRIBIR 1 VEZ POR MINUTO, no por tick. ta_poll corre cada REFRESH_SECS (1 s) y un
            # commit por segundo con journal_mode=delete crea y borra el journal 3.600 veces por
            # hora, compitiendo por el lock con todo lo demas. Se vuelca solo cuando cambia el
            # minuto de la ultima vela; la que se esta formando se actualiza al cerrarse.
            _ult = rows[-1].get("date")
            _clave = _ult.strftime("%Y-%m-%d %H:%M") if hasattr(_ult, "strftime") else str(_ult)[:16]
            if not primera and _clave == getattr(self, "_bars_last_clave", None):
                return
            self._bars_last_clave = _clave
            lote = rows if primera else rows[-3:]
            datos = []
            for r in lote:
                d = r.get("date")
                if hasattr(d, "strftime"):
                    fecha, hora = d.strftime("%Y-%m-%d"), d.strftime("%H:%M")
                else:
                    s = str(d)
                    if len(s) < 16:
                        continue
                    fecha, hora = s[:10], s[11:16]
                datos.append((fecha, hora, r.get("open"), r.get("high"), r.get("low"),
                              r.get("close"), r.get("volume")))
            if not datos:
                return
            self.db.executemany(
                "INSERT OR REPLACE INTO bars_minute(fecha,hora,open,high,low,close,volume) "
                "VALUES(?,?,?,?,?,?,?)", datos)
            self.db.commit()
            if primera:
                self._bars_backfill_ok = True
                ACT.info("BARRAS: %d velas de 1 min volcadas a bars_minute (backfill de %s). "
                         "Rango %s -> %s", len(datos), BARS_DURATION,
                         datos[0][0] + " " + datos[0][1], datos[-1][0] + " " + datos[-1][1])
        except Exception as _e:
            self._bars_err = getattr(self, "_bars_err", 0) + 1
            self._bars_err_last = "%s: %s" % (type(_e).__name__, _e)

    def _calc_regimen(self, rows):
        """EFFICIENCY RATIO (Kaufman) + impulso, desde las velas que ya estan en memoria.

            ER = |close(t) - close(t-N)| / suma de |close(i) - close(i-1)| en esos N minutos

        ER cerca de 1 -> el precio fue RECTO: TENDENCIA. Cerca de 0 -> mucho ir y venir:
        REVERSION. Es el discriminante que salio de medir la reversion en dos dias: -0.35 el
        08-12 (lateral) frente a -0.06 el 08-11 (con tendencia). Sin el, un retroceso fijo
        ayuda un dia y estorba el otro.

        Se calcula aqui y NO leyendo bars_minute de la BD: `rows` ya esta en memoria y esto
        corre cada segundo. None cuando no hay historia suficiente, que es la verdad.
        Nunca puede romper ta_poll.
        """
        try:
            cl = [r.get("close") for r in rows[-(ER_VENTANA + 1):]
                  if r.get("close") is not None]
            if len(cl) >= max(5, ER_VENTANA // 2):
                bruto = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl)))
                self.er_actual = (abs(cl[-1] - cl[0]) / bruto) if bruto > 0 else None
            else:
                self.er_actual = None
            cl2 = [r.get("close") for r in rows[-(IMPULSO_VENTANA + 1):]
                   if r.get("close") is not None]
            self.impulso_actual = (cl2[-1] - cl2[0]) if len(cl2) >= 2 else None
        except Exception:
            self.er_actual = None
            self.impulso_actual = None

    def _retroceso_pendiente(self):
        """La compuerta de entrada. Devuelve (esperar: bool, motivo: str).

        Solo RETRASA. Al llegar a RETRO_MAX_MIN devuelve False y se entra igual: la operacion
        NUNCA se pierde. Ante cualquier duda (sin ancla, sin ER, sin precio, excepcion) devuelve
        False -> comportamiento de siempre. Es deliberado: el peor caso de esta funcion tiene
        que ser 'como antes', nunca 'no entra'.
        """
        try:
            if not ENTRADA_RETROCESO:
                return False, ""
            a = self.retro_ancla
            if not a or a.get("lado") != self.target:
                return False, ""
            esperado = (time.monotonic() - a["t"]) / 60.0
            if esperado >= RETRO_MAX_MIN:
                return False, ""                      # TOPE: se entra igual
            er = a.get("er")
            if er is None or er >= ER_UMBRAL:
                return False, ""                      # TENDENCIA -> no esperar
            px = self.spy_price
            if px is None or math.isnan(px):
                return False, ""
            imp, obj = a["imp"], a["objetivo"]
            llego = (px <= obj) if imp > 0 else (px >= obj)
            if llego:
                return False, ""
            return True, (f"esperando retroceso a {obj:.2f} (SPY {px:.2f}, impulso {imp:+.2f}, "
                          f"ER {er:.2f}<{ER_UMBRAL} = reversion) "
                          f"{esperado:.1f}/{RETRO_MAX_MIN:.0f} min")
        except Exception:
            return False, ""

    def ta_poll(self):
        if self.demo or self.bars is None or not HAVE_PD:
            return
        try:
            # `open` con getattr y NO con b.open: si un objeto barra no lo trae, `b.open`
            # lanza AttributeError, el except de abajo hace `return` y ta_poll DEJA DE
            # FUNCIONAR ENTERA — sin TA, sin precio, sin registro del minuto. Lo cazo la cold
            # run diferencial (gap21 paso de TODO VERDE a 6 FALLOS). Ausente -> None -> NULL,
            # que es la verdad, y el resto sigue vivo.
            rows = [{"open": getattr(b, "open", None), "high": b.high, "low": b.low,
                     "close": b.close, "volume": b.volume, "date": b.date}
                    for b in self.bars]
        except Exception:
            return
        self._chequear_barras(rows)
        self._guardar_barras(rows)
        self._calc_regimen(rows)
        # PRECIO EN VIVO: self.spy_price solo se fijaba en setup_contracts (1 vez por sesion),
        # asi que quedaba CONGELADO todo el dia -> transitions.spy, walls_snapshot.spot, el GEX
        # (factor spot^2) y la Ladder usaban el precio de la apertura. Las barras ya llegan en
        # vivo (keepUpToDate=True): se reutiliza ese dato, sin pedir nada mas a IBKR.
        # OJO: va ANTES del corte de 26 barras, o el precio seguiria congelado 26 minutos.
        if rows:
            _px = rows[-1]["close"]
            if _px is not None and not math.isnan(_px) and _px > 0:
                self.spy_price = float(_px)
        if len(rows) < 26:
            # GAP 21 (2026-08-11): el TA necesita 26 barras, pero el PREMIUM existe desde el
            # primer segundo (_on_ticks acumula desde las 09:30). Antes se hacia `return` aqui
            # y el flujo por minuto de los ~26 primeros minutos NO se guardaba ni en ta_minute
            # ni en el log -> justo la franja mas activa del dia (giros de apertura) quedaba
            # sin foto minuto a minuto. Ahora se registra igual, con el TA en NULL.
            if len(rows) >= 2:
                last_time = rows[-1]["date"]
                if self.last_bar_time is None:
                    self.last_bar_time = last_time
                elif last_time != self.last_bar_time:
                    self._log_minute(None, rows[-2]["date"], rows[-2])
                    self.last_bar_time = last_time
            return
        df = pd.DataFrame(rows)
        self.ta_vals = self.ta.compute(df)          # en vivo (para la pantalla)
        last_time = rows[-1]["date"]
        if self.last_bar_time is None:
            self.last_bar_time = last_time
            return
        if last_time != self.last_bar_time:
            # se cerro un minuto -> registrar la barra ya cerrada (sin la ultima en formacion)
            closed = self.ta.compute(df.iloc[:-1]) if len(df) > 27 else self.ta_vals
            self._log_minute(closed, rows[-2]["date"] if len(rows) >= 2 else last_time,
                             rows[-2] if len(rows) >= 2 else None)
            self.last_bar_time = last_time

    def _log_minute(self, vals, bar_dt, bar=None):
        """Registro por minuto: TA + señal + premium (BD y log).

        GAP 21: `vals` puede venir en None cuando el TA aun no tiene sus 26 barras. En ese caso
        NO se sale: se guarda igual el PREMIUM (que ya existe) y las columnas de TA quedan en
        NULL, que es la verdad. Antes se hacia `return` y se perdia el flujo por minuto de la
        media hora mas activa del dia.

        `bar` (2026-08-12) es la fila de la vela YA CERRADA, para guardar su maximo y su minimo.
        Se pasa la barra en vez de sacarlo de `vals` A PROPOSITO: `vals` es None durante los ~26
        primeros minutos (GAP 21) y ahi es justamente donde mas se mueve el precio. Con la barra,
        high/low se guardan desde las 09:30. Es opcional para no romper a ningun llamador."""
        v = vals or {}
        sin_ta = not vals
        _hi = bar.get("high") if isinstance(bar, dict) else None
        _lo = bar.get("low") if isinstance(bar, dict) else None
        # CIERRE DE LA VELA QUE REPRESENTA ESTA FILA (2026-08-12, arreglo de bug).
        # Antes era `v.get("close", self.spy_price)`. Con >=26 barras `v["close"]` es el cierre
        # de la vela CERRADA y todo cuadra; pero con `vals` en None (los ~26 primeros minutos,
        # GAP 21) caia a `self.spy_price`, que ta_poll acaba de fijar con rows[-1] -> la vela
        # EN FORMACION. La fila llevaba la HORA de una vela y el CIERRE de la siguiente.
        # Medido: fila hora='09:42' con spy=773.6 cuando 09:42 cerro en 773.40 y 09:43 en 773.60.
        # Afectaba a CINCO tablas: ta_minute, m1_minute, m2_minute, clasico_minute y
        # confirmacion_minute (todas via `_spy_m`), y rompia `spy_low <= spy <= spy_high`.
        # Se resuelve una sola vez aqui y se usa en todas: el cierre de la barra que se esta
        # registrando, y solo si no hay barra se cae a self.spy_price (llamadores antiguos).
        # OJO con el nombre: `_cl` YA ESTA COGIDO mas abajo (:3458) por el estado del metodo
        # CLASICO, que es un TEXTO. Usarlo aqui lo pisaba y el log de la linea 3565 reventaba
        # con "TypeError: must be real number, not str". La BD salia bien porque sus dos usos
        # son ANTERIORES a la reasignacion; solo fallaba el log. Lo cazo gap21_coldrun.
        _cierre = v.get("close")
        if _cierre is None and isinstance(bar, dict):
            _cierre = bar.get("close")
        if _cierre is None:
            _cierre = self.spy_price
        try:
            if hasattr(bar_dt, "strftime"):
                fecha = bar_dt.strftime("%Y-%m-%d"); hora = bar_dt.strftime("%H:%M")
            else:
                s = str(bar_dt); fecha, hora = s[:10], s[11:16]
            # flujo en ventana movil (solo se guarda; NO decide). None mientras no haya
            # historia suficiente -> se persiste NULL, que es la verdad, no un 0 inventado.
            c1m = self._flujo_ventana(60.0)
            c5m = self._flujo_ventana(300.0)
            c15m = self._flujo_ventana(900.0)
            # premium que entro en ESTA vela, call y put por separado (bruto y neto)
            vc, vp, vnc, vnp = self._prem_de_la_vela()
            self.db.execute(
                "INSERT OR REPLACE INTO ta_minute(fecha,hora,spy,rsi,ema8,ema21,ema50,"
                "macd_line,macd_signal,macd_hist,bb_up,bb_mid,bb_low,atr,atr_pct,vwap,"
                "obv_trend,ta_score,ta_dir,net_call,net_put,prem_state,"
                "diff,thr,momentum,prem_call_min,prem_put_min,net_call_min,net_put_min,"
                "net_call_1m,net_put_1m,net_call_5m,net_put_5m,"
                "net_call_15m,net_put_15m,sma20,sma50,sma200,spy_high,spy_low) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?)",
                # GAP 21: v.get(...) y no vals[...]: sin TA todas estas columnas van a NULL,
                # pero el spy y TODO el bloque de premium se guardan igual. El precio no falta
                # aunque no haya TA: ta_poll actualiza self.spy_price ANTES del corte de 26.
                (fecha, hora, _cierre,
                 v.get("rsi"), v.get("ema8"), v.get("ema21"),
                 v.get("ema50"), v.get("macd_line"), v.get("macd_signal"), v.get("macd_hist"),
                 v.get("bb_up"), v.get("bb_mid"), v.get("bb_low"), v.get("atr"), v.get("atr_pct"),
                 v.get("vwap"), v.get("obv_trend"), v.get("score"), v.get("dir"),
                 self.net_call, self.net_put, self.state,
                 # lo que DECIDE hoy (acumulado desde 09:30) ...
                 self.last_diff, self.last_thr, self.last_momentum,
                 # ... el premium de ESTA vela (estacionario, cruzable con el precio) ...
                 vc, vp, vnc, vnp,
                 # ... y las mismas magnitudes en ventana movil, solo para comparar despues
                 c1m[0], c1m[1], c5m[0], c5m[1], c15m[0], c15m[1],
                 # SMA 20/50/200: None (NULL) mientras no haya N barras. Ver TAEngine.compute.
                 v.get("sma20"), v.get("sma50"), v.get("sma200"),
                 # maximo/minimo de la vela: NULL si el llamador no paso la barra
                 _hi, _lo))
            # --- M1 / M2 (2026-08-11): se registran cada minuto. M1 ademas DECIDE (USAR_M1).
            # Los contadores avanzan aqui y solo aqui: M1 es un contador de MINUTOS, no puede
            # sumar 1 por segundo. Efecto: los flips solo pueden ocurrir al cambiar de minuto.
            _ac = abs(self.net_call); _ap = abs(self.net_put)
            _dif = _ac - _ap
            _sen = "UP" if _dif > 0 else "DOWN"
            if _dif > 0:
                self.m1_up += 1; self.m2_up += _dif
            else:
                self.m1_down += 1; self.m2_down += -_dif
            _m1 = ("UP" if self.m1_up > self.m1_down else
                   "DOWN" if self.m1_down > self.m1_up else "NEUTRAL")
            _m2 = ("UP" if self.m2_up > self.m2_down else
                   "DOWN" if self.m2_down > self.m2_up else "NEUTRAL")
            self.m1_racha = self.m1_racha + 1 if _m1 == self.m1_estado else 1
            self.m2_racha = self.m2_racha + 1 if _m2 == self.m2_estado else 1
            self.m1_estado = _m1; self.m2_estado = _m2
            # historia con sello de tiempo para el RETARDO (se poda a 2x el retardo)
            _tnow = time.monotonic()
            _corte = _tnow - max(120.0, RETARDO_M1_MIN * 120.0)
            self.m1_hist.append((_tnow, _m1))
            self.m1_hist[:] = [r for r in self.m1_hist if r[0] >= _corte] or self.m1_hist[-1:]
            self.m2_hist.append((_tnow, _m2))
            self.m2_hist[:] = [r for r in self.m2_hist if r[0] >= _corte] or self.m2_hist[-1:]
            # el efectivo de M2 y del CLASICO se calcula igual que el de M1, pero SOLO
            # se registra: ninguno de los dos decide nada (manda M1 via USAR_M1).
            _lim = _tnow - RETARDO_M1_MIN * 60.0
            def _efec(hist):
                r = None
                for _ts, _st in hist:
                    if _ts <= _lim:
                        r = _st
                    else:
                        break
                return r
            self.m2_efectivo = _efec(self.m2_hist)
            # mismo cierre que ta_minute: las 5 tablas del minuto tienen que contar lo mismo
            _spy_m = _cierre
            self.db.execute(
                "INSERT OR REPLACE INTO m1_minute(fecha,hora,spy,net_call,net_put,abs_call,"
                "abs_put,dif,senal_min,n_up,n_down,marcador,m1,racha,m1_efectivo,"
                "retardo_min,recentrado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, _spy_m, self.net_call, self.net_put, _ac, _ap, _dif, _sen,
                 self.m1_up, self.m1_down, self.m1_up - self.m1_down, _m1,
                 self.m1_racha, self.m1_efectivo, RETARDO_M1_MIN, self.m_recentrado))
            self.db.execute(
                "INSERT OR REPLACE INTO m2_minute(fecha,hora,spy,net_call,net_put,abs_call,"
                "abs_put,dif,senal_min,usd_up,usd_down,acumulado,m2,racha,m2_efectivo,"
                "retardo_min,recentrado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, _spy_m, self.net_call, self.net_put, _ac, _ap, _dif, _sen,
                 self.m2_up, self.m2_down, self.m2_up - self.m2_down, _m2,
                 self.m2_racha, self.m2_efectivo, RETARDO_M1_MIN, self.m_recentrado))
            # MEDIA CORTA: el metodo que DECIDE desde el 2026-08-12. Se registra su lectura
            # cruda (media, distancia con y sin signo), lo que dijo la señal ESE minuto, y el
            # estado en que quedo el sistema, para poder reconstruir despues por que hizo lo
            # que hizo. `senal` en NULL significa "dentro de la banda": no habia nada que
            # capturar, que es distinto de "no habia dato" (ahi la media sale NULL tambien).
            try:
                _med = (self.ta_vals or {}).get("vwap")
                _dst = (_spy_m - _med) if (_med and _spy_m is not None) else None
                _seg = None
                if self.pos in ("CALL", "PUT") and self.trade_open:
                    _seg = time.monotonic() - self.trade_open.get("ts", time.monotonic())
                self.db.execute(
                    "INSERT OR REPLACE INTO media_minute(fecha,hora,spy,media,dist,dist_abs,"
                    "senal,estado,target,pos,seg_en_pos,activo,media_dist,minutos_pos,decide,"
                    "origen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (fecha, hora, _spy_m, _med, _dst, abs(_dst) if _dst is not None else None,
                     self._senal_media(), self.state, self.target, self.pos, _seg,
                     1 if USAR_MEDIA else 0, MEDIA_DIST, MINUTOS_POS,
                     "MEDIA" if USAR_MEDIA else ("M1" if USAR_M1 else "CLASICO"), None))
            except Exception:
                LOG.exception("Error registrando media_minute")
            # METODO ANTIGUO (diff/thr): NO decide, pero se registra igual para comparar.
            _diff = self.net_call - self.net_put
            if ADAPTIVE:
                _thr = max(SIGNAL_THRESHOLD, ADAPT_FRAC * (_ac + _ap))
            else:
                _thr = SIGNAL_THRESHOLD
            _cl = "UP" if _diff > _thr else "DOWN" if _diff < -_thr else "NEUTRAL"
            self.cl_racha = self.cl_racha + 1 if _cl == self.cl_estado else 1
            self.cl_estado = _cl
            self.cl_hist.append((_tnow, _cl))
            self.cl_hist[:] = [r for r in self.cl_hist if r[0] >= _corte] or self.cl_hist[-1:]
            self.cl_efectivo = _efec(self.cl_hist)
            self.db.execute(
                "INSERT OR REPLACE INTO clasico_minute(fecha,hora,spy,net_call,net_put,"
                "diff,thr,banda,momentum,mom_min,clasico,estado_real,warn_side,racha,"
                "clasico_efectivo,retardo_min,recentrado) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, _spy_m, self.net_call, self.net_put, _diff, _thr,
                 _thr * WARN_BAND_FRAC, self.last_momentum, MOM_FRAC * _thr, _cl,
                 self.state, self.last_warn_side, self.cl_racha, self.cl_efectivo,
                 RETARDO_M1_MIN, self.m_recentrado))
            # --- CONFIRMACION (SOLO REGISTRO, no decide): la SEÑAL del minuto (_sen) solo se
            # "confirma" si aguanta CONFIRMACION_MIN minutos seguidos. Se compara con el resto
            # de metodos, con su mismo efectivo por retardo. NO toca _update_signal ni la ejecucion.
            self.sen_racha = self.sen_racha + 1 if _sen == self.sen_estado else 1
            self.sen_estado = _sen
            if self.sen_racha >= CONFIRMACION_MIN:
                self.conf_estado = _sen
            self.conf_hist.append((_tnow, self.conf_estado))
            self.conf_hist[:] = [r for r in self.conf_hist if r[0] >= _corte] or self.conf_hist[-1:]
            self.conf_efectivo = _efec(self.conf_hist)
            self.db.execute(
                "INSERT OR REPLACE INTO confirmacion_minute(fecha,hora,spy,net_call,net_put,"
                "abs_call,abs_put,dif,senal_min,racha,confirmado,confirmado_efectivo,"
                "confirmacion_min,retardo_min,recentrado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fecha, hora, _spy_m, self.net_call, self.net_put, _ac, _ap, _dif, _sen,
                 self.sen_racha, self.conf_estado, self.conf_efectivo,
                 CONFIRMACION_MIN, RETARDO_M1_MIN, self.m_recentrado))
            # --- REGIMEN Y COMPUERTA DE ENTRADA (2026-08-12) ---
            # Se registra SIEMPRE, este activa o no la compuerta: con ENTRADA_RETROCESO=False
            # esta tabla es exactamente el "que habria hecho" que hace falta para juzgarla.
            # Se guardan tambien los parametros de esa fila: si manana se cambian, las filas
            # viejas siguen siendo interpretables (§7: el criterio se fija ANTES, no despues).
            # se inicializan FUERA del try: la linea de log de mas abajo los usa, y si el try
            # fallara quedarian sin definir -> NameError que tumbaria el registro del minuto
            # entero (premium por strike incluido). Con valores neutros, el peor caso es que
            # la linea diga "-".
            _esp, _anc, _reg, _minesp = False, {}, "-", None
            # getattr y NO self.er_actual: `_log_minute` se invoca en cold runs con objetos app
            # MINIMOS que no tienen estos atributos, y un AttributeError aqui se propaga al try
            # exterior y se lleva por delante el registro del minuto ENTERO (premium por strike
            # incluido). Lo cazo la cold run diferencial: logs_metodos perdio 28 lineas.
            # Es el mismo fallo que `b.open` en ta_poll: no dar por hecho que el atributo existe.
            _er = getattr(self, "er_actual", None)
            _imp = getattr(self, "impulso_actual", None)
            try:
                _esp, _ = self._retroceso_pendiente()
                _anc = getattr(self, "retro_ancla", None) or {}
                _reg = ("-" if _er is None
                        else ("REVERSION" if _er < ER_UMBRAL else "TENDENCIA"))
                _minesp = ((time.monotonic() - _anc["t"]) / 60.0) if _anc.get("t") else None
                self.db.execute(
                    "INSERT OR REPLACE INTO entrada_minute(fecha,hora,spy,er,regimen,impulso,"
                    "objetivo,esperando,min_esperando,target,pos,activo,er_umbral,retro_frac,"
                    "retro_max_min) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (fecha, hora, _spy_m, _er, _reg, _imp,
                     _anc.get("objetivo"), 1 if _esp else 0, _minesp, self.target, self.pos,
                     1 if ENTRADA_RETROCESO else 0, ER_UMBRAL, RETRO_FRAC, RETRO_MAX_MIN))
            except Exception:
                LOG.exception("Error registrando entrada_minute")
            # --- LOG de los 4 metodos (2026-08-12, peticion del usuario) ---
            # Hasta ahora M1/M2/CLASICO/CONFIRMACION solo escribian en sus tablas y en el
            # panel: 0 lineas en spy_activity.log. Como M1 es el que DECIDE (USAR_M1), un
            # fallo suyo era invisible en el log y solo se podia ver consultando la BD.
            # Se registra el estado del minuto, la racha, y el EFECTIVO (el que de verdad
            # se aplica, con RETARDO_M1_MIN de retraso). MANDA marca cual decide.
            ACT.info("MIN %s | METODOS  M1=%s(r%d)%s  M2=%s(r%d)  CLASICO=%s(r%d)  "
                     "CONFIRMA=%s(sen %s r%d/%d) | efectivos(-%dmin) M1=%s M2=%s CL=%s CONF=%s"
                     " | MANDA %s",
                     hora, _m1, self.m1_racha, "  <-MANDA" if (USAR_M1 and not USAR_MEDIA) else "",
                     _m2, self.m2_racha, _cl, self.cl_racha,
                     self.conf_estado or "-", _sen, self.sen_racha, CONFIRMACION_MIN,
                     RETARDO_M1_MIN, self.m1_efectivo or "-", self.m2_efectivo or "-",
                     self.cl_efectivo or "-", self.conf_efectivo or "-",
                     "MEDIA" if USAR_MEDIA else ("M1" if USAR_M1 else "CLASICO"))
            # MEDIA CORTA: la lectura cruda del que DECIDE. Se imprime SIEMPRE (aunque no
            # decida) para poder comparar los cinco metodos sobre el mismo minuto, y porque
            # sin esta linea un dia entero sin operar seria indistinguible de un fallo mudo.
            try:
                _med_l = (self.ta_vals or {}).get("vwap")
                _dst_l = (_spy_m - _med_l) if (_med_l and _spy_m is not None) else None
                _sm = self._senal_media()
                ACT.info("MIN %s | MEDIA  spy=%s media=%s dist=%s (umbral %.2f) -> senal=%s"
                         "%s | estado=%s target=%s pos=%s%s",
                         hora,
                         ("%.2f" % _spy_m) if _spy_m is not None else "-",
                         ("%.2f" % _med_l) if _med_l else "SIN DATO",
                         ("%+.3f" % _dst_l) if _dst_l is not None else "-",
                         MEDIA_DIST, _sm or "-",
                         "  <-MANDA" if USAR_MEDIA else " (solo registro)",
                         self.state, self.target, self.pos,
                         (" | %.1f/%d min en posicion" % (
                             (time.monotonic() - self.trade_open.get("ts", time.monotonic())) / 60.0,
                             MINUTOS_POS))
                         if (self.pos in ("CALL", "PUT") and self.trade_open) else "")
            except Exception:
                LOG.exception("Error en la linea de log de MEDIA")
            # REGIMEN: en el log tambien, no solo en la BD. Si la compuerta retrasa una entrada
            # hay que poder verlo leyendo el log, sin consultar entrada_minute.
            ACT.info("MIN %s | REGIMEN ER=%s (%s, umbral %.2f) | impulso(%dmin)=%s | "
                     "compuerta=%s%s",
                     hora, ("%.3f" % _er) if _er is not None else "-",
                     _reg, ER_UMBRAL, IMPULSO_VENTANA,
                     ("%+.2f" % _imp) if _imp is not None else "-",
                     "ON" if ENTRADA_RETROCESO else "OFF",
                     (f" | ESPERANDO retroceso a {_anc.get('objetivo'):.2f} "
                      f"({_minesp:.1f}/{RETRO_MAX_MIN} min)"
                      if (_esp and _anc.get("objetivo") is not None and _minesp is not None)
                      else ""))
            # contadores crudos: es lo que hay que mirar si M1 no gira cuando deberia
            ACT.info("MIN %s | M1 contadores up=%d down=%d marcador=%+d | M2 usd_up=%.0f "
                     "usd_down=%.0f acum=%+.0f | abs C=%.0f P=%.0f dif=%+.0f senal_min=%s"
                     " | hist m1=%d (necesita >=%d min para decidir) | recentrados=%d",
                     hora, self.m1_up, self.m1_down, self.m1_up - self.m1_down,
                     self.m2_up, self.m2_down, self.m2_up - self.m2_down,
                     _ac, _ap, _dif, _sen, len(self.m1_hist), RETARDO_M1_MIN,
                     self.m_recentrado)
            self.m_recentrado = 0
            for (exp, strike, right), cp in self.accum.items():
                dp = self.today_prem.get((exp, strike, right), 0.0)
                # NO usar INSERT OR REPLACE: esta fila puede haberla escrito _persist_walls
                # con 10 columnas (incluidos open_interest/gamma/net_prem de la banda) y el
                # REPLACE las dejaria en NULL. ON CONFLICT ... DO UPDATE solo pisa lo que
                # nombra y preserva el resto (mismo idioma que _persist_accum).
                # PRECIO del contrato (2026-08-11): del ticker YA vivo, sin pedir nada a IBKR.
                # Si el contrato no esta suscrito (p.ej. una expiry VENCIDA que sigue en accum)
                # devuelve None en todo y aqui se guarda NULL.
                px = self._precio_de(exp, strike, right)
                self.db.execute(
                    "INSERT INTO premium_minute(fecha,hora,expiry,strike,right,"
                    "cum_prem,day_prem,bid,ask,mid,last,spread) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(fecha,hora,expiry,strike,right) "
                    "DO UPDATE SET cum_prem=excluded.cum_prem, day_prem=excluded.day_prem, "
                    "bid=excluded.bid, ask=excluded.ask, mid=excluded.mid, "
                    "last=excluded.last, spread=excluded.spread",
                    (fecha, hora, exp, strike, right, cp, dp,
                     px["bid"], px["ask"], px["mid"], px["last"], px["spread"]))
            # LA BANDA (40 contratos de la expiry cercana) NO esta en self.accum: _on_ticks solo
            # acumula senal + baseline. Hasta ahora sus filas solo se escribian en _persist_walls,
            # cada WALLS_RECALC_SECS (3 min). Para que TODOS los contratos tengan precio POR
            # MINUTO se recorre aqui tambien. No cuesta ninguna peticion: son tickers vivos.
            # Se escriben SOLO las columnas de precio: cum_prem/day_prem/OI/gamma/net_prem de
            # estos strikes los lleva _persist_walls y no se deben pisar desde aqui.
            for c in (self.band_contracts or []):
                # getattr: un contrato sin expiry no puede tumbar el registro del minuto entero
                # (este bucle vive dentro del try de _log_minute). Se cae a self.expiry, que es
                # la de la banda por definicion.
                exp_c = getattr(c, "lastTradeDateOrContractMonth", None) or self.expiry
                if not exp_c:
                    continue
                px = self._precio_de(exp_c, c.strike, c.right)
                if px["bid"] is None and px["ask"] is None and px["last"] is None:
                    continue          # sin cotizacion: no se crea una fila vacia
                self.db.execute(
                    "INSERT INTO premium_minute(fecha,hora,expiry,strike,right,"
                    "bid,ask,mid,last,spread) VALUES(?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(fecha,hora,expiry,strike,right) "
                    "DO UPDATE SET bid=excluded.bid, ask=excluded.ask, mid=excluded.mid, "
                    "last=excluded.last, spread=excluded.spread",
                    (fecha, hora, exp_c, c.strike, c.right,
                     px["bid"], px["ask"], px["mid"], px["last"], px["spread"]))
            self.db.commit()
            # --- LOG EXHAUSTIVO POR MINUTO (respaldo completo del dia por si la BD falla) ---
            if sin_ta:
                # GAP 21: sin 26 barras no hay TA que imprimir, pero el minuto SI se registra.
                # Se dice explicitamente por que faltan los indicadores, para que al leer el log
                # no parezca que el sistema estaba caido.
                ACT.info("MIN %s | SPY=%.2f | TA todavia sin 26 barras (faltan indicadores) "
                         "-> se registra el PREMIUM igualmente", hora, _cierre or 0.0)
            else:
                ACT.info("MIN %s | SPY=%.2f | TA dir=%s score=%+d rsi=%.1f macd=%.3f/%.3f/%+.3f "
                         "ema8/21/50=%.2f/%.2f/%.2f bb=%.2f/%.2f/%.2f atr=%.2f(%.2f%%) "
                         "vwap=%.2f obv=%s",
                         hora, v["close"], v["dir"], v["score"], v["rsi"],
                         v["macd_line"], v["macd_signal"], v["macd_hist"],
                         v["ema8"], v["ema21"], v["ema50"],
                         v["bb_up"], v["bb_mid"], v["bb_low"],
                         v["atr"], v["atr_pct"], v["vwap"], v["obv_trend"])
            # SMA 20/50/200: se loguean aparte de las EMAs para no tocar la linea de TA de arriba
            # (que el usuario ya lee a diario). "-" cuando aun no hay N barras: la SMA200 no
            # existe hasta ~12:50 con "1 D", y decirlo es mejor que imprimir un numero inventado.
            if not sin_ta:
                _p = v.get("close")
                _rel = lambda s: (f"{_p - s:+.2f}" if (s is not None and _p is not None) else "-")
                ACT.info("MIN %s | SMA 20/50/200 = %s/%s/%s | precio-SMA: %s/%s/%s "
                         "(informativo, NO decide)", hora,
                         _fmt(v.get("sma20")), _fmt(v.get("sma50")), _fmt(v.get("sma200")),
                         _rel(v.get("sma20")), _rel(v.get("sma50")), _rel(v.get("sma200")))
            ACT.info("MIN %s | SENAL netC=%.0f netP=%.0f diff=%.0f thr=%.0f mom=%.0f(%.0fs) "
                     "-> estado=%s pos=%s",
                     hora, self.net_call, self.net_put, self.last_diff, self.last_thr,
                     self.last_momentum, MOMENTUM_SECS, self.state, self.pos)
            # PREMIUM DE ESTA VELA: cuanto entro en el minuto, call y put por separado. A
            # diferencia del acumulado, este numero NO crece con la hora -> se puede cruzar
            # directamente con lo que hizo el precio en esta misma vela.
            ACT.info("MIN %s | VELA %s bruto C=%s P=%s (sesgo %s) | neto C=%s P=%s (diff %s)",
                     hora, self.expiry, _fmt(vc), _fmt(vp),
                     ("CALL" if (vc or 0) > (vp or 0) else "PUT") if vc is not None else "-",
                     _fmt(vnc), _fmt(vnp),
                     _fmt((vnc - vnp) if vnc is not None else None))
            # VENTANAS MOVILES: lo que la senal HABRIA visto sin acumular desde la apertura.
            # No deciden nada; se registran para poder compararlas con datos en unas sesiones.
            ACT.info("MIN %s | VENTANAS 1m: C=%s P=%s diff=%s | 5m: C=%s P=%s diff=%s | "
                     "15m: C=%s P=%s diff=%s   (informativo, NO decide)",
                     hora, _fmt(c1m[0]), _fmt(c1m[1]),
                     _fmt((c1m[0] - c1m[1]) if c1m[0] is not None else None),
                     _fmt(c5m[0]), _fmt(c5m[1]),
                     _fmt((c5m[0] - c5m[1]) if c5m[0] is not None else None),
                     _fmt(c15m[0]), _fmt(c15m[1]),
                     _fmt((c15m[0] - c15m[1]) if c15m[0] is not None else None))
            # TAPE: volcar lo pendiente del minuto y dejar constancia de cuanto se registro.
            # Va DESPUES del commit de arriba para no alargar esa transaccion.
            if TAPE_ENABLED:
                _n = self._flush_tape(forzar=True)
                try:
                    _g = self.db.execute(
                        "SELECT COUNT(*), MAX(size), ROUND(AVG(size),1) FROM tape "
                        "WHERE fecha=? AND hora LIKE ?", (fecha, hora + ":%")).fetchone()
                    # 2026-08-12: se reportan tambien los fallos de CAPTURA. En _on_ticks
                    # no se puede loguear por tick (alta frecuencia, hilo de la GUI), asi
                    # que se cuentan alli y se vuelcan aqui, una vez por minuto. Si sale
                    # "capturas_fallidas>0" se estan PERDIENDO operaciones del tape.
                    _te = getattr(self, "_tape_err", 0)
                    ACT.info("MIN %s | TAPE %d operaciones este minuto (mayor=%s contratos, "
                             "media=%s) | volcadas=%d, total dia=%d | capturas_fallidas=%d%s",
                             hora, _g[0] or 0, _fmt(_g[1]), _fmt(_g[2]), _n, self._tape_n,
                             _te, (" ULTIMO: " + getattr(self, "_tape_err_last", "")) if _te else "")
                    if _te:
                        ACT.warning("TAPE: %d capturas FALLIDAS acumuladas -> se estan "
                                    "perdiendo operaciones. Ultimo error: %s",
                                    _te, getattr(self, "_tape_err_last", "?"))
                except Exception:
                    LOG.exception("Error componiendo el resumen del TAPE del minuto")
            ACT.info("MIN %s | %s", hora, self.resumen_cuenta())
            if self.pos in ("CALL", "PUT"):
                en = self.entry_price or 0.0
                pr = self.contract_price
                pnl = ((pr - en) * 100.0 * QTY) if (pr is not None and en) else 0.0
                ACT.info("MIN %s | CONTRATO %s entrada=%.2f actual=%s pnl=%+.0f$", hora, self.pos,
                         en, (f"{pr:.2f}" if pr is not None else "-"), pnl)
            for (exp, strike, right), dp in sorted(self.today_prem.items()):
                if dp > 0:   # solo strikes con actividad
                    k = (exp, strike, right)
                    # day/cum = BRUTO (solo suma, es actividad: un hecho)
                    # netdia/netcum = NETO firmado por agresor (compras - ventas: inferencia)
                    # net3m = neto de la banda a resolucion 3 min (otra via de calculo)
                    # PRECIO (2026-08-11): el premium dice cuanto DINERO paso por el strike;
                    # esto dice cuanto VALE el contrato. '-' cuando no hay cotizacion.
                    _px = self._precio_de(exp, strike, right)
                    ACT.info("MIN %s | PREM %s %g%s day=%.0f cum=%.0f | netdia=%+.0f "
                             "netcum=%+.0f | net3m=%+.0f | bid=%s ask=%s mid=%s last=%s sprd=%s",
                             hora, exp, strike, right, dp,
                             self.accum.get(k, 0.0),
                             self.today_net.get(k, 0.0), self.accum_net.get(k, 0.0),
                             self.net_prem.get(k, 0.0),
                             _fmt(_px["bid"]), _fmt(_px["ask"]), _fmt(_px["mid"]),
                             _fmt(_px["last"]), _fmt(_px["spread"]))
        except Exception:
            LOG.exception("Error guardando registro por minuto")


# ----------------------- GUI Tkinter -----------------------
import tkinter as tk


def _draw_ladder(canvas, app):
    """Dibuja la Gamma Ladder (solo lectura). El PRECIO y el CONTRATO comprado tienen su propio
    carril de etiqueta a la izquierda (NO encima de las barras) y una raya horizontal a su nivel."""
    canvas.delete("all")
    W = int(canvas["width"]); H = int(canvas["height"])
    data = app.ladder_rows()
    rows = data["rows"]
    if not rows:
        canvas.create_text(W // 2, H // 2, text="Gamma Ladder: (esperando OI/premium en vivo...)",
                           fill="#67e8f9", font=("Consolas", 10))
        return
    n = len(rows)
    top = 4
    row_h = max(11, min(20, (H - 8) // n))
    x_strike_r = 42            # etiqueta de strike (anchor e)
    x_mark_r = 100             # carril de marcadores precio/contrato (anchor e) -> NO sobre barras
    x_bar0 = 104               # inicio de las barras
    bar_max = W - x_bar0 - 52  # ancho maximo de barra (deja espacio al valor)
    max_prem = data["max_prem"] or 1.0

    def y_at(i):
        return top + i * row_h + row_h // 2

    def y_of_level(level):
        if level is None:
            return None
        for i in range(len(rows) - 1):
            s0 = rows[i][0]; s1 = rows[i + 1][0]     # s0 > s1 (orden desc)
            if s0 >= level >= s1 and s0 != s1:
                frac = (s0 - level) / (s0 - s1)
                return y_at(i) + frac * (y_at(i + 1) - y_at(i))
        return None

    # separador del carril de marcadores
    canvas.create_line(x_bar0 - 2, top, x_bar0 - 2, top + n * row_h, fill="#1f2937", width=1)

    for i, (s, prem, side, tag) in enumerate(rows):
        y = y_at(i)
        lbl = f"{s:g}{tag}"
        if "CW" in tag:
            col_lbl = "#22c55e"
        elif "PW" in tag:
            col_lbl = "#ef4444"
        elif "M" in tag:                 # magneto (Max Pain)
            col_lbl = "#a78bfa"
        else:
            col_lbl = "#cbd5e1"
        canvas.create_text(x_strike_r, y, text=lbl, fill=col_lbl, font=("Consolas", 8), anchor="e")
        ln = int(bar_max * (prem / max_prem)) if max_prem > 0 else 0
        col = "#16a34a" if side == "call" else "#dc2626"
        if ln > 0:
            canvas.create_rectangle(x_bar0, y - row_h // 2 + 2, x_bar0 + ln, y + row_h // 2 - 2,
                                    fill=col, outline="")
        canvas.create_text(x_bar0 + ln + 4, y, text=_money(prem), fill="#94a3b8",
                           font=("Consolas", 7), anchor="w")

    # --- GAMMA FLIP: raya punteada naranja + etiqueta a la derecha ---
    yf = y_of_level(data["flip"])
    if yf is not None:
        canvas.create_line(x_bar0, yf, W - 2, yf, fill="#f59e0b", width=1, dash=(3, 2))
        canvas.create_text(W - 4, yf + 6, text=f"flip {data['flip']:.2f}",
                           fill="#f59e0b", font=("Consolas", 7), anchor="e")

    # --- PRECIO: raya blanca cruzando las barras + etiqueta en el carril (con estado) ---
    price = data["price"]
    yp = y_of_level(price) if (price is not None and not math.isnan(price)) else None
    if yp is not None:
        st = data["state"]
        stcol = {"UP": "#22c55e", "DOWN": "#ef4444"}.get(st, "#e5e7eb")
        arrow = {"UP": "^", "DOWN": "v"}.get(st, "-")
        canvas.create_line(x_bar0, yp, W - 2, yp, fill="#f8fafc", width=1)
        canvas.create_text(x_mark_r, yp, text=f"{arrow} {price:.2f}", fill=stcol,
                           font=("Consolas", 8, "bold"), anchor="e")

    # --- CONTRATO COMPRADO: raya amarilla al nivel del strike + etiqueta en el carril ---
    ct = data.get("contract")
    if ct is not None:
        yc = y_of_level(ct["strike"])
        if yc is None:
            yce = [y_at(i) for i, r in enumerate(rows) if r[0] == ct["strike"]]
            yc = yce[0] if yce else None
        if yc is not None:
            rl = "C" if ct["side"] == "CALL" else "P"
            pr = ct.get("price"); en = ct.get("entry")
            # color de la raya/etiqueta segun P&L: verde si subio, rojo si bajo, amarillo si sin dato
            ccol = "#fbbf24"
            if pr is not None and en:
                ccol = "#22c55e" if pr >= en else "#ef4444"
            canvas.create_line(x_bar0, yc, W - 2, yc, fill=ccol, width=2)
            ytxt = yc + (9 if (yp is not None and abs(yc - yp) < 9) else 0)
            txt = f">{ct['strike']:g}{rl}"
            if pr is not None:
                txt += f" {pr:.2f}"
            canvas.create_text(x_mark_r, ytxt, text=txt, fill=ccol,
                               font=("Consolas", 8, "bold"), anchor="e")


def run_gui(app):
    root = tk.Tk()
    root.title("SPY Direction")
    root.report_callback_exception = lambda *a: LOG.error("Error en GUI", exc_info=a)
    root.configure(bg="#111111")
    root.geometry("560x940")

    big = tk.Label(root, text="-", font=("Segoe UI", 46, "bold"),
                   fg="#888888", bg="#111111")
    big.pack(pady=(8, 0))

    sub = tk.Label(root, text="", font=("Segoe UI", 12), fg="#dddddd", bg="#111111")
    sub.pack()

    # --- fila de TRADING: indicador + posicion + boton ARMAR ---
    trow = tk.Frame(root, bg="#111111")
    trow.pack(pady=(6, 0))
    trade_ind = tk.Label(trow, text="TRADING OFF", font=("Segoe UI", 11, "bold"),
                         fg="#111111", bg="#ef4444", padx=8, pady=2)
    trade_ind.grid(row=0, column=0, padx=4)
    pos_lbl = tk.Label(trow, text="POSICION: FLAT", font=("Segoe UI", 11, "bold"),
                       fg="#e5e7eb", bg="#111111")
    pos_lbl.grid(row=0, column=1, padx=8)

    def _toggle():
        on = app.toggle_trading()
        btn.config(text="DESARMAR" if on else "ARMAR")
    btn = tk.Button(trow, text=("DESARMAR" if app.trading else "ARMAR"),
                    font=("Segoe UI", 10, "bold"),
                    command=_toggle, bg="#1f2937", fg="#ffffff", activebackground="#374151")
    btn.grid(row=0, column=2, padx=4)

    trade_msg_lbl = tk.Label(root, text="", font=("Consolas", 9), fg="#f59e0b", bg="#111111")
    trade_msg_lbl.pack()

    # Contrato comprado (solo aparece si hay posicion real en IBKR; al vender desaparece)
    contract_lbl = tk.Label(root, text="", font=("Consolas", 10, "bold"), fg="#fbbf24", bg="#111111")
    contract_lbl.pack()

    # Estado de CUENTA: cuanto hay, cuanto se movio hoy y que se lleva acumulado
    acct_lbl = tk.Label(root, text="Cuenta: (leyendo de IBKR...)", font=("Consolas", 9, "bold"),
                        fg="#e5e7eb", bg="#111111")
    acct_lbl.pack()

    alert = tk.Label(root, text="", font=("Segoe UI", 15, "bold"),
                     fg="#111111", bg="#111111", pady=6)
    alert.pack(fill="x", padx=10, pady=(6, 0))

    status = tk.Label(root, text="", font=("Consolas", 9), fg="#8ab4f8",
                      bg="#111111", wraplength=480, justify="center")
    status.pack(pady=(6, 2))

    ta_lbl = tk.Label(root, text="TA 1m: (esperando barras...)", font=("Consolas", 9),
                      fg="#c4b5fd", bg="#111111")
    ta_lbl.pack(pady=(0, 2))

    walls_lbl = tk.Label(root, text="Walls/GEX: (esperando OI/greeks...)", font=("Consolas", 9),
                         fg="#67e8f9", bg="#111111", wraplength=520, justify="center")
    walls_lbl.pack(pady=(0, 2))

    # PANEL DE LOS 3 METODOS (2026-08-11). Los tres se ven; SOLO M1 decide (USAR_M1).
    metodos_lbl = tk.Label(root, text="Metodos: (esperando el primer minuto...)",
                           font=("Consolas", 10, "bold"), fg="#fcd34d", bg="#111111")
    metodos_lbl.pack(pady=(0, 2))

    # Gamma Ladder (solo lectura, estilo MarketSnack): premium $ por strike
    tk.Label(root, text="Gamma Ladder - premium $ por strike (verde>precio / rojo<precio):",
             font=("Consolas", 8, "bold"), fg="#67e8f9", bg="#111111").pack()
    ladder = tk.Canvas(root, width=540, height=380, bg="#0b0b0b", highlightthickness=0)
    ladder.pack(pady=(2, 6))

    tk.Label(root, text="Linea base (fechas posteriores) - hoy vs dia previo:",
             font=("Consolas", 9, "bold"), fg="#f59e0b", bg="#111111").pack()
    basebox = tk.Text(root, height=3, width=56, bg="#0b0b0b", fg="#e5e7eb",
                      font=("Consolas", 9), bd=0)
    basebox.pack(pady=(2, 6))

    tk.Label(root, text="Historial de giros (SQLite):",
             font=("Consolas", 9, "bold"), fg="#8ab4f8", bg="#111111").pack()
    logbox = tk.Text(root, height=4, width=56, bg="#0b0b0b", fg="#aaaaaa",
                     font=("Consolas", 9), bd=0)
    logbox.pack(pady=(2, 8))

    colors = {"UP": "#22c55e", "DOWN": "#ef4444", "-": "#888888"}
    connected = {"ok": False}
    sesion = {"fecha": None, "reintento": 0.0}   # fecha de la sesion viva + cooldown de reintento

    def try_connect(nuevo_dia):
        try:
            if nuevo_dia:
                # SOLO en dia nuevo: acumuladores intradia en 0. En una RECONEXION no se toca,
                # o cada caida de socket borraria net_call/net_put del dia.
                app.reset_day()
            app.connect()
            if app.setup_contracts():
                connected["ok"] = True
                app.reconciled = False   # re-sincronizar posicion/ordenes tras (re)conectar
        except Exception as e:
            app.status = f"SIN CONEXION a IB Gateway ({e}). Reintentando..."
            LOG.exception("Fallo al conectar/setup")

    def tick():
        if app.demo:
            app.simulate_step()
        elif app.is_market_open():
            # MERCADO ABIERTO (09:30-16:00 ET): arrancar/recolectar. (Trading cesa 15:45 en trade_poll.)
            # La verdad de la conexion es el SOCKET, no una bandera local: si se cae a mitad
            # de sesion hay que reintentar (antes quedaba muda hasta las 16:00, sin error).
            if not app.ib.isConnected():
                if connected["ok"]:
                    connected["ok"] = False
                    ACT.info("DESCONEXION detectada - reintentando cada %.0fs", RECONNECT_SECS)
                hoy = now_et().strftime("%Y-%m-%d")
                if time.monotonic() >= sesion["reintento"]:
                    sesion["reintento"] = time.monotonic() + RECONNECT_SECS
                    try_connect(nuevo_dia=(sesion["fecha"] != hoy))
                    if connected["ok"]:
                        sesion["fecha"] = hoy
                        ACT.info("CONECTADO (sesion %s)", hoy)
            try:
                if app.ib.isConnected():
                    app.ib.sleep(REFRESH_SECS)
                    if time.monotonic() - app.last_snapshot > SNAPSHOT_SECS:
                        app._persist_accum()
                        app.last_snapshot = time.monotonic()
                    app.ta_poll()        # ANTES de re-centrar: actualiza el precio en vivo
                    # GAP 17: el stream de barras murio (por 10182 o en silencio) -> reponerlo
                    # SOLO. Con backoff: repedir sin freno provoca pacing violations de IBKR
                    # (162/420), que es un fallo peor que el original.
                    if (app.bars_stale and app.is_rth()
                            and time.monotonic() - app.bars_retry_ts > BARS_RETRY_SECS):
                        app.bars_retry_ts = time.monotonic()
                        app.bars_retries += 1
                        _sin = time.monotonic() - (app.bars_last_advance or time.monotonic())
                        if app._subscribe_bars():
                            # OJO con el texto: se ha REPEDIDO, no se ha confirmado que llegue
                            # nada. Quien confirma es _chequear_barras al ver avanzar la barra.
                            ACT.info("BARRAS: stream repedido (intento %d, %.0fs sin avanzar). "
                                     "Sigue marcado STALE hasta que la barra avance de verdad",
                                     app.bars_retries, _sin)
                        else:
                            ACT.info("BARRAS: fallo el intento %d de reponer el stream",
                                     app.bars_retries)
                    if time.monotonic() - app.last_strikes > STRIKE_REFRESH_SECS:
                        app.refresh_strikes()   # senal/ejecucion/banda siguen al precio
                        app.last_strikes = time.monotonic()
                    app.trade_poll()
                    if time.monotonic() - app.last_acct > 10.0:
                        app._read_account()      # estado de cuenta para la vista
                        app.last_acct = time.monotonic()
                    if (WALLS_ENABLED
                            and time.monotonic() - app.last_walls_calc > WALLS_RECALC_SECS):
                        app.compute_walls()   # informativo: recalcula/guarda cada 3 min
                        app.last_walls_calc = time.monotonic()
                    # precio ACTUAL del contrato comprado (tiempo real, para P&L)
                    _cc = app.buy_call if app.pos == "CALL" else (app.buy_put if app.pos == "PUT" else None)
                    if _cc is not None:
                        _m = app._mid(_cc)
                        if _m is not None:
                            app.contract_price = _m
                            # MFE/MAE a 1 Hz, sin escribir en BD: asi hasta una posicion de 10 s
                            # deja su recorrido real. El 2026-08-10 un PUT llego a +130$ y se
                            # vendio en +45$, y ese maximo solo existia en el log como texto.
                            app._seguir_extremos(_m)
                        # RECORRIDO en la BD cada POS_LOG_SECS (la entrada y la salida se
                        # graban aparte, siempre, desde _trade_abrir/_trade_cerrar).
                        if (app.trade_id is not None
                                and time.monotonic() - app.last_pos_log > POS_LOG_SECS):
                            app.last_pos_log = time.monotonic()
                            app._pos_snapshot("minuto")
                    # log de cambios de decision de trading (por que opera / por que no)
                    if app.trade_msg != app._last_trade_log:
                        ACT.info("TRADE %s", app.trade_msg)
                        app._last_trade_log = app.trade_msg
            except Exception:
                LOG.exception("Error en el ciclo principal (tick)")
        else:
            # MERCADO CERRADO: detener la sesion una vez y esperar la proxima apertura
            if connected["ok"] or app.ib.isConnected():
                app.end_session()
                connected["ok"] = False
            app.status = "MERCADO CERRADO (ET) - esperando apertura 09:30"

        big.config(text=app.state, fg=colors.get(app.state, "#888888"))
        sub.config(text=(f"SPY {app.spy_price:.2f}    "
                         f"CALL net ${app.net_call:,.0f}   PUT net ${app.net_put:,.0f}"))
        status.config(text=f"[{app.mode}] {app.status}")

        # --- estado de trading ---
        if app.pos == "CALL" and app.call is not None:
            pos_txt = f"LONG CALL {app.buy_call.strike:g}" if app.buy_call else "LONG CALL"
        elif app.pos == "PUT" and app.put is not None:
            pos_txt = f"LONG PUT {app.buy_put.strike:g}" if app.buy_put else "LONG PUT"
        else:
            pos_txt = "FLAT"
        pos_lbl.config(text=f"POSICION: {pos_txt}")
        if app.trading:
            trade_ind.config(text="TRADING ON", bg="#22c55e")
        else:
            trade_ind.config(text="TRADING OFF", bg="#ef4444")
        trade_msg_lbl.config(text=app.trade_msg)

        # --- cuenta / acumulado del dia (verde si gana, rojo si pierde) ---
        _acol = "#e5e7eb"
        if app.acct_net is not None and app.acct_net_open:
            _d = app.acct_net - app.acct_net_open
            _acol = "#22c55e" if _d > 0 else ("#ef4444" if _d < 0 else "#e5e7eb")
        acct_lbl.config(text=app.resumen_cuenta(), fg=_acol)

        v = app.ta_vals
        if v:
            _col = {"UP": "#22c55e", "DOWN": "#ef4444", "NEUTRAL": "#9ca3af", None: "#9ca3af"}
            _m1 = app.m1_estado or "-"; _m2 = app.m2_estado or "-"; _cl = app.cl_estado or "-"
            _conf = app.conf_estado or "-"
            _mand = "M1" if USAR_M1 else "CLASICO"
            metodos_lbl.config(
                text=(f"M1 {_m1:>7} ({app.m1_up}-{app.m1_down})   "
                      f"M2 {_m2:>7} ({app.m2_up - app.m2_down:+,.0f}$)   "
                      f"CLASICO {_cl:>7}   CONF {_conf:>7} (r{app.sen_racha}/{CONFIRMACION_MIN})"
                      f"  |  MANDA: {_mand}"
                      + (f"  [retardo {RETARDO_M1_MIN}m -> {app.m1_efectivo or '-'}]"
                         if USAR_M1 and RETARDO_M1_MIN else "")),
                fg=_col.get(app.m1_estado, "#9ca3af"))
            ta_lbl.config(text=(f"TA 1m: {v['dir']}  RSI {v['rsi']:.0f}  "
                                f"MACDh {v['macd_hist']:+.2f}  EMA8/21 {v['ema8']:.2f}/{v['ema21']:.2f}"
                                f"  score {v['score']:+d}"))

        if WALLS_ENABLED and app.walls:
            w = app.walls
            gg = app.gex or {}
            gxt = gg.get("gex_total")
            gtxt = f"{gxt/1e9:+.2f}Bn" if isinstance(gxt, (int, float)) else "-"
            walls_lbl.config(text=(
                f"PW {_fmt(w.get('put_wall'))}  CW {_fmt(w.get('call_wall'))}  "
                f"Mag {_fmt(w.get('max_pain_static'))}/{_fmt(w.get('max_pain_dyn'))}  "
                f"peso {_fmt(w.get('prem_center'))}\n"
                f"GEX {gtxt} {gg.get('regime', '-')}  Flip {_fmt(gg.get('gamma_flip'))}"))

        # contrato comprado (SOLO si hay posicion real; al vender/FLAT desaparece).
        # Precio en vivo + P&L, color verde/rojo segun subio/bajo desde la entrada.
        _bc = app.buy_call if app.pos == "CALL" else (app.buy_put if app.pos == "PUT" else None)
        if _bc is not None:
            rl = "C" if app.pos == "CALL" else "P"
            en = app.entry_price
            pr = app.contract_price
            txt = f"Contrato: SPY {_bc.strike:g}{rl} {app.expiry or ''}"
            col = "#fbbf24"
            if en:
                txt += f"  entrada {en:.2f}"
            if pr is not None:
                txt += f"  ->  {pr:.2f}"
                if en:
                    pnl = (pr - en) * 100.0 * QTY
                    pct = (pr / en - 1.0) * 100.0
                    txt += f"  ({pnl:+.0f}$ / {pct:+.1f}%)"
                    col = "#22c55e" if pr >= en else "#ef4444"
            contract_lbl.config(text=txt, fg=col)
        else:
            contract_lbl.config(text="")

        # Gamma Ladder (solo lectura, estilo MarketSnack)
        if WALLS_ENABLED:
            try:
                _draw_ladder(ladder, app)
            except Exception:
                LOG.exception("Error dibujando Gamma Ladder")

        if app.pending_sound is not None:
            if HAVE_SOUND:
                try:
                    if app.pending_sound == "flip":
                        winsound.Beep(880, 300); winsound.Beep(1175, 300)
                    else:
                        winsound.Beep(660, 200)
                except Exception:
                    pass
            app.pending_sound = None
        if app.alert_text and time.monotonic() < app.alert_until:
            bg = "#ef4444" if app.alert_kind == "FLIP" else "#f59e0b"
            alert.config(text="  " + app.alert_text + "  ", bg=bg, fg="#111111")
            try:
                root.attributes("-topmost", True); root.lift()
                root.after(1200, lambda: root.attributes("-topmost", False))
            except Exception:
                pass
        else:
            alert.config(text="", bg="#111111")

        # baseline (fechas posteriores)
        basebox.delete("1.0", tk.END)
        for exp, ch, cp, ph, pp in app.baseline_summary():
            cflag = " STRONG" if (cp > 0 and ch > cp * OPEN_JUMP_FACTOR) else ""
            pflag = " STRONG" if (pp > 0 and ph > pp * OPEN_JUMP_FACTOR) else ""
            basebox.insert(tk.END,
                           f"{exp}  C hoy ${ch:,.0f}/prev ${cp:,.0f}{cflag}\n"
                           f"          P hoy ${ph:,.0f}/prev ${pp:,.0f}{pflag}\n")
        if not app.base_expiries:
            basebox.insert(tk.END, "(sin datos aun / conectando...)\n")

        logbox.delete("1.0", tk.END)
        for fecha, hora, estado, tipo, spy in app.recent(8):
            sp = f"{spy:.2f}" if spy else "-"
            logbox.insert(tk.END, f"  {fecha} {hora}  {tipo:4}  {estado:4}  SPY {sp}\n")

        root.after(int(REFRESH_SECS * 1000), tick)

    root.after(200, tick)
    root.mainloop()

    try:
        app._persist_accum()
    except Exception:
        pass
    try:
        if not app.demo and app.ib.isConnected():
            app._cancel_working()   # no dejar limits huerfanas al cerrar
    except Exception:
        pass
    try:
        app.ib.disconnect()
    except Exception:
        pass
    try:
        app.db.close()
    except Exception:
        pass


def selftest():
    app = SpyDirection()
    try:
        app.connect()
        print(f"Conexion IB Gateway OK ({HOST}:{PORT})")
    except Exception as e:
        print(f"SIN CONEXION: {e}")
        return
    ok = app.setup_contracts()
    print("Resultado setup:", app.status)
    if ok:
        print(f"  Modo datos : {app.mode}")
        print(f"  SPY        : {app.spy_price:.2f}")
        print(f"  Cercano    : {app.expiry}")
        print(f"  CALL/PUT   : {app.call.strike:g}C / {app.put.strike:g}P")
        print(f"  Baseline exps futuras: {app.base_expiries}")
        print(f"  Contratos baseline seguidos: {len(app.info_base)}")
    app.ib.disconnect()


if __name__ == "__main__":
    util.patchAsyncio()
    if "--selftest" in sys.argv:
        selftest()
    elif "--demo" in sys.argv:
        run_gui(SpyDirection(demo=True))
    else:
        run_gui(SpyDirection())
