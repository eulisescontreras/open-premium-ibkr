# -*- coding: utf-8 -*-
"""Logging EXHAUSTIVO + notificaciones para el sistema vivo. Sin dashboard: todo se ve por
los logs (archivo diario + consola) y por notificaciones marcadas (===NOTIF===).

- log(...)      : detalle exhaustivo (cada decisión, cada descarte) -> archivo + consola.
- notificar(...): eventos importantes (compra/venta/arranque/error) -> muy visibles + archivo.
Los logs viven en sys2/vivo/logs/vivo_YYYY-MM-DD.log (uno por día).
"""
import os
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _ahora():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _hoy():
    return time.strftime("%Y-%m-%d")


def _ruta():
    return os.path.join(LOG_DIR, "vivo_%s.log" % _hoy())


def _escribir(linea):
    try:
        with open(_ruta(), "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception:
        pass


def log(msg, cat="INFO"):
    """Log exhaustivo con hora + categoría. cat: INFO/DEBUG/SENAL/POS/ORDEN/DATA/WARN/ERROR."""
    linea = "%s | %-6s | %s" % (_ahora(), cat, msg)
    print(linea)
    _escribir(linea)


def notificar(msg, tipo="AVISO"):
    """Notificación VISIBLE (compra/venta/arranque/error). Se ve en consola resaltada + log."""
    barra = "═" * 60
    bloque = "%s\n🔔 %s | %s | %s\n%s" % (barra, _ahora(), tipo, msg, barra)
    print(bloque)
    _escribir("=== NOTIF === %s | %s | %s" % (_ahora(), tipo, msg))


def error(msg, exc=None):
    """Error prominente (también notifica)."""
    detalle = "%s%s" % (msg, (" :: %r" % exc) if exc is not None else "")
    log(detalle, "ERROR")
    notificar(detalle, "ERROR")
