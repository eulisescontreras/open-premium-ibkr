# ¿CUÁNTO CUESTA RESPETAR LA FRONTERA REAL DE IBKR?  (cierre del pendiente 🔴 #2)
#
# MAPA MEDIDO HOY EN VIVO (521 órdenes reales, tabla `barrido` de fills_reales.db):
#   % rechazo por margen, hora x moneyness de la pata larga
#   hora      -5      -3      -2      -1      +0      +1      +2      +3      +4      +5
#   10:xx    0%      0%       -      0%      0%      0%      0%      -       -      0%
#   11:xx    0%      0%       -      0%      0%      0%      0%      0%      -      0%
#   12:xx    0%      0%      0%      0%      0%      0%     60%     50%    100%    33%
#   13:xx    0%      0%      0%      0%      0%      -      33%     40%     38%    38%
#   14:xx    0%      0%      0%     22%    100%      -      67%     86%     85%    55%
#   15:xx     -      0%      0%     17%    100%    100%    100%    100%     86%    50%
# LEYES: (1) antes de las 12:00 no se rechaza NADA. (2) desde las 12:00 cae el ITM >= +2.
#        (3) desde las 14:00 la frontera baja hasta ATM. (4) el OTM <= -2 no se rechaza NUNCA.
# El saldo queda descartado: a las 15:16 rechazó 55$ con 1.298$ en caja (4,2%).
#
# `barrido_moneyness.py` midió topes FIJOS (mny<=2 -> -53,7%). Pero un tope fijo paga todo el día
# un precio que solo hace falta por la tarde, y el 49,7% de las operaciones del sistema son a las
# 09:xx, donde el rechazo medido es 0%. Aquí se mide la regla DEPENDIENTE DE LA HORA.
#
# ⚠️ Para permitir OTM hay que tocar TAMBIÉN el `mny < 0.5` de elegir_vert: sin eso ninguna
# candidata OTM pasa el primer filtro y la variante daría idéntica al control (el "0 días
# distintos" que ya engañó una vez hoy).
# ⚠️ El README del 2026-08-19 avisa: "OTM todo el día -> el sistema MUERE (340$)". Por eso se
# prueban tramos, no OTM global.
import shutil, subprocess, sys, os, time, json

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
INS = os.path.join(RAIZ, "sys2", "core", "instrumento.py")
BAK = INS + ".mnh.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
OUT = os.path.join(AQUI, "Dh")
os.makedirs(OUT, exist_ok=True)

A_DEF = 'def elegir_vert(cands, S, h, rt, tope, ancho):'
N_DEF = ('import os as _os\n'
         '# tramos "HH:MM:mnymax" separados por ";". Vacío = sin restricción (control).\n'
         '_TR = [t.split(":", 2) for t in _os.environ.get("RL_TRAMOS", "").split(";") if t]\n'
         '_TRAMOS = sorted([("%s:%s" % (a, b), float(c)) for a, b, c in _TR], reverse=True)\n'
         '\n\n'
         'def _lim_h(h):\n'
         '    """Techo de moneyness vigente a la hora h, según el mapa real de IBKR."""\n'
         '    for hh, mx in _TRAMOS:\n'
         '        if h >= hh:\n'
         '            return mx\n'
         '    return None\n'
         '\n\n'
         'def elegir_vert(cands, S, h, rt, tope, ancho):')
A_MNY = ("        mny = (S - kl) if rt == 'C' else (kl - S)\n"
         "        if mny < 0.5:\n"
         "            continue")
N_MNY = ("        mny = (S - kl) if rt == 'C' else (kl - S)\n"
         "        _mx = _lim_h(h)\n"
         "        if _mx is None:\n"
         "            if mny < 0.5:\n"
         "                continue\n"
         "        else:\n"
         "            # el mínimo baja con el techo: si el techo es OTM, hay que PODER ir a OTM\n"
         "            if mny > _mx or mny < min(0.5, _mx - 2.0):\n"
         "                continue")

# (nombre, RL_TRAMOS)   —  "" = control
V = [("h_base", ""),
     ("h_map", "12:00:1.0;14:00:-1.0"),    # la regla que sale del mapa medido
     ("h_suave", "12:00:3.0;14:00:1.0"),   # versión indulgente
     ("h_12", "12:00:1.0"),                # solo el corte de las 12
     ("h_14", "14:00:1.0"),                # solo el corte de las 14
     ("h_14otm", "14:00:-1.0")]            # sin tocar la mañana, OTM desde las 14

for d in (os.path.dirname(INS), os.path.join(RAIZ, "sys2", "backtest")):
    assert not [x for x in os.listdir(d) if x.endswith(".bak")], "otro barrido vivo en %s" % d
base = open(INS, encoding="utf-8").read()
for pat in (A_DEF, A_MNY):
    assert base.count(pat) == 1, "patrón no único: %r" % pat[:50]

txt = base.replace(A_DEF, N_DEF).replace(A_MNY, N_MNY)
assert txt.count("def _lim_h(h):") == 1, "helper NO aplicado"
assert txt.count("if mny > _mx or mny < min(0.5, _mx - 2.0):") == 1, "filtro NO aplicado"
compile(txt, INS, "exec")

shutil.copy2(INS, BAK)
try:
    open(INS, "w", encoding="utf-8").write(txt)
    procs = []
    for nombre, tramos in V:
        env = dict(os.environ, RL_TRAMOS=tramos)
        p = subprocess.Popen([sys.executable, HIJO, os.path.join(OUT, nombre + ".json")],
                             cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        procs.append((nombre, tramos, p))
        print("lanzado %-8s tramos=%s" % (nombre, tramos or "SIN RESTRICCIÓN"), flush=True)
    print("\n-- %d en paralelo --\n" % len(procs), flush=True)
    t0 = time.time()
    res = {}
    for nombre, tramos, p in procs:
        o, e = p.communicate(timeout=3000)
        print("%-8s %s" % (nombre, ((o or "").strip() or (e or "").strip()[-200:])[-110:]),
              flush=True)
        f = os.path.join(OUT, nombre + ".json")
        if os.path.exists(f):
            res[nombre] = (600.0 + sum(json.load(open(f)).values()), json.load(open(f)))
    print("\ntiempo: %.1f min" % ((time.time() - t0) / 60.0), flush=True)
    if "h_base" in res:
        b, Db = res["h_base"]
        print("\nCONTROL h_base = %.0f$ (esperado 83.805$)" % b, flush=True)
        for n, (s, D) in res.items():
            if n == "h_base":
                continue
            dif = [k for k in D if abs(D[k] - Db.get(k, 0)) > 0.005]
            av = "   <-- ⚠️ IDÉNTICO AL CONTROL: sospechar del parche" if not dif else ""
            print("  %-8s %9.0f$   %+8.0f$   días distintos: %d%s"
                  % (n, s, s - b, len(dif), av), flush=True)
finally:
    shutil.copy2(BAK, INS)
    os.remove(BAK)
    print("[instrumento.py RESTAURADO]", flush=True)
