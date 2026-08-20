# SALIR CUANDO LA LÍNEA SE APLANA — idea del usuario (2026-08-20, 3ª formulación, tras 2 fotos).
#
# LO QUE DICE EL USUARIO: "cuando el precio va en contra o se mantiene en un rango, el ST-3 se
# mantiene plano; cuando el precio va a favor del ST-3, NO se mantiene plano. Eso nos puede ayudar
# a saber si la tendencia va bien, si aún estamos en tendencia o tenemos que SALIR para no
# comernos la lateralidad que no mueve el contrato, o porque el precio se va a regresar".
#
# POR QUÉ ESTO NO ES LO YA REFUTADO. `test_ruptura.py` midió la planitud como PREDICTOR
# DIRECCIONAL ("tras X, el precio irá hacia Y") y no hay nada: la distribución de movimientos
# grandes es idéntica en todos los grupos (32,7%/30,1% en la base, 32,1%/30,8% con la línea
# activa). Aquí se usa como ESTADO PRESENTE: "línea plana" ≡ "el precio NO está haciendo extremos
# a favor del ST", que es MECÁNICAMENTE CIERTO por construcción (rebote.py:68-69, la línea solo
# se actualiza con extremo nuevo). No predice: describe. Y para gestionar una posición ABIERTA,
# el presente es lo que hace falta.
# Argumento económico: en 0DTE la lateralidad NO es neutra, cuesta theta.
#
# HUECO REAL: en `PROMPT_CONTINUAR.md` §6 están medidas y descartadas las salidas por stop, por
# % del débito, por tiempo máximo, por % del ancho y el trailing. SALIDA POR PLANITUD DE LA LÍNEA
# NO APARECE. Está sin medir.
#
# ⚠️ CONTROL PENDIENTE SI SALE POSITIVO: salir antes reduce exposición, y eso solo puede parecer
# bueno. Igual que "doblar" hay que compararlo contra "doblar siempre" y "doblar al azar la misma
# proporción", esto hay que compararlo contra SALIR AL AZAR LA MISMA PROPORCIÓN DE VECES.
# Este barrido NO lo incluye: primero se mide si hay efecto, y solo entonces se monta el control.
#
# ⚠️ Sin look-ahead: se consulta el bucket ANTERIOR al actual ((mm(h)//3)*3 - 3). Sin ese -3 se
# usaría el bucket que EMPIEZA en h y no cierra hasta 2 min después.
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".slp.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import pipeline"
N_IMP = """from sys2.core import pipeline
import os as _os
_SALP = int(_os.environ.get("RL_SALP", "0"))      # salir si la línea lleva >= N buckets plana
_SALMIN = int(_os.environ.get("RL_SALMIN", "0"))  # ... y la posición lleva >= N minutos abierta"""

# `_plano` calculado igual que en barrido_compresion.py (solo pasado)
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
N_SEN = A_SEN + '''
        _plano = {}
        if _SALP:
            _pl = 0
            for _q in range(1, len(ks)):
                _pl = (_pl + 1) if abs(L[ks[_q]]['linea'] - L[ks[_q - 1]]['linea']) < 1e-9 else 0
                _plano[ks[_q]] = _pl'''

A_SAL = "                if gira or h >= aplan or _tp:"
N_SAL = """                _sp = False
                if _SALP and _plano.get((mm(h) // 3) * 3 - 3, 0) >= _SALP:
                    if not _SALMIN or (mm(h) - mm(pos['h0'])) >= _SALMIN:
                        _sp = True          # la línea se aplanó: el impulso se agotó
                if gira or h >= aplan or _tp or _sp:"""

# (nombre, RL_SALP, RL_SALMIN)
V = [("s_base", "0", "0"),        # CONTROL: tiene que dar 83.805$ exacto
     ("s_p4", "4", "0"),
     ("s_p6", "6", "0"),
     ("s_p8", "8", "0"),
     ("s_p12", "12", "0"),
     ("s_p8m6", "8", "6")]        # exige 6 min abierta: "se agotó ESTANDO dentro"

for d in (os.path.dirname(MOT), os.path.join(RAIZ, "sys2", "core")):
    assert not [x for x in os.listdir(d) if x.endswith(".bak")], "otro barrido vivo en %s" % d
base = open(MOT, encoding="utf-8").read()
for pat in (A_IMP, A_SEN, A_SAL):
    assert base.count(pat) == 1, "patrón no único: %r" % pat[:50]

txt = base.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN).replace(A_SAL, N_SAL)
assert txt.count("_sp = True") == 1 and txt.count("or _tp or _sp:") == 1, "parche NO aplicado"
assert txt.count("_plano[ks[_q]] = _pl") == 1, "cálculo de planitud NO aplicado"
compile(txt, MOT, "exec")

shutil.copy2(MOT, BAK)
try:
    open(MOT, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, salp, salmin in V:
        env = dict(os.environ, RL_SALP=salp, RL_SALMIN=salmin)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, salp, salmin, p))
        print("lanzado %-8s salir si plana>=%s  min_abierta=%s" % (nombre, salp, salmin),
              flush=True)
    print("\n-- %d en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    res = {}
    for nombre, salp, salmin, p in procs:
        o, e = p.communicate(timeout=3000)
        print("%-8s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-200:])[-110:]),
              flush=True)
        f = os.path.join(OUT, nombre + ".json")
        if os.path.exists(f):
            res[nombre] = (600.0 + sum(json.load(open(f)).values()), json.load(open(f)))
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
    if "s_base" in res:
        b, Db = res["s_base"]
        print("\nCONTROL s_base = %.0f$ (esperado 83.805$)" % b, flush=True)
        for n, (s, D) in res.items():
            if n == "s_base":
                continue
            dif = [k for k in D if abs(D[k] - Db.get(k, 0)) > 0.005]
            print("  %-8s %9.0f$   %+8.0f$   días que cambian: %d de %d"
                  % (n, s, s - b, len(dif), len(D)), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("[motor.py RESTAURADO]", flush=True)
