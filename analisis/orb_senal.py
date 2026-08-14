# -*- coding: utf-8 -*-
"""ORB DE APERTURA — función EXACTA usada en el backtest que dio +25.769$

Extraída literalmente de la corrida de validación (2026-08-14).
Conteo sobre 512 sesiones de spy_bars_year.db + spy_bars_year2.db:

    con señal .................. 183   (tu implementacion: 182, difiere 1 dia)
    descartados por FILTRO ..... 113   (22%)
    pasan filtro y NO rompen ... 216
    sin señal, total ........... 329

    horas: 09:40=77  09:41=30  09:42=30  09:43=24  09:44=22
    direccion: 106 CALL / 77 PUT

RESPUESTAS A TUS 3 PREGUNTAS
  1. DISPARO: por CIERRE (`cl`), no por toque.
     El toque se midió: 246 dias, 58% de aciertos (vs 64% del cierre),
     y NO pasa el control de azar en el año 1 (p=0.227 vs p=0.025). Descartado.
  2. RANGO: solo RTH. El rango se construye con barras de 09:30 a 09:39.
     El premarket NO entra en el rango del ORB.
     (Ojo: el premarket SÍ entra en el ATR del Supertrend principal. Son cosas
      distintas y es fácil confundirlas.)
  3. VENTANA: barras de 1 minuto etiquetadas por su propio minuto. El disparo
     se evalúa en barras con 09:40 <= hora < 09:45, es decir 09:40..09:44.
     El minuto 09:45 pertenece a la principal. Incluirlo da 214 dias y +23.432$,
     que es PEOR que los +25.769$ de la version estricta.

NOTA SOBRE EL DIA DE DIFERENCIA (183 vs 182)
  El filtro descarta con MENOR ESTRICTO:  if (hi - lo) < 0.75  -> no operar.
  Un rango de exactamente 0.75 SI opera. Si usas `<= 0.75` para descartar,
  ahi esta el dia. Irrelevante para el P&L.
"""


def mm(h):
    """'HH:MM' -> minutos desde medianoche."""
    return int(h[:2]) * 60 + int(h[3:5])


def orb_senal(bars, rango_min=0.75):
    """bars: [(hora, high, low, close), ...] de 1 minuto, ordenadas.
             Puede traer premarket: se filtra aqui dentro.

    Devuelve [(hora, 'C'|'P')] con como maximo UNA señal, o [] si no hay.
    REVERSION: rompe por arriba -> PUT ; rompe por abajo -> CALL.
    """
    # ventana de trabajo: 09:30 .. 09:44  (ESTRICTO: < "09:45")
    B = [(h, hi, lo, cl) for h, hi, lo, cl in bars if "09:30" <= h < "09:45"]

    # rango de apertura: los primeros 10 minutos, 09:30 .. 09:39
    # (mm(h) < 580  <=>  h < "09:40")
    ini = [x for x in B if mm(x[0]) < 580]
    if not ini:
        return []

    hi = max(x[1] for x in ini)     # HIGH de las barras, no close
    lo = min(x[2] for x in ini)     # LOW  de las barras, no close

    # filtro de amplitud: MENOR ESTRICTO
    if (hi - lo) < rango_min:
        return []

    # disparo: primer CIERRE fuera del rango, entre 09:40 y 09:44
    for h, H, L, C in B:
        if mm(h) < 580:
            continue
        if C > hi:
            return [(h, 'P')]       # rompe ARRIBA -> PUT   (REVERSION)
        if C < lo:
            return [(h, 'C')]       # rompe ABAJO  -> CALL  (REVERSION)
    return []


# ---------------------------------------------------------------------------
# COMO SE FUSIONA CON LA PRINCIPAL (tal cual en el backtest)
#
#   p = senales_principal(bars)          # ST-3, ya con shift_sen(...,3), hora >= 09:45
#   s = orb_senal(bars)                  # 0 o 1 señal, hora < 09:45
#   senales = sorted(s + p)              # lista unica ordenada por hora
#
#   ops, cap = simular(fecha, senales=senales, trail=99.0,
#                      mid=False, mag_umbral=None,
#                      size_cap=400.0,          # FIJO, no compuesto
#                      salir_en_flip=True,
#                      max_trades=4)            # cuenta ORB + principal
#
# NO hay parametro hora_min: el filtrado horario ya viene dado por las dos
# funciones de señal (ORB < 09:45, principal >= 09:45).
#
# Verificado sobre 512 sesiones:
#   - solapamiento horario ORB/principal: 0 casos
#   - doble spread por reabrir el mismo lado: 0 casos
#     (el motor MANTIENE la posicion si la nueva señal coincide en direccion;
#      comprobado: fusionar y reabrir dan el MISMO total, +25.769$)
# ---------------------------------------------------------------------------