# -*- coding: utf-8 -*-
"""DERIVA + BAJAR EL LISTON.

(1) Mide el sesgo alcista del SPY (mean del movimiento a favor si SIEMPRE compras CALL) a
    varios horizontes, y el acierto direccional de 'siempre CALL'.
(2) Compara ese acierto contra el liston de equilibrio: 56.7% (capital 320) y 54.4% (capital 800).
(3) EV a 8 min con la economia conocida (delta 85$/pt, coste 2.22) para 320 y (escalado) 800.

LIMITE HONESTO (Regla 13): mantener una opcion 0DTE horas tiene theta no lineal que NO se puede
modelar solo con el precio del SPY (no hay historico de primas). Por eso el EV en $ solo es fiel
al horizonte ~8 min; a horizontes largos se reporta SOLO el acierto direccional y el movimiento.

Uso: python analisis/deriva_liston.py
"""
import os, sqlite3, sys, statistics as st
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = "historico_spy.db"; N_EXPLORA = 170
def mm(h): return int(h[:2]) * 60 + int(h[3:5])
OUT = []
def p(s=""):
    print(s); OUT.append(s)

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dias = {}
    for f, h, o, hi, lo, cl in c.execute(
            "select fecha,hora,open,high,low,close from bars_historico order by fecha,hora"):
        dias.setdefault(f, []).append((h, cl))
    c.close()
    orden = [f for f in sorted(dias) if len(dias[f]) >= 300]
    return orden, dias

def always_call(orden, dias, H):
    """acierto direccional y movimiento medio a favor de 'siempre CALL' a horizonte H (no solapado)."""
    favs = []
    for f in orden:
        b = dias[f]; horas = [x[0] for x in b]; close = [x[1] for x in b]; mins = [mm(x) for x in horas]
        i = 0; n = len(b)
        while i < n:
            if horas[i] >= "15:40": break
            fin = [k for k in range(i, n) if mins[k] >= mins[i] + H]
            if not fin: break
            k = fin[0]
            favs.append(close[k] - close[i])   # CALL: a favor si sube
            i = k
    n = len(favs)
    if n == 0:
        return 0.0, 0.0, 0
    acc = 100 * sum(1 for x in favs if x > 0) / n
    mfav = sum(favs) / n
    return acc, mfav, n

def main():
    orden, dias = carga()
    expl = orden[:N_EXPLORA]; resv = orden[N_EXPLORA:]
    p("=" * 92)
    p("DERIVA (siempre CALL) — acierto direccional y movimiento medio, por horizonte")
    p("  LISTON de equilibrio: 56.7% (capital 320)  |  54.4% (capital 800)")
    p("=" * 92)
    p(f"{'H(min)':>7} | {'EXPL acc%':>9} {'EXPL movfav':>12} {'EV8_320$':>9} {'EV8_800$':>9} | {'RESERVA acc%':>12} {'RES movfav':>11}   n_expl")
    for H in (8, 15, 30, 60, 120, 240, 390):
        ae, me, ne = always_call(expl, dias, H)
        ar, mr, nr = always_call(resv, dias, H)
        # EV solo fiel a 8 min. 320: delta 85, coste 2.22. 800: delta escalado ~ (para bajar liston a 54.4)
        # el agente dio los listones; para EV en $ a 8min uso delta 85 (320) y delta 85*(45.6/43.3) aprox (800)
        ev320 = 85.0 * me - 2.22 if H == 8 else float('nan')
        ev800 = (85.0 * 1.47) * me - 2.22 if H == 8 else float('nan')   # 800 da 1.47x el pago (dato del brief)
        s320 = f"{ev320:+9.2f}" if H == 8 else "   (n/a)"
        s800 = f"{ev800:+9.2f}" if H == 8 else "   (n/a)"
        p(f"{H:>7} | {ae:>9.1f} {me:>+12.4f} {s320} {s800} | {ar:>12.1f} {mr:>+11.4f}   {ne}")
    p("\nNOTA: EV en $ solo es fiel a H=8 (economia 0DTE conocida). A H largos, ver acierto+movimiento;")
    p("      el P&L real de mantener la opcion horas necesita historico de primas que NO tenemos.")
    p("=" * 92)
    os.makedirs("investigacion", exist_ok=True)
    with open(os.path.join("investigacion", "deriva_liston.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print("\nsalida en:", os.path.abspath(os.path.join('investigacion', 'deriva_liston.txt')))

if __name__ == "__main__":
    main()
