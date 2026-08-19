# REACCION HONESTA (sin look-ahead) x MAX_TRADES.
#
# DIAGNOSTICO (fase 4, verificado): el vivo entra SIEMPRE en el minuto del flip con la direccion
# original (11/11 discrepan de reb2 completo). Motivo mecanico: con ventana minima reb2 sale por
# `return [] if toco else [(h,d)]` con toco=False -> NORMAL fechado en h -> el vivo lo obedece.
# reb2 no distingue "recorri 12 buckets y no toco" de "todavia no he visto nada".
#
# TECHO en el motor (con look-ahead, no aplicable): RETRASA +12.763$ (5.08σ), INVIERTE +13.640$
# (3.62σ), DESCARTA +3.904$ (2.04σ).
#
# REACCION HONESTA: se entra igual que ahora, y al CIERRE de cada bucket posterior se reevalua
# reb2 con la ventana disponible (ks[:j+1]). Los buckets ya cerrados NO cambian al añadir barras
# (st_lin_p es incremental) -> reb2(L, ks[:j+1], ...) es EXACTAMENTE lo que ve el vivo en ese
# momento. Si emite direccion CONTRARIA -> se inserta señal contraria en ks[j]+3 y el motor gira
# solo (mecanismo existente `gira`, motor.py:165). Sin datos futuros.
import shutil, subprocess, sys, os

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".rea.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_IMP = "from sys2.core import instrumento as I"
N_IMP = ("from sys2.core import instrumento as I\n"
         "from sys2.core.rebote import reb2 as _reb2\n"
         "from sys2.core.supertrend import mm as _mm2, hhmm as _hh2")
A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
A_MT = "hechas < C.MAX_TRADES"

TPL = A_SEN + '''

        _ap2 = {k: v for k, v in Sen.items() if not (_origen.get(k) or "").startswith("ST-3")}
        for _h, _d in sp:
            if _h < "09:45":
                continue
            _i = ik.get((_mm2(_h) // 3) * 3)
            if _i is None:
                continue
            # (1) entrada tal como la hace el vivo HOY (reb2 con ventana minima)
            _n = min(_i + 1, len(ks) - 1)
            _ks2 = ks[:_n + 1]; _ik2 = {_k: _q for _q, _k in enumerate(_ks2)}
            for _r in _reb2(L, _ks2, _ik2, _h, _d):
                _ap2.setdefault(_r[0], _r[1])
            # (2) REACCION: reevaluar al cierre de cada bucket posterior (solo pasado)
            if %(REAC)s:
                for _j in range(_i + 1, min(_i + 13, len(ks))):
                    _ks3 = ks[:_j + 1]; _ik3 = {_k: _q for _q, _k in enumerate(_ks3)}
                    _r3 = _reb2(L, _ks3, _ik3, _h, _d)
                    if not _r3:
                        continue                      # aun sin resolver
                    if _r3[0][1] != _d:               # INVIERTE detectado AHORA
                        _t3 = _hh2(ks[_j] + 3)
                        if _t3 < "15:40":
                            _ap2.setdefault(_t3, _r3[0][1])
                        break
                    if _r3[0][0] != _h:               # RETRASA: ya estamos dentro
                        break
        Sen = dict(sorted(_ap2.items()))
'''

# (nombre, REAC, MAX_TRADES)
VARIANTES = [
    ("rx_base_mt4",  "False", "4"),    # CONTROL: debe reproducir hn_base +35.878
    ("rx_reac_mt4",  "True",  "4"),    # la reaccion honesta, cupo actual
    ("rx_reac_mt6",  "True",  "6"),
    ("rx_reac_mt8",  "True",  "8"),
    ("rx_reac_mt10", "True",  "10"),
    ("rx_reac_mt99", "True",  "99"),   # sin limite de operaciones
    ("rx_base_mt6",  "False", "6"),    # control: solo subir el cupo, sin reaccion
    ("rx_base_mt8",  "False", "8"),
    ("rx_base_mt99", "False", "99"),
]

assert not [x for x in os.listdir(os.path.dirname(MOT)) if x.endswith(".bak")], "otro barrido vivo"
shutil.copy2(MOT, BAK)
base = open(BAK, encoding="utf-8").read()
assert base.count(A_IMP) == 1 and base.count(A_SEN) == 1 and base.count(A_MT) == 1

try:
    for nombre, reac, mt in VARIANTES:
        txt = base.replace(A_IMP, N_IMP)
        txt = txt.replace(A_SEN, TPL % {"REAC": reac})
        txt = txt.replace(A_MT, "hechas < %s" % mt)
        try:
            compile(txt, MOT, "exec")
        except SyntaxError as e:
            print("%-13s NO COMPILA: %s (linea %s)" % (nombre, e.msg, e.lineno), flush=True)
            continue
        open(MOT, "w", encoding="utf-8").write(txt)
        dest = os.path.join(OUT, nombre + ".json")
        r = subprocess.run([sys.executable, HIJO, dest], cwd=RAIZ,
                           capture_output=True, text=True, timeout=2400)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()[-300:]
        print("%-13s %s" % (nombre, out[-130:]), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("\n[motor.py RESTAURADO]", flush=True)
