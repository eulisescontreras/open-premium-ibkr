# VALIDACION con el flujo FILTRADO, en los dos dias.
#
# ⚠️ ASIMETRIA INEVITABLE, y se declara: el tape en vivo (08-13) NO guarda exchange ni cond,
# asi que a hoy solo se le puede aplicar el filtro por TAMAÑO (quitar odd lots <100 acciones).
# Al 08-12 se le aplica ademas el filtro de FINRA, que fue el que mas aporto.
# Por eso se corre el 08-12 en DOS versiones, para ver cuanto de la mejora viene de cada filtro.
#
# El sistema es el mismo de siempre: entrada por flujo >= 1x mediana del dia + direccion 5 min,
# salida por trailing de extremo 20 min. Contrato ITM que quepa en 320$.
import sqlite3
import statistics as st

TXT = "VALIDACION_LIMPIA.txt"
UMBRAL_ZZ, DIR_MIN = 1.50, 5
CAPITAL, FRAC = 400.0, 0.80
TOPE = CAPITAL * FRAC


def ticks_dia(dia, filtro):
    """filtro: 'todo' | 'sin_odd' | 'sin_odd_finra'"""
    if dia == "2026-08-13":
        c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
        t = c.execute("select substr(hora,1,5), last, size from tape where fecha=? "
                      "and grupo='SPY' and last is not null and size is not null "
                      "order by ts,id", (dia,)).fetchall()
        c.close()
        # hoy no hay exchange ni cond: el unico filtro posible es por tamaño
        if filtro in ("sin_odd", "sin_odd_finra"):
            t = [x for x in t if x[2] >= 100]
        return t
    d = sqlite3.connect("spy_tape_ayer.db")
    t = d.execute("select minuto, price, size, exchange, cond from trades_raw "
                  "order by ts_et, rowid").fetchall()
    d.close()
    if filtro == "sin_odd":
        t = [x for x in t if not (x[4] and "I" in x[4])]
    elif filtro == "sin_odd_finra":
        t = [x for x in t if not (x[4] and "I" in x[4]) and x[3] != "FINRA"
             and not (x[4] and ("7" in x[4] or "V" in x[4]))]
    return [(x[0], x[1], x[2]) for x in t]


def correr(dia, filtro):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
    pm = c.execute("select hora,strike,right,bid,ask,mid from premium_minute where fecha=? "
                   "and expiry=?", (dia, dia.replace("-", ""))).fetchall()
    c.close()
    PR = {}
    for hora, k, r, b, a, m in pm:
        PR.setdefault(hora, {})[(k, r)] = (b, a, m)
    h = [x[0] for x in v]
    hi = [x[1] for x in v]
    lo = [x[2] for x in v]
    cl = [x[3] for x in v]
    n = len(v)

    acc, pp, ps = {}, None, None
    for m_, price, size in ticks_dia(dia, filtro):
        if price is None or size is None or size <= 0:
            continue
        ag = None if pp is None else (1 if price > pp else (-1 if price < pp else ps))
        if ag:
            ps = ag
        pp = price
        if ag:
            acc[m_] = acc.get(m_, 0.0) + ag * price * size
    net = [acc.get(x, 0.0) for x in h]
    med = st.median([abs(x) for x in net if x]) or 1.0

    piv, d_, hii, loi = [0], 0, 0, 0
    for i in range(1, n):
        if cl[i] > cl[hii]:
            hii = i
        if cl[i] < cl[loi]:
            loi = i
        if d_ >= 0 and cl[hii] - cl[i] >= UMBRAL_ZZ:
            piv.append(hii); d_ = -1; loi = i
        elif d_ <= 0 and cl[i] - cl[loi] >= UMBRAL_ZZ:
            piv.append(loi); d_ = 1; hii = i
    piv.append(n - 1)
    piv = sorted(set(piv))
    tramos = [(piv[k], piv[k + 1]) for k in range(len(piv) - 1) if piv[k + 1] - piv[k] >= 3]

    def elegir(i, right):
        d = PR.get(h[i], {})
        px = cl[i]
        ks = sorted([k for (k, r) in d if r == right and
                     (k < px if right == "C" else k > px)], reverse=(right == "P"))
        for k in ks:
            b, a, m = d[(k, right)]
            c_ = a or m
            if c_ and c_ > 0 and c_ * 100 <= TOPE:
                return k
        cs = [k for (k, r) in d if r == right]
        return min(cs, key=lambda k: abs(k - px)) if cs else None

    usd, ops, gan, sinp = 0.0, 0, 0, 0
    det = []
    for a, b in tramos:
        lado = 1 if cl[b] > cl[a] else -1
        e = None
        for i in range(a + 1, b + 1):
            if i < DIR_MIN:
                continue
            f = sum(net[max(0, i - 4):i + 1]) / 5
            dd = cl[i] - cl[i - DIR_MIN]
            if abs(f) >= med and dd != 0 and (1 if dd > 0 else -1) == lado:
                e = i
                break
        if e is None:
            continue
        s = n - 1
        for i in range(e + 1, n):
            if (cl[i] < min(lo[max(e, i - 20):i])) if lado > 0 else \
               (cl[i] > max(hi[max(e, i - 20):i])):
                s = i
                break
        right = "C" if lado > 0 else "P"
        k = elegir(e, right)
        de = PR.get(h[e], {}).get((k, right)) if k else None
        ds = PR.get(h[s], {}).get((k, right)) if k else None
        if not de or not ds:
            sinp += 1
            continue
        pa, pb = (de[1] or de[2]), (ds[0] or ds[2])
        nc = int(TOPE // (pa * 100)) if pa else 0
        if nc < 1:
            sinp += 1
            continue
        g = (pb - pa) * 100 * nc
        usd += g
        ops += 1
        gan += 1 if g > 0 else 0
        det.append((h[e], h[s], right, g))
    return med, len(tramos), ops, gan, usd, sinp, det


O = []
def p(s=""):
    O.append(s)


p("VALIDACION CON FLUJO FILTRADO  -  los dos dias")
p("=" * 100)
p("⚠️ El tape EN VIVO (08-13) no guarda exchange ni cond: a hoy solo se le puede quitar")
p("   los odd lots por tamaño. El filtro de FINRA -el que mas aporto- NO es aplicable")
p("   a hoy ni al sistema en produccion sin cambiar lo que se captura.")
p("")
p(f"{'dia':>12} {'filtro':>16} {'mediana':>13} {'tramos':>7} {'ops':>5} {'gana':>5} "
  f"{'USD':>10} {'sin precio':>11}")
for dia in ("2026-08-13", "2026-08-12"):
    for filtro in ("todo", "sin_odd", "sin_odd_finra"):
        if dia == "2026-08-13" and filtro == "sin_odd_finra":
            continue          # identico a sin_odd: no hay datos para mas
        med, nt, ops, gan, usd, sinp, det = correr(dia, filtro)
        p(f"{dia:>12} {filtro:>16} {med:13,.0f} {nt:7} {ops:5} {gan:5} {usd:+10.2f} {sinp:11}")
p("")

p("DETALLE DEL 08-12 CON EL FILTRO COMPLETO")
p("-" * 100)
med, nt, ops, gan, usd, sinp, det = correr("2026-08-12", "sin_odd_finra")
p(f"{'entra':>7} {'sale':>7} {'lado':>5} {'USD':>10}")
for e, s, r, g in det:
    p(f"{e:>7} {s:>7} {r:>5} {g:+10.2f}")
p(f"   {ops} operaciones, {gan} ganadoras, total {usd:+.2f}$  ({sinp} sin precio)")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
