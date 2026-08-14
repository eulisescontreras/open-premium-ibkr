# -*- coding: utf-8 -*-
"""PASO 1 — ¿M1/M2 dan la DIRECCION GLOBAL del dia? (sobre los 3 dias de flujo que existen)

Compara el estado de M1 y M2 (a apertura+30, +60 min y el dominante del dia) contra el SIGNO REAL
del dia (spy_cierre - spy_apertura). SOLO datos disponibles: m1_minute/m2_minute (08-10..08-12).

AVISO: n=3 sesiones -> estadisticamente NULO. Es descripcion, no validacion. Read-only.
Uso: python analisis/m1m2_direccion_dia.py
Salida: investigacion/m1m2_direccion_dia.txt
"""
import os, sqlite3, sys
from collections import Counter
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
DB = "spy_history.db"
def mm(h): return int(h[:2]) * 60 + int(h[3:5])
OUT = []
def p(s=""):
    print(s); OUT.append(s)

def estado_en(rows, col_idx, minuto_objetivo):
    """estado (col_idx) en el primer minuto >= apertura+minuto_objetivo."""
    m0 = mm(rows[0][0])
    for r in rows:
        if mm(r[0]) >= m0 + minuto_objetivo:
            return r[col_idx]
    return rows[-1][col_idx]

def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    p("=" * 84)
    p("PASO 1 — M1/M2 como DIRECCION DEL DIA vs signo real (n=3, SOLO descripcion)")
    p("=" * 84)
    p(f"{'fecha':>12} {'signo_dia':>9} | {'M1@30':>6} {'M1@60':>6} {'M1dom':>7} {'camb':>4} | {'M2@30':>6} {'M2@60':>6} {'M2dom':>7} {'camb':>4}")
    aciertos_m1_dom = 0; aciertos_m2_dom = 0; total = 0
    for (f,) in c.execute("select distinct fecha from m1_minute order by fecha"):
        r1 = c.execute("select hora,spy,m1 from m1_minute where fecha=? order by hora", (f,)).fetchall()
        r2 = c.execute("select hora,spy,m2 from m2_minute where fecha=? order by hora", (f,)).fetchall()
        spies = [x[1] for x in r1 if x[1] is not None]
        signo = "UP" if spies[-1] > spies[0] else "DOWN"
        m1_30 = estado_en(r1, 2, 30); m1_60 = estado_en(r1, 2, 60)
        m2_30 = estado_en(r2, 2, 30); m2_60 = estado_en(r2, 2, 60)
        e1 = [x[2] for x in r1 if x[2]]; e2 = [x[2] for x in r2 if x[2]]
        m1_dom = Counter(e1).most_common(1)[0][0]; m2_dom = Counter(e2).most_common(1)[0][0]
        c1 = sum(1 for i in range(1, len(e1)) if e1[i] != e1[i-1])
        c2 = sum(1 for i in range(1, len(e2)) if e2[i] != e2[i-1])
        total += 1
        aciertos_m1_dom += (m1_dom == signo); aciertos_m2_dom += (m2_dom == signo)
        p(f"{f:>12} {signo:>9} | {m1_30:>6} {m1_60:>6} {m1_dom:>7} {c1:>4} | {m2_30:>6} {m2_60:>6} {m2_dom:>7} {c2:>4}")
    p("-" * 84)
    p(f"acierto (dominante vs signo dia): M1 {aciertos_m1_dom}/{total}  M2 {aciertos_m2_dom}/{total}")
    p("TODOS los dias disponibles fueron DOWN -> no se puede distinguir skill de sesgo. n=3 = NULO.")
    p("VEREDICTO: la premisa 'M1/M2 dan la direccion del dia' NO es verificable con estos datos.")
    p("=" * 84)
    os.makedirs("investigacion", exist_ok=True)
    with open(os.path.join("investigacion", "m1m2_direccion_dia.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print("\nsalida:", os.path.abspath(os.path.join("investigacion", "m1m2_direccion_dia.txt")))

if __name__ == "__main__":
    main()
