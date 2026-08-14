# -*- coding: utf-8 -*-
"""08-13 con SUPERTREND AUTONOMO (senales=None, sin nada hard-codeado).
El ST(7,3) se calcula desde las velas reconstruidas del tape + trail + magnitud + capital.
Diferencial: tape VIVO (31k) vs tape DENSO IBKR (377k).

Aviso (R7): las velas del tape son RTH puro (09:30-15:59, SIN premarket) -> el ATR
arranca en 09:30; el ST puede no coincidir con las senales reales del Webull.
Es la corrida AUTONOMA honesta.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from simulador_st import simular, carga, supertrend, FUENTES, CAPITAL_0

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DENSO = os.path.join(RAIZ, "spy_tape_20260813_denso.db")
F = "2026-08-13"
dbv, dbt_vivo, exp = FUENTES[F]


def senales_st(db_tape):
    B, P, NET = carga(F, dbv, db_tape, exp)
    D = supertrend(B, 7, 3.0, -1)
    flips = [(B[i][0], "C" if D[i] == 1 else "P") for i in range(1, len(B)) if D[i] != D[i-1]]
    return flips


def corre(nombre, db_tape):
    print("\n" + "=" * 78)
    print(f"{nombre}")
    print("=" * 78)
    flips = senales_st(db_tape)
    print(f"  senales ST(7,3): {len(flips)}  ->  " + "  ".join(f"{h}{r}" for h, r in flips))
    ops, cap = simular(F, senales=None, db_velas=dbv, db_tape=db_tape, expiry=exp, verbose=True)
    g = cap - CAPITAL_0
    print(f"  {F}: {len(ops)} ops   {g:+.2f}$")
    return g


gv = corre("VIVO  ·  ST autonomo (spy_tape_20260813.db, 31k)", dbt_vivo)
gd = corre("DENSO ·  ST autonomo (descarga IBKR, 377k)", DENSO)

print("\n" + "=" * 78)
print(f"DIFERENCIAL  ST autonomo   vivo {gv:+.2f}$   vs   denso {gd:+.2f}$   (delta {gd-gv:+.2f}$)")
print("=" * 78)
