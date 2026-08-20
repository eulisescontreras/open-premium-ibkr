# ¿LA LÍNEA ACTIVA ANTES DEL FLIP DELATA UN FALSO FLIP? — idea del usuario (2026-08-20).
#
# LO QUE DICE EL USUARIO: "también pienso que se podrían detectar falsos flips con eso".
#
# QUÉ ESTÁ YA MEDIDO Y QUÉ NO:
#   YA: `plana>=8` ANTES del flip -> el ST flipea más (17,5% -> 36,3%) y DOBLAR ahí vale
#       +13.826$ (6,20 sigmas). O sea la planitud previa marca flips que SÍ funcionan.
#   YA: "no operar DENTRO de tramos planos" -> -7.289$ (descartado).
#   NO: lo COMPLEMENTARIO — descartar los flips que llegan con la línea ACTIVA (poco plana),
#       que por la mecánica de `st_lin_p` son flips nacidos sin compresión previa.
#
# TECHO A BATIR (medido con look-ahead A PROPÓSITO, `barrido_techo.py`): `reb2` con visión
# completa vale RETRASA +12.763$ · INVIERTE +13.640$ · DESCARTA +3.904$. Si esto funciona,
# sería un sustituto HONESTO de parte de ese techo: la planitud se conoce ANTES del flip.
#
# ⚠️ DESFASE ANTI-LOOK-AHEAD. `sen_p` aplica shift_sen(+3), así que el bucket inmediatamente
# anterior al flip es donde la línea SALTA DE LADO y da plana=0 en los 1.505 flips (error
# documentado en el README del 2026-08-20). Por eso se prueban DOS desfases:
#   -6 (dos buckets atrás, el que el README dice correcto para flips)
#   -3 (un bucket atrás, el que usó el barrido de compresión que dio +13.826$)
# Ninguno mira el futuro: ambos son buckets ya cerrados.
#
# Se filtra SOLO el origen "ST-3" (los flips). ORB y aperturas no son flips y no aplican.
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".ff.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import pipeline"
N_IMP = """from sys2.core import pipeline
import os as _os
_FFMIN = int(_os.environ.get("RL_FFMIN", "0"))    # descartar flips con planitud previa < N
_FFDES = int(_os.environ.get("RL_FFDES", "6"))    # desfase del bucket consultado (3 o 6)
_FFST3 = int(_os.environ.get("RL_FFST3", "1"))    # 1 = filtrar solo señales de origen ST-3"""

# ⚠️ PUNTO DE INYECCIÓN — ERROR COMETIDO Y CORREGIDO (2026-08-20):
# el primer intento filtraba justo tras `construir_sen`. NO SIRVE: `motor.py:160` DESCARTA todas
# las señales de origen "ST-3" y las REGENERA con `_reb2` (visión honesta), marcándolas como
# "ST-3h NORMAL/RETRASA/INVIERTE". Filtrar antes es filtrar algo que el motor tira 9 líneas
# después -> las variantes daban 0 días distintos y parecía "la regla no toca nada".
# El punto correcto es DESPUÉS de `Sen = dict(sorted(_ap.items()))` (motor.py:181).
# Requiere C.VISION_HONESTA=True (verificado en config.py:73).
A_SEN = "            Sen = dict(sorted(_ap.items()))"
N_SEN = A_SEN + '''
            if _FFMIN:
                _plano = {}
                _pl = 0
                for _q in range(1, len(ks)):
                    _pl = (_pl + 1) if abs(L[ks[_q]]['linea'] - L[ks[_q - 1]]['linea']) < 1e-9 else 0
                    _plano[ks[_q]] = _pl
                Sen = {_k: _v for _k, _v in Sen.items()
                       if (_FFST3 and not (_origen.get(_k) or "").startswith("ST-3"))
                       or _plano.get((mm(_k) // 3) * 3 - _FFDES, 0) >= _FFMIN}'''

# (nombre, RL_FFMIN, RL_FFDES, RL_FFST3)
V = [("f_base", "0", "6", "1"),      # CONTROL: tiene que dar 83.805$ exacto
     ("f_a3", "3", "6", "1"),
     ("f_a5", "5", "6", "1"),
     ("f_a8", "8", "6", "1"),
     ("f_b5", "5", "3", "1"),        # mismo umbral, desfase del barrido de compresión
     ("f_c5", "5", "6", "0")]        # filtra TODAS las señales, no solo ST-3

for d in (os.path.dirname(MOT), os.path.join(RAIZ, "sys2", "core")):
    assert not [x for x in os.listdir(d) if x.endswith(".bak")], "otro barrido vivo en %s" % d
base = open(MOT, encoding="utf-8").read()
for pat in (A_IMP, A_SEN):
    assert base.count(pat) == 1, "patrón no único: %r" % pat[:50]

txt = base.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN)
assert txt.count("_plano.get((mm(_k) // 3) * 3 - _FFDES, 0) >= _FFMIN") == 1, "parche NO aplicado"
assert txt.count('_FFMIN = int(_os.environ') == 1, "declaración NO aplicada"
compile(txt, MOT, "exec")

shutil.copy2(MOT, BAK)
try:
    open(MOT, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, ffmin, ffdes, ffst3 in V:
        env = dict(os.environ, RL_FFMIN=ffmin, RL_FFDES=ffdes, RL_FFST3=ffst3)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, ffmin, ffdes, ffst3, p))
        print("lanzado %-8s exigir plana>=%s  desfase=-%s  solo_ST3=%s"
              % (nombre, ffmin, ffdes, ffst3), flush=True)
    print("\n-- %d en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    res = {}
    for nombre, ffmin, ffdes, ffst3, p in procs:
        o, e = p.communicate(timeout=3000)
        print("%-8s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-200:])[-110:]),
              flush=True)
        f = os.path.join(OUT, nombre + ".json")
        if os.path.exists(f):
            D = json.load(open(f))
            res[nombre] = (600.0 + sum(D.values()), D)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
    if "f_base" in res:
        b, Db = res["f_base"]
        print("\nCONTROL f_base = %.0f$ (esperado 83.805$)" % b, flush=True)
        for n, (s, D) in res.items():
            if n == "f_base":
                continue
            dif = [k for k in D if abs(D[k] - Db.get(k, 0)) > 0.005]
            aviso = ""
            if not dif:
                # LECCIÓN DEL 2026-08-20: 0 días distintos NO es "la regla no aporta", es casi
                # siempre "el parche está en el sitio equivocado". Se marca en ROJO, no se lee
                # como resultado.
                aviso = "   <-- ⚠️ IDÉNTICO AL CONTROL: sospechar del punto de inyección"
            print("  %-8s %9.0f$   %+8.0f$   días distintos: %d%s"
                  % (n, s, s - b, len(dif), aviso), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("[motor.py RESTAURADO]", flush=True)
