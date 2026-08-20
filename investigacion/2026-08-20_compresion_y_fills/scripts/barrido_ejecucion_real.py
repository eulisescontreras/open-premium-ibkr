# EL SISTEMA CON LA EJECUCIÓN REAL METIDA DENTRO — la cifra más cercana a la realidad que
# permiten los datos de hoy.
#
# Aplica la superficie de `ejecucion_real.py` (587 órdenes reales contra IBKR) DENTRO del motor:
#   1. RECHAZO por margen: P(rechazo | hora, moneyness). Si sale rechazada, la señal SE PIERDE
#      (es lo que hace el vivo: no tiene plan B, de ahí los `sin_contrato` observados).
#   2. FILL: P(fill | moneyness) sobre las no rechazadas. Si no llena, la operación no existe.
#   3. SLIPPAGE DE SALIDA por tramo de débito (-1,15% a -5,38%). 139 de 139 ventas se forzaron
#      a mercado, así que esto NO es un caso peor: es el caso NORMAL.
# NO se toca el coste de ENTRADA: el motor ya aplica *1.01 y el slippage de compra medido hoy
# fue +0,80%. Aplicar además el medio spread sería contarlo DOS VECES.
#
# ⚠️ ESTO ES ESTOCÁSTICO. Con fill probabilístico el resultado deja de ser un número y pasa a
# ser una distribución. Dar una sola corrida sería presentar una realización arbitraria como si
# fuera una medición. Se corren N SEMILLAS y se reporta mediana y rango.
#
# ⚠️ HIPÓTESIS, NO MEDICIÓN: la superficie es de UN SOLO DÍA (2026-08-20). La estructura
# (el ITM se rechaza por la tarde, el fill cae cuando sube el spread) es microestructura y
# probablemente estable; el NIVEL depende de la volatilidad de esa sesión.
#
# CONTROL (§2.3): con RL_EJEC=0 tiene que dar 83.805$ exacto.
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MOT = os.path.join(RAIZ, "sys2", "backtest", "motor.py")
BAK = MOT + ".xr.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
OUT = os.path.join(AQUI, "Dh")
EJEC = os.path.join(RAIZ, "investigacion", "2026-08-20_compresion_y_fills", "resultados",
                    "ejecucion_real.json")
os.makedirs(OUT, exist_ok=True)
assert os.path.exists(EJEC), "falta ejecucion_real.json — correr ejecucion_real.py primero"

A_IMP = "from sys2.core import pipeline"
N_IMP = '''from sys2.core import pipeline
import os as _os, json as _json, random as _rnd
_EJEC = int(_os.environ.get("RL_EJEC", "0"))
# DESCOMPOSICIÓN (2026-08-20, pregunta del usuario: "si quito el bloqueo de IBKR, ¿recupero los
# 40.000$?"). Cada causa se puede activar por separado para saber cuánto cuesta CADA UNA en el
# MISMO montaje — sumar resultados de barridos distintos no vale.
_XRECH = int(_os.environ.get("RL_XRECH", "1"))   # rechazo por margen de IBKR
_XFILL = int(_os.environ.get("RL_XFILL", "1"))   # que no haya contrapartida
_XSAL = int(_os.environ.get("RL_XSAL", "1"))     # coste de la venta forzada a mercado
_SEM = int(_os.environ.get("RL_SEM", "1"))
_COMPR = int(_os.environ.get("RL_COMPR", "0"))
_RNG = _rnd.Random(_SEM)
_E = _json.load(open(r"%s")) if _EJEC else {}
_RECH = _E.get("rechazo", {})
_RECHH = _E.get("rechazo_hora", {})
_FILL = _E.get("fill", {})
_SLIPV = _E.get("slip_venta", {})


def _p_rech(h, mny):
    """P(rechazo por margen). Celda (hora,mny) si existe; si no, el agregado de la hora."""
    _m = int(round(mny))
    _k = "%%s|%%d" %% (h[:2], _m)
    if _k in _RECH:
        return _RECH[_k]
    return _RECHH.get(h[:2], 0.0)


def _p_fill(mny):
    """P(fill | no rechazada). Si el moneyness exacto no está medido, se usa el más cercano."""
    _m = int(round(mny))
    if str(_m) in _FILL:
        return _FILL[str(_m)]
    _ks = sorted(int(k) for k in _FILL)
    if not _ks:
        return 1.0
    return _FILL[str(min(_ks, key=lambda z: abs(z - _m)))]


def _slip_salida(deb):
    """Slippage de venta segun el tramo de debito de ENTRADA (media medida)."""
    for _lo, _hi in ((20, 80), (80, 150), (150, 250), (250, 10000)):
        if _lo <= deb < _hi:
            _v = _SLIPV.get("%%d-%%d" %% (_lo, _hi))
            return abs(_v["media"]) / 100.0 if _v else 0.0
    return 0.0
''' % EJEC.replace("\\", "\\\\")

A_SEN = "        Sen, L, ks, ik, sp, _origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc, extra)"
N_SEN = A_SEN + '''
        _plano = {}
        if _COMPR:
            _pl = 0
            for _q in range(1, len(ks)):
                _pl = (_pl + 1) if abs(L[ks[_q]]['linea'] - L[ks[_q - 1]]['linea']) < 1e-9 else 0
                _plano[ks[_q]] = _pl'''
A_NQ = "'vert': True, 'nq': (nq if h >= C.DIABUENO_DESDE else 1)}"
N_NQ = ("'vert': True, 'nq': (min(nq * 2, _AC.TOPE_UNIDADES) if (_COMPR and "
        "_plano.get((mm(h) // 3) * 3 - 3, 0) >= _COMPR) else (nq if h >= C.DIABUENO_DESDE else 1)), "
        "'_deb': (pl_ - psh) * 100}")

# rechazo + fill: justo tras elegir el vertical, ANTES de abrir la posición
A_EV = "                    if ev:\n                        kl, pl_, ksh, psh = ev"
N_EV = ("                    if ev and _EJEC:\n"
        "                        _kl0, _pl0, _ks0, _ps0 = ev\n"
        "                        _mny0 = (Sx - _kl0) if rt == 'C' else (_kl0 - Sx)\n"
        "                        if _XRECH and _RNG.random() < _p_rech(h, _mny0):\n"
        "                            ev = None          # IBKR rechaza: la señal se PIERDE\n"
        "                        elif _XFILL and _RNG.random() > _p_fill(_mny0):\n"
        "                            ev = None          # nadie al otro lado: no llena\n"
        "                    if ev:\n"
        "                        kl, pl_, ksh, psh = ev")

# slippage de salida al cerrar, según el débito de entrada
A_CIERRE = "                    g = ((pos['mid'] - pos['ask']) * 100 - C.COMISION) * pos.get('nq', 1)"
N_CIERRE = ("                    _sv = _slip_salida(pos.get('_deb', 0)) if (_EJEC and _XSAL) else 0.0\n"
            "                    g = ((pos['mid'] * (1.0 - _sv) - pos['ask']) * 100 "
            "- C.COMISION) * pos.get('nq', 1)")

SEMILLAS = [1, 2, 3, 4, 5, 6, 7, 8]
SEM4 = [1, 2, 3, 4]
# (nombre, RL_EJEC, RL_SEM, RL_COMPR, RL_XRECH, RL_XFILL, RL_XSAL)
V = [("z_control", "0", "0", "0", "1", "1", "1")]
V += [("z_real_s%d" % s, "1", str(s), "0", "1", "1", "1") for s in SEMILLAS]
V += [("z_comp_s%d" % s, "1", str(s), "8", "1", "1", "1") for s in SEMILLAS]
# ── DESCOMPOSICIÓN: ¿cuánto cuesta CADA causa por separado? ──────────────────────────
# Pregunta del usuario (2026-08-20): "si IBKR deja de bloquear, ¿recupero los 40.000$?".
# Hay que medirlo en el MISMO montaje: sumar resultados de barridos distintos no vale.
V += [("y_rech_s%d" % s, "1", str(s), "0", "1", "0", "0") for s in SEM4]   # solo el rechazo
V += [("y_fill_s%d" % s, "1", str(s), "0", "0", "1", "0") for s in SEM4]   # solo el fill
V += [("y_sal", "1", "1", "0", "0", "0", "1")]                             # solo la salida (determinista)

assert not [x for x in os.listdir(os.path.dirname(MOT)) if x.endswith(".bak")], "otro barrido vivo"
base = open(MOT, encoding="utf-8").read()
for pat in (A_IMP, A_SEN, A_NQ, A_EV, A_CIERRE):
    assert base.count(pat) == 1, "patrón no único: %r" % pat[:55]
txt = (base.replace(A_IMP, N_IMP).replace(A_SEN, N_SEN).replace(A_NQ, N_NQ)
       .replace(A_EV, N_EV).replace(A_CIERRE, N_CIERRE))
for chk in ("def _p_rech(h, mny):", "IBKR rechaza: la señal se PIERDE",
            "_sv = _slip_salida(pos.get('_deb', 0))", "'_deb': (pl_ - psh) * 100"):
    assert txt.count(chk) == 1, "parche NO aplicado: %r" % chk[:40]
compile(txt, MOT, "exec")

shutil.copy2(MOT, BAK)
try:
    open(MOT, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, ejec, sem, compr, xr, xf, xs in V:
        # con los tres flags a 1 el parche es equivalente al anterior: los resultados ya en
        # disco siguen siendo válidos y no se re-corren (el control lo confirma).
        # el CONTROL se re-corre SIEMPRE: es lo que demuestra que el parche nuevo no cambió nada.
        if (nombre != "z_control" and os.path.exists(os.path.join(OUT, nombre + ".json"))
                and (xr, xf, xs) == ("1", "1", "1")):
            print("ya corrida, se salta: %s" % nombre, flush=True)
            continue
        env = dict(os.environ, RL_EJEC=ejec, RL_SEM=sem, RL_COMPR=compr,
                   RL_XRECH=xr, RL_XFILL=xf, RL_XSAL=xs)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, p))
        while sum(1 for _, q in procs if q.poll() is None) >= 6:
            time.sleep(2)
    print("-- %d corridas (1 control + %d semillas x 2) --\n" % (len(procs), len(SEMILLAS)),
          flush=True)
    t0 = time.time()
    for nombre, p in procs:
        o, e = p.communicate(timeout=4000)
        print("%-14s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-160:])[-80:]),
              flush=True)
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
finally:
    shutil.copy2(BAK, MOT)
    os.remove(BAK)
    print("[motor.py RESTAURADO]", flush=True)


def met(D):
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
    return dict(s=s, dd=100 * dd, ra=rmax, v=v, r=r, mn=min(curva),
                a1=sum(D[k] for k in f if k < co), a2=sum(D[k] for k in f if k >= co),
                op=sum(1 for g in D.values() if abs(g) >= 1e-9))


def carga(n):
    f = os.path.join(OUT, n + ".json")
    return met(json.load(open(f))) if os.path.exists(f) else None


ctrl = carga("z_control")
print("\n" + "=" * 96)
if ctrl:
    ok = abs(ctrl['s'] - 83805) <= 1
    print("CONTROL z_control = %.0f$  %s" % (ctrl['s'], "OK (replica 83.805$)" if ok
                                             else "!! DESVIADO, NO usar estas cifras !!"))
print("=" * 96)
for et, pref in (("EJECUCIÓN REAL (sin compresión)", "z_real_s"),
                 ("EJECUCIÓN REAL + COMPRESIÓN d8", "z_comp_s")):
    M = [carga(pref + str(s)) for s in SEMILLAS]
    M = [x for x in M if x]
    if not M:
        continue
    ss = sorted(x['s'] for x in M)
    print("\n%s   (%d semillas)" % (et, len(M)))
    print("   saldo    mediana %8.0f$   min %8.0f$   max %8.0f$   (%.1fx mediana)"
          % (ss[len(ss) // 2], ss[0], ss[-1], ss[len(ss) // 2] / 600.0))
    for cl, nm, u in (("dd", "drawdown", "%"), ("ra", "racha", ""), ("v", "verdes", ""),
                      ("r", "rojos", ""), ("op", "días operados", ""), ("mn", "saldo mínimo", "$")):
        vs = sorted(x[cl] for x in M)
        print("   %-14s mediana %8.1f%s   min %8.1f%s   max %8.1f%s"
              % (nm, vs[len(vs) // 2], u, vs[0], u, vs[-1], u))
    a1 = sorted(x['a1'] for x in M)
    a2 = sorted(x['a2'] for x in M)
    print("   AÑO1 mediana %+.0f$   AÑO2 mediana %+.0f$" % (a1[len(a1) // 2], a2[len(a2) // 2]))
    if ctrl:
        print("   vs BASE (83.805$): %+.0f$ (%+.1f%%)  |  días operados %d -> %d"
              % (ss[len(ss) // 2] - ctrl['s'], 100.0 * (ss[len(ss) // 2] - ctrl['s']) / ctrl['s'],
                 ctrl['op'], sorted(x['op'] for x in M)[len(M) // 2]))
