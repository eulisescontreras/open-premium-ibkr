"""
significancia.py — READ-ONLY

La pregunta que decide si algo de lo anterior sirve:

    ¿El mejor resultado del barrido es mayor que el mejor resultado que sale
    barajando los datos al azar?

Se probaron ~33 variables x 6 horizontes = ~200 combinaciones. Con 200 intentos,
que UNA salga con +5 puntos de lift es lo NORMAL aunque no haya ninguna senal.
Esto es el problema de las comparaciones multiples, y es exactamente la trampa
que ya hizo caer al "8/9 = 89% de acierto" en ANALISIS_ENTRADA_SALIDA.md.

Metodo (test de permutacion, no parametrico, sin supuestos):
  1. Se mide el LIFT MEDIO MAXIMO observado sobre todas las variables/horizontes.
  2. Se baraja el retorno futuro (rompiendo cualquier relacion con las variables)
     y se repite TODO el barrido. N veces.
  3. Si el maximo real cae dentro de la nube de maximos barajados -> es ruido.

Tambien imprime el error estandar de cada candidato: con n observaciones
independientes, un lift menor que ~2 sigma no es distinguible de cero.
"""
import sys
import os
import math
import random
import sqlite3
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from direccion_premium import DB, HORIZONTES
from direccion_foco import recoger

N_PERM = 200
random.seed(12345)          # reproducible


def muestras_por_feature(muestras, precio, horiz):
    """feat -> [(valor, retorno, minuto)] con retorno != 0."""
    out = defaultdict(list)
    for m, ff in muestras:
        if m not in precio or (m + horiz) not in precio:
            continue
        ret = precio[m + horiz] - precio[m]
        if ret == 0:
            continue
        for k, v in ff.items():
            if k.startswith("_") or v is None or v == 0:
                continue
            out[k].append((v, ret, m))
    return out


def lift_medio(pares, min_lado=10):
    n = len(pares)
    if n < 30:
        return None
    base_up = sum(1 for _, r, _ in pares if r > 0) / n
    up = [p for p in pares if p[0] > 0]
    dn = [p for p in pares if p[0] < 0]
    if len(up) < min_lado or len(dn) < min_lado:
        return None
    p_up = sum(1 for _, r, _ in up if r > 0) / len(up)
    p_dn = sum(1 for _, r, _ in dn if r < 0) / len(dn)
    return ((p_up - base_up) + (p_dn - (1 - base_up))) / 2 * 100


def nosolapado(pares, horiz):
    k, ult = 0, -10 ** 9
    for _, _, m in sorted(pares, key=lambda t: t[2]):
        if m - ult >= horiz:
            k += 1
            ult = m
    return k


def main():
    db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    c = db.cursor()
    fechas = [f for (f,) in c.execute(
        "SELECT DISTINCT fecha FROM premium_minute ORDER BY fecha")]

    # pool de las dos fechas, por horizonte
    pool = {h: defaultdict(list) for h in HORIZONTES}
    for f in fechas:
        muestras, precio = recoger(c, f)
        for h in HORIZONTES:
            for k, v in muestras_por_feature(muestras, precio, h).items():
                pool[h][k].extend(v)
    db.close()

    # ---------------- 1. error estandar de los candidatos
    print("=" * 92)
    print("¿SUPERA CADA CANDIDATO SU PROPIO MARGEN DE ERROR?")
    print("(sigma = error estandar del lift con las observaciones NO SOLAPADAS)")
    print("=" * 92)
    print("%-26s %6s %7s %8s %8s %8s   %s" %
          ("variable", "horiz", "lift", "n", "n_indep", "sigma", "veredicto"))
    print("-" * 92)
    reales = []
    for h in HORIZONTES:
        for k, pares in pool[h].items():
            lm = lift_medio(pares)
            if lm is None:
                continue
            reales.append((abs(lm), lm, k, h, pares))
    reales.sort(reverse=True)
    for _, lm, k, h, pares in reales[:12]:
        ni = nosolapado(pares, h)
        sigma = math.sqrt(0.25 / ni) * 100 if ni else 999
        z = abs(lm) / sigma if sigma else 0
        ver = "SIGNIFICATIVO" if z >= 2 else ("marginal" if z >= 1.5 else "RUIDO")
        print("%-26s %6d %+7.1f %8d %8d %8.1f   %s (z=%.1f)" %
              (k, h, lm, len(pares), ni, sigma, ver, z))

    # ---------------- 2. permutacion sobre TODO el barrido
    mejor_real = reales[0][0] if reales else 0.0
    print("\n" + "=" * 92)
    print("TEST DE PERMUTACION SOBRE EL BARRIDO COMPLETO (%d repeticiones)" % N_PERM)
    print("=" * 92)
    print("Mejor |lift medio| REAL de todo el barrido: %+.1f  (%s, %d min)"
          % (reales[0][1], reales[0][2], reales[0][3]))

    # ⚠️ La permutacion NO puede ser un shuffle plano. Dos ventanas de 30 min
    # separadas 1 minuto comparten 29 minutos de retorno: los datos estan
    # fuertemente autocorrelados. Barajar destruye esa estructura y produce una
    # nula DEMASIADO ESTRECHA -> significancia inventada.
    # Nula correcta: DESPLAZAMIENTO CIRCULAR de la serie de retornos. Conserva
    # intacta la autocorrelacion y solo rompe la alineacion con las variables.
    maximos = []
    for it in range(N_PERM):
        despl = {}
        mx = 0.0
        for h in HORIZONTES:
            for k, pares in pool[h].items():
                if len(pares) < 30:
                    continue
                orden = sorted(pares, key=lambda t: t[2])
                n = len(orden)
                if (h, k) not in despl:
                    despl[(h, k)] = random.randint(n // 10, n - n // 10) if n > 20 else 1
                d = despl[(h, k)]
                rot = [orden[(i + d) % n][1] for i in range(n)]
                girado = [(orden[i][0], rot[i], orden[i][2]) for i in range(n)]
                lm = lift_medio(girado)
                if lm is not None and abs(lm) > mx:
                    mx = abs(lm)
        maximos.append(mx)

    maximos.sort()
    p95 = maximos[int(len(maximos) * .95)]
    p99 = maximos[int(len(maximos) * .99)]
    peores = sum(1 for m in maximos if m >= mejor_real)
    print("Maximo |lift| obtenido BARAJANDO (puro azar):")
    print("   mediana=%.1f   p95=%.1f   p99=%.1f   maximo=%.1f"
          % (maximos[len(maximos) // 2], p95, p99, maximos[-1]))
    print("   barajadas que igualan o superan al resultado real: %d de %d  ->  p = %.3f"
          % (peores, N_PERM, peores / N_PERM))
    print()
    if mejor_real > p95:
        print(">>> El mejor resultado real SUPERA el percentil 95 del azar.")
        print(">>> Hay algo. Sigue haciendo falta mas dias para fijarlo.")
    else:
        print(">>> El mejor resultado real NO supera lo que sale barajando al azar.")
        print(">>> Con estos datos, NINGUNA variable de premium determina la direccion.")
        print(">>> No es que la senal sea mala: es que no se puede distinguir de ruido.")


if __name__ == "__main__":
    main()
