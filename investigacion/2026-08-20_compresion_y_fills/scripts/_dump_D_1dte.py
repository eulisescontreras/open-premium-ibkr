# -*- coding: utf-8 -*-
import json, sys, os
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C

def _f(nom, defecto):
    v = os.environ.get(nom, "")
    return float(v) if v not in ("", None) else defecto

if os.environ.get("RL_SCORE_OFF") == "1":
    C.SCORE_OPCIONES = 0        # pipeline.py lo lee EN RUNTIME
C.TP_ANCHO = _f("RL_TP", C.TP_ANCHO)              # objetivo: fracción del ANCHO
C.MAX_TRADES = int(_f("RL_MT", C.MAX_TRADES))
C.PAUSA_ROJOS = int(_f("RL_PAUSA", C.PAUSA_ROJOS))
C.SIZING_FRAC = _f("RL_FRAC", C.SIZING_FRAC)
C.SIZING_SUELO = _f("RL_SUELO", C.SIZING_SUELO)

_ANC = _f("RL_ANCHO", 0)
if _ANC:                                           # forzar el ancho SIN tocar archivos
    from sys2.core import autocalibra as _AC
    _orig = _AC.sizing
    def _sz(saldo):
        c = _orig(saldo)
        if c:
            c = dict(c, ancho=_ANC)
        return c
    _AC.sizing = _sz

from sys2.backtest import motor
from sys2.db import repo
con = repo.abrir(); SES, PREM, ETFB = motor.cargar(con); con.close()
D = motor.SIS70(SES, PREM, ETFB, capital=600)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
s = 600.0
for f in sorted(D):
    s += D[f]
print("OK %d dias  saldo %.0f  (tp=%s anc=%s score=%s corte=%s)"
      % (len(D), s, C.TP_ANCHO, _ANC or "auto", C.SCORE_OPCIONES,
         os.environ.get("RL_CORTE") or "-"))
