# TEST DE LA ENVOLVENTE: ¿aguanta el sistema si las opciones hubieran estado más caras o más
# baratas? Y sobre todo: ¿la COMPRESIÓN (k_d8) empeora o mejora esa robustez?
#
# El agente del motor original avisa de que es "donde la composición al 18% se rompía: al 2% de
# coste moría en 4 de 6 regímenes de precios". Es el test que le queda a la compresión.
#
# MÉTODO: se sustituye el precio real de cada opción por  max(intrínseco + pct * rango_día, 0.01)
# usando la superficie de percentiles construida con `envolvente.py` (celdas separadas por C/P).
import shutil, subprocess, sys, os, time

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".env.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_env.py")
OUT = os.path.join(AQUI, "Dh")
ENV = os.path.join(RAIZ, "investigacion", "2026-08-19_sistema_real", "resultados", "envolvente.json")

open(HIJO, "w", encoding="utf-8").write('''# -*- coding: utf-8 -*-
import json, sys, os, sqlite3
RAIZ = r"%s"
sys.path.insert(0, RAIZ)
from sys2.backtest import motor
from sys2.db import repo
from sys2.core.supertrend import mm

PCT = os.environ.get("RL_PCT", "")
E = json.load(open(r"%s"))
TAB, RANGOS = E["tabla"], E["rangos"]

def celda(mny, minutos):
    m = max(-10, min(10, int(round(mny))))
    t = min(6, int(minutos // 60))
    return (m, t)

con = repo.abrir()
SES, PREM, ETFB = motor.cargar(con)
# spot por (fecha,hora) para calcular intrinseco y moneyness
SP = {}
for f, h, cl in con.execute("select fecha,hora,close from bars where hora>=? and hora<=?",
                            ("09:30", "16:00")):
    SP[(f, h)] = cl
con.close()

if PCT:
    n_cambiadas = n_total = 0
    for fk, dias in PREM.items():
        rango = RANGOS.get(fk)
        if not rango:
            continue
        for hora, cad in dias.items():
            S = SP.get((fk, hora))
            if S is None:
                continue
            minutos = max(0, 960 - mm(hora))
            for (right, k), v in list(cad.items()):
                n_total += 1
                intr = max(0.0, (S - k) if right == "C" else (k - S))
                mny = (S - k) if right == "C" else (k - S)
                c = TAB.get("%%s|%%d|%%d" %% ((right,) + celda(mny, minutos)))
                if not c:
                    continue
                cad[(right, k)] = (max(intr + c[PCT] * rango, 0.01), v[1])
                n_cambiadas += 1
    print("precios sustituidos: %%d de %%d (%%.0f%%%%)" %% (n_cambiadas, n_total,
          100.0 * n_cambiadas / max(1, n_total)), file=sys.stderr)

D = motor.SIS70(SES, PREM, ETFB, capital=600)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
c = 600.0
s = c; pico = c; ddp = 0.0
for f in sorted(D):
    s += D[f]; pico = max(pico, s); ddp = min(ddp, (s - pico) / pico * 100)
print("OK saldo %%.0f  dd %%.1f%%%%" %% (s, ddp))
''' % (RAIZ, ENV))

A_IMP = "from sys2.core import pipeline"
N_IMP = """from sys2.core import pipeline
import os as _os
_COMPR = int(_os.environ.get("RL_COMPR", "0"))"""
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
N_SEN = A_SEN + '''
        _plano = {}
        if _COMPR:
            _pl = 0
            for _q in range(1, len(ks)):
                _pl = (_pl + 1) if abs(L[ks[_q]]['linea'] - L[ks[_q - 1]]['linea']) < 1e-9 else 0
                _plano[ks[_q]] = _pl'''
A_NQ = "'vert': True, 'nq': (nq if h >= C.DIABUENO_DESDE else 1)}"
N_NQ = ("'vert': True, 'nq': (min(nq * 2, _AC.TOPE_UNIDADES) if (_COMPR and "
        "_plano.get((mm(h) // 3) * 3 - 3, 0) >= _COMPR) else (nq if h >= C.DIABUENO_DESDE else 1))}")

# (nombre, percentil, compresion)
V = []
for pct in ("", "10", "25", "50", "75", "90"):
    for compr, et in (("0", "sin"), ("8", "d8")):
        V.append(("e_%s_%s" % (pct or "real", et), pct, compr))

assert not [x for x in os.listdir(os.path.dirname(MOT)) if x.endswith(".bak")], "otro barrido vivo"
base = open(MOT, encoding="utf-8").read()
for pat in (A_IMP, A_SEN, A_NQ):
    assert base.count(pat) == 1, "patron no unico: %r" % pat[:40]
shutil.copy2(MOT, BAK)
txt = base.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN).replace(A_NQ, N_NQ)
assert "_plano" in txt

try:
    compile(txt, MOT, "exec")
    open(MOT, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, pct, compr in V:
        env = dict(os.environ, RL_PCT=pct, RL_COMPR=compr)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, p))
        while sum(1 for _, q in procs if q.poll() is None) >= 6:
            time.sleep(2)
    print("-- %d corridas --\n" % len(procs), flush=True)
    for nombre, p in procs:
        o, e = p.communicate(timeout=3000)
        print("%-12s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-150:])[-100:]), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("[motor.py RESTAURADO]", flush=True)
