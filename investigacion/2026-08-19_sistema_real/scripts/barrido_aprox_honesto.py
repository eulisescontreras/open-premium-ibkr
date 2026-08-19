# BARRIDO "APROXIMACION A LA LINEA" — HONESTO (entrada DESPLAZADA al momento de la decision).
#
# POR QUE: la variante de ayer (`ap_ent_k4u15`, +17.477$) consultaba los buckets _i+1.._i+k
# (12 min DESPUES) pero registraba la señal en la hora del flip -> el motor abria en `h`
# (motor.py:215) sabiendo el futuro. Aqui la entrada se desplaza a ks[_i+k]+3 (la vela k ya
# cerro; convencion shift_sen +3) y se busca el primer minuto con cadena disponible.
#
# FILTROS: los que ganan el test HONESTO (objetivo = recorrido real del precio desde la
# decision, 485 sesiones): dult (distancia en la ULTIMA vela) supera a dmin (minima).
#   k=4 dult<=0.75 -> 61.0% malos vs 34.5%  (A1 +29.3 / A2 +23.6)
#   k=4 dmin<=0.50 -> 60.9% vs 34.9%
#   k=6 dult<=1.00 -> 51.8% vs 34.3%  (n=218, mas muestra)
#
# CONTROL OBLIGATORIO (regla 8): `hn_esp_k*` = MISMO retraso, SIN filtro. Sin el no se puede
# saber si el delta viene del filtro o de entrar mas tarde.
# NO se filtra por "15:40": Sen tambien CIERRA por giro (motor.py:165) y el motor ya limita
# la apertura con ABRIR_HASTA. (Verificado: filtrarlo movia 52 dias y -234$ contra ap_base.)
import shutil, subprocess, sys, os

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".hon.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import instrumento as I"
N_IMP = ("from sys2.core import instrumento as I\n"
         "from sys2.core.rebote import reb2 as _reb2\n"
         "from sys2.core.supertrend import mm as _mm2, hhmm as _hh2")
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"

HELP = A_SEN + '''

        _PMh = sorted(PM)

        def _dist_ap(_j, _lado):
            _x = L[ks[_j]]
            _a = [L[ks[q]]['hi'] - L[ks[q]]['lo'] for q in range(max(0, _j - 10), _j + 1)]
            _at = (sum(_a) / len(_a)) or 0.5
            return abs((_x['lo'] if _lado > 0 else _x['hi']) - _x['linea']) / _at
'''

# K velas miradas ; MODO 'dmin'|'dult'|None (sin filtro) ; U umbral ; RET desplazar la entrada
TPL = '''        _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
        for _h, _d in sp:
            if _h < "09:45":
                continue
            _i = ik.get((_mm2(_h) // 3) * 3)
            if _i is None:
                continue
            _j = _i + %(K)d
            if _j > len(ks) - 1:
                continue
            _lado = 1 if _d == 'C' else -1
            _modo = %(MODO)s
            if _modo is not None:
                _dd = [_dist_ap(_q, _lado) for _q in range(_i + 1, _j + 1)]
                if _dd and (min(_dd) if _modo == 'dmin' else _dd[-1]) <= %(U)s:
                    continue
            _n = min(_i + 1, len(ks) - 1)
            _ks2 = ks[:_n + 1]; _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
            for _r in _reb2(L, _ks2, _ik2, _h, _d):
                _he = _r[0]
                if %(RET)s:
                    _t = _hh2(ks[_j] + 3)
                    _cand = [_x for _x in _PMh if _x >= _t]
                    if not _cand:
                        continue
                    _he = _cand[0]
                _ap2.setdefault(_he, _r[1])
        Sen = dict(sorted(_ap2.items()))
'''

# (nombre, K, MODO, U, RET)   —  retraso = 3*(K+1) minutos ; K buckets mirados
# TANDA 4: localizar el CODO de la curva de coste del retraso. Medido ya: 3 min +600 /
# 12 min -3.912 / 15 min -4.356 / 21 min -6.049. Entre 3 y 12 no hay ningun punto medido, y
# la señal de la linea empieza a existir hacia los 9 min (a los 3 no hay ni 25 casos cerca).
VARIANTES = [
    ("hn_esp_6min",    1, "None",   "0",    "True"),   # CONTROL retraso 6 min
    ("hn_esp_9min",    2, "None",   "0",    "True"),   # CONTROL retraso 9 min
    ("hn_9m_dult100",  2, "'dult'", "1.00", "True"),   # mejor filtro a 9 min (brecha +25.7)
    ("hn_9m_dult075",  2, "'dult'", "0.75", "True"),
    ("hn_9m_dmin050",  2, "'dmin'", "0.50", "True"),
    ("hn_6m_dult125",  1, "'dult'", "1.25", "True"),
]

assert not os.path.exists(MOT + ".ap.bak"), "hay otro barrido vivo: motor.py esta parcheado"
shutil.copy2(MOT, BAK)
base = open(BAK, encoding="utf-8").read()
assert base.count(A_IMP) == 1 and base.count(A_SEN) == 1

try:
    for nombre, k, modo, u, ret in VARIANTES:
        txt = base.replace(A_IMP, N_IMP)
        txt = txt.replace(A_SEN, HELP + (TPL % {"K": k, "MODO": modo, "U": u, "RET": ret}))
        open(MOT, "w", encoding="utf-8").write(txt)
        dest = os.path.join(OUT, nombre + ".json")
        r = subprocess.run([sys.executable, HIJO, dest], cwd=RAIZ,
                           capture_output=True, text=True, timeout=2400)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()[-300:]
        print("%-16s %s" % (nombre, out[-120:]), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("\n[motor.py RESTAURADO]", flush=True)
