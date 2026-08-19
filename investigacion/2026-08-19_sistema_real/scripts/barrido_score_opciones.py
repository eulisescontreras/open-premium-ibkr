# SCORE DE OPCIONES EN EL MOTOR REAL — la señal de fase 2/3 llevada al dinero.
#
# REGLA: en el minuto del flip (coste de tiempo CERO) se cuentan 3 condiciones adversas:
#   costv <= U_COST   el vertical ATM esta barato -> el mercado no cobra por el movimiento
#   ivatm <= U_IV     volatilidad implicita muerta
#   skew  >= U_SKEW   pagan proteccion CONTRA la direccion del flip
# score >= S_MIN -> NO ENTRAR.
#
# UMBRALES APRENDIDOS SOLO CON EL AÑO 1 (fase3_modelo.py). Validacion out-of-sample en A2:
#   score 0 -> 51.0% pierden | 1 -> 59.1% | 2 -> 74.1% | 3 -> 89.3%   (monotono, p=0.0000)
#
# Se reutilizan las FUNCIONES REALES que el motor YA importa: R.skew_l2, G.implied_vol, _T.
# La cadena se lee del LIBRO VIGENTE (ultimo precio conocido <=10 min, solo pasado) porque
# massive solo trae los contratos que cotizaron ese minuto (~13, no 82) — igual que fase 2.
import shutil, subprocess, sys, os

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".sco.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import instrumento as I"
N_IMP = ("from sys2.core import instrumento as I\n"
         "from sys2.core.rebote import reb2 as _reb2\n"
         "from sys2.core.supertrend import mm as _mm2")
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"

TPL = A_SEN + '''

        # libro vigente: ultimo precio conocido por strike (<=10 min, SOLO PASADO)
        _vig = {}
        _LIB = {}
        for _hh in sorted(PM):
            for _k2, _v2 in PM[_hh].items():
                _vig[_k2] = (_v2[0], _v2[1], _mm2(_hh))
            _lim = _mm2(_hh) - 10
            _LIB[_hh] = {_a: (_b[0], _b[1]) for _a, _b in _vig.items() if _b[2] >= _lim}

        _ANC = 2.0
        def _score_op(_h, _d):
            """0..3 condiciones adversas de la cadena en el minuto del flip."""
            _m = _LIB.get(_h)
            _S = cl_.get(_h)
            if not _m or _S is None:
                return 0
            _lado = 1 if _d == 'C' else -1
            _sc = 0
            _sk = R.skew_l2(_m, _S, _h, _lado)
            if _sk is not None and _sk >= %(USK)s:
                _sc += 1
            _kk = sorted({_k for (_r2, _k) in _m if _r2 == _d}, key=lambda _k: abs(_k - _S))
            if not _kk:
                return _sc
            _ka = _kk[0]
            _vl = _m.get((_d, _ka))
            _vc = _m.get((_d, _ka + _ANC * _lado))
            if _vl and _vl[0] > 0.01:
                _iv = G.implied_vol(_vl[0], _S, _ka, _T(_h), C.GREEKS_R, C.GREEKS_Q, _d)
                if _iv is not None and _iv <= %(UIV)s:
                    _sc += 1
            if _vl and _vc and _vl[0] > 0 and _vc[0] > 0:
                if (_vl[0] - _vc[0]) / _ANC <= %(UCO)s:
                    _sc += 1
            return _sc

        _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
        for _h, _d in sp:
            if _h < "09:45":
                continue
            _i = ik.get((_mm2(_h) // 3) * 3)
            if _i is None:
                continue
            if %(SMIN)s <= 3 and _score_op(_h, _d) >= %(SMIN)s:
                continue                      # el mercado de opciones desmiente el flip
            _n = min(_i + 1, len(ks) - 1)
            _ks2 = ks[:_n + 1]; _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
            for _r in _reb2(L, _ks2, _ik2, _h, _d):
                _ap2.setdefault(_r[0], _r[1])
        Sen = dict(sorted(_ap2.items()))
'''

# (nombre, U_COST, U_IV, U_SKEW, S_MIN)  — umbrales de fase3, aprendidos SOLO en A1
VARIANTES = [
    ("sc_base",    "0.155", "0.137", "0.038", "9"),    # CONTROL: debe dar +35.878 exacto
    ("sc_p20_s3",  "0.155", "0.137", "0.038", "3"),    # descarta las 3 señales a la vez
    ("sc_p25_s3",  "0.195", "0.150", "0.031", "3"),
    ("sc_p30_s3",  "0.230", "0.163", "0.027", "3"),
    ("sc_p25_s2",  "0.195", "0.150", "0.031", "2"),    # mas cobertura, menos precision
    ("sc_p20_s2",  "0.155", "0.137", "0.038", "2"),
]

assert not [x for x in os.listdir(os.path.dirname(MOT)) if x.endswith(".bak")], \
    "hay otro barrido vivo: motor.py esta parcheado"
shutil.copy2(MOT, BAK)
base = open(BAK, encoding="utf-8").read()
assert base.count(A_IMP) == 1 and base.count(A_SEN) == 1

try:
    for nombre, uco, uiv, usk, smin in VARIANTES:
        txt = base.replace(A_IMP, N_IMP)
        txt = txt.replace(A_SEN, TPL % {"UCO": uco, "UIV": uiv, "USK": usk, "SMIN": smin})
        try:
            compile(txt, MOT, "exec")
        except SyntaxError as e:
            print("%-11s PARCHE NO COMPILA: %s (linea %s)" % (nombre, e.msg, e.lineno), flush=True)
            continue
        open(MOT, "w", encoding="utf-8").write(txt)
        dest = os.path.join(OUT, nombre + ".json")
        r = subprocess.run([sys.executable, HIJO, dest], cwd=RAIZ,
                           capture_output=True, text=True, timeout=2400)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()[-300:]
        print("%-11s %s" % (nombre, out[-130:]), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("\n[motor.py RESTAURADO]", flush=True)
