# BARRIDO "ESPERA CONDICIONAL" (idea del usuario): el peaje del retraso se paga SOLO en los
# flips dudosos. Si la 1a vela post-flip AVANZA respecto a la vela que genero el flip -> se
# entra en h+3. Si no avanza -> se espera a h+12 (y opcionalmente se mira la linea del ST).
#
# MEDIDO ANTES (485 sesiones, 1458 flips, test_espera_condicional.py; objetivo independiente =
# recorrido real desde el minuto de entrada):
#   base entrar YA .................. 30.9% malos, 3.27 ATR
#   1a vela avanza >=0.15 -> h+3 .... 25.0% malos, 3.50 ATR  (A1 25.8 / A2 24.0)  <- selecciona
#   2a vela avanza >=0.15 -> h+6 .... 30.7% malos            <- NO aporta (ya se consumio)
#   no avanza ....................... 37.2% malos, 2.92 ATR  <- peores, pero aun dan 2.92
#
# ARITMETICA (verificada contra rebote.sen_p, que emite en el bucket del flip + shift +3):
#   _i = ik[(mm(h)//3)*3]  ->  _i-1 = vela QUE GENERO el flip ; _i = 1a post ; _i+3 = h+12
#
# CONTROLES OBLIGATORIOS (regla 8): hn_esp_3min y hn_esp_12min = mismo retraso SIN condicion.
import shutil, subprocess, sys, os

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".cnd.bak"
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

# AV = umbral de avance de la 1a vela (ATR). FILT = umbral dult en la rama lenta (None = sin
# filtro). SOLO = descartar los flips que no avanzan en vez de esperarlos.
TPL = '''        _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
        for _h, _d in sp:
            if _h < "09:45":
                continue
            _i = ik.get((_mm2(_h) // 3) * 3)
            if _i is None or _i < 1 or _i > len(ks) - 1:
                continue
            _lado = 1 if _d == 'C' else -1
            _aa = [L[ks[q]]['hi'] - L[ks[q]]['lo'] for q in range(max(0, _i - 10), _i + 1)]
            _atr = (sum(_aa) / len(_aa)) or 0.5
            _av = (L[ks[_i]]['cl'] - L[ks[_i - 1]]['cl']) * _lado / _atr
            if _av >= %(AV)s:
                _t = _hh2(ks[_i] + 3)                      # arranco -> entra en h+3
            else:
                _j = _i + 3                                # dudoso -> espera a h+12
                if _j > len(ks) - 1:
                    continue
                _f = %(FILT)s
                if _f is not None:
                    _dd = [_dist_ap(_q, _lado) for _q in range(_i + 1, _j + 1)]
                    if _dd and _dd[-1] <= _f:
                        continue
                if %(SOLO)s:
                    continue
                _t = _hh2(ks[_j] + 3)
            _cand = [_x for _x in _PMh if _x >= _t]
            if not _cand:
                continue
            _he = _cand[0]
            _n = min(_i + 1, len(ks) - 1)
            _ks2 = ks[:_n + 1]; _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
            for _r in _reb2(L, _ks2, _ik2, _h, _d):
                _ap2.setdefault(_he, _r[1])
        Sen = dict(sorted(_ap2.items()))
'''

# (nombre, AV, FILT, SOLO)
VARIANTES = [
    ("hn_esp_3min",   "-9.99", "None",  "False"),  # CONTROL: todos a h+3, sin condicion
    ("hn_cond_nf",    "0.15",  "None",  "False"),  # espera condicional PURA (la idea)
    ("hn_cond_f075",  "0.15",  "0.75",  "False"),  # + filtro de linea en la rama lenta
    ("hn_solo_av",    "0.15",  "None",  "True"),   # solo entra si avanza (descarta el resto)
    ("hn_esp_12min",  "9.99",  "None",  "False"),  # CONTROL: todos a h+12, sin condicion
    ("hn_cond_av060", "0.60",  "None",  "False"),  # umbral de avance mas exigente
]

assert not os.path.exists(MOT + ".hon.bak"), "hay otro barrido vivo"
shutil.copy2(MOT, BAK)
base = open(BAK, encoding="utf-8").read()
assert base.count(A_IMP) == 1 and base.count(A_SEN) == 1

try:
    for nombre, av, filt, solo in VARIANTES:
        txt = base.replace(A_IMP, N_IMP)
        txt = txt.replace(A_SEN, HELP + (TPL % {"AV": av, "FILT": filt, "SOLO": solo}))
        open(MOT, "w", encoding="utf-8").write(txt)
        dest = os.path.join(OUT, nombre + ".json")
        r = subprocess.run([sys.executable, HIJO, dest], cwd=RAIZ,
                           capture_output=True, text=True, timeout=2400)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()[-300:]
        print("%-15s %s" % (nombre, out[-120:]), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("\n[motor.py RESTAURADO]", flush=True)
