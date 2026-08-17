# -*- coding: utf-8 -*-
"""Estado en vivo del sistema para el PANEL. El sistema escribe `estado.json` cada minuto/evento;
el panel (vivo/panel.py) lo lee y refresca. Desacoplado: el panel corre aparte y no toca la lógica.
"""
import json
import os
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA = os.path.join(_DIR, "estado.json")


def escribir(d):
    """Escribe el estado de forma atómica (tmp + replace) para que el panel nunca lea a medias."""
    d = dict(d)
    d["ts"] = time.time()
    d.setdefault("ultima_act", time.strftime("%H:%M:%S"))
    tmp = RUTA + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, RUTA)
    except Exception:
        pass


def leer():
    """Devuelve el estado (dict) o None si no existe / ilegible."""
    try:
        with open(RUTA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
