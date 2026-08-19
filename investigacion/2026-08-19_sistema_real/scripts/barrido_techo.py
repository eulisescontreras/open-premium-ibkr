# TECHO DE CADA DECISION DE reb2, MEDIDO EN EL MOTOR REAL (no en un proxy).
#
# ⚠️ ESTAS VARIANTES USAN LOOK-AHEAD A PROPOSITO. No son aplicables: miden el TECHO, es decir
# cuanto vale como MAXIMO replicar cada decision, para saber si merece la pena buscar el
# predictor honesto antes de gastar dias en ello.
#
# Contexto (fase 1b, proxy de P&L con ancho 2 / debito 46%): DESCARTA +10.235$ (62%),
# INVIERTE +4.836$ (29%), RETRASA +1.514$ (9%). Falta confirmarlo con el MOTOR REAL.
# Suelo de ruido medido: ±4.000-6.000$ (1 sigma) sobre ~420 dias afectados -> solo algo del
# tamaño de DESCARTA seria demostrable.
#
# Base de comparacion: hn_base (+35.878$) = el vivo honesto (reb2 con 1 bucket).
import shutil, subprocess, sys, os

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".tch.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D.py")
HIJO_T = os.path.join(AQUI, "_dump_D_test.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)
PRUEBA = "--prueba" in sys.argv          # valida el parche con 40 dias antes de las 485

A_IMP = "from sys2.core import instrumento as I"
N_IMP = ("from sys2.core import instrumento as I\n"
         "from sys2.core.rebote import reb2 as _reb2\n"
         "from sys2.core.supertrend import mm as _mm2")
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"

TPL = A_SEN + '''

        _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
        for _h, _d in sp:
            if _h < "09:45":
                continue
            _i = ik.get((_mm2(_h) // 3) * 3)
            if _i is None:
                continue
            _rf = _reb2(L, ks, ik, _h, _d)          # VISION COMPLETA (look-ahead deliberado)
            if not _rf:
                _g = "DESCARTA"
            elif _rf[0][0] == _h and _rf[0][1] == _d:
                _g = "NORMAL"
            elif _rf[0][1] != _d:
                _g = "INVIERTE"
            else:
                _g = "RETRASA"
            if _g == "DESCARTA" and %(DESC)s:
                continue
            if _g == "INVIERTE" and %(INV)s:
                _ap2.setdefault(_rf[0][0], _rf[0][1])
                continue
            if _g == "RETRASA" and %(RET)s:
                _ap2.setdefault(_rf[0][0], _rf[0][1])
                continue
            # por defecto: exactamente lo que hace el vivo (reb2 con 1 bucket)
            _n = min(_i + 1, len(ks) - 1)
            _ks2 = ks[:_n + 1]; _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
            for _r in _reb2(L, _ks2, _ik2, _h, _d):
                _ap2.setdefault(_r[0], _r[1])
        Sen = dict(sorted(_ap2.items()))
'''

# (nombre, usa DESCARTA, usa INVIERTE, usa RETRASA)
VARIANTES = [
    ("tc_vivo",     "False", "False", "False"),   # CONTROL: debe reproducir hn_base +35.878
    ("tc_desc",     "True",  "False", "False"),   # techo de NO ENTRAR (62% del valor segun proxy)
    ("tc_inv",      "False", "True",  "False"),   # techo de INVERTIR
    ("tc_ret",      "False", "False", "True"),    # techo de RETRASAR
    ("tc_desc_inv", "True",  "True",  "False"),   # las dos que concentran el 91%
    ("tc_todo",     "True",  "True",  "True"),    # reb2 completo = el motor con look-ahead
]

assert not [x for x in os.listdir(os.path.dirname(MOT)) if x.endswith(".bak")], \
    "hay otro barrido vivo: motor.py esta parcheado"
shutil.copy2(MOT, BAK)
base = open(BAK, encoding="utf-8").read()
assert base.count(A_IMP) == 1 and base.count(A_SEN) == 1

try:
    for nombre, de, iv, re_ in VARIANTES:
        txt = base.replace(A_IMP, N_IMP)
        txt = txt.replace(A_SEN, TPL % {"DESC": de, "INV": iv, "RET": re_})
        # VALIDACION PREVIA (instantanea): que el parche COMPILE antes de gastar 3 min de motor.
        # (correrlo sobre 40 dias NO ahorra: lo que tarda es motor.cargar, no el bucle.)
        try:
            compile(txt, MOT, "exec")
        except SyntaxError as e:
            print("%-12s PARCHE NO COMPILA: %s (linea %s)" % (nombre, e.msg, e.lineno), flush=True)
            continue
        open(MOT, "w", encoding="utf-8").write(txt)
        dest = os.path.join(OUT, nombre + ".json")
        cmd = [sys.executable, HIJO, dest]
        r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, timeout=2400)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()[-300:]
        print("%-12s %s" % (nombre, out[-130:]), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("\n[motor.py RESTAURADO]", flush=True)
