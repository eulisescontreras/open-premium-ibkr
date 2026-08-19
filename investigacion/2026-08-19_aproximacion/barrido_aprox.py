# BARRIDO "APROXIMACION A LA LINEA DEL ST" (idea del usuario 2026-08-19, viendo el grafico).
# MEDIDO ANTES (485 sesiones, 1552 flips): tras el flip, si el precio YA TOCO la linea
# (mecha a <=1.0 ATR) el flip resulta FALSO el 49.1% de las veces vs 21.4% si no toco (k=4).
# Separacion 0.54-0.67 -> la señal mas fuerte encontrada (lo anterior: 0.33 como mucho).
# NO es look-ahead: son velas YA FORMADAS en el minuto en que se decide.
#
# Se mide como FILTRO DE ENTRADA (no obedecer el flip) y como SALIDA (cerrar la posicion).
# Base = esp_vivo: el sistema REAL (obedece todo flip con ~1 bucket).
import shutil, subprocess, sys, os

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".ap.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D.py")
OUT = os.path.join(AQUI, "D")

A_IMP = "from sys2.core import instrumento as I"
N_IMP = ("from sys2.core import instrumento as I\n"
         "from sys2.core.rebote import reb2 as _reb2\n"
         "from sys2.core.supertrend import mm as _mm2")
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
A_SAL = "                if gira or h >= aplan:"
A_OPEN = "                        pos = {'k': kl, 'ks': ksh, 'rt': rt, 'ask': (pl_ - psh) * 1.01,"

# --- helper comun: distancia de la mecha a la linea en un bucket ---
HELP = A_SEN + '''

        def _dist_ap(_j, _lado):
            _x = L[ks[_j]]
            _a = [L[ks[q]]['hi'] - L[ks[q]]['lo'] for q in range(max(0, _j - 10), _j + 1)]
            _at = (sum(_a) / len(_a)) or 0.5
            return abs((_x['lo'] if _lado > 0 else _x['hi']) - _x['linea']) / _at
'''

# --- ENTRADA: tras el flip espera K velas; si se acerco a <=U ATR, NO entra ---
ENT = '''        _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
        for _h, _d in sp:
            if _h < "09:45":
                continue
            _i = ik.get((_mm2(_h) // 3) * 3)
            if _i is None or _i + %d > len(ks) - 1:
                continue
            _lado = 1 if _d == 'C' else -1
            _dd = [_dist_ap(_q, _lado) for _q in range(_i + 1, _i + 1 + %d)]
            if _dd and min(_dd) <= %s:
                continue                      # se acerco a la linea -> flip sospechoso
            _n = min(_i + 1, len(ks) - 1)
            _ks2 = ks[:_n + 1]; _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
            for _r in _reb2(L, _ks2, _ik2, _h, _d):
                _ap2.setdefault(_r[0], _r[1])
        Sen = dict(sorted(_ap2.items()))
'''

# --- SALIDA: con posicion abierta, si el precio se acerca a la linea -> cerrar ---
SAL = '''                _bn = ik.get((_mm2(h) // 3) * 3)
                _cerca = False
                if _bn is not None and pos.get('_bk0') is not None and (_bn - pos['_bk0']) >= %d:
                    _lado = 1 if pos['rt'] == 'C' else -1
                    _dd = [_dist_ap(_q, _lado) for _q in range(pos['_bk0'] + 1, _bn + 1)]
                    if _dd and min(_dd) <= %s:
                        _cerca = True
                _cerca = _cerca%s
'''

VARIANTES = [
    ("ap_base",      None, None, None, ""),
    ("ap_ent_k3u10", "E", 3, "1.0", ""),
    ("ap_ent_k4u10", "E", 4, "1.0", ""),
    ("ap_ent_k4u15", "E", 4, "1.5", ""),
    ("ap_sal_k3u10", "S", 3, "1.0", ""),
    ("ap_sal_k4u10", "S", 4, "1.0", ""),
    ("ap_sal_k4u15", "S", 4, "1.5", ""),
    ("ap_sal_k4ben", "S", 4, "1.0", " and pos['mid'] > pos['ask']"),
    ("ap_sal_k2u10", "S", 2, "1.0", ""),
]

shutil.copy2(MOT, BAK)
base = open(BAK, encoding="utf-8").read()
assert base.count(A_IMP) == 1 and base.count(A_SEN) == 1 and base.count(A_SAL) == 1

try:
    for nombre, tipo, k, u, ben in VARIANTES:
        txt = base.replace(A_IMP, N_IMP)
        # base = vivo (obedece todo flip con 1 bucket)
        txt = txt.replace(A_SEN, HELP + '''        _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
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
''' if tipo != "E" else HELP + (ENT % (k, k, u)))
        if tipo == "S":
            txt = txt.replace(A_OPEN, "                        pos = {'_bk0': ik.get((_mm2(h) // 3) * 3), 'k': kl, 'ks': ksh, 'rt': rt, 'ask': (pl_ - psh) * 1.01,")
            txt = txt.replace(A_SAL, (SAL % (k, u, ben)) + "                if gira or h >= aplan or _cerca:")
        open(MOT, "w", encoding="utf-8").write(txt)
        dest = os.path.join(OUT, nombre + ".json")
        r = subprocess.run([sys.executable, HIJO, dest], cwd=RAIZ,
                           capture_output=True, text=True, timeout=2400)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()[-250:]
        print("%-14s %s" % (nombre, out[-90:]), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("\\n[motor.py RESTAURADO]", flush=True)
