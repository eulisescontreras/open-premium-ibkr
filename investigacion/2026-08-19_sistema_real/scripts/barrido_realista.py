# BASE REALISTA — quitar TODAS las mentiras medibles del backtest. EJECUCION EN PARALELO.
#
# MOTIVO (usuario): "74 mil segun era la realidad y era mentira; necesito que sea real todo
# absolutamente real". Optimizar sobre un backtest que miente produce otro +74k falso.
#
# MENTIRAS Y ESTADO:
#  1. reb2 con 12 buckets futuros ...... flag "v": el vivo honesto (reb2 con 1 bucket).
#     VERIFICADO en fase 4: el vivo entra SIEMPRE en el minuto del flip, direccion original.
#  2. ORB futuro (pipeline.py:38-41) ... flag "o": una apertura de 09:38 se descartaba por el
#     ORB de las 09:40, que AUN NO HA OCURRIDO. Fix: comparar solo contra señales YA ocurridas.
#  3. dia_bueno desde el minuto 1 ...... flag "d": `nq` se calcula antes del bucle (motor.py:158)
#     y dobla unidades a las 09:35 con datos de las 10:30. En vivo (reglas.py:60) es False hasta
#     tener 60 barras = 10:30. Fix: nq solo en aperturas >= 10:31.
#  4. Tamaño .......................... flag "t": el backtest usa TOPE=320/ANCHO=4; el vivo REAL
#     opera tope=110/ancho=2 (log de hoy; debitos reales 82-101$).
#  5. Slippage ........................ RL_SLIP: el motor asume fill a close*1.01. Unica evidencia
#     real disponible (op131): lleno a 1.52 con ask 1.54 y 0.51 con bid 0.52 -> DENTRO del spread.
#     Con 2 fills no hay base estadistica -> se mide SENSIBILIDAD (1%/2%/3%).
# NO corregible con estos datos: fills parciales, rechazos por margen, densidad de cadena.
#
# PARALELO: se parchean motor.py/pipeline.py UNA SOLA VEZ con lectura de os.environ, y las
# variantes se lanzan a la vez con distinto entorno (16 nucleos). Minutos en vez de media hora.
import shutil, subprocess, sys, os, time

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
PIP = os.path.join(RAIZ, "sys2", "core", "pipeline.py")
BMOT, BPIP = MOT + ".rl.bak", PIP + ".rl.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

# ── parche motor.py ──
A_IMP = "from sys2.core import instrumento as I"
N_IMP = """from sys2.core import instrumento as I
import os as _os
from sys2.core.rebote import reb2 as _reb2
from sys2.core.supertrend import mm as _mm2
_RL = _os.environ.get("RL", "")
_SLIP = float(_os.environ.get("RL_SLIP", "1.01"))"""

A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
N_SEN = A_SEN + '''
        if "v" in _RL:          # VIVO HONESTO: reb2 con 1 bucket (lo que ve el sistema real)
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

A_NQ1 = "'vert': True, 'nq': nq}"
N_NQ1 = "'vert': True, 'nq': (1 if ('d' in _RL and h < '10:31') else nq)}"
A_NQ2 = "'rod': 0, 'extra': None, 'h0': h, 'd0': d0, 'nq': nq}"
N_NQ2 = "'rod': 0, 'extra': None, 'h0': h, 'd0': d0, 'nq': (1 if ('d' in _RL and h < '10:31') else nq)}"
A_TOPE = "    tope = tope if tope is not None else C.TOPE"
N_TOPE = "    tope = tope if tope is not None else (110.0 if 't' in _RL else C.TOPE)"
A_ANCHO = "if C.ANCHO:"
N_ANCHO = "if (2.0 if 't' in _RL else C.ANCHO):"
A_ANCHO2 = "I.elegir_vert(cd2, Sx, h, rt, tope, C.ANCHO)"
N_ANCHO2 = "I.elegir_vert(cd2, Sx, h, rt, tope, (2.0 if 't' in _RL else C.ANCHO))"

# ── parche pipeline.py (fix ORB futuro) ──
P_IMP = "from sys2 import config as C"
P_IMPN = "from sys2 import config as C\nimport os as _os\n_RL = _os.environ.get(\"RL\", \"\")"
P_VIEJO = "        if sg and all(abs(mm(sg[0][0]) - mm(x[0])) > C.DESCARTE_MIN for x in S):"
P_NUEVO = ("        if sg and all(abs(mm(sg[0][0]) - mm(x[0])) > C.DESCARTE_MIN\n"
           "                      for x in S if ('o' not in _RL or mm(x[0]) <= mm(sg[0][0]))):")

# (nombre, RL, RL_SLIP)
VARIANTES = [
    ("rl_motor_full", "",      "1.01"),   # CONTROL: motor original CON look-ahead = +72.497
    ("rl_v0_control", "v",     "1.01"),   # CONTROL: vivo honesto = debe dar +35.878 exacto
    ("rl_orb",        "vo",    "1.01"),   # + fix ORB futuro
    ("rl_dia",        "vd",    "1.01"),   # + fix dia_bueno
    ("rl_real",       "vod",   "1.01"),   # BASE HONESTA (tamaño del backtest)
    ("rl_real_t110",  "vodt",  "1.01"),   # + tamaño REAL del vivo (tope 110 / ancho 2)
    ("rl_real_s2",    "vod",   "1.02"),   # sensibilidad al slippage
    ("rl_real_s3",    "vod",   "1.03"),
]

for f, b in ((MOT, BMOT), (PIP, BPIP)):
    assert not os.path.exists(b), "hay otro barrido vivo: %s" % b
bmot = open(MOT, encoding="utf-8").read()
bpip = open(PIP, encoding="utf-8").read()
for txt, pat in ((bmot, A_IMP), (bmot, A_SEN), (bmot, A_NQ1), (bmot, A_NQ2), (bmot, A_TOPE),
                 (bmot, A_ANCHO), (bmot, A_ANCHO2), (bpip, P_IMP), (bpip, P_VIEJO)):
    assert txt.count(pat) == 1, "patron no unico: %r" % pat[:50]
shutil.copy2(MOT, BMOT)
shutil.copy2(PIP, BPIP)

tm = (bmot.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN).replace(A_NQ1, N_NQ1)
      .replace(A_NQ2, N_NQ2).replace(A_TOPE, N_TOPE).replace(A_ANCHO2, N_ANCHO2)
      .replace(A_ANCHO, N_ANCHO).replace("* 1.01", "* _SLIP"))
tp = bpip.replace(P_IMP, P_IMPN).replace(P_VIEJO, P_NUEVO)

try:
    for txt, ruta in ((tm, MOT), (tp, PIP)):
        compile(txt, ruta, "exec")          # validacion instantanea antes de gastar motor
    open(MOT, "w", encoding="utf-8").write(tm)
    open(PIP, "w", encoding="utf-8").write(tp)
    procs = []
    for nombre, rl, slip in VARIANTES:
        env = dict(os.environ, RL=rl, RL_SLIP=slip)
        dest = os.path.join(OUT, nombre + ".json")
        p = subprocess.Popen([sys.executable, HIJO, dest], cwd=RAIZ, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        procs.append((nombre, rl, slip, p))
        print("lanzado %-14s RL=%-6s slip=%s" % (nombre, rl or "(ninguno)", slip), flush=True)
    print("\n-- %d variantes en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    for nombre, rl, slip, p in procs:
        o, e = p.communicate(timeout=3000)
        r = (o or "").strip() or (e or "").strip()[-200:]
        print("%-14s %s" % (nombre, r[-110:]), flush=True)
    print("\ntiempo total: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BMOT, MOT); os.remove(BMOT)
    shutil.copy2(BPIP, PIP); os.remove(BPIP)
    print("[motor.py y pipeline.py RESTAURADOS]", flush=True)
