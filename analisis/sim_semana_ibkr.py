# -*- coding: utf-8 -*-
"""SEMANA "TODO IBKR": para cada dia -> ST(7,3) premarket (spy_bars_pm.db) + simulador real
con tape denso IBKR + premium_minute real. Corre los dias con tape listo; marca PENDIENTE
los que aun se descargan.

  senales  = ST premarket (velas useRTH=False)          [el ST correcto]
  tape     = descarga densa IBKR (spy_tape.db por fecha) [magnitud + cierres del trail]
             08-12: usa spy_tape_ayer.db (live 380k) hasta que baje su version IBKR
  premium  = spy_history_YYYYMMDD.db (bid/ask reales 0DTE)
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from simulador_st import simular, CAPITAL_0
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)
PMDB = R("spy_bars_pm.db")
TAPE = R("spy_tape.db")
DIAS = ["20260810", "20260811", "20260812", "20260813"]
P, MULT = 7, 3.0


def supertrend(hi, lo, cl, p, mult):
    """COPIA VERBATIM de st_check_premarket.py (ST que reprodujo el Webull)."""
    n = len(cl); tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    atr = [None] * n
    if n > p:
        atr[p] = sum(tr[1:p + 1]) / p
        for i in range(p + 1, n):
            atr[i] = (atr[i - 1] * (p - 1) + tr[i]) / p
    tend = [0] * n; fu = fl = None; d = 1
    for i in range(n):
        if atr[i] is None:
            continue
        med = (hi[i] + lo[i]) / 2
        bu = med + mult * atr[i]; bl = med - mult * atr[i]
        fu = bu if (fu is None or bu < fu or cl[i - 1] > fu) else fu
        fl = bl if (fl is None or bl > fl or cl[i - 1] < fl) else fl
        if d == 1 and cl[i] < fl: d = -1
        elif d == -1 and cl[i] > fu: d = 1
        tend[i] = d
    return tend


def senales_pm(fkey):
    con = sqlite3.connect(f"file:{PMDB}?mode=ro", uri=True)
    b = con.execute("select hora,high,low,close from bars_pm where fecha=? order by hora", (fkey,)).fetchall()
    con.close()
    if not b:
        return None
    hi = [x[1] for x in b]; lo = [x[2] for x in b]; cl = [x[3] for x in b]; ho = [x[0] for x in b]
    tend = supertrend(hi, lo, cl, P, MULT)
    out = []; prev = None
    for i in range(len(b)):
        if ho[i] < "09:30" or ho[i] > "16:00":
            continue
        d = tend[i]
        if d == 0:
            continue
        if prev is None or d != prev:
            out.append((ho[i], "C" if d > 0 else "P"))
        prev = d
    return out


def tape_dense_db(dkey, fkey):
    """Devuelve ruta a un trades_raw denso para el dia, o None si el tape no esta listo.
       08-12: fallback a spy_tape_ayer.db (live) si su descarga IBKR aun no esta."""
    con = sqlite3.connect(f"file:{TAPE}?mode=ro", uri=True)
    listo = con.execute("select count(*) from dias_listos where fecha=?", (fkey,)).fetchone()[0]
    con.close()
    if listo:
        dst = R(f"spy_tape_{dkey}_denso.db")
        if not os.path.exists(dst):
            src = sqlite3.connect(f"file:{TAPE}?mode=ro", uri=True)
            filas = src.execute("select substr(ts,12,8), substr(ts,12,5), price, size from trades "
                                "where fecha=? and price is not null and size is not null and size>0 "
                                "order by ts", (fkey,)).fetchall()
            src.close()
            d = sqlite3.connect(dst)
            d.execute("CREATE TABLE trades_raw (ts_et TEXT, minuto TEXT, price REAL, size REAL, exchange TEXT, cond TEXT)")
            d.executemany("insert into trades_raw values (?,?,?,?,NULL,NULL)", filas)
            d.commit(); d.close()
        return dst, f"IBKR denso ({dkey})"
    if dkey == "20260812" and os.path.exists(R("spy_tape_ayer.db")):
        return R("spy_tape_ayer.db"), "live 380k (respaldo)"
    return None, "PENDIENTE (tape bajando)"


print("=" * 92)
print("SEMANA  ·  ST premarket IBKR + tape denso + premium real  ·  cada dia arranca en $400")
print("=" * 92)
cap_comp = CAPITAL_0
resultados = []
for dkey in DIAS:
    fkey = f"{dkey[:4]}-{dkey[4:6]}-{dkey[6:]}"
    sen = senales_pm(fkey)
    tape, origen = tape_dense_db(dkey, fkey)
    print(f"\n### {fkey}   tape: {origen}")
    if sen is None:
        print("   sin velas premarket -> SKIP"); continue
    print(f"   ST(7,3) premarket: {len(sen)} sen -> " + "  ".join(f"{h}{r}" for h, r in sen))
    if tape is None:
        print("   tape no disponible aun -> PENDIENTE"); resultados.append((fkey, None)); continue
    ops, cap = simular(fkey, senales=sen, db_velas=R(f"spy_history_{dkey}.db"),
                       db_tape=tape, expiry=dkey, verbose=True)
    g = cap - CAPITAL_0
    print(f"   {fkey}: {len(ops)} ops   {g:+.2f}$  (desde $400)")
    resultados.append((fkey, g))
    if g is not None:
        cap_comp += g

print("\n" + "=" * 92)
hechos = [(f, g) for f, g in resultados if g is not None]
tot = sum(g for _, g in hechos)
for f, g in hechos:
    print(f"   {f}: {g:+.2f}$")
pend = [f for f, g in resultados if g is None]
print(f"\n   TOTAL dias corridos: {tot:+.2f}$   ({len(hechos)} dias)")
if pend:
    print(f"   PENDIENTES (tape bajando): {', '.join(pend)}")
print(f"   Capital compuesto semana (desde $400): ${cap_comp:.2f}")
print("=" * 92)
