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


_ULTIMA = None          # última notificación emitida (para que el PANEL pueda mostrarla)


def ultima():
    """Última notificación como dict(ts, tipo, msg), o None. La consume _volcar_estado."""
    return _ULTIMA


def notificar(msg, tipo="AVISO"):
    """Notificación VISIBLE (compra/venta/arranque/error). Consola + log + `ultima()`.
    OJO: el sistema arranca con `nohup ... >> log 2>&1`, así que el print NO se ve en ninguna
    consola y además ib_insync escribe al mismo stdout y puede PISAR la línea (pasó el
    2026-08-18 11:01: el aviso de COMPRA VERTICAL quedó ilegible). Por eso se guarda también
    en memoria: el panel la lee de estado.json y la muestra, que es el canal que sí se ve."""
    global _ULTIMA
    barra = "═" * 60
    bloque = "%s\n🔔 %s | %s | %s\n%s" % (barra, _ahora(), tipo, msg, barra)
    print(bloque)
    _escribir("=== NOTIF === %s | %s | %s" % (_ahora(), tipo, msg))
    _ULTIMA = {"ts": _ahora(), "tipo": tipo, "msg": msg}


def error(msg, exc=None):
    """Error prominente (también notifica)."""
    detalle = "%s%s" % (msg, (" :: %r" % exc) if exc is not None else "")
    log(detalle, "ERROR")
    notificar(detalle, "ERROR")
