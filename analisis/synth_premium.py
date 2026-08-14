# -*- coding: utf-8 -*-
"""Sintetiza el premium 0DTE (contratos ITM completos) = intrinseco + extrinseco calibrado
con los contratos REALES guardados. Genera una BD premium_minute usable por el simulador.

VALIDACION END-TO-END: sintetiza el 08-13 (calibrando SOLO con 11+12, sin verlo) y corre el
simulador; compara el P&L sintetico vs el real (mid). Si coincide ~, el metodo sirve p/ 08-10.
"""
import os, sys, sqlite3, statistics as st
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from simulador_st import simular, FUENTES, CAPITAL_0
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
PMDB = R("spy_bars_pm.db")
DIAS = {"2026-08-11": "20260811", "2026-08-12": "20260812", "2026-08-13": "20260813"}


def spy_min(fk):
    con = sqlite3.connect(f"file:{PMDB}?mode=ro", uri=True)
    d = {h: c for h, c in con.execute(
        "select hora,close from bars_pm where fecha=? and hora>='09:30' and hora<='16:00'", (fk,))}
    con.close(); return d


def ttc(h): return 960 - (int(h[:2]) * 60 + int(h[3:5]))
def bkt(dep, t): return (round(dep * 2) / 2.0, round(t / 30.0) * 30)


def calibra(dias_cal):
    modelo = {}
    for fk in dias_cal:
        dk = DIAS[fk]; S = spy_min(fk)
        con = sqlite3.connect(f"file:{R('spy_history_'+dk+'.db')}?mode=ro", uri=True)
        rows = con.execute("select hora,strike,right,bid,ask from premium_minute "
                           "where fecha=? and expiry=? and bid is not null and ask is not null",
                           (fk, dk)).fetchall()
        con.close()
        for h, K, r, b, a in rows:
            if h not in S: continue
            s = S[h]; midr = (b + a) / 2.0
            intr = max(s - K, 0.0) if r == "C" else max(K - s, 0.0)
            dep = (s - K) if r == "C" else (K - s)
            modelo.setdefault(bkt(dep, t=ttc(h)), []).append(midr - intr)
    return {k: st.mean(v) for k, v in modelo.items()}


def extr(modelo, dep, t):
    b = bkt(dep, t)
    if b in modelo: return modelo[b]
    c = [k for k in modelo if k[0] == b[0]]
    if c: return modelo[min(c, key=lambda x: abs(x[1] - b[1]))]
    return 0.0   # sin info -> extrinseco 0 (deep ITM ~ intrinseco puro)


def genera_synth_db(fk, dk, modelo, dst, strikes_rango=12):
    """Genera premium_minute sintetico (bid=ask=mid) para todos los minutos RTH y strikes ~ATM."""
    S = spy_min(fk)
    if os.path.exists(dst): os.remove(dst)
    con = sqlite3.connect(dst)
    con.execute("CREATE TABLE premium_minute (fecha TEXT,hora TEXT,expiry TEXT,strike REAL,right TEXT,bid REAL,ask REAL)")
    filas = []
    for h, s in S.items():
        k0 = round(s)
        for K in range(k0 - strikes_rango, k0 + strikes_rango + 1):
            for r in ("C", "P"):
                intr = max(s - K, 0.0) if r == "C" else max(K - s, 0.0)
                dep = (s - K) if r == "C" else (K - s)
                mid = max(intr + extr(modelo, dep, ttc(h)), 0.01)
                filas.append((fk, h, dk, float(K), r, mid, mid))
    con.executemany("insert into premium_minute values (?,?,?,?,?,?,?)", filas)
    con.commit(); con.close()
    return len(filas)


if __name__ == "__main__":
    # VALIDACION END-TO-END: sintetiza 08-13 calibrando SOLO con 11+12 (sin verlo),
    # corre el simulador con premium sintetico y compara vs premium real (mid).
    F, DK = "2026-08-13", "20260813"
    modelo = calibra(["2026-08-11", "2026-08-12"])          # NO usa el 13
    dst = R("spy_prem_synth_20260813.db")
    n = genera_synth_db(F, DK, modelo, dst)
    print(f"premium sintetico 08-13: {n} filas (bid=ask=mid)  modelo de 11+12")

    # senales premarket reales del 08-13 (las que ya validamos)
    SEN = [("09:30", "P"), ("09:34", "C"), ("10:44", "P"), ("12:05", "C"),
           ("13:33", "P"), ("14:30", "C"), ("15:13", "P")]
    denso = R("spy_tape_20260813_denso.db")
    dbv_real = R(f"spy_history_{DK}.db")

    # REAL (mid)  vs  SINTETICO
    _, cap_real = simular(F, senales=SEN, db_velas=dbv_real, db_tape=denso, expiry=DK, mid=True, verbose=True)
    print(f"  REAL(mid)     08-13: {cap_real - CAPITAL_0:+.2f}$")
    print("  ---")
    _, cap_syn = simular(F, senales=SEN, db_velas=dst, db_tape=denso, expiry=DK, mid=True, verbose=True)
    print(f"  SINTETICO     08-13: {cap_syn - CAPITAL_0:+.2f}$")
    print(f"\n  DELTA sintetico-real: {cap_syn - cap_real:+.2f}$")
