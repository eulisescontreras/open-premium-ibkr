# EL SISTEMA CONTRA LA REALIDAD MEDIDA — las dos únicas correcciones que se sostienen.
#
# QUÉ SE DESCARTA Y POR QUÉ (para no volver a proponerlo):
# La regla "OTM desde las 14:00" (-4.410$ en backtest) NO se integra. Su premisa es falsa:
# el backtest la simula con ejecución perfecta, pero el sondeo de 587 órdenes reales dice que
#   - los OTM profundos (mny -2/-3/-5) tienen débitos de 2-14$ y NO LLEGAN al mínimo de 20$
#     del sistema: son contratos que `elegir_vert` jamás compraría (0 de 68 en mny -5).
#   - el único OTM operable (mny -1) llena el 59% contra el 84% del ATM.
# Es una tenaza: donde hay contrapartida IBKR rechaza, y donde IBKR deja no hay contrapartida.
# Ningún moneyness es bueno por la tarde -> el arreglo no está en QUÉ comprar.
#
# LO QUE SÍ SE MIDE AQUÍ:
#
# (c1) NO ABRIR a partir de cierta hora. Si por la tarde el sistema no puede ejecutar, la
#      pregunta honesta no es "¿qué compra en su lugar?" sino "¿cuánto vale abstenerse?".
#      Cruce con el backtest: el 49,7% de las operaciones son a las 09:xx y solo el 17,5% a
#      partir de las 13:00, así que el corte puede salir barato.
#
# (c2) COSTE DE SALIDA REAL. El motor ya modela la ENTRADA (`'ask': (pl_-psh)*1.01`, un 1%) y el
#      slippage de compra medido es +0,80%: bien calibrado. Lo que NO modela es la salida.
#      Medido hoy sobre 132 operaciones completas, por débito (la zona del sistema es 150-350$):
#           20-80$ -1,15%  ·  80-150$ -1,93%  ·  150-250$ -2,62%  ·  250-999$ -5,38%
#      (el -6,15% global está inflado por OTM baratos que el sistema no compra: NO usar ese.)
#      Y el dato duro: **132 de 132 ventas se forzaron a mercado**. Ninguna llenó al límite.
#
# CONTROL (§2.3): `r_base` tiene que dar 83.805$ exacto.
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".rl.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import pipeline"
N_IMP = """from sys2.core import pipeline
import os as _os
_NOABRE = _os.environ.get("RL_NOABRE", "")        # no abrir a partir de esta hora
_SLIPV = float(_os.environ.get("RL_SLIPV", "0"))  # coste de SALIDA (fracción del mid al cerrar)
_COMPR = int(_os.environ.get("RL_COMPR", "0"))    # compresión d8 (para el combinado)"""

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

# (c1) no abrir desde cierta hora — se añade a la condición de apertura (motor.py:280)
A_ABRE = "            if (pos is None and h in Sen and hechas < C.MAX_TRADES and h < C.ABRIR_HASTA"
N_ABRE = ("            if (pos is None and h in Sen and hechas < C.MAX_TRADES and h < C.ABRIR_HASTA\n"
          "                    and (not _NOABRE or h < _NOABRE)")

# (c2) coste de SALIDA: el mid cobrado al cerrar se reduce. El cierre es motor.py:252.
A_CIERRE = "                    g = ((pos['mid'] - pos['ask']) * 100 - C.COMISION) * pos.get('nq', 1)"
N_CIERRE = ("                    g = ((pos['mid'] * (1.0 - _SLIPV) - pos['ask']) * 100 "
            "- C.COMISION) * pos.get('nq', 1)")

# (nombre, RL_NOABRE, RL_SLIPV, RL_COMPR, esperado)
V = [("r_base", "", "0", "0", 83805),          # CONTROL
     ("r_no14", "14:00", "0", "0", None),      # (c1) no abrir desde las 14:00
     ("r_no13", "13:00", "0", "0", None),
     ("r_no15", "15:00", "0", "0", None),
     ("r_sal26", "", "0.026", "0", None),      # (c2) coste de salida medido (150-250$)
     ("r_sal54", "", "0.054", "0", None),      # (c2) peor caso medido (250$+)
     ("r_real", "", "0.026", "0", None),       # se recalcula abajo: realidad sin compresión
     ("r_real_d8", "", "0.026", "8", None)]    # realidad + compresión
V = [v for v in V if v[0] != "r_real"]         # r_real == r_sal26, no se duplica la corrida

assert not [x for x in os.listdir(os.path.dirname(MOT)) if x.endswith(".bak")], "otro barrido vivo"
base = open(MOT, encoding="utf-8").read()
for pat in (A_IMP, A_SEN, A_NQ, A_ABRE, A_CIERRE):
    assert base.count(pat) == 1, "patrón no único: %r" % pat[:55]
txt = (base.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN).replace(A_NQ, N_NQ)
       .replace(A_ABRE, N_ABRE).replace(A_CIERRE, N_CIERRE))
assert txt.count("not _NOABRE or h < _NOABRE") == 1, "corte horario NO aplicado"
assert txt.count("pos['mid'] * (1.0 - _SLIPV)") == 1, "coste de salida NO aplicado"
compile(txt, MOT, "exec")

shutil.copy2(MOT, BAK)
try:
    open(MOT, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, noabre, slipv, compr, esp in V:
        env = dict(os.environ, RL_NOABRE=noabre, RL_SLIPV=slipv, RL_COMPR=compr)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, esp, p))
        print("lanzado %-10s no_abrir=%-6s salida=%-6s compr=%s"
              % (nombre, noabre or "-", slipv, compr), flush=True)
    print("\n-- %d en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    R = {}
    for nombre, esp, p in procs:
        o, e = p.communicate(timeout=3000)
        print("%-10s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-200:])[-100:]),
              flush=True)
        f = os.path.join(OUT, nombre + ".json")
        if os.path.exists(f):
            R[nombre] = (json.load(open(f)), esp)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("[motor.py RESTAURADO]", flush=True)


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
    f = sorted(D)
    co = f[len(f) // 2]
    return (s, 100 * dd, rmax, v, r, min(curva),
            sum(D[k] for k in f if k < co), sum(D[k] for k in f if k >= co))


NOM = {"r_base": "BASE (fantasía)", "r_no14": "no abrir desde 14h",
       "r_no13": "no abrir desde 13h", "r_no15": "no abrir desde 15h",
       "r_sal26": "coste salida 2,6%", "r_sal54": "coste salida 5,4%",
       "r_real_d8": "salida 2,6% + compresión"}
print("\n" + "=" * 104)
print("EL SISTEMA CONTRA LA REALIDAD MEDIDA — 485 sesiones, capital 600$")
print("=" * 104)
print("%-26s %10s %7s %8s %6s %6s %6s %9s %10s %10s"
      % ("", "saldo", "mult", "drawdn", "racha", "verde", "rojo", "mínimo", "AÑO 1", "AÑO 2"))
malo = []
for n in ("r_base", "r_no13", "r_no14", "r_no15", "r_sal26", "r_sal54", "r_real_d8"):
    if n not in R:
        continue
    D, esp = R[n]
    s, dd, ra, v, r, mn, a1, a2 = met(D)
    if esp is not None and abs(s - esp) > 1:
        malo.append("%s: %.0f (esperado %d)" % (n, s, esp))
    print("%-26s %9.0f$ %6.1fx %7.1f%% %6d %6d %6d %8.0f$ %+10.0f %+10.0f"
          % (NOM[n], s, s / 600.0, dd, ra, v, r, mn, a1, a2), flush=True)
if malo:
    print("\nCONTROL DESVIADO — NO usar estas cifras: " + " | ".join(malo))
