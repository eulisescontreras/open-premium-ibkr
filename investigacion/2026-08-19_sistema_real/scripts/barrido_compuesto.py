# COMPOSICION REAL — el sistema recalibra su tamaño con el saldo, como hace el vivo.
#
# LO QUE FALTABA: el backtest corre los 485 dias con el tamaño CONGELADO. El sistema real llama
# a autocalibra.configuracion(saldo) y sube de nivel cuando la cuenta crece (MANUAL §13.1):
#   600$ -> ancho 2 tope 110 | 1.800$ -> ancho 4 tope 320 | 3.600$ -> +2 contratos
#   5.400$ -> 3 contratos (TOPE_UNIDADES, no crece mas)
# Medido hoy: base honesta con tope 320 = +32.620$; con tope 110 (cuenta real) = +6.442$.
# Pero una cuenta que gana 6.442$ NO sigue operando con tope 110: sube de nivel por el camino.
#
# Se REUTILIZA la funcion real `autocalibra.configuracion` (R9), no una copia.
# TODOS los fixes anti-look-ahead activos (RL=vod): reb2 honesto + ORB + dia_bueno.
#
# Variables: RL_CAP = capital inicial. RL_SLIP = slippage. "c" en RL = composicion ON.
import shutil, subprocess, sys, os, time

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
PIP = os.path.join(RAIZ, "sys2", "core", "pipeline.py")
BMOT, BPIP = MOT + ".cp.bak", PIP + ".cp.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import instrumento as I"
N_IMP = """from sys2.core import instrumento as I
import os as _os
from sys2.core.rebote import reb2 as _reb2
from sys2.core.supertrend import mm as _mm2
from sys2.core import autocalibra as _AC
_RL = _os.environ.get("RL", "")
_SLIP = float(_os.environ.get("RL_SLIP", "1.01"))
_CAP0 = float(_os.environ.get("RL_CAP", "600"))"""

# saldo vivo entre dias (se inicializa al entrar en SIS70)
A_D = "    D = {}\n    prev = None"
N_D = "    D = {}\n    prev = None\n    _saldo = _CAP0\n    _anc = C.ANCHO\n    _uni = 1"

A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
N_SEN = '''        if "c" in _RL:              # COMPOSICION: nivel del dia segun el saldo REAL
            _cfg = _AC.configuracion(_saldo)
            if _cfg is None:        # cuenta por debajo de 200$ -> no opera mas
                D[fk] = 0.0
                continue
            tope = _cfg["tope"]; _anc = _cfg["ancho"]; _uni = _cfg["unidades"]
''' + A_SEN + '''
        if "v" in _RL:              # VIVO HONESTO: reb2 con 1 bucket
            _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
            for _h, _d in sp:
                if _h < "09:45":
                    continue
                _i = ik.get((_mm2(_h) // 3) * 3)
                if _i is None:
                    continue
                _n = min(_i + 1, len(ks) - 1)
                _ks2 = ks[:_n + 1]; _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
                for _r in _reb2(L, _ks2, _ik2, _h, _d):
                    _ap2.setdefault(_r[0], _r[1])
            Sen = dict(sorted(_ap2.items()))
'''

# unidades del nivel (el vivo: nq = unidades_base * (2 si dia_bueno), tope TOPE_UNIDADES)
A_NQ = "        nq = 1\n"
N_NQ = "        nq = _uni if \"c\" in _RL else 1\n"
A_NQ2 = "            nq = 2"
N_NQ2 = "            nq = min(nq * 2, _AC.TOPE_UNIDADES)"

A_NQA = "'vert': True, 'nq': nq}"
N_NQA = "'vert': True, 'nq': (1 if ('d' in _RL and h < '10:31') else nq)}"
A_NQB = "'rod': 0, 'extra': None, 'h0': h, 'd0': d0, 'nq': nq}"
N_NQB = "'rod': 0, 'extra': None, 'h0': h, 'd0': d0, 'nq': (1 if ('d' in _RL and h < '10:31') else nq)}"
A_TOPE = "    tope = tope if tope is not None else C.TOPE"
N_TOPE = "    tope = tope if tope is not None else (110.0 if 't' in _RL else C.TOPE)"
A_ANCHO = "if C.ANCHO:"
N_ANCHO = "if (_anc if 'c' in _RL else (2.0 if 't' in _RL else C.ANCHO)):"
A_ANCHO2 = "I.elegir_vert(cd2, Sx, h, rt, tope, C.ANCHO)"
N_ANCHO2 = "I.elegir_vert(cd2, Sx, h, rt, tope, (_anc if 'c' in _RL else (2.0 if 't' in _RL else C.ANCHO)))"

# al cerrar el dia, el saldo compone
A_FIN = "        D[fk] = tot"
N_FIN = "        D[fk] = tot\n        _saldo += tot"

P_IMP = "from sys2 import config as C"
P_IMPN = "from sys2 import config as C\nimport os as _os\n_RL = _os.environ.get(\"RL\", \"\")"
P_VIEJO = "        if sg and all(abs(mm(sg[0][0]) - mm(x[0])) > C.DESCARTE_MIN for x in S):"
P_NUEVO = ("        if sg and all(abs(mm(sg[0][0]) - mm(x[0])) > C.DESCARTE_MIN\n"
           "                      for x in S if ('o' not in _RL or mm(x[0]) <= mm(sg[0][0]))):")

# (nombre, RL, capital inicial, slippage)
VARIANTES = [
    ("cp_ctrl_fijo",  "vod",  "600",   "1.01"),  # CONTROL: sin composicion = rl_real (+32.620)
    ("cp_600",        "vodc", "600",   "1.01"),  # tu cuenta REAL, componiendo
    ("cp_600_s2",     "vodc", "600",   "1.02"),  # con slippage 2%
    ("cp_1000",       "vodc", "1000",  "1.01"),
    ("cp_1800",       "vodc", "1800",  "1.01"),  # nivel de ancho 4 / tope 320 desde el dia 1
    ("cp_3600",       "vodc", "3600",  "1.01"),  # nivel de 2 contratos
    ("cp_5400",       "vodc", "5400",  "1.01"),  # nivel maximo (3 contratos)
    ("cp_400",        "vodc", "400",   "1.01"),
]

for b in (BMOT, BPIP):
    assert not os.path.exists(b), "hay otro barrido vivo"
bmot = open(MOT, encoding="utf-8").read()
bpip = open(PIP, encoding="utf-8").read()
for txt, pat in ((bmot, A_IMP), (bmot, A_D), (bmot, A_SEN), (bmot, A_NQ), (bmot, A_NQ2),
                 (bmot, A_NQA), (bmot, A_NQB), (bmot, A_TOPE), (bmot, A_ANCHO),
                 (bmot, A_ANCHO2), (bmot, A_FIN), (bpip, P_IMP), (bpip, P_VIEJO)):
    assert txt.count(pat) == 1, "patron no unico o ausente: %r" % pat[:60]
shutil.copy2(MOT, BMOT); shutil.copy2(PIP, BPIP)

tm = (bmot.replace(A_IMP, N_IMP).replace(A_D, N_D).replace(A_SEN, N_SEN)
      .replace(A_NQ, N_NQ).replace(A_NQ2, N_NQ2).replace(A_NQA, N_NQA).replace(A_NQB, N_NQB)
      .replace(A_TOPE, N_TOPE).replace(A_ANCHO2, N_ANCHO2).replace(A_ANCHO, N_ANCHO)
      .replace(A_FIN, N_FIN).replace("* 1.01", "* _SLIP"))
tp = bpip.replace(P_IMP, P_IMPN).replace(P_VIEJO, P_NUEVO)

try:
    for txt, ruta in ((tm, MOT), (tp, PIP)):
        compile(txt, ruta, "exec")
    open(MOT, "w", encoding="utf-8").write(tm)
    open(PIP, "w", encoding="utf-8").write(tp)
    procs = []
    for nombre, rl, cap, slip in VARIANTES:
        env = dict(os.environ, RL=rl, RL_CAP=cap, RL_SLIP=slip)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, cap, p))
        print("lanzado %-14s cap=%s RL=%s" % (nombre, cap, rl), flush=True)
    print("\n-- %d en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    for nombre, cap, p in procs:
        o, e = p.communicate(timeout=3000)
        r = (o or "").strip() or (e or "").strip()[-250:]
        print("%-14s %s" % (nombre, r[-120:]), flush=True)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BMOT, MOT); os.remove(BMOT)
    shutil.copy2(BPIP, PIP); os.remove(BPIP)
    print("[RESTAURADOS]", flush=True)
