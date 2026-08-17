# -*- coding: utf-8 -*-
"""Los 4 TESTS OBLIGATORIOS de validación de reglas (MANUAL §2.1). Transcripción VERBATIM.
Cada test compara `base` (sistema SIN la regla) vs `nuevo` (sistema CON la regla), ambos
dict {fecha: pnl_dia}. Una regla que no pasa los 4 es RUIDO y se rechaza.

  TEST 1 — Bloques cronológicos: 4 bloques de ~121 días; la regla mejora en >=3 de 4.
  TEST 2 — Quitar los mejores días (5/10/20): el aporte debe seguir siendo positivo.
  TEST 3 — Permutación: barajar las diferencias día a día; exigir p<0.05.
           (⚠️ pierde poder si la regla afecta TODAS las ops -> fiarse de 1,2,4.)
  TEST 4 — % de días afectados que mejoran: exigir >=60%.
OBLIGATORIO: antes de modificar, leer el MANUAL §2.1 y correr cr_validacion.py.
"""
import random


def test1_bloques(base, nuevo):
    """>=3 de 4 bloques cronológicos mejoran. Devuelve (pasa, mejoras)."""
    F = sorted(set(base) & set(nuevo))
    q = len(F) // 4
    mejoras = 0
    for i in range(4):
        B = F[i * q:(i + 1) * q] if i < 3 else F[3 * q:]
        if sum(nuevo[f] for f in B) > sum(base[f] for f in B):
            mejoras += 1
    return mejoras >= 3, mejoras


def test2_mejores_dias(base, nuevo, ks=(5, 10, 20)):
    """Quitar los k mejores días de cada serie; el aporte debe seguir positivo.
    Devuelve (pasa, {k: aporte_sin_k})."""
    v_base = sorted(base.values(), reverse=True)
    v_nuevo = sorted(nuevo.values(), reverse=True)
    ap = {}
    ok = True
    for k in ks:
        aporte = sum(v_nuevo[k:]) - sum(v_base[k:])
        ap[k] = aporte
        if aporte <= 0:
            ok = False
    return ok, ap


def test3_permutacion(base, nuevo, n=3000, semilla=12345):
    """p = fracción de permutaciones del azar que igualan/superan el aporte real. p<0.05.
    Devuelve (pasa, p, n_afectados)."""
    F = sorted(set(base) & set(nuevo))
    difs = [nuevo[f] - base[f] for f in F]
    afectados = [f for f in F if abs(nuevo[f] - base[f]) > 1]
    real = sum(nuevo.values()) - sum(base.values())
    if not afectados:
        return False, 1.0, 0
    rnd = random.Random(semilla)
    superan = sum(1 for _ in range(n)
                  if sum(rnd.choice(difs) for _ in range(len(afectados))) >= real)
    p = superan / n
    return p < 0.05, p, len(afectados)


def test4_pct_mejoran(base, nuevo, umbral=60.0):
    """De los días donde la regla cambia algo, % que mejora. Exigir >=60%.
    Devuelve (pasa, pct, n_afectados)."""
    F = sorted(set(base) & set(nuevo))
    afectados = [f for f in F if abs(nuevo[f] - base[f]) > 1]
    if not afectados:
        return False, 0.0, 0
    pct = 100.0 * sum(1 for f in afectados if nuevo[f] > base[f]) / len(afectados)
    return pct >= umbral, pct, len(afectados)


def valida_regla(base, nuevo, nombre=""):
    """Corre los 4 tests. Devuelve dict con resultados y `pasa_todos` (1,2,4; el 3 es
    informativo por su pérdida de poder cuando la regla afecta a todas las ops)."""
    t1 = test1_bloques(base, nuevo)
    t2 = test2_mejores_dias(base, nuevo)
    t3 = test3_permutacion(base, nuevo)
    t4 = test4_pct_mejoran(base, nuevo)
    aporte = sum(nuevo.values()) - sum(base.values())
    return {
        "nombre": nombre, "aporte": aporte,
        "test1": t1, "test2": t2, "test3": t3, "test4": t4,
        # criterio duro = tests 1, 2 y 4 (el 3 es informativo por §2.1)
        "pasa": t1[0] and t2[0] and t4[0],
    }
