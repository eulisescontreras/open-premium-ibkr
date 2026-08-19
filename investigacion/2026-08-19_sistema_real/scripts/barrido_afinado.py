# SIZING — arreglar el AUTOAPAGADO y medir el RIESGO DE RUINA. Todo sin look-ahead (RL=vodc).
#
# FALLO ENCONTRADO (verificado): con 600$ el sistema opera 6 dias de 485 y muere.
# No muere por perder: al bajar el saldo, autocalibra baja el tope a 75$ y NINGUN vertical cabe
# (los elegibles cuestan 88-135$). Espiral: pierde -> baja nivel -> no puede operar -> muere.
# Con tope FIJO 320 y 600$ la cuenta llega a -410$ (quiebra real).
# Desde 1.000$ sobrevive (minimo 712$) y termina en 38.012$ (38x) — pero eso es UNA realizacion.
#
# SE PRUEBAN (modos de sizing, env RL_SIZE):
#   tabla   : autocalibra tal cual (baseline, se autoapaga)
#   hist    : HISTERESIS — el nivel sube pero NUNCA baja (mata la espiral)
#   suelo   : nunca por debajo del nivel inicial
#   frac    : tope = RL_FRAC * saldo (escalado continuo, sin tabla), ancho por tramos
#   fracmin : igual pero con un suelo minimo de tope
# Y RIESGO DE RUINA: mismo sistema empezando en 12 puntos distintos de los 2 años (RL_DESDE).
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
PIP = os.path.join(RAIZ, "sys2", "core", "pipeline.py")
BMOT, BPIP = MOT + ".af.bak", PIP + ".af.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D2.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import instrumento as I"
N_IMP = """from sys2.core import instrumento as I
import os as _os
from sys2.core.rebote import reb2 as _reb2
from sys2.core.supertrend import mm as _mm2, hhmm as _hh2
from sys2.core import autocalibra as _AC
_RL = _os.environ.get("RL", "")
_SLIP = float(_os.environ.get("RL_SLIP", "1.01"))
_CAP0 = float(_os.environ.get("RL_CAP", "600"))
_SIZE = _os.environ.get("RL_SIZE", "tabla")
_FRAC = float(_os.environ.get("RL_FRAC", "0.18"))
_TMIN = float(_os.environ.get("RL_TMIN", "0"))
_FRENO = int(_os.environ.get("RL_FRENO", "0"))     # racha negativa que activa el freno (0=off)
_FRENOF = float(_os.environ.get("RL_FRENOF", "0.5"))   # factor de reduccion del tope
_PAUSA = int(_os.environ.get("RL_PAUSA", "0"))     # no operar tras N dias rojos seguidos (0=off)
_STOPD = float(_os.environ.get("RL_STOPD", "0"))   # stop diario: % del saldo (0=off)
_MT = int(_os.environ.get("RL_MT", "4"))           # MAX_TRADES por dia
_REAC = int(_os.environ.get("RL_REAC", "0"))       # 1 = reaccion honesta (INVIERTE con ventana creciente)
_SCORE = int(_os.environ.get("RL_SCORE", "0"))     # >0 = descartar flips con score de opciones >= N
_UCO = float(_os.environ.get("RL_UCO", "0.155"))
_UIV = float(_os.environ.get("RL_UIV", "0.137"))
_USK = float(_os.environ.get("RL_USK", "0.038"))

def _score_op(_h, _d, cl_, _LIB):
    \"\"\"0..3 condiciones adversas de la cadena en el minuto del flip (umbrales de A1).\"\"\"
    _m = _LIB.get(_h)
    _S = cl_.get(_h)
    if not _m or _S is None:
        return 0
    _lado = 1 if _d == 'C' else -1
    _sc = 0
    _sk = R.skew_l2(_m, _S, _h, _lado)
    if _sk is not None and _sk >= _USK:
        _sc += 1
    _kk = sorted({_k for (_r2, _k) in _m if _r2 == _d}, key=lambda _k: abs(_k - _S))
    if not _kk:
        return _sc
    _ka = _kk[0]
    _vl = _m.get((_d, _ka))
    _vc = _m.get((_d, _ka + 2.0 * _lado))
    if _vl and _vl[0] > 0.01:
        _iv2 = G.implied_vol(_vl[0], _S, _ka, _T(_h), C.GREEKS_R, C.GREEKS_Q, _d)
        if _iv2 is not None and _iv2 <= _UIV:
            _sc += 1
    if _vl and _vc and _vl[0] > 0 and _vc[0] > 0:
        if (_vl[0] - _vc[0]) / 2.0 <= _UCO:
            _sc += 1
    return _sc

def _cfg_dia(_saldo, _nivmax, _racha=0):
    \"\"\"Config del dia segun el modo de sizing. Devuelve (cfg, nivel_alcanzado) o (None,·).
    FRENO: tras `_FRENO` dias seguidos en rojo, el tope se reduce a `_FRENOF` (ataca racha/dd).\"\"\"
    _fr = _FRENOF if (_FRENO and _racha >= _FRENO) else 1.0
    if _SIZE in ("frac", "fracmin"):
        _t = max(_saldo * _FRAC * _fr, _TMIN)
        if _t < 35:
            return None, _nivmax
        _a = float(_os.environ.get("RL_ANCHO", "0")) or (2.0 if _t < 140 else (3.0 if _t < 250 else 4.0))
        _u = 1 if _saldo < 3600 else (2 if _saldo < 5400 else 3)
        return {"tope": _t, "ancho": _a, "unidades": _u, "nivel": 0}, _nivmax
    _c = _AC.configuracion(_saldo)
    _n = _c["nivel"] if _c else 0
    if _SIZE in ("hist", "suelo"):
        _n = max(_n, _nivmax)                      # el nivel NO baja
        if _n <= 0:
            return None, _nivmax
        _f = _AC.TABLA[_n - 1]
        return {"tope": float(_f[3]) * _fr, "ancho": float(_f[2]),
                "unidades": min(_f[4], _AC.TOPE_UNIDADES), "nivel": _n}, _n
    if _c is not None and _fr != 1.0:
        _c = dict(_c, tope=_c["tope"] * _fr)
    return _c, max(_n, _nivmax)"""

A_D = "    D = {}\n    prev = None"
N_D = ("    D = {}\n    prev = None\n    _saldo = _CAP0\n    _anc = C.ANCHO\n    _uni = 1\n"
       "    _nivmax = (_AC.configuracion(_CAP0) or {}).get('nivel', 0) if _SIZE in ('hist','suelo') else 0\n"
       "    _racha = 0")

A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
N_SEN = '''        _LIB = {}
        if _SCORE:
            _vig = {}
            for _hh in sorted(PM):
                for _k2, _v2 in PM[_hh].items():
                    _vig[_k2] = (_v2[0], _v2[1], _mm2(_hh))
                _lim = _mm2(_hh) - 10
                _LIB[_hh] = {_a2: (_b2[0], _b2[1]) for _a2, _b2 in _vig.items() if _b2[2] >= _lim}
        if _PAUSA and _racha >= _PAUSA:
            D[fk] = 0.0
            _racha = 0                      # el dia en pausa CORTA la racha
            continue
        if "c" in _RL:
            _cfg, _nivmax = _cfg_dia(_saldo, _nivmax, _racha)
            if _cfg is None:
                D[fk] = 0.0
                continue
            tope = _cfg["tope"]; _anc = _cfg["ancho"]; _uni = _cfg["unidades"]
''' + A_SEN + '''
        if "v" in _RL:
            _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
            for _h, _d in sp:
                if _h < "09:45":
                    continue
                _i = ik.get((_mm2(_h) // 3) * 3)
                if _i is None:
                    continue
                if _SCORE and _score_op(_h, _d, cl_, _LIB) >= _SCORE:
                    continue          # el mercado de opciones desmiente el flip
                _n = min(_i + 1, len(ks) - 1)
                _ks2 = ks[:_n + 1]; _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
                for _r in _reb2(L, _ks2, _ik2, _h, _d):
                    _ap2.setdefault(_r[0], _r[1])
                if _REAC:             # reevaluar al cierre de cada bucket (SOLO PASADO)
                    for _j in range(_i + 1, min(_i + 13, len(ks))):
                        _ks3 = ks[:_j + 1]; _ik3 = {_k: _q for _q, _k in enumerate(_ks3)}
                        _r3 = _reb2(L, _ks3, _ik3, _h, _d)
                        if not _r3:
                            continue
                        if _r3[0][1] != _d:
                            _t3 = _hh2(ks[_j] + 3)
                            if _t3 < "15:40":
                                _ap2.setdefault(_t3, _r3[0][1])
                            break
                        if _r3[0][0] != _h:
                            break
            Sen = dict(sorted(_ap2.items()))
'''

A_NQ = "        nq = 1\n"
N_NQ = "        nq = _uni if \"c\" in _RL else 1\n"
A_NQ2 = "            nq = 2"
N_NQ2 = "            nq = min(nq * 2, _AC.TOPE_UNIDADES)"
A_NQA = "'vert': True, 'nq': nq}"
N_NQA = "'vert': True, 'nq': (1 if ('d' in _RL and h < '10:31') else nq)}"
A_NQB = "'rod': 0, 'extra': None, 'h0': h, 'd0': d0, 'nq': nq}"
N_NQB = "'rod': 0, 'extra': None, 'h0': h, 'd0': d0, 'nq': (1 if ('d' in _RL and h < '10:31') else nq)}"
A_STOP = "            if pos is None and h in Sen and hechas < C.MAX_TRADES and h < C.ABRIR_HASTA:"
A_MT2 = "hechas < C.MAX_TRADES"
N_STOP = ("            if (pos is None and h in Sen and hechas < _MT "
          "and h < C.ABRIR_HASTA\n"
          "                    and (not _STOPD or tot > -(_STOPD * _saldo))):")
A_ANCHO = "if C.ANCHO:"
N_ANCHO = "if (_anc if 'c' in _RL else C.ANCHO):"
A_ANCHO2 = "I.elegir_vert(cd2, Sx, h, rt, tope, C.ANCHO)"
N_ANCHO2 = "I.elegir_vert(cd2, Sx, h, rt, tope, (_anc if 'c' in _RL else C.ANCHO))"
A_FIN = "        D[fk] = tot"
N_FIN = "        D[fk] = tot\n        _saldo += tot\n        _racha = (_racha + 1) if tot < 0 else 0"

P_IMP = "from sys2 import config as C"
P_IMPN = "from sys2 import config as C\nimport os as _os\n_RL = _os.environ.get(\"RL\", \"\")"
P_VIEJO = "        if sg and all(abs(mm(sg[0][0]) - mm(x[0])) > C.DESCARTE_MIN for x in S):"
P_NUEVO = ("        if sg and all(abs(mm(sg[0][0]) - mm(x[0])) > C.DESCARTE_MIN\n"
           "                      for x in S if ('o' not in _RL or mm(x[0]) <= mm(sg[0][0]))):")

# (nombre, cap, size, frac, tmin, freno, frenof, pausa, stopd)
# OBJETIVO DEL USUARIO: capital <= 800$, racha maxima 2-3 dias, perdidas contenidas, 0 look-ahead.
# Mejor hasta ahora: suelo 140 -> 600$ -> 48.689$ (81.1x) pero RACHA 7 y peor dia -1.412.
# El freno por tamaño NO arregla la racha (verificado: identica con y sin freno) -> se atacan
# las dos unicas vias reales: PAUSA tras racha (corta la racha por construccion) y STOP DIARIO.
# umbrales del score APRENDIDOS EN A1 (fase3_modelo.py), por percentil:
#   p20: costv<=0.155 IV<=0.137 skew>=0.038   |   p25: 0.195 / 0.150 / 0.031
#   p30: 0.230 / 0.163 / 0.027                |   p35: 0.260 / 0.172 / 0.023
# El peor dia resulto ser -5.8% de la cuenta (no un fallo) -> se puede subir la fraccion:
# con el score la varianza baja, asi que el optimo de Kelly se desplaza hacia arriba.
V = [
    ("a_p20_f18", "600", "0.18", "140", "3", "0.15", "4", "0", "0", "2", "0.155", "0.137", "0.038"),
    ("a_p25_f18", "600", "0.18", "140", "3", "0.15", "4", "0", "0", "2", "0.195", "0.150", "0.031"),
    ("a_p30_f18", "600", "0.18", "140", "3", "0.15", "4", "0", "0", "2", "0.230", "0.163", "0.027"),
    ("a_p35_f18", "600", "0.18", "140", "3", "0.15", "4", "0", "0", "2", "0.260", "0.172", "0.023"),
    ("a_p25_f22", "600", "0.22", "140", "3", "0.15", "4", "0", "0", "2", "0.195", "0.150", "0.031"),
    ("a_p25_f25", "600", "0.25", "140", "3", "0.15", "4", "0", "0", "2", "0.195", "0.150", "0.031"),
    ("a_p25_f30", "600", "0.30", "140", "3", "0.15", "4", "0", "0", "2", "0.195", "0.150", "0.031"),
    ("a_p20_f22", "600", "0.22", "140", "3", "0.15", "4", "0", "0", "2", "0.155", "0.137", "0.038"),
    ("a_p20_f25", "600", "0.25", "140", "3", "0.15", "4", "0", "0", "2", "0.155", "0.137", "0.038"),
    ("a_p30_f25", "600", "0.25", "140", "3", "0.15", "4", "0", "0", "2", "0.230", "0.163", "0.027"),
    ("a_p30_s3",  "600", "0.18", "140", "3", "0.15", "4", "0", "0", "3", "0.230", "0.163", "0.027"),
    ("a_p35_s3",  "600", "0.18", "140", "3", "0.15", "4", "0", "0", "3", "0.260", "0.172", "0.023"),
    ("a_p25_p2",  "600", "0.18", "140", "2", "0.15", "4", "0", "0", "2", "0.195", "0.150", "0.031"),
    ("a_p25_np",  "600", "0.18", "140", "0", "0.15", "4", "0", "0", "2", "0.195", "0.150", "0.031"),
]

for b in (BMOT, BPIP):
    assert not os.path.exists(b), "otro barrido vivo"
bmot = open(MOT, encoding="utf-8").read()
bpip = open(PIP, encoding="utf-8").read()
for txt, pat in ((bmot, A_IMP), (bmot, A_D), (bmot, A_SEN), (bmot, A_NQ), (bmot, A_NQ2),
                 (bmot, A_NQA), (bmot, A_NQB), (bmot, A_ANCHO), (bmot, A_ANCHO2),
                 (bmot, A_FIN), (bmot, A_STOP), (bpip, P_IMP), (bpip, P_VIEJO)):
    assert txt.count(pat) == 1, "patron no unico: %r" % pat[:60]
shutil.copy2(MOT, BMOT); shutil.copy2(PIP, BPIP)

tm = (bmot.replace(A_IMP, N_IMP).replace(A_D, N_D).replace(A_SEN, N_SEN)
      .replace(A_NQ, N_NQ).replace(A_NQ2, N_NQ2).replace(A_NQA, N_NQA).replace(A_NQB, N_NQB)
      .replace(A_STOP, N_STOP).replace(A_ANCHO2, N_ANCHO2).replace(A_ANCHO, N_ANCHO)
      .replace(A_FIN, N_FIN).replace("* 1.01", "* _SLIP"))
tp = bpip.replace(P_IMP, P_IMPN).replace(P_VIEJO, P_NUEVO)

try:
    for txt, ruta in ((tm, MOT), (tp, PIP)):
        compile(txt, ruta, "exec")
    open(MOT, "w", encoding="utf-8").write(tm)
    open(PIP, "w", encoding="utf-8").write(tp)
    procs = []
    for nombre, cap, frac, tmin, pausa, stopd, mt, anc, reac, score, uco, uiv, usk in V:
        env = dict(os.environ, RL="vodc", RL_CAP=cap, RL_SLIP="1.01",
                   RL_SIZE="fracmin", RL_FRAC=frac, RL_TMIN=tmin,
                   RL_FRENO="0", RL_FRENOF="0.5", RL_PAUSA=pausa, RL_STOPD=stopd,
                   RL_MT=mt, RL_ANCHO=anc, RL_REAC=reac, RL_SCORE=score,
                   RL_UCO=uco, RL_UIV=uiv, RL_USK=usk)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, p))
        print("lanzado %-11s frac=%s score>=%s umbrales=%s/%s/%s" % (nombre, frac, score, uco, uiv, usk), flush=True)
    print("\n-- %d en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    for nombre, p in procs:
        o, e = p.communicate(timeout=3000)
        r = (o or "").strip() or (e or "").strip()[-250:]
        print("%-12s %s" % (nombre, r[-120:]), flush=True)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BMOT, MOT); os.remove(BMOT)
    shutil.copy2(BPIP, PIP); os.remove(BPIP)
    print("[RESTAURADOS]", flush=True)
