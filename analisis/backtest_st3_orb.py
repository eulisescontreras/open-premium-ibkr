# -*- coding: utf-8 -*-
"""BACKTEST COMPLETO ST-3 + ORB — reproduce el resultado titular del sistema.

    python analisis/backtest_st3_orb.py                 # resultado titular
    python analisis/backtest_st3_orb.py ventanas        # A/B  <09:45 vs <=09:45
    python analisis/backtest_st3_orb.py capital         # barrido de size_cap
    python analisis/backtest_st3_orb.py dias            # P&L por sesion a CSV

CIFRA DE REFERENCIA (2026-08-14), premium SINTETICO:

    AÑO1  2024-07-31..2025-07-31   251 sesiones   +13.983$
    AÑO2  2025-08-01..2026-08-13   260 sesiones   +11.786$   (reserva OOS)
    TOTAL                          511 sesiones   +25.769$

⚠️ OJO CON EL UNIVERSO: spy_bars_year.db tiene 261 dias y spy_bars_year2.db 251,
   suman 512, pero 2025-07-31 esta DUPLICADO en ambas con barras identicas.
   La union son 511 sesiones unicas. Este script deduplica por fecha.
   Contar el duplicado infla el total en +115$ (+25.885$ en vez de +25.769$).

⚠️ EL PREMIUM ES SINTETICO. Calibrado con 3 dias (2026-08-11/12/13) y extrapolado
   a 2 años. NADA de esto esta validado contra precios reales. Ese es el gate.

Requiere en la raiz del repo:
    spy_bars_year.db, spy_bars_year2.db, spy_bars_pm.db
    analisis/: synth_premium.py, year_backtest.py, exp_trail_2min.py,
               exp_timing_realista.py, simulador_st.py
"""
import os
import sqlite3
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "analisis"))
os.chdir(RAIZ)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from simulador_st import simular, CAPITAL_0          # noqa: E402
from synth_premium import calibra                     # noqa: E402
from year_backtest import st_dir                      # noqa: E402
from exp_trail_2min import build_tmp, TMP             # noqa: E402
from exp_timing_realista import shift_sen             # noqa: E402

DIAS_CALIBRACION = ["2026-08-11", "2026-08-12", "2026-08-13"]
CORTE_ANIOS = "2025-08-01"
SIZE_CAP = 400.0          # FIJO por operacion, NO compuesto dentro del dia
MAX_TRADES = 4
ORB_RANGO_MIN = 0.75
BDS = ("spy_bars_year2.db", "spy_bars_year.db")      # year2 = cronologicamente PRIMERO


def mm(h):
    return int(h[:2]) * 60 + int(h[3:5])


def hhmm(m):
    return f"{m//60:02d}:{m%60:02d}"


# ---------------------------------------------------------------- señales
def sen_principal(bars):
    """ST-3(7, 3.0), ATR calentado con premarket, timing realista (+3 min).
       Solo señales desde las 09:45."""
    buck = {}
    for h, hi, lo, cl in bars:
        s = (mm(h) // 3) * 3
        a = buck.setdefault(s, {"hi": hi, "lo": lo, "cl": cl})
        a["hi"] = max(a["hi"], hi)
        a["lo"] = min(a["lo"], lo)
        a["cl"] = cl
    ks = sorted(buck)
    D = st_dir([buck[s]["hi"] for s in ks],
               [buck[s]["lo"] for s in ks],
               [buck[s]["cl"] for s in ks])
    HO = [hhmm(s) for s in ks]
    out = []
    prev = None
    for i in range(len(ks)):
        if HO[i] < "09:30" or HO[i] > "16:00" or D[i] == 0:
            continue
        if prev is None or D[i] != prev:
            out.append((HO[i], "C" if D[i] > 0 else "P"))
        prev = D[i]
    return [(h, d) for h, d in shift_sen(out, 3) if h >= "09:45"]


def orb_senal(bars, rango_min=ORB_RANGO_MIN, hasta="09:45"):
    """Rango 09:30-09:39 con HIGH/LOW (solo RTH, sin premarket).
       Disparo: primer CIERRE fuera del rango, con 09:40 <= hora < hasta.
       REVERSION: rompe arriba -> PUT, rompe abajo -> CALL."""
    B = [(h, hi, lo, cl) for h, hi, lo, cl in bars if "09:30" <= h < hasta]
    ini = [x for x in B if mm(x[0]) < 580]           # < 09:40
    if not ini:
        return []
    hi = max(x[1] for x in ini)
    lo = min(x[2] for x in ini)
    if (hi - lo) < rango_min:                        # MENOR ESTRICTO
        return []
    for h, H, L, C in B:
        if mm(h) < 580:
            continue
        if C > hi:
            return [(h, "P")]
        if C < lo:
            return [(h, "C")]
    return []


# ------------------------------------------------------------------ datos
_CACHE = {}


def sesiones():
    """Devuelve [(fecha, bars_con_premarket, rth)] DEDUPLICADO por fecha."""
    if "d" not in _CACHE:
        vistos = set()
        L = []
        for db in BDS:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            for (fk,) in con.execute("select distinct fecha from bars order by fecha"):
                if fk in vistos:            # 2025-07-31 esta en las dos BD
                    continue
                vistos.add(fk)
                bars = con.execute(
                    "select hora,high,low,close from bars where fecha=? order by hora",
                    (fk,)).fetchall()
                rth = [(h, cl, hi, lo, cl) for (h, hi, lo, cl) in bars
                       if "09:30" <= h <= "16:00"]
                if len(rth) < 300:
                    continue
                L.append((fk, bars, rth))
            con.close()
        L.sort(key=lambda x: x[0])
        _CACHE["d"] = L
    return _CACHE["d"]


# --------------------------------------------------------------- backtest
def corre(usar_orb=True, max_trades=MAX_TRADES, size_cap=SIZE_CAP,
          orb_hasta="09:45", orb_rango_min=ORB_RANGO_MIN, modelo=None):
    """Devuelve {fecha: pnl}, {fecha: n_ops}, n_dias_con_orb."""
    if modelo is None:
        modelo = calibra(DIAS_CALIBRACION)
    P = {}
    N = {}
    n_orb = 0
    for fk, bars, rth in sesiones():
        dk = fk.replace("-", "")
        build_tmp(modelo, fk, dk, rth)
        p = sen_principal(bars)
        s = orb_senal(bars, orb_rango_min, orb_hasta) if usar_orb else []
        if s:
            n_orb += 1
        sen = sorted(s + p)
        if not sen:
            P[fk] = 0.0
            N[fk] = 0
            continue
        ops, cap = simular(fk, senales=sen, trail=99.0, db_velas=TMP, db_tape=None,
                           expiry=dk, mid=False, mag_umbral=None,
                           size_cap=size_cap, salir_en_flip=True,
                           max_trades=max_trades)
        P[fk] = cap - CAPITAL_0
        N[fk] = len(ops)
    if os.path.exists(TMP):
        os.remove(TMP)
    return P, N, n_orb


def resume(P, etiqueta):
    F = sorted(P)
    A1 = [f for f in F if f < CORTE_ANIOS]
    A2 = [f for f in F if f >= CORTE_ANIOS]
    s1, s2 = sum(P[f] for f in A1), sum(P[f] for f in A2)
    print(f"  {etiqueta:>34}  A1 {s1:>+9.0f}$ ({len(A1)})  "
          f"A2 {s2:>+9.0f}$ ({len(A2)})  TOTAL {s1+s2:>+9.0f}$")
    return s1, s2


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "titular"
    modelo = calibra(DIAS_CALIBRACION)
    print(f"sesiones unicas: {len(sesiones())}   (511 esperadas)")
    print()

    if modo == "titular":
        print("RESULTADO TITULAR")
        Pb, _, _ = corre(usar_orb=False, max_trades=None, modelo=modelo)
        resume(Pb, "ST-3 puro")
        Pm, _, _ = corre(usar_orb=False, modelo=modelo)
        resume(Pm, "+ max_trades=4")
        Po, No, n = corre(usar_orb=True, modelo=modelo)
        s1, s2 = resume(Po, "+ ORB apertura  <-- SISTEMA")
        print()
        print(f"  dias con señal ORB: {n} de {len(sesiones())}")
        v = sorted(Po.values(), reverse=True)
        print(f"  T2: total {sum(v):+.0f}$ | sin 5 {sum(v[5:]):+.0f}$ | sin 10 {sum(v[10:]):+.0f}$")
        print()
        print(f"  ESPERADO: A1 +13983$ | A2 +11786$ | TOTAL +25769$")
        ok = abs(s1 - 13983) < 1 and abs(s2 - 11786) < 1
        print(f"  {'OK — REPRODUCE' if ok else '*** NO REPRODUCE ***'}")

    elif modo == "ventanas":
        print("A/B DE LA VENTANA DEL ORB")
        for hasta in ("09:45", "09:46"):
            P, _, n = corre(orb_hasta=hasta, modelo=modelo)
            nom = "< 09:45 (estricta, SPEC)" if hasta == "09:45" else "<= 09:45 (antigua)"
            resume(P, f"{nom}  [{n} dias]")

    elif modo == "capital":
        print("BARRIDO DE size_cap  (indicio de sesgo del premium sintetico)")
        for cap in (200.0, 300.0, 400.0, 600.0, 800.0):
            P, _, _ = corre(size_cap=cap, modelo=modelo)
            resume(P, f"size_cap = {cap:.0f}$")

    elif modo == "dias":
        Po, No, _ = corre(modelo=modelo)
        ruta = os.path.join("investigacion", "backtest_st3_orb_por_dia.csv")
        os.makedirs("investigacion", exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write("fecha,pnl,n_ops\n")
            for f in sorted(Po):
                fh.write(f"{f},{Po[f]:.2f},{No[f]}\n")
        print(f"escrito: {os.path.abspath(ruta)}")


if __name__ == "__main__":
    main()
