# COMPRESIÓN -> EXPANSIÓN en el MOTOR (idea del usuario, 2026-08-20).
#
# HALLAZGO (56.156 buckets de 485 sesiones, `test_tiempo_muerto.py`): cuando la línea del ST-3
# lleva MUCHOS buckets sin moverse, el movimiento posterior es MAYOR y MÁS EFICIENTE:
#     plana >= 6   recorrido -3,0%   (tramos cortos = tiempo muerto, como intuía el usuario)
#     plana >= 16  recorrido +2,2%
#     plana >= 21  recorrido +4,1%  eficiencia +4,0%
#     plana >= 26  recorrido +7,4%  eficiencia +6,8%
# Consistente en los dos años (plana 21-30: A1 4,063 / A2 4,044).
# ⚠️ SE USA EL BUCKET ANTERIOR (-3): el bucket de la hora de la señal EMPIEZA en h y no
# cierra hasta 2 min después — su línea usaría un cierre que aún no existe (look-ahead
# de 2 minutos, el mismo tipo de error que costó el 43% ayer).
#
# AQUÍ se mide en DINERO: ¿sirve como criterio para DOBLAR unidades (donde hoy manda `dia_bueno`)
# o para FILTRAR entradas en tramos planos cortos?
#
# ⚠️ Este barrido parchea el motor ACTUAL (con los cambios del 2026-08-19 ya aplicados).
import shutil, subprocess, sys, os, time

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".bim.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

# hijo que corre el motor con capital (composición)
open(HIJO, "w", encoding="utf-8").write('''import json, sys
sys.path.insert(0, r"%s")
from sys2.backtest import motor
from sys2.db import repo
con = repo.abrir(); SES, PREM, ETFB = motor.cargar(con); con.close()
import os as _o
D = motor.SIS70(SES, PREM, ETFB, capital=600, desde=(_o.environ.get("RL_DESDE") or None))
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
c=600.0; s=c
for f in sorted(D): s += D[f]
print("OK %%d dias  saldo %%.0f" %% (len(D), s))
''' % RAIZ)

A_IMP = "from sys2.core import pipeline"
N_IMP = """from sys2.core import pipeline
import os as _os
_COMPR = int(_os.environ.get("RL_COMPR", "0"))        # doblar si la línea lleva >= N buckets plana
_CMODO = _os.environ.get("RL_CMODO", "dobla")         # dobla | filtra"""

# calcular la planitud de la línea (solo pasado) justo tras construir las señales
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
N_SEN = A_SEN + '''
        _plano = {}
        if _COMPR:
            _pl = 0
            for _q in range(1, len(ks)):
                _pl = (_pl + 1) if abs(L[ks[_q]]['linea'] - L[ks[_q - 1]]['linea']) < 1e-9 else 0
                _plano[ks[_q]] = _pl
            if _CMODO == "filtra":     # NO entrar en tramos planos CORTOS (6-15 buckets)
                Sen = {k: v for k, v in Sen.items()
                       if not (6 <= _plano.get((mm(k) // 3) * 3 - 3, 0) < 16)}'''

# doblar unidades cuando hay compresión larga
A_NQ = "'vert': True, 'nq': (nq if h >= C.DIABUENO_DESDE else 1)}"
N_NQ = ("'vert': True, 'nq': (min(nq * 2, _AC.TOPE_UNIDADES) if (_COMPR and _CMODO == 'dobla' "
        "and _plano.get((mm(h) // 3) * 3 - 3, 0) >= _COMPR) else (nq if h >= C.DIABUENO_DESDE else 1))}")

# (nombre, RL_COMPR, RL_CMODO)
V = [
    ("b_sin_240815", "0", "dobla", "2024-08-15"),
    ("b_d8_240815",  "8", "dobla", "2024-08-15"),
    ("b_sin_241216", "0", "dobla", "2024-12-16"),
    ("b_d8_241216",  "8", "dobla", "2024-12-16"),
    ("b_sin_250218", "0", "dobla", "2025-02-18"),
    ("b_d8_250218",  "8", "dobla", "2025-02-18"),
    ("b_sin_250415", "0", "dobla", "2025-04-15"),
    ("b_d8_250415",  "8", "dobla", "2025-04-15"),
    ("b_sin_250616", "0", "dobla", "2025-06-16"),
    ("b_d8_250616",  "8", "dobla", "2025-06-16"),
    ("b_sin_250815", "0", "dobla", "2025-08-15"),
    ("b_d8_250815",  "8", "dobla", "2025-08-15"),
    ("b_sin_251015", "0", "dobla", "2025-10-15"),
    ("b_d8_251015",  "8", "dobla", "2025-10-15"),
    ("b_sin_260217", "0", "dobla", "2026-02-17"),
    ("b_d8_260217",  "8", "dobla", "2026-02-17")]

assert not [x for x in os.listdir(os.path.dirname(MOT)) if x.endswith(".bak")], "otro barrido vivo"
base = open(MOT, encoding="utf-8").read()
for pat in (A_IMP, A_SEN, A_NQ):
    assert base.count(pat) == 1, "patrón no único: %r" % pat[:50]
shutil.copy2(MOT, BAK)

txt = base.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN).replace(A_NQ, N_NQ)
assert "_plano" in txt and txt.count("_COMPR") >= 3, "parche NO aplicado"
try:
    compile(txt, MOT, "exec")
    open(MOT, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, compr, cmodo, desde in V:
        env = dict(os.environ, RL_COMPR=compr, RL_CMODO=cmodo, RL_DESDE=desde)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, compr, cmodo, p))
        while sum(1 for _,_,_,q in procs if q.poll() is None) >= 8:
            time.sleep(2)
        print("lanzado %-14s compr=%s desde %s" % (nombre, compr, desde), flush=True)
    print("\n-- %d en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    for nombre, compr, cmodo, p in procs:
        o, e = p.communicate(timeout=3000)
        print("%-10s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-200:])[-110:]), flush=True)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("[motor.py RESTAURADO]", flush=True)
