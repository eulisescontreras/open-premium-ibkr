# ¿CUÁNTO CUESTA OBLIGAR AL SISTEMA A COMPRAR DONDE SÍ HAY CONTRAPARTIDA?  (pendiente 🔴 #2)
#
# MEDIDO EN VIVO (255+ órdenes reales, `fills_reales.db`): el fill depende del moneyness de la
# pata larga y cae a CERO en el ITM profundo, que es justo donde compra el sistema.
#     mny   -5    -3    -1    +0    +1    +2    +3    +5   +10   +20
#     fill  22%   35%   59%   87%   67%   59%   39%   23%    0%    0%   (0 de 41 en +10/+20)
#
# `elegir_vert` (instrumento.py:21-24) ordena por moneyness DESCENDENTE y devuelve el PRIMERO
# cuyo débito quepa en el tope: es decir, compra deliberadamente el ITM MÁS PROFUNDO posible.
# Con la cuenta grande el tope sube, cabe el ITM profundo, y el sistema se mueve SOLO hacia la
# zona sin contrapartida. El backtest no lo ve porque asume que todo lo de la cadena es comprable.
#
# AQUÍ se mide el coste en DINERO de acotar el moneyness por ARRIBA (RL_MNYMAX), o sea de
# comprar más cerca de ATM. NO mide fills (el backtest llena siempre): mide qué le pasa al P&L
# cuando se le quita al sistema el contrato que hoy elige y no puede ejecutar.
#
# ⚠️ NO ES UN CAMBIO NEUTRO DE TAMAÑO: acotar el moneyness BAJA el débito (mny+2 a4 ≈ 240$ vs
# mny+10 ≈ 390$, medido hoy en la cadena real), así que reduce el riesgo por operación. Si sale
# positivo hay que descartar después que sea solo "arriesgar menos" (control: bajar el tope la
# misma proporción SIN tocar el moneyness).
#
# CONTROL OBLIGATORIO (§2.3): `x_base` (RL_MNYMAX=0 = sin restricción) DEBE dar 83.805$ exacto.
# Si se desvía, el parche está mal y la tanda entera se descarta.
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
INS = os.path.join(RAIZ, "sys2", "core", "instrumento.py")
BAK = INS + ".mny.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

# hijo: motor con composición (capital=600). RL_HASTA permite la prueba de humo con pocos días.
open(HIJO, "w", encoding="utf-8").write('''import json, sys, os
sys.path.insert(0, r"%s")
from sys2.backtest import motor
from sys2.db import repo
con = repo.abrir(); SES, PREM, ETFB = motor.cargar(con); con.close()
_h = os.environ.get("RL_HASTA") or None
D = motor.SIS70(SES, PREM, ETFB, capital=600, hasta=_h)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
s = 600.0
for f in sorted(D):
    s += D[f]
print("OK %%d dias  saldo %%.0f" %% (len(D), s))
''' % RAIZ)

A_DEF = 'def elegir_vert(cands, S, h, rt, tope, ancho):'
N_DEF = ('import os as _os\n'
         '_MNYMAX = float(_os.environ.get("RL_MNYMAX", "0"))   # 0 = sin restricción (control)\n'
         '\n\n'
         'def elegir_vert(cands, S, h, rt, tope, ancho):')
A_MNY = ("        mny = (S - kl) if rt == 'C' else (kl - S)\n"
         "        if mny < 0.5:\n"
         "            continue")
N_MNY = ("        mny = (S - kl) if rt == 'C' else (kl - S)\n"
         "        if mny < 0.5:\n"
         "            continue\n"
         "        if _MNYMAX and mny > _MNYMAX:\n"
         "            continue          # no comprar más ITM de lo que el mercado puede llenar")

# (nombre, RL_MNYMAX)
V = [("x_base", "0"),      # CONTROL: sin restricción -> tiene que dar 83.805$
     ("x_m15", "1.5"),     # lo más cerca de ATM que permite el mny>=0.5 del sistema
     ("x_m2", "2.0"),      # zona de fill 59-87%
     ("x_m3", "3.0"),
     ("x_m4", "4.0"),
     ("x_m6", "6.0")]      # control de curva: si es monótono, es tamaño, no elección

HUMO = os.environ.get("HUMO", "")     # p.ej. HUMO=2026-04-01 -> corre solo hasta esa fecha

assert not [x for x in os.listdir(os.path.dirname(INS)) if x.endswith(".bak")], "otro barrido vivo"
assert not [x for x in os.listdir(os.path.join(RAIZ, "sys2", "backtest")) if x.endswith(".bak")], \
    "otro barrido vivo (backtest)"
base = open(INS, encoding="utf-8").read()
for pat in (A_DEF, A_MNY):
    assert base.count(pat) == 1, "patrón no único: %r" % pat[:50]
# el parche se construye y se VALIDA antes de tocar nada: si el assert salta después de copiar
# el .bak, queda un .bak huérfano que bloquea el siguiente barrido (pasó en la 1ª ejecución).
txt = base.replace(A_DEF, N_DEF).replace(A_MNY, N_MNY)
# assert sobre el patrón EXACTO, no sobre el conteo del nombre: "RL_MNYMAX" contiene "_MNYMAX"
# como subcadena y hace que el conteo mienta (falló así en la 2ª ejecución).
assert txt.count("if _MNYMAX and mny > _MNYMAX:") == 1, "parche NO aplicado"
assert txt.count('_MNYMAX = float(_os.environ.get("RL_MNYMAX"') == 1, "declaración NO aplicada"
compile(txt, INS, "exec")

shutil.copy2(INS, BAK)
try:
    open(INS, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, mnymax in V:
        env = dict(os.environ, RL_MNYMAX=mnymax)
        if HUMO:
            env["RL_HASTA"] = HUMO
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, mnymax, p))
        print("lanzado %-8s mny_max=%s" % (nombre, mnymax if mnymax != "0" else "SIN RESTRICCIÓN"),
              flush=True)
    print("\n-- %d en paralelo%s --\n" % (len(procs), (" [HUMO hasta %s]" % HUMO) if HUMO else ""),
          flush=True)
    t0 = time.time()
    res = {}
    for nombre, mnymax, p in procs:
        o, e = p.communicate(timeout=3000)
        sal = (o or "").strip() or (e or "").strip()[-200:]
        print("%-8s mny<=%-4s %s" % (nombre, mnymax, sal[-110:]), flush=True)
        f = os.path.join(OUT, nombre + ".json")
        if os.path.exists(f):
            D = json.load(open(f))
            res[nombre] = 600.0 + sum(D.values())
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
    if "x_base" in res:
        print("\nCONTROL x_base = %.0f$ (esperado 83.805$ sin HUMO)" % res["x_base"], flush=True)
        for n, s in res.items():
            if n != "x_base":
                print("  %-8s %9.0f$   %+8.0f$ vs control" % (n, s, s - res["x_base"]), flush=True)
finally:
    shutil.copy2(BAK, INS)
    os.remove(BAK)
    print("[instrumento.py RESTAURADO]", flush=True)
