# -*- coding: utf-8 -*-
# ¿QUÉ CONTRATO COMPRA REALMENTE EL SISTEMA?  (pieza que falta del pendiente 🔴 #2)
#
# `barrido_moneyness.py` midió lo que CUESTA acotar el moneyness (mny<=2 -> -53,7%). Pero para
# decidir hace falta el otro lado: qué compra hoy el sistema, cuándo, y a qué precio — porque
# las dos restricciones reales medidas en vivo dependen de eso:
#   FILL   por moneyness:  0 -> 87% · +1 -> 67% · +2 -> 59% · +3 -> 39% · +5 -> 23% · +10 -> 0%
#   MARGEN por ITM y HORA: ATM/OTM 1,3% rechazo · ITM 25,4%; ITM 10:xx 0% · 12:xx 33% · 14:xx 65%
#
# VERIFICADO (motor.py:293-305): si `elegir_vert` devuelve un vertical, la posición se abre ahí
# mismo, sin filtro posterior. Registrar en su `return` = registrar operaciones reales.
#
# NO estima P&L por operación (el motor no lo expone por operación): mide CUÁNTAS operaciones
# caen en cada banda y en qué hora. El cruce con las tasas de arriba es una COTA, no un P&L.
import shutil, subprocess, sys, os, collections

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
INS = os.path.join(RAIZ, "sys2", "core", "instrumento.py")
BAK = INS + ".dmp.bak"
AQUI = os.path.dirname(os.path.abspath(__file__))
HIJO = os.path.join(AQUI, "_dump_D_cap.py")
RES = os.path.join(AQUI, "..", "resultados")
os.makedirs(RES, exist_ok=True)
OPS = os.path.join(RES, "ops_moneyness.csv")
OUTJ = os.path.join(AQUI, "Dh", "dump_ops.json")
os.makedirs(os.path.dirname(OUTJ), exist_ok=True)

A_DEF = 'def elegir_vert(cands, S, h, rt, tope, ancho):'
N_DEF = ('import os as _os\n'
         '_DUMP = _os.environ.get("RL_DUMP", "")\n'
         '\n\n'
         'def elegir_vert(cands, S, h, rt, tope, ancho):')
A_RET = "        if 20 <= deb <= tope + 1:\n            return (kl, vl[0], ksh, vsh[0])"
N_RET = ("        if 20 <= deb <= tope + 1:\n"
         "            if _DUMP:\n"
         "                with open(_DUMP, 'a') as _fd:\n"
         "                    _fd.write('%s,%s,%.2f,%.2f,%.1f,%.2f\\n'\n"
         "                              % (h, rt, mny, deb, ancho, tope))\n"
         "            return (kl, vl[0], ksh, vsh[0])")

txt = open(INS, encoding="utf-8").read()
assert txt.count(A_DEF) == 1 and txt.count(A_RET) == 1, "patrón no único"
nuevo = txt.replace(A_DEF, N_DEF).replace(A_RET, N_RET)
assert nuevo.count("_fd.write") == 1 and nuevo.count('_DUMP = _os.environ') == 1, "parche NO aplicado"
compile(nuevo, INS, "exec")
assert not [x for x in os.listdir(os.path.dirname(INS)) if x.endswith(".bak")], "otro barrido vivo"

if os.path.exists(OPS):
    os.remove(OPS)
shutil.copy2(INS, BAK)
try:
    open(INS, "w", encoding="utf-8").write(nuevo)
    env = dict(os.environ, RL_DUMP=OPS)
    p = subprocess.run([sys.executable, HIJO, OUTJ], cwd=RAIZ, env=env,
                       capture_output=True, text=True, timeout=3000)
    print((p.stdout or "").strip() or (p.stderr or "").strip()[-400:], flush=True)
finally:
    shutil.copy2(BAK, INS)
    os.remove(BAK)
    print("[instrumento.py RESTAURADO]", flush=True)

# ── agregación ──────────────────────────────────────────────────────────────────────
filas = []
for ln in open(OPS):
    h, rt, mny, deb, anc, tope = ln.strip().split(",")
    filas.append(dict(h=h, rt=rt, mny=float(mny), deb=float(deb), anc=float(anc),
                      tope=float(tope)))
n = len(filas)
print("\noperaciones registradas: %d\n" % n)

# tasas MEDIDAS EN VIVO (fills_reales.db). Fuera de rango se extrapola al vecino más cercano.
FILL = {0: .87, 1: .67, 2: .59, 3: .39, 4: .31, 5: .23, 6: .18, 7: .14, 8: .09, 9: .05}


def fill_de(m):
    if m < 0.5:
        return .87
    return FILL.get(int(round(m)), 0.0)


print("=== DISTRIBUCIÓN POR MONEYNESS DE LA PATA LARGA ===")
print("%-14s %7s %6s %9s %9s   %8s" % ("mny", "n", "%", "débito~", "tope~", "fill medido"))
bandas = [(0.5, 1.5), (1.5, 2.5), (2.5, 3.5), (3.5, 4.5), (4.5, 6.5), (6.5, 10.5), (10.5, 999)]
for lo, hi in bandas:
    s = [x for x in filas if lo <= x['mny'] < hi]
    if not s:
        continue
    print("%-14s %7d %5.1f%% %9.0f %9.0f   %7.0f%%"
          % ("%.1f-%.1f" % (lo, hi), len(s), 100.0 * len(s) / n,
             sum(x['deb'] for x in s) / len(s), sum(x['tope'] for x in s) / len(s),
             100.0 * sum(fill_de(x['mny']) for x in s) / len(s)))
print()

print("=== POR HORA (la tasa de rechazo por margen del ITM crece con la hora) ===")
print("%-10s %7s %6s %9s %9s" % ("hora", "n", "%", "mny medio", "% ITM>2"))
for hh in sorted({x['h'][:2] for x in filas}):
    s = [x for x in filas if x['h'][:2] == hh]
    print("%-10s %7d %5.1f%% %9.2f %8.0f%%"
          % (hh + ":xx", len(s), 100.0 * len(s) / n, sum(x['mny'] for x in s) / len(s),
             100.0 * sum(1 for x in s if x['mny'] > 2) / len(s)))
print()

print("=== COTA DE EJECUTABILIDAD (fill medido x nº de operaciones) ===")
esp = sum(fill_de(x['mny']) for x in filas)
print("operaciones que el mercado llenaría, según el fill medido por moneyness:")
print("   %.0f de %d  =  %.1f%%" % (esp, n, 100.0 * esp / n))
print("(COTA, no P&L: supone que cada operación vale lo mismo y que el fill es independiente)")
