# SISTEMA INTEGRADO: COMPRESIÓN (ST-3) + FRONTERA HORARIA DE MONEYNESS (IBKR).
#
# Pregunta del usuario: con las dos cosas metidas a la vez, ¿cuáles son los números REALES?
# NO se puede estimar sumando +13.826 y -4.410: con composición el saldo de cada día fija el
# tamaño del siguiente, así que los efectos NO son aditivos. Hay que correrlo.
#
# LAS DOS REGLAS
#  (1) COMPRESIÓN d8 — doblar unidades cuando la línea del ST-3 lleva >=8 buckets plana.
#      Medido: 97.631$ (+13.826). Sin look-ahead (auditado en el README: compara buckets ambos
#      cerrados y consulta el ANTERIOR con -3). Parche VERBATIM de `barrido_compresion.py`.
#  (2) FRONTERA HORARIA — desde las 14:00 solo OTM. Sale del mapa hora x moneyness medido HOY
#      con 547 órdenes reales contra IBKR (antes de las 12:00 no rechaza nada; desde las 14:00
#      la frontera baja hasta ATM; el OTM <=-2 no se rechaza NUNCA).
#      Medido en solitario: 79.394$ (-4.410). Parche VERBATIM de `barrido_mny_horario.py`.
#
# ⚠️ EL CORTE DE LAS 14:00 NO SALE DEL BACKTEST, sale del sondeo de IBKR de hoy — es un parámetro
# externo posterior al periodo medido. No es look-ahead (ningún dato futuro entra en la decisión
# de cada operación) pero tampoco es un umbral aprendido en el AÑO 1: es una restricción de la
# plataforma. Se declara porque las 14:00 resultan ser TAMBIÉN el mejor corte en P&L, y esa
# coincidencia hay que mirarla con desconfianza, no celebrarla.
#
# CONTROLES DENTRO DE LA TANDA (§2.3): `c_base` tiene que dar 83.805$, `c_comp` 97.631$ y
# `c_hora` 79.394$. Si alguno se desvía, los parches interfieren y la tanda entera se descarta.
#
# MÉTRICAS: el calculador está VALIDADO contra la base publicada (83.805$, dd -21,1%, racha 3,
# 308 verdes / 156 rojos, mejor +2.368,85, peor -1.411,56, mínimo 600$). La racha usa la
# definición del MOTOR (`_racha = _racha+1 if tot < 0 else 0`): un día sin operar RESETEA.
# Con la definición ingenua (reset solo si tot>0) la base daría 5, no 3.
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
INS = os.path.join(RAIZ, "sys2", "core", "instrumento.py")
BMOT, BINS = MOT + ".int.bak", INS + ".int.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

# ── (1) COMPRESIÓN — verbatim de barrido_compresion.py ──────────────────────────────
A_IMP = "from sys2.core import pipeline"
N_IMP = """from sys2.core import pipeline
import os as _os
_COMPR = int(_os.environ.get("RL_COMPR", "0"))
_CMODO = _os.environ.get("RL_CMODO", "dobla")"""
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
N_SEN = A_SEN + '''
        _plano = {}
        if _COMPR:
            _pl = 0
            for _q in range(1, len(ks)):
                _pl = (_pl + 1) if abs(L[ks[_q]]['linea'] - L[ks[_q - 1]]['linea']) < 1e-9 else 0
                _plano[ks[_q]] = _pl
            if _CMODO == "filtra":
                Sen = {k: v for k, v in Sen.items()
                       if not (6 <= _plano.get((mm(k) // 3) * 3 - 3, 0) < 16)}'''
A_NQ = "'vert': True, 'nq': (nq if h >= C.DIABUENO_DESDE else 1)}"
N_NQ = ("'vert': True, 'nq': (min(nq * 2, _AC.TOPE_UNIDADES) if (_COMPR and _CMODO == 'dobla' "
        "and _plano.get((mm(h) // 3) * 3 - 3, 0) >= _COMPR) else (nq if h >= C.DIABUENO_DESDE else 1))}")

# ── (2) FRONTERA HORARIA — verbatim de barrido_mny_horario.py ───────────────────────
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
# (nombre, RL_COMPR, RL_TRAMOS, esperado_si_replicacion)
V = [("c_base", "0", "", 83805),
     ("c_comp", "8", "", 97631),
     ("c_hora", "0", OTM14, 79394),
     ("c_ambas", "8", OTM14, None)]

for d in (os.path.dirname(MOT), os.path.dirname(INS)):
    assert not [x for x in os.listdir(d) if x.endswith(".bak")], "otro barrido vivo en %s" % d
bmot, bins = open(MOT, encoding="utf-8").read(), open(INS, encoding="utf-8").read()
for txt_, pat in ((bmot, A_IMP), (bmot, A_SEN), (bmot, A_NQ), (bins, A_DEF), (bins, A_MNY)):
    assert txt_.count(pat) == 1, "patrón no único: %r" % pat[:50]

tm = bmot.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN).replace(A_NQ, N_NQ)
ti = bins.replace(A_DEF, N_DEF).replace(A_MNY, N_MNY)
assert tm.count("_plano[ks[_q]] = _pl") == 1 and tm.count("_COMPR and _CMODO == 'dobla'") == 1, \
    "parche de compresión NO aplicado"
assert ti.count("def _lim_h(h):") == 1 and ti.count("if mny > _mx or mny < min(0.5, _mx - 2.0):") == 1, \
    "parche horario NO aplicado"
compile(tm, MOT, "exec")
compile(ti, INS, "exec")

shutil.copy2(MOT, BMOT)
shutil.copy2(INS, BINS)
try:
    open(MOT, "w", encoding="utf-8").write(tm)
    open(INS, "w", encoding="utf-8").write(ti)
    procs = []
    for nombre, compr, tramos, esp in V:
        env = dict(os.environ, RL_COMPR=compr, RL_CMODO="dobla", RL_TRAMOS=tramos)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, esp, p))
        print("lanzado %-8s compresion=%-2s tramos=%s" % (nombre, compr, tramos or "-"), flush=True)
    print("\n-- %d en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    R = {}
    for nombre, esp, p in procs:
        o, e = p.communicate(timeout=3000)
        print("%-8s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-200:])[-110:]),
              flush=True)
        f = os.path.join(OUT, nombre + ".json")
        if os.path.exists(f):
            R[nombre] = (json.load(open(f)), esp)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BMOT, MOT)
    os.remove(BMOT)
    shutil.copy2(BINS, INS)
    os.remove(BINS)
    print("[motor.py e instrumento.py RESTAURADOS]", flush=True)


def metricas(D):
    """Calculador VALIDADO contra la base publicada. Racha = definición del motor."""
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
        racha = (racha + 1) if g < 0 else 0     # un día a 0 RESETEA (motor.py)
        rmax = max(rmax, racha)
    a1 = [D[k] for k in sorted(D)[:len(D) // 2]]
    a2 = [D[k] for k in sorted(D)[len(D) // 2:]]
    return dict(saldo=s, x=s / 600.0, dd=100 * dd, racha=rmax, v=v, r=r,
                op=sum(1 for g in D.values() if abs(g) >= 1e-9),
                mejor=max(D.values()), peor=min(D.values()), minimo=min(curva),
                a1=sum(a1), a2=sum(a2))


print("\n" + "=" * 100)
print("RESULTADO INTEGRADO — 485 sesiones, capital 600$, sin look-ahead")
print("=" * 100)
print("%-9s %10s %7s %8s %6s %6s %6s %9s %10s %10s %9s"
      % ("variante", "saldo", "mult", "drawdn", "racha", "verde", "rojo", "peor día",
         "AÑO 1", "AÑO 2", "mín"))
ok = True
for nombre, (D, esp) in R.items():
    m = metricas(D)
    marca = ""
    if esp is not None:
        if abs(m['saldo'] - esp) > 1:
            marca = "  <-- ⚠️ CONTROL DESVIADO (esperado %d) — TANDA SOSPECHOSA" % esp
            ok = False
        else:
            marca = "  ✓ replica"
    print("%-9s %9.0f$ %6.1fx %7.1f%% %6d %6d %6d %+9.0f %+10.0f %+10.0f %8.0f%s"
          % (nombre, m['saldo'], m['x'], m['dd'], m['racha'], m['v'], m['r'],
             m['peor'], m['a1'], m['a2'], m['minimo'], marca))
if "c_base" in R and "c_ambas" in R:
    b = metricas(R["c_base"][0])
    a = metricas(R["c_ambas"][0])
    print("\nINTEGRADO vs BASE:  %+.0f$ (%+.1f%%)   drawdown %.1f%% -> %.1f%%   racha %d -> %d"
          % (a['saldo'] - b['saldo'], 100.0 * (a['saldo'] - b['saldo']) / b['saldo'],
             b['dd'], a['dd'], b['racha'], a['racha']))
    if "c_comp" in R and "c_hora" in R:
        c, h = metricas(R["c_comp"][0]), metricas(R["c_hora"][0])
        sum_ = c['saldo'] + h['saldo'] - 2 * b['saldo']
        print("¿ADITIVO?  suma de efectos por separado %+.0f$  vs  integrado real %+.0f$  "
              "(diferencia %+.0f$)" % (sum_, a['saldo'] - b['saldo'], a['saldo'] - b['saldo'] - sum_))
if not ok:
    print("\n⚠️ ALGÚN CONTROL SE DESVIÓ: los parches interfieren. NO usar estas cifras.")
