# -*- coding: utf-8 -*-
# FASE 4 — ¿CUANTAS SEÑALES DE reb2 CAPTA REALMENTE EL VIVO?  (diagnostico, sin motor)
#
# POR QUE: el techo en el motor dice que RETRASA vale +12.763$ (5.08 sigmas, mejora las 6
# metricas) e INVIERTE +13.640$. Y la regla de RETRASA NO es look-ahead: "flip -> toco la linea
# -> cuando el cierre se despega 1.5 ATR, entro" solo usa pasado (rebote.py:126-129).
#
# EL VIVO (sistema.py:246,254-255) recalcula construir_sen CADA MINUTO con la ventana crecida,
# pero solo consulta `Sen.get(h_dec)` con h_dec = minuto que acaba de cerrar. Y reb2 fecha la
# señal en hhmm(ks[j]) = INICIO del bucket j, que no esta completo hasta ks[j]+2.
# -> hay que comprobar SI ESAS DOS COSAS LLEGAN A COINCIDIR ALGUNA VEZ.
#
# Se simula el bucle real: para cada minuto t, barras hasta t, reb2 sobre esa ventana, y se
# comprueba si devuelve una señal fechada EXACTAMENTE en t (que es lo unico que el vivo mira).
import sqlite3, sys

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import sen_p, reb2, st_lin_p, _grupo
from sys2.core.supertrend import mm, hhmm

con = sqlite3.connect(RAIZ + r"\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
if len(sys.argv) > 1:
    k_ = int(sys.argv[1])
    FECHAS = FECHAS[::max(1, len(FECHAS) // k_)][:k_]
    print("MODO PRUEBA: %d dias" % len(FECHAS))

MINUTOS = 45          # ventana de simulacion tras el flip
tot = {}
det = []
for f in FECHAS:
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                       (f,)).fetchall()
    if len(bars) < 100:
        continue
    try:
        sp, L, ks = sen_p(bars, C.ST_PER, C.ST_MULT)
    except Exception:
        continue
    ik = {kk: i for i, kk in enumerate(ks)}
    for h, d in [(h, d) for h, d in sp if h >= "09:45"]:
        i = ik.get((mm(h) // 3) * 3)
        if i is None or i < 11 or i + 12 > len(ks) - 1:
            continue
        # (a) lo que decide reb2 con VISION COMPLETA (lo que mide el techo)
        r_full = reb2(L, ks, ik, h, d)
        g = _grupo(r_full, h, d)
        # (b) lo que el VIVO llega a ver: reb2 con ventana creciente, minuto a minuto,
        #     aceptando SOLO señales fechadas en el minuto que el vivo consulta (h_dec = t)
        capta = None
        for t in range(mm(h), mm(h) + MINUTOS):
            hb = hhmm(t)
            bb = [b for b in bars if b[0] <= hb]
            if len(bb) < 30:
                continue
            try:
                L2, ks2, _D2 = st_lin_p(bb, C.ST_PER, C.ST_MULT)
            except Exception:
                continue
            ik2 = {kk: q for q, kk in enumerate(ks2)}
            if (mm(h) // 3) * 3 not in ik2:
                continue
            r2 = reb2(L2, ks2, ik2, h, d)
            if r2 and r2[0][0] == hb:          # el vivo consulta EXACTAMENTE esta clave
                capta = (r2[0][0], r2[0][1], hb)
                break
        k = (g, "capta" if capta else "PIERDE")
        tot[k] = tot.get(k, 0) + 1
        if g in ("RETRASA", "INVIERTE"):
            det.append((f, h, d, g, r_full[0] if r_full else None, capta))

print("\n== ¿QUE CAPTA EL VIVO DE CADA DECISION DE reb2? ==")
print("%-10s %8s %8s %8s" % ("grupo", "capta", "PIERDE", "% captado"))
for g in ("NORMAL", "RETRASA", "INVIERTE", "DESCARTA"):
    c = tot.get((g, "capta"), 0)
    p = tot.get((g, "PIERDE"), 0)
    if c + p:
        print("%-10s %8d %8d %7.1f%%" % (g, c, p, 100.0 * c / (c + p)))

print("\n== ¿COINCIDE LO QUE CAPTA CON LO CORRECTO? (RETRASA/INVIERTE) ==")
ig = dis = 0
for f, h, d, g, full, cap in det:
    if cap is None:
        continue
    if full and cap[0] == full[0] and cap[1] == full[1]:
        ig += 1
    else:
        dis += 1
print("  identico a reb2 completo: %d   |   distinto (hora o direccion): %d" % (ig, dis))
print("\n  ejemplos (fecha, flip, dir, grupo, reb2_completo, lo_que_capta_el_vivo):")
for x in det[:12]:
    print("   ", x)
