# -*- coding: utf-8 -*-
"""SALIDA del sistema (vivo). Espeja la lógica de salida del motor validado pero con los tiempos
OPERABLES (§12.4), NO los del backtest:
  - flip del ST-3 (señal contraria) -> cerrar.
  - APLANAR a las 15:50 (aplanado operable; el backtest usa 15:59 pero §12.4 lo PROHÍBE en vivo:
    "el coste de un solo fallo es la cuenta entera" por riesgo de asignación §12).
  - orden a MERCADO a las 15:55 si sigue abierta.
  - verificación EXPLÍCITA de posición plana ANTES de las 16:00 (bloqueante de asignación).

Decisión pura (sin IBKR) -> cold-runnable. La EJECUCIÓN la hace vivo/sistema.py vía data/ibkr.py.
OBLIGATORIO: antes de modificar, leer §12 (riesgo de asignación) y correr cr_salida.py.
"""
from sys2 import config as C


def decidir_salida(pos, sen_dir_ahora, hora):
    """Devuelve la razón de salida o None. pos = posición abierta (dict con 'rt'); sen_dir_ahora
    = 'C'/'P'/None (dirección de la señal del ST-3 en este minuto, si la hay); hora 'HH:MM'.
      'flip'    -> señal contraria (gira): cerrar al precio del momento.
      'aplanar' -> hora >= APLANADO_VIVO (15:50): cerrar (límite/mid).
      'mercado' -> hora >= MERCADO_VIVO (15:55): forzar a MERCADO (sigue abierta).
      None      -> mantener."""
    if pos is None:
        return None
    if hora >= C.MERCADO_VIVO:
        return "mercado"
    if hora >= C.APLANADO_VIVO:
        return "aplanar"
    if sen_dir_ahora is not None and sen_dir_ahora != pos["rt"]:
        return "flip"
    return None


def debe_verificar_plana(hora):
    """True si ya toca verificar EXPLÍCITAMENTE que no queda posición (>= VERIF_PLANA, <16:00)."""
    return C.VERIF_PLANA <= hora < "16:00"


def puede_abrir(hora, hechas):
    """No abrir después de ABRIR_HASTA (15:40) ni superando MAX_TRADES."""
    return hechas < C.MAX_TRADES and hora < C.ABRIR_HASTA
