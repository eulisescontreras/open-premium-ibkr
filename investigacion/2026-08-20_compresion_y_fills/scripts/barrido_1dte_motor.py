# -*- coding: utf-8 -*-
# EL SISTEMA CON EL VENCIMIENTO SIGUIENTE: HÍBRIDO (idea del usuario) y 1DTE TODO EL DÍA.
#
# LA IDEA DEL USUARIO (2026-08-21): "tradear hasta las 12 aplicando las técnicas de 0DTE que ya
# definimos, y de ahí en adelante usar 1DTE para evitar el bloqueo".
# Encaja con el mapa medido el 20/08 con 587 órdenes reales: ANTES DE LAS 12:00 IBKR NO RECHAZA
# NADA; desde las 12:00 cae el ITM; desde las 14:00 la frontera baja hasta el ATM. Así que el
# híbrido conserva el 0DTE exactamente donde funciona y donde el sistema hace el 49,7% de sus
# operaciones (09:xx), y solo cambia de vencimiento donde empieza el problema.
#
# ⚠️ LA REFERENCIA REALISTA NO ES 83.805$. Ese número supone ejecución perfecta y es INALCANZABLE
# (IBKR rechaza, no todo llena, y 139 de 139 ventas se fuerzan a mercado). Con la ejecución real
# medida el sistema vale ~41.000$. Aquí 83.805$ se usa SOLO como CONTROL TÉCNICO: es lo que el
# motor tiene que reproducir EXACTO con el parche desactivado. Si sale otra cosa, el parche está
# mal y la tanda se descarta. NO es una expectativa de ganancia.
#
# EL RIESGO QUE SE MIDE: el sistema gana porque el vertical SATURA en el ancho (95% del ancho =
# 139,7x; por % del débito DESTRUYE = 479$). Un 0DTE satura porque el tiempo se acaba HOY; un
# 1DTE tiene un día entero por delante y puede no llegar nunca al 95% intradía. El híbrido
# existe justamente para conservar la saturación durante la mañana.
#
# ── BUG QUE COSTÓ LA PRIMERA TANDA (corregido) ──────────────────────────────────────
# `greeks.parse_occ` devuelve el vencimiento CON GUIONES ('2026-08-13'), y la primera versión de
# este script lo guardaba SIN guiones ('20260813'): no coincidía nunca y se descartaba TODO.
# No dio error: dio "OK 0 dias saldo 600" — un resultado con pinta de resultado. Mismo patrón que
# los "0 días distintos" del 20/08. **Cuando un número sale redondo y malo, sospechar del
# instrumento antes que del sistema.**
#
# ── EL SCORE DE OPCIONES NO VALE PARA 1DTE ──────────────────────────────────────────
# `SCORE_COSTV/IV/SKEW` (config.py:82-85) salen del percentil 25 del AÑO 1 **de 0DTE**. Un 1DTE
# tiene IV estructuralmente distinta. Se aplica en pipeline.py:51,65 leyendo `C.SCORE_OPCIONES`
# EN RUNTIME, así que el hijo lo apaga con `C.SCORE_OPCIONES = 0` sin parchear nada.
# La comparación limpia es SIN SCORE en ambos lados. Si el híbrido aguanta, el paso siguiente es
# re-aprender los cortes con el AÑO 1 de 1DTE y validarlos en el AÑO 2 (como fase3_modelo.py).
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".d1.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_1dte.py")
OUT = os.path.join(AQUI, "Dh")
BD1 = os.path.join(RAIZ, "data_1dte", "massive_premium_1dte.db")
os.makedirs(OUT, exist_ok=True)
assert os.path.exists(BD1), "falta %s (rearmar el zip partido de data_1dte/)" % BD1

# HIJO TOTALMENTE PARAMETRIZABLE. `motor.py` lee C.TP_ANCHO, C.MAX_TRADES, C.PAUSA_ROJOS y el
# sizing EN TIEMPO DE EJECUCIÓN (motor.py:236,346,379 y autocalibra), así que se pueden barrer
# TODOS desde aquí SIN PARCHEAR el motor: menos riesgo de romper algo y el control lo demuestra.
# El ancho lo impone `autocalibra.sizing`, así que para forzarlo se envuelve esa función.
open(HIJO, "w", encoding="utf-8").write('''# -*- coding: utf-8 -*-
import json, sys, os
sys.path.insert(0, r"%s")
from sys2 import config as C

def _f(nom, defecto):
    v = os.environ.get(nom, "")
    return float(v) if v not in ("", None) else defecto

if os.environ.get("RL_SCORE_OFF") == "1":
    C.SCORE_OPCIONES = 0        # pipeline.py lo lee EN RUNTIME
C.TP_ANCHO = _f("RL_TP", C.TP_ANCHO)              # objetivo: fracción del ANCHO
C.MAX_TRADES = int(_f("RL_MT", C.MAX_TRADES))
C.PAUSA_ROJOS = int(_f("RL_PAUSA", C.PAUSA_ROJOS))
C.SIZING_FRAC = _f("RL_FRAC", C.SIZING_FRAC)
C.SIZING_SUELO = _f("RL_SUELO", C.SIZING_SUELO)

_ANC = _f("RL_ANCHO", 0)
if _ANC:                                           # forzar el ancho SIN tocar archivos
    from sys2.core import autocalibra as _AC
    _orig = _AC.sizing
    def _sz(saldo):
        c = _orig(saldo)
        if c:
            c = dict(c, ancho=_ANC)
        return c
    _AC.sizing = _sz

from sys2.backtest import motor
from sys2.db import repo
con = repo.abrir(); SES, PREM, ETFB = motor.cargar(con); con.close()
D = motor.SIS70(SES, PREM, ETFB, capital=600)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
s = 600.0
for f in sorted(D):
    s += D[f]
print("OK %%d dias  saldo %%.0f  (tp=%%s anc=%%s score=%%s corte=%%s)"
      %% (len(D), s, C.TP_ANCHO, _ANC or "auto", C.SCORE_OPCIONES,
         os.environ.get("RL_CORTE") or "-"))
''' % RAIZ)

# ── parche 1: config por env + estado del vencimiento vigente ───────────────────────
A_MAS = 'MASSIVE = os.path.join(RAIZ, "massive_premium.db")'
N_MAS = '''MASSIVE = os.path.join(RAIZ, "massive_premium.db")
_BD1 = os.environ.get("RL_BD1", "")
# RL_CORTE: ""=0DTE puro (control) | "00:00"=1DTE todo el día | "12:00"=híbrido desde esa hora
_CORTE = os.environ.get("RL_CORTE", "")
# FILTRO POR RÉGIMEN (2026-08-21): cambiar de vencimiento SOLO si la mañana tuvo rango. Medido
# sobre el h11: con rango de mañana en el quintil bajo el híbrido aporta -2$/día (A1 -1,5 / A2
# -3,1) y en el alto +97$/día (A1 +106 / A2 +85). Es el ÚNICO régimen que aguantó los dos años
# — el gap de apertura tenía mejor ratio (16,5x) pero A1 +175 vs A2 +44: ruido.
# El umbral se aprende SOLO con el AÑO 1 (primera mitad de sesiones), como los del score.
_RANGOP = float(os.environ.get("RL_RANGOP", "0"))   # percentil (0 = sin filtro)
# DÍAS DE LA SEMANA (idea del usuario 2026-08-21): el aporte del h11 se reparte MITAD Y MITAD
# entre lunes-jueves (1DTE, +11.985$) y el viernes (3DTE, +11.115$). Separarlos dice si el 1DTE
# de UN día aporta por sí solo o si todo venía del contrato de 3 días.
#   RL_DOW_1DTE: días (0=lun..4=vie) en los que se cambia de vencimiento. "" = todos.
#   RL_DOW_PARA: días en los que NO se abre después del corte. El viernes no puede quedarse en
#     0DTE toda la tarde: ahí es cuando IBKR bloquea. Sin esto se mediría un sistema imposible.
_DOW1 = set(int(x) for x in os.environ.get("RL_DOW_1DTE", "").split(",") if x.strip() != "")
_DOWP = set(int(x) for x in os.environ.get("RL_DOW_PARA", "").split(",") if x.strip() != "")
_PARADIA = set()      # fechas concretas en las que no se abre tras el corte
_EXPDIA = {}      # fecha -> vencimiento siguiente, MISMO FORMATO que parse_occ: 'YYYY-MM-DD'
_DTEDIA = {}      # fecha -> días naturales hasta ese vencimiento
_DTEHOY = [0]     # días del día en curso (los usa _T)'''

# ── parche 2: _T sabe QUÉ vencimiento se está usando a cada hora ─────────────────────
A_T = 'def _T(h):\n    return max(1e-6, (960 - mm(h)) / (60 * 24 * 252))'
N_T = ('def _T(h):\n'
       '    # antes del corte se opera 0DTE (vence hoy); a partir del corte, el siguiente\n'
       '    _d = 0 if (not _CORTE or h < _CORTE) else _DTEHOY[0]\n'
       '    return max(1e-6, (960 - mm(h) + _d * 1440) / (60 * 24 * 252))')

# ── parche 3: cargar TAMBIÉN la cadena del vencimiento siguiente y combinarla por hora ──
A_FIN = "    mv.close()\n\n    # bars (1-min con premarket) + rth  desde sys2.bars"
N_FIN = '''    mv.close()

    # ── cadena del VENCIMIENTO SIGUIENTE (1DTE) y combinación por hora ──────────────
    # La clave de PREM es (right, strike) SIN vencimiento: dos vencimientos se pisarían en la
    # misma casilla. Por eso se elige UN vencimiento por día (el más cercano posterior) y las
    # horas >= _CORTE se SUSTITUYEN enteras por esa cadena.
    if _CORTE and _BD1:
        import datetime as _dtm
        _mv1 = sqlite3.connect(_BD1)
        _PR1 = {}
        for _fk in dias:
            _dd1 = {}
            _mejor = None
            for _tk, _ts, _cl, _vol in _mv1.execute(
                    "select ticker,ts,close,volume from aggs where fecha=?", (_fk,)):
                _p = G.parse_occ(_tk)
                if _p is None:
                    continue
                _ex, _rt, _st = _p
                if _ex <= _fk:                 # solo posteriores a la sesión
                    continue
                if _mejor is None or _ex < _mejor:
                    _mejor = _ex               # el MÁS CERCANO de los posteriores
                _dd1.setdefault(_hora_et(_ts), {}).setdefault(_ex, {})[(_rt, _st)] = (_cl, _vol)
            if not _mejor:
                continue
            _lim = {}
            for _h, _porexp in _dd1.items():
                if _mejor in _porexp:
                    _lim[_h] = _porexp[_mejor]
            if _lim:
                _PR1[_fk] = _lim
                _d0 = _dtm.date(int(_fk[:4]), int(_fk[5:7]), int(_fk[8:10]))
                _d1 = _dtm.date(int(_mejor[:4]), int(_mejor[5:7]), int(_mejor[8:10]))
                _EXPDIA[_fk] = _mejor
                _DTEDIA[_fk] = (_d1 - _d0).days
        _mv1.close()

        # ── FILTRO POR RÉGIMEN: solo cambiar de vencimiento si la MAÑANA tuvo rango ──────
        # Solo se usa la ventana 09:30-_CORTE: es lo ÚNICO observable en el momento de decidir.
        # (El primer análisis usaba el rango del DÍA COMPLETO -> habría sido look-ahead.)
        _APLICA = None
        if _RANGOP:
            _am = {}
            for _f, _o, _hi, _lo in con.execute(
                    "select fecha,open,high,low from bars where hora>='09:30' and hora<? "
                    "order by fecha,hora", (_CORTE,)):
                _e = _am.setdefault(_f, [_o, _hi, _lo])
                _e[1] = max(_e[1], _hi)
                _e[2] = min(_e[2], _lo)
            _rg = {_f: ((_v[1] - _v[2]) / _v[0]) for _f, _v in _am.items() if _v[0]}
            # el umbral se aprende SOLO con el AÑO 1 (primera mitad de las sesiones con datos)
            _fs = sorted(set(_rg) & set(PREM))
            _a1 = sorted(_rg[_f] for _f in _fs[:len(_fs) // 2])
            _umb = _a1[min(len(_a1) - 1, int(len(_a1) * _RANGOP / 100.0))] if _a1 else 0.0
            _APLICA = {_f: (_rg.get(_f, 0.0) >= _umb) for _f in set(list(PREM) + list(_PR1))}
            print("[REGIMEN] percentil %.0f del AÑO 1 -> umbral rango_am %.5f | aplica en %d de %d días"
                  % (_RANGOP, _umb, sum(1 for _v in _APLICA.values() if _v), len(_APLICA)),
                  file=sys.stderr)

        _n0 = _n1 = 0
        for _fk in list(set(list(PREM) + list(_PR1))):
            _a = PREM.get(_fk, {})
            _b = _PR1.get(_fk, {})
            # día que NO pasa el filtro de régimen: se queda TODO en 0DTE (y sin días extra
            # en _T, por eso se borra de _DTEDIA)
            _dow = _dtm.date(int(_fk[:4]), int(_fk[5:7]), int(_fk[8:10])).weekday()
            if _DOWP and _dow in _DOWP:
                _PARADIA.add(_fk)          # ese día no se abre después del corte
            if _DOW1 and _dow not in _DOW1:
                _DTEDIA.pop(_fk, None)     # día excluido: se queda TODO en 0DTE
                _n0 += len(_a)
                continue
            if _APLICA is not None and not _APLICA.get(_fk, False):
                _DTEDIA.pop(_fk, None)
                _n0 += len(_a)
                continue
            _out = {}
            for _h in set(list(_a) + list(_b)):
                if _h < _CORTE:
                    if _h in _a:
                        _out[_h] = _a[_h]; _n0 += 1
                else:
                    if _h in _b:
                        _out[_h] = _b[_h]; _n1 += 1
            if _out:
                PREM[_fk] = _out
            elif _fk in PREM:
                del PREM[_fk]
        print("[1DTE] corte=%s  minutos 0DTE=%d  minutos siguiente-venc=%d  dias=%d"
              % (_CORTE, _n0, _n1, len(PREM)), file=sys.stderr)

    # bars (1-min con premarket) + rth  desde sys2.bars'''

A_ABRE = "            if (pos is None and h in Sen and hechas < C.MAX_TRADES and h < C.ABRIR_HASTA"
N_ABRE = ("            if (pos is None and h in Sen and hechas < C.MAX_TRADES "
          "and h < C.ABRIR_HASTA\n"
          "                    and not (fk in _PARADIA and _CORTE and h >= _CORTE)")

A_PM = "        PM = PREM[fk]"
N_PM = "        PM = PREM[fk]\n        _DTEHOY[0] = _DTEDIA.get(fk, 0)"

A_IMPSYS = "import os\nimport sqlite3"
N_IMPSYS = "import os\nimport sys\nimport sqlite3"

# ── BLOQUE A: EL OBJETIVO DE SALIDA ─────────────────────────────────────────────────
# `TP_ANCHO=0.95` está calibrado PARA 0DTE, que satura porque el tiempo se acaba HOY. Un 1DTE
# tiene un día más por delante y puede NO llegar nunca al 95% intradía — y el "1DTE todo el día"
# murió (428$) con ese objetivo puesto. Si el objetivo correcto es otro, esto lo rescata.
# ⚠️ SIN LOOK-AHEAD: el objetivo es un PARÁMETRO, no mira el futuro. Pero optimizarlo sobre los
# 2 años sería ajustar a los datos de validación -> se juzga por CONSISTENCIA AÑO 1 / AÑO 2,
# no por el total. Lo que no aguante los dos años es ruido.
# (nombre, RL_BD1, RL_CORTE, RL_SCORE_OFF, RL_RANGOP, RL_TP, RL_ANCHO, esperado)
V = [("a_h11_tp95", BD1, "11:00", "1", "0", "0.95", "", 97657),   # CONTROL (ya medido)
     ("a_h11_tp90", BD1, "11:00", "1", "0", "0.90", "", None),
     ("a_h11_tp85", BD1, "11:00", "1", "0", "0.85", "", None),
     ("a_h11_tp80", BD1, "11:00", "1", "0", "0.80", "", None),
     ("a_h11_tp75", BD1, "11:00", "1", "0", "0.75", "", None),   # <- el PREDICHO por saturación
     ("a_h11_tp70", BD1, "11:00", "1", "0", "0.70", "", None),
     ("a_d1_tp85", BD1, "00:00", "1", "0", "0.85", "", None),     # ¿rescata el 1DTE puro?
     ("a_d1_tp80", BD1, "00:00", "1", "0", "0.80", "", None),
     ("a_d1_tp75", BD1, "00:00", "1", "0", "0.75", "", None),    # <- el PREDICHO
     ("a_d1_tp70", BD1, "00:00", "1", "0", "0.70", "", None),
     ("a_d1_tp60", BD1, "00:00", "1", "0", "0.60", "", None)]

assert not [x for x in os.listdir(os.path.dirname(MOT)) if x.endswith(".bak")], "otro barrido vivo"
base = open(MOT, encoding="utf-8").read()
for pat in (A_MAS, A_T, A_FIN, A_PM, A_IMPSYS, A_ABRE):
    assert base.count(pat) == 1, "patrón no único: %r" % pat[:55]
txt = (base.replace(A_IMPSYS, N_IMPSYS).replace(A_MAS, N_MAS).replace(A_T, N_T)
       .replace(A_FIN, N_FIN).replace(A_PM, N_PM).replace(A_ABRE, N_ABRE))
for chk in ("_d * 1440", "_mejor is None or _ex < _mejor", "minutos siguiente-venc",
            "fk in _PARADIA"):
    assert txt.count(chk) == 1, "parche NO aplicado: %r" % chk
compile(txt, MOT, "exec")

shutil.copy2(MOT, BAK)
try:
    open(MOT, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, bd1, corte, soff, rgp, tp, anc, esp in V:
        env = dict(os.environ, RL_BD1=bd1, RL_CORTE=corte, RL_SCORE_OFF=soff, RL_RANGOP=rgp,
                   RL_TP=tp, RL_ANCHO=anc)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, esp, p))
        print("lanzado %-14s corte=%-6s tp=%-5s anc=%-3s" % (nombre, corte or "(0DTE)", tp, anc or "auto"),
              flush=True)
        while sum(1 for _, _, q in procs if q.poll() is None) >= 3:   # 3: el vivo captura
            time.sleep(2)
    print("\n-- %d corridas --\n" % len(procs), flush=True)
    t0 = time.time()
    R = {}
    for nombre, esp, p in procs:
        o, e = p.communicate(timeout=9000)
        eo = (e or "").strip()
        det = [l for l in eo.splitlines() if l.startswith("[1DTE]")]
        print("%-14s %s %s" % (nombre, ((o or "").strip() or eo[-200:])[-95:],
                               ("| " + det[-1]) if det else ""), flush=True)
        f = os.path.join(OUT, nombre + ".json")
        if os.path.exists(f):
            R[nombre] = (json.load(open(f)), esp)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("[motor.py RESTAURADO]", flush=True)


def met(D):
    if not D:
        return None
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
            sum(D[k] for k in f if k < co), sum(D[k] for k in f if k >= co),
            sum(1 for g in D.values() if abs(g) >= 1e-9))


NOM = {n[0]: n[0].replace("a_h11_","hibrido 11:00  TP=").replace("a_d1_","1DTE todo dia TP=").replace("tp"," 0.") for n in V}
print("\n" + "=" * 104)
print("0DTE vs VENCIMIENTO SIGUIENTE — 485/482 sesiones, capital 600$, TODOS sin score salvo el control")
print("=" * 104)
print("%-30s %10s %7s %8s %6s %6s %6s %8s %10s %10s"
      % ("", "saldo", "mult", "drawdn", "racha", "verde", "rojo", "dias op", "AÑO 1", "AÑO 2"))
malo = []
for n in [x[0] for x in V]:
    if n not in R:
        continue
    D, esp = R[n]
    m = met(D)
    if m is None:
        print("%-30s  (SIN DATOS: 0 días -> revisar el parche)" % NOM[n], flush=True)
        continue
    s, dd, ra, v, r, mn, a1, a2, op = m
    if esp is not None and abs(s - esp) > 1:
        malo.append("%s: %.0f (esperado %d)" % (n, s, esp))
    print("%-30s %9.0f$ %6.1fx %7.1f%% %6d %6d %6d %8d %+10.0f %+10.0f"
          % (NOM[n], s, s / 600.0, dd, ra, v, r, op, a1, a2), flush=True)
if malo:
    print("\n⚠️ CONTROL DESVIADO — NO usar estas cifras: " + " | ".join(malo))
else:
    print("\n✓ los controles reproducen la base")
ref = met(R["a_h11_tp95"][0])[0] if "a_h11_tp95" in R else None
if ref:
    print("\nCOMPARACIÓN LIMPIA (todo SIN score, misma vara de medir):")
    for n in [x[0] for x in V if x[0] != "a_h11_tp95"]:
        if n in R and met(R[n][0]):
            s = met(R[n][0])[0]
            print("   %-30s %9.0f$   %+8.0f$  (%+.1f%%) vs 0DTE sin score"
                  % (NOM[n], s, s - ref, 100.0 * (s - ref) / ref))
print("\n⚠️ 83.805$ es CONTROL TÉCNICO, no expectativa: con la ejecución real medida el sistema")
print("   vale ~41.000$. Lo que importa aquí es la comparación RELATIVA entre vencimientos.")
