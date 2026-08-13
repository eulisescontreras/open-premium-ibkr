# VALIDACION A CIEGAS: el sistema calibrado con el 08-13 aplicado al 08-12 sin tocar nada.
#
# Unico ajuste, y es obligado: el umbral de entrada pasa de "1.0 M$/min" a "1x la mediana del
# propio dia". Las dos fuentes de tape cuentan cosas distintas (RTVolume en vivo vs tick-by-tick
# historico: 40x mas ticks), asi que un valor absoluto no es transferible. El resto -direccion
# a 5 min, salidas, tope de capital- es identico.
#
# 08-13: tape de spy_history.db (grupo SPY, agresor por bid/ask en vivo)
# 08-12: tape de spy_tape_ayer.db (descargado de IBKR, agresor por regla del tick)
import sqlite3
import statistics as st

TXT = "VALIDACION.txt"
DIR_MIN, VENT = 5, 5
CAPITAL, FRAC = 400.0, 0.80
TOPE = CAPITAL * FRAC


def cargar(dia):
    src = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    velas = src.execute("select hora,high,low,close from bars_minute where fecha=? "
                        "order by hora", (dia,)).fetchall()
    pm = src.execute("select hora,strike,right,bid,ask,mid from premium_minute where fecha=? "
                     "and expiry=?", (dia, dia.replace("-", ""))).fetchall()
    # AMBOS dias salen de una BD con el MISMO esquema (trades_raw) y se les aplica la MISMA
    # regla del tick. Asi la unica diferencia que queda es la granularidad de la fuente
    # (RTVolume en vivo vs tick-by-tick historico), no el metodo de clasificacion.
    src.close()
    d = sqlite3.connect(f"spy_tape_{dia.replace('-', '')}.db")
    filas = d.execute("select minuto, price, size from trades_raw "
                      "order by ts_et, rowid").fetchall()
    d.close()
    if True:
        acc = {}
        pp = ps = None
        for minuto, price, size in filas:
            if pp is None:
                ag = None
            elif price > pp:
                ag = 1
            elif price < pp:
                ag = -1
            else:
                ag = ps
            if ag:
                ps = ag
            pp = price
            c, v = acc.get(minuto, (0.0, 0.0))
            imp = price * size
            acc[minuto] = (c + imp if ag == 1 else c, v + imp if ag == -1 else v)
        tp = acc
    PR = {}
    for hora, k, r, b, a, m in pm:
        PR.setdefault(hora, {})[(k, r)] = (b, a, m)
    return velas, tp, PR


def analizar(dia):
    velas, tp, PR = cargar(dia)
    h = [x[0] for x in velas]
    hi = [x[1] for x in velas]
    lo = [x[2] for x in velas]
    cl = [x[3] for x in velas]
    n = len(velas)
    net = [tp.get(x, (0, 0))[0] - tp.get(x, (0, 0))[1] for x in h]
    med = st.median([abs(x) for x in net if x]) or 1.0
    ENT = med          # umbral = 1x la mediana del propio dia

    def fmov(i):
        return None if i < VENT - 1 else sum(net[i - VENT + 1:i + 1]) / VENT

    def salida(e_i, lado, modo, par):
        mejor = cl[e_i]
        for i in range(e_i + 1, n):
            mejor = max(mejor, cl[i]) if lado > 0 else min(mejor, cl[i])
            if modo == "PCT":
                fuera = (cl[i] <= mejor * (1 - par / 100)) if lado > 0 else \
                        (cl[i] >= mejor * (1 + par / 100))
            else:
                fuera = (cl[i] < min(lo[max(e_i, i - par):i])) if lado > 0 else \
                        (cl[i] > max(hi[max(e_i, i - par):i]))
            if fuera:
                return i
        return n - 1

    def elegir_itm(i, right):
        d = PR.get(h[i], {})
        px = cl[i]
        ks = sorted([k for (k, r) in d if r == right and (k < px if right == "C" else k > px)],
                    reverse=(right == "P"))
        for k in ks:
            b, a, m = d[(k, right)]
            coste = a or m
            if coste and coste > 0 and coste * 100 <= TOPE:
                return k
        cands = [k for (k, r) in d if r == right]
        return min(cands, key=lambda k: abs(k - px)) if cands else None

    def dinero(e_i, s_i, lado):
        right = "C" if lado > 0 else "P"
        k = elegir_itm(e_i, right)
        if k is None:
            return None
        de, ds = PR.get(h[e_i], {}).get((k, right)), PR.get(h[s_i], {}).get((k, right))
        if not de or not ds:
            return None
        pe, psx = (de[1] or de[2]), (ds[0] or ds[2])
        if not pe or not psx or pe <= 0:
            return None
        nc = int(TOPE // (pe * 100))
        return ((psx - pe) * 100 * nc) if nc >= 1 else None

    # entradas (con la salida de referencia: extremo 20m)
    entradas, pos, e_i = [], 0, 0
    for i in range(DIR_MIN, n):
        f = fmov(i)
        if f is None:
            continue
        d = cl[i] - cl[i - DIR_MIN]
        sg = 1 if d > 0 else (-1 if d < 0 else 0)
        if pos == 0:
            if f >= ENT and sg != 0:
                pos, e_i = sg, i
                entradas.append((i, sg))
            continue
        if (cl[i] < min(lo[max(e_i, i - 20):i])) if pos > 0 else \
           (cl[i] > max(hi[max(e_i, i - 20):i])):
            pos = 0
    entradas = [e for e in entradas if e[0] < n - 5]

    REGLAS = [("extremo 20 min", "EXT", 20), ("extremo 10 min", "EXT", 10),
              ("trail 0.096%", "PCT", 0.096), ("trail 0.11%", "PCT", 0.11),
              ("trail 0.06%", "PCT", 0.06)]
    out = {"dia": dia, "n": n, "med": med, "entradas": len(entradas), "reglas": {}}
    for nom, modo, par in REGLAS:
        pts, usd, ops, gan = 0.0, 0.0, 0, 0
        sin = 0
        for e_i, lado in entradas:
            s_i = salida(e_i, lado, modo, par)
            g = (cl[s_i] - cl[e_i]) * lado
            pts += g
            ops += 1
            gan += 1 if g > 0 else 0
            m = dinero(e_i, s_i, lado)
            if m is None:
                sin += 1
            else:
                usd += m
        out["reglas"][nom] = (ops, gan, pts, usd, sin)
    return out


O = []
def p(s=""):
    O.append(s)


p("VALIDACION A CIEGAS: parametros calibrados en el 08-13, aplicados al 08-12")
p("=" * 104)
p("Unico cambio: el umbral de entrada es 1x la MEDIANA DEL PROPIO DIA, no un valor fijo.")
p("Motivo: el tape en vivo (RTVolume) y el historico (tick-by-tick) no cuentan lo mismo.")
p("")

res = {}
for dia in ("2026-08-13", "2026-08-12"):
    try:
        res[dia] = analizar(dia)
    except Exception as e:
        p(f"ERROR en {dia}: {type(e).__name__}: {e}")

for dia, r in res.items():
    etiqueta = "CALIBRACION" if dia == "2026-08-13" else "VALIDACION (no visto)"
    p(f"{dia}  [{etiqueta}]   {r['n']} velas   mediana flujo {r['med']:,.0f}   "
      f"{r['entradas']} entradas")
    p("-" * 104)
    p(f"{'salida':>18} {'ops':>5} {'gana':>5} {'%':>7} {'puntos':>9} {'USD':>10} {'sin precio':>11}")
    for nom, (ops, gan, pts, usd, sin) in r["reglas"].items():
        pc = 100 * gan / ops if ops else 0
        p(f"{nom:>18} {ops:5} {gan:5} {pc:6.1f}% {pts:+9.2f} {usd:+10.2f} {sin:11}")
    p("")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
