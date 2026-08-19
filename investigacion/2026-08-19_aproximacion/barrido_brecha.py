# BRECHA BACKTEST vs VIVO: ¿cuanto de los +72.497$ depende de clasificar los flips del ST-3
# con datos que en VIVO no existen todavia?
#
# EL PROBLEMA (verificado 2026-08-18):
#   motor.py:124 -> construir_sen(bars...) se llama UNA VEZ con TODAS las barras del dia, ANTES
#   del bucle de minutos. reb2 mira hasta 12 buckets DESPUES de cada flip para clasificarlo, asi
#   que el backtest sabe a las 14:19 que el flip de las 14:18 es falso... usando datos de 14:54.
#   El VIVO, a las 14:19, solo tiene hasta 14:19: reb2 no tiene nada que recorrer y devuelve
#   NORMAL. Hoy paso con los DOS flips del dia (14:18 C y 15:15 P): el backtest los habria
#   ignorado (DESCARTA) y el vivo los obedecio (el de 15:15 cerro la posicion).
#
# LA MEDICION: reconstruir Sen clasificando cada flip con la informacion disponible EN EL
# MOMENTO DE DECIDIR (bucket del flip + `vis` buckets), que es lo que tiene el vivo.
#   vis=1  -> exactamente lo que ve el sistema real (decide al minuto siguiente).
#   vis=2,4 -> cuanto mejoraria si esperase un poco antes de obedecer el flip.
# Las aperturas (ORB/pm_rev/v1/gap_fade/ayer_rev) NO se tocan: no dependen del futuro.
import shutil, subprocess, sys, os

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".br.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D.py")
OUT = os.path.join(AQUI, "D")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import instrumento as I"
N_IMP = ("from sys2.core import instrumento as I\n"
         "from sys2.core.rebote import reb2 as _reb2\n"
         "from sys2.core import reglas as _R2")
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"

# Reclasifica los flips del ST-3 con vision limitada y REEMPLAZA su aporte dentro de Sen.
HONESTO = A_SEN + '''

        # [BRECHA] Sen HONESTO: los flips del ST-3 se clasifican con la info disponible en el
        # momento de decidir (bucket del flip + %d), no con el dia completo.
        _Sen_ap = dict(Sen)
        for _h, _d in sp:                      # quitar de Sen lo que aporto CADA flip del ST-3
            for _k in [k for k, v in _Sen_ap.items()
                       if (_origen.get(k) or "").startswith("ST-3")]:
                _Sen_ap.pop(_k, None)
        for _h, _d in sp:
            if _h < "09:45":
                continue
            _i = ik.get((mm(_h) // 3) * 3)
            if _i is None:
                continue
            _n = min(_i + %d, len(ks) - 1)
            _ks2 = ks[:_n + 1]
            _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
            if C.ST1_ON:
                _S1, _k1 = pipeline.st_full(bars, 1, C.ST_PER, C.ST_MULT)
                if pipeline.giros(_S1, _k1, _h, C.ST1_VENTANA) >= 1:
                    continue
            for _x in _reb2(L, _ks2, _ik2, _h, _d):
                _Sen_ap.setdefault(_x[0], _x[1])
        Sen = dict(sorted(_Sen_ap.items()))
'''

VARIANTES = [("br_ctrl", 99)]

shutil.copy2(MOT, BAK)
base = open(BAK, encoding="utf-8").read()
assert base.count(A_IMP) == 1 and base.count(A_SEN) == 1

try:
    for nombre, vis in VARIANTES:
        txt = base if vis is None else base.replace(A_IMP, N_IMP).replace(
            A_SEN, HONESTO % (vis, vis))
        open(MOT, "w", encoding="utf-8").write(txt)
        dest = os.path.join(OUT, nombre + ".json")
        r = subprocess.run([sys.executable, HIJO, dest], cwd=RAIZ,
                           capture_output=True, text=True, timeout=2400)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()[-300:]
        print("%-10s %s" % (nombre, out[-100:]), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("\\n[motor.py RESTAURADO]", flush=True)
