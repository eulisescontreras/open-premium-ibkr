# -*- coding: utf-8 -*-
# FASE 3 — "PROBABILITY ENGINE" honesto: combinar las señales de la cadena de opciones.
#
# IDEA DEL USUARIO: que el sistema aprenda de su historial (2 años) para anticipar sus errores.
# RIESGO REAL: 1.520 flips y suelo de ruido +-5.000$ -> un modelo con muchas features encuentra
# "condicion A -> 73%" aunque los datos sean azar. Por eso aqui:
#   * los UMBRALES se calculan SOLO con el AÑO 1 (los cuantiles salen de A1, nunca de A2)
#   * el AÑO 2 se usa UNICAMENTE para evaluar -> out-of-sample estricto
#   * score = CONTEO de condiciones adversas (0..3). Interpretable y con pocos grados de
#     libertad; una logistica con 8 features sobre 750 muestras memorizaria.
#
# Señales (fase 2, todas disponibles EN EL MINUTO DEL FLIP, coste de tiempo cero):
#   costv  bajo  -> el mercado no cobra por el movimiento   (Q1 72.9% pierde vs Q5 34.1%)
#   ivatm  baja  -> mercado dormido                          (Q1 74.5% vs Q5 41.6%)
#   skew   alto  -> pagan proteccion CONTRA la direccion     (Q5 80.0% pierde)
import json, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(AQUI, "fase2_dataset.json")))
D = [x for x in D if x.get("neto") is not None]
fechas = sorted(set(x["f"] for x in D))
CORTE = fechas[len(fechas) // 2]
A1 = [x for x in D if x["f"] < CORTE]
A2 = [x for x in D if x["f"] >= CORTE]
print("dataset %d flips | A1 %d (%s..%s) | A2 %d (%s..%s)"
      % (len(D), len(A1), fechas[0], CORTE, len(A2), CORTE, fechas[-1]))
print("%% que pierden: global %.1f | A1 %.1f | A2 %.1f\n"
      % (100.0 * sum(x["malo"] for x in D) / len(D),
         100.0 * sum(x["malo"] for x in A1) / len(A1),
         100.0 * sum(x["malo"] for x in A2) / len(A2)))


def q(vals, p):
    v = sorted(vals)
    if not v:
        return None
    i = int(p * (len(v) - 1))
    return v[i]


# ── UMBRALES APRENDIDOS SOLO CON EL AÑO 1 ──
def umbral(campo, p):
    return q([x[campo] for x in A1 if x[campo] is not None], p)


for PCT in (0.20, 0.25, 0.30, 0.35):
    U_COST = umbral("costv", PCT)
    U_IV = umbral("ivatm", PCT)
    U_SKEW = umbral("skew", 1.0 - PCT)

    def score(x):
        s = 0
        if x["costv"] is not None and x["costv"] <= U_COST:
            s += 1
        if x["ivatm"] is not None and x["ivatm"] <= U_IV:
            s += 1
        if x["skew"] is not None and x["skew"] >= U_SKEW:
            s += 1
        return s

    print("=" * 78)
    print("UMBRALES APRENDIDOS EN A1 (percentil %d): costv<=%.3f  IV<=%.3f  skew>=%.3f"
          % (PCT * 100, U_COST, U_IV, U_SKEW))
    print("%-6s | %-28s | %-28s" % ("score", "AÑO 1 (entrenamiento)", "AÑO 2 (OUT-OF-SAMPLE)"))
    print("%-6s | %6s %8s %10s | %6s %8s %10s"
          % ("", "n", "%pierde", "pnl$med", "n", "%pierde", "pnl$med"))
    for s in (0, 1, 2, 3):
        s1 = [x for x in A1 if score(x) == s]
        s2 = [x for x in A2 if score(x) == s]
        f = lambda S: ("%6d %7.1f%% %10.0f" % (len(S), 100.0 * sum(x["malo"] for x in S) / len(S),
                                               sum(x["pnl"] for x in S) / len(S))) if S else \
                      ("%6d %8s %10s" % (0, "--", "--"))
        print("  %d    | %s | %s" % (s, f(s1), f(s2)))
    # regla operativa: descartar los flips con score >= 2
    for corte_s in (2, 3):
        d2 = [x for x in A2 if score(x) >= corte_s]
        r2 = [x for x in A2 if score(x) < corte_s]
        if not d2 or not r2:
            continue
        print("  -> DESCARTAR score>=%d en A2: quita %d de %d (%.1f%%), de los cuales pierden "
              "%.1f%% (resto %.1f%%)  | pnl medio evitado %.0f$"
              % (corte_s, len(d2), len(A2), 100.0 * len(d2) / len(A2),
                 100.0 * sum(x["malo"] for x in d2) / len(d2),
                 100.0 * sum(x["malo"] for x in r2) / len(r2),
                 sum(x["pnl"] for x in d2) / len(d2)))
    print()

# ── control de honestidad: ¿y si el score fuera aleatorio? ──
import random
random.seed(11)
U_COST, U_IV, U_SKEW = umbral("costv", 0.25), umbral("ivatm", 0.25), umbral("skew", 0.75)


def score(x):
    s = 0
    if x["costv"] is not None and x["costv"] <= U_COST:
        s += 1
    if x["ivatm"] is not None and x["ivatm"] <= U_IV:
        s += 1
    if x["skew"] is not None and x["skew"] >= U_SKEW:
        s += 1
    return s


real = [x for x in A2 if score(x) >= 2]
p_real = 100.0 * sum(x["malo"] for x in real) / len(real) if real else 0
sim = []
for _ in range(2000):
    m = random.sample(A2, len(real))
    sim.append(100.0 * sum(x["malo"] for x in m) / len(m))
sim.sort()
mejor = sum(1 for s in sim if s >= p_real)
print("=" * 78)
print("CONTROL — ¿el score bate al azar en A2?")
print("  score>=2 selecciona %d flips de A2 con %.1f%% de perdedores" % (len(real), p_real))
print("  muestras ALEATORIAS del mismo tamaño: mediana %.1f%%, percentil 95 %.1f%%"
      % (sim[1000], sim[1900]))
print("  p-valor (azar >= lo observado): %.4f  -> %s"
      % (mejor / 2000.0, "SEÑAL REAL" if mejor / 2000.0 < 0.05 else "NO distinguible del azar"))
