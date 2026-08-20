# LA ENVOLVENTE SOBRE EL SISTEMA INTEGRADO — ¿aguanta con opciones más caras o más baratas?
#
# El README ya tiene la envolvente para BASE y COMPRESIÓN. Falta la columna del INTEGRADO
# (compresión d8 + OTM desde las 14:00). Aquí se corren las TRES en los SEIS regímenes.
#
# MÉTODO (verbatim de `barrido_envolvente.py`): se sustituye el precio de cada opción por
#   max(intrínseco + pct * rango_del_día, 0.01)
# usando la superficie de percentiles de `envolvente.py` (294 celdas, 2.544.226 observaciones,
# CALLS Y PUTS SEPARADOS — mezclarlos le costó tres sesiones al agente del motor original).
# NO son datos nuevos: son las MISMAS 485 sesiones vistas con las opciones más caras/baratas.
#
# CONTROLES (§2.3) — tienen que replicar cifras ya publicadas o la tanda se descarta:
#   e_real_base 83.805$ · e_real_d8 97.631$ · e_real_int 92.179$ · e_25_base 56.310$
#   e_50_base 59.158$ · y p10/p75/p90 con base deben MORIR (el sistema base ya muere ahí).
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
INS = os.path.join(RAIZ, "sys2", "core", "instrumento.py")
BMOT, BINS = MOT + ".ei.bak", INS + ".ei.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_env.py")
OUT = os.path.join(AQUI, "Dh")
ENV = os.path.join(RAIZ, "investigacion", "2026-08-19_sistema_real", "resultados", "envolvente.json")
os.makedirs(OUT, exist_ok=True)

# hijo VERBATIM de barrido_envolvente.py (mismo archivo, no se duplica el artefacto)
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
    print("precios sustituidos: %%d de %%d" %% (n_cambiadas, n_total), file=sys.stderr)

D = motor.SIS70(SES, PREM, ETFB, capital=600)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
s = 600.0
for f in sorted(D):
    s += D[f]
print("OK saldo %%.0f" %% s)
''' % (RAIZ, ENV))

# ── parche 1: COMPRESIÓN (motor.py) ────────────────────────────────────────────────
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

# ── parche 2: FRONTERA HORARIA (instrumento.py) ────────────────────────────────────
A_DEF = 'def elegir_vert(cands, S, h, rt, tope, ancho):'
N_DEF = ('import os as _os\n'
         '_TR = [t.split(":", 2) for t in _os.environ.get("RL_TRAMOS", "").split(";") if t]\n'
         '_TRAMOS = sorted([("%s:%s" % (a, b), float(c)) for a, b, c in _TR], reverse=True)\n'
         '\n\n'
         'def _lim_h(h):\n'
         '    for hh, mx in _TRAMOS:\n'
         '        if h >= hh:\n'
         '            return mx\n'
         '    return None\n'
         '\n\n'
         'def elegir_vert(cands, S, h, rt, tope, ancho):')
A_MNY = ("        mny = (S - kl) if rt == 'C' else (kl - S)\n"
         "        if mny < 0.5:\n"
         "            continue")
N_MNY = ("        mny = (S - kl) if rt == 'C' else (kl - S)\n"
         "        _mx = _lim_h(h)\n"
         "        if _mx is None:\n"
         "            if mny < 0.5:\n"
         "                continue\n"
         "        else:\n"
         "            if mny > _mx or mny < min(0.5, _mx - 2.0):\n"
         "                continue")

OTM14 = "14:00:-1.0"
CFG = [("base", "0", ""), ("d8", "8", ""), ("int", "8", OTM14)]
PCTS = ["", "10", "25", "50", "75", "90"]
V = [("e_%s_%s" % (p or "real", et), p, cp, tr) for p in PCTS for et, cp, tr in CFG]
ESPERADO = {"e_real_base": 83805, "e_real_d8": 97631, "e_real_int": 92179,
            "e_25_base": 56310, "e_50_base": 59158}

for d in (os.path.dirname(MOT), os.path.dirname(INS)):
    assert not [x for x in os.listdir(d) if x.endswith(".bak")], "otro barrido vivo en %s" % d
bmot, bins = open(MOT, encoding="utf-8").read(), open(INS, encoding="utf-8").read()
for t_, pat in ((bmot, A_IMP), (bmot, A_SEN), (bmot, A_NQ), (bins, A_DEF), (bins, A_MNY)):
    assert t_.count(pat) == 1, "patrón no único: %r" % pat[:45]
tm = bmot.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN).replace(A_NQ, N_NQ)
ti = bins.replace(A_DEF, N_DEF).replace(A_MNY, N_MNY)
assert tm.count("_plano[ks[_q]] = _pl") == 1, "compresión NO aplicada"
assert ti.count("def _lim_h(h):") == 1, "horario NO aplicado"
compile(tm, MOT, "exec")
compile(ti, INS, "exec")

shutil.copy2(MOT, BMOT)
shutil.copy2(INS, BINS)
try:
    open(MOT, "w", encoding="utf-8").write(tm)
    open(INS, "w", encoding="utf-8").write(ti)
    procs = []
    for nombre, pct, compr, tramos in V:
        env = dict(os.environ, RL_PCT=pct, RL_COMPR=compr, RL_TRAMOS=tramos)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, p))
        print("lanzado %-14s pct=%-4s compr=%-2s tramos=%s"
              % (nombre, pct or "REAL", compr, tramos or "-"), flush=True)
        while sum(1 for _, q in procs if q.poll() is None) >= 6:   # tope de paralelismo
            time.sleep(2)
    print("\n-- %d corridas --\n" % len(procs), flush=True)
    t0 = time.time()
    for nombre, p in procs:
        o, e = p.communicate(timeout=4000)
        print("%-14s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-160:])[-90:]),
              flush=True)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BMOT, MOT)
    os.remove(BMOT)
    shutil.copy2(BINS, INS)
    os.remove(BINS)
    print("[motor.py e instrumento.py RESTAURADOS]", flush=True)


def met(D):
    s = 600.0
    pico = s
    dd = 0.0
    racha = rmax = v = r = 0
    curva = []
    for k in sorted(D):
        g = D[k]
        s += g
        curva.append(s)
        pico = max(pico, s)
        dd = max(dd, (pico - s) / pico)
        if g > 0:
            v += 1
        elif g < 0:
            r += 1
        racha = (racha + 1) if g < 0 else 0
        rmax = max(rmax, racha)
    return s, 100 * dd, rmax, v, r, min(curva)


print("\n" + "=" * 96)
print("ENVOLVENTE x CONFIGURACIÓN — saldo final (drawdown / racha / verdes-rojos / mínimo)")
print("=" * 96)
print("%-12s %26s %26s %26s" % ("régimen", "BASE", "+ COMPRESIÓN d8", "INTEGRADO"))
malo = []
for p in PCTS:
    fila = "%-12s" % (("precios reales" if not p else "p%s" % p))
    for et, _, _ in CFG:
        n = "e_%s_%s" % (p or "real", et)
        f = os.path.join(OUT, n + ".json")
        if not os.path.exists(f):
            fila += "%26s" % "-"
            continue
        s, dd, ra, v, r, mn = met(json.load(open(f)))
        if n in ESPERADO and abs(s - ESPERADO[n]) > 1:
            malo.append("%s: %.0f (esperado %d)" % (n, s, ESPERADO[n]))
        fila += "%12.0f$ %5.0f%% r%d %2d/%-3d" % (s, dd, ra, v, r) if s > 1000 else \
                "%12.0f$ %13s" % (s, "MUERE")
    print(fila, flush=True)
if malo:
    print("\n⚠️ CONTROLES DESVIADOS — NO usar estas cifras:")
    for x in malo:
        print("   " + x)
else:
    print("\n✓ todos los controles replican las cifras publicadas")
