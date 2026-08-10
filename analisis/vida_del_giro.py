# -*- coding: utf-8 -*-
"""Analisis READ-ONLY: que hace el SPY DESPUES de cada giro confirmado.
Responde: dejar correr vs cerrar antes. Datos reales de spy_history.db, sesion 2026-08-10.
LIMITACION: ta_minute solo guarda el CIERRE del minuto (no high/low), asi que el maximo
favorable es el maximo de los cierres, NUNCA el intrabarra -> es un SUELO del recorrido real.
"""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)

FECHA = "2026-08-10"


def mins(h):
    p = h.split(":")
    return int(p[0]) * 60 + int(p[1])


ta = {}
for h, spy in c.execute(
        "SELECT hora, spy FROM ta_minute WHERE fecha=? ORDER BY hora", (FECHA,)):
    ta[mins(h)] = spy
if not ta:
    raise SystemExit("sin ta_minute")

flips = c.execute(
    "SELECT hora, estado, spy FROM transitions WHERE fecha=? AND tipo='FLIP' "
    "ORDER BY id", (FECHA,)).fetchall()
print("FLIPs de hoy: %d   |  minutos de TA disponibles: %d (%s -> %s)"
      % (len(flips), len(ta), min(ta), max(ta)))

# ---------- 1) recorrido del SPY tras cada giro, a horizonte fijo ----------
print("\n== 1) A FAVOR del giro, a horizonte fijo (centavos de SPY) ==")
print("  horiz |  n |  % a favor |  media  |  mediana |   p25    |   p75")
for H in (1, 2, 3, 5, 10, 15):
    movs = []
    for hora, estado, p0 in flips:
        t0 = mins(hora)
        if p0 is None:
            continue
        t1 = t0 + H
        if t1 not in ta or ta[t1] is None:
            continue
        d = ta[t1] - p0
        movs.append(d if estado == "UP" else -d)   # signo A FAVOR del giro
    if not movs:
        continue
    movs.sort()
    n = len(movs)
    fav = sum(1 for m in movs if m > 0) / n * 100.0
    media = sum(movs) / n
    med = movs[n // 2]
    print("  %4d m | %2d |   %5.1f%%   | %+7.3f | %+7.3f  | %+7.3f | %+7.3f"
          % (H, n, fav, media, med, movs[n // 4], movs[(3 * n) // 4]))

# ---------- 2) vida real de cada giro: del flip al SIGUIENTE flip ----------
print("\n== 2) VIDA REAL de cada giro (del flip al siguiente flip = lo que hace el bot hoy) ==")
recs = []
for i in range(len(flips) - 1):
    hora, estado, p0 = flips[i]
    hora2, _, _ = flips[i + 1]
    if p0 is None:
        continue
    t0, t1 = mins(hora), mins(hora2)
    if t1 <= t0:
        continue
    serie = [ta[t] for t in range(t0 + 1, t1 + 1) if t in ta and ta[t] is not None]
    if not serie:
        continue
    sig = 1.0 if estado == "UP" else -1.0
    favs = [(p - p0) * sig for p in serie]
    recs.append({"hora": hora, "estado": estado, "dur": t1 - t0,
                 "mfe": max(favs),          # maximo a favor alcanzado
                 "mae": min(favs),          # peor momento
                 "cierre": favs[-1]})       # con lo que se sale al girar
if recs:
    n = len(recs)
    tot_mfe = sum(r["mfe"] for r in recs)
    tot_cie = sum(r["cierre"] for r in recs)
    dejado = [r["mfe"] - r["cierre"] for r in recs]
    print("  episodios medibles: %d" % n)
    print("  duracion (min): mediana %d | media %.1f | max %d"
          % (sorted(r["dur"] for r in recs)[n // 2],
             sum(r["dur"] for r in recs) / n, max(r["dur"] for r in recs)))
    print("  MAXIMO a favor (MFE) : total %+.2f  media %+.3f" % (tot_mfe, tot_mfe / n))
    print("  AL CERRAR en el flip : total %+.2f  media %+.3f" % (tot_cie, tot_cie / n))
    print("  DEJADO SOBRE LA MESA : total %+.2f  media %+.3f  mediana %+.3f"
          % (sum(dejado), sum(dejado) / n, sorted(dejado)[n // 2]))
    print("  episodios que cerraron por DEBAJO de su maximo: %d de %d (%.0f%%)"
          % (sum(1 for d in dejado if d > 0.001), n,
             sum(1 for d in dejado if d > 0.001) / n * 100.0))
    print("  episodios que NUNCA estuvieron a favor (MFE<=0): %d (%.0f%%)"
          % (sum(1 for r in recs if r["mfe"] <= 0), sum(1 for r in recs if r["mfe"] <= 0) / n * 100.0))

    print("\n  -- los 8 giros con mayor recorrido a favor --")
    print("   hora     dir  dur  MFE(max)  cierre  dejado")
    for r in sorted(recs, key=lambda x: -x["mfe"])[:8]:
        print("   %s %4s %3dm  %+7.3f %+7.3f %+7.3f"
              % (r["hora"], r["estado"], r["dur"], r["mfe"], r["cierre"],
                 r["mfe"] - r["cierre"]))

# ---------- 3) simulacion: y si cerrara al llegar a X centavos a favor? ----------
print("\n== 3) SIMULACION: salir al tocar un objetivo fijo, vs esperar al flip ==")
print("  (mismo conjunto de episodios; el objetivo se da por tocado si el MFE lo alcanza)")
print("  objetivo | veces tocado |   total con objetivo  |  total esperando al flip")
for obj in (0.10, 0.20, 0.30, 0.50, 0.80, 1.00):
    tot = 0.0
    tocados = 0
    for r in recs:
        if r["mfe"] >= obj:
            tot += obj
            tocados += 1
        else:
            tot += r["cierre"]
    print("   %+.2f    |   %2d de %2d   |        %+8.2f       |        %+8.2f"
          % (obj, tocados, len(recs), tot, tot_cie))
