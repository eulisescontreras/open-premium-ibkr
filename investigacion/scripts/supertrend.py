# SUPERTREND para entrar Y salir, en los dos dias, en dinero.
#
# No existia en el proyecto: se calcula aqui desde bars_minute (high, low, close).
#   ATR(p) por Wilder | banda = (high+low)/2 +- mult*ATR, con arrastre |
#   tendencia: cambia cuando el CIERRE cruza la banda final
#
# El Supertrend da entrada Y salida: se opera siempre en el lado que marca, girando en cada
# cambio. Se prueban varias combinaciones (p, mult) para leer la REGION, no la celda maxima.
# Contrato ITM que quepa en 320$, precios ASK/BID. Lee la BD en SOLO-LECTURA.
import sqlite3

TXT = "SUPERTREND.txt"
CAPITAL, FRAC = 400.0, 0.80
TOPE = CAPITAL * FRAC


def cargar(dia):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
    pm = c.execute("select hora,strike,right,bid,ask,mid from premium_minute where fecha=? "
                   "and expiry=?", (dia, dia.replace("-", ""))).fetchall()
    c.close()
    PR = {}
    for hora, k, r, b, a, m in pm:
        PR.setdefault(hora, {})[(k, r)] = (b, a, m)
    return [x[0] for x in v], [x[1] for x in v], [x[2] for x in v], [x[3] for x in v], PR


def supertrend(hi, lo, cl, p, mult):
    """Devuelve la tendencia por minuto: +1 alcista, -1 bajista, 0 sin datos."""
    n = len(cl)
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    atr = [None] * n
    if n > p:
        atr[p] = sum(tr[1:p + 1]) / p
        for i in range(p + 1, n):
            atr[i] = (atr[i - 1] * (p - 1) + tr[i]) / p      # suavizado de Wilder
    tend = [0] * n
    fu = fl = None
    d = 1
    for i in range(n):
        if atr[i] is None:
            continue
        med = (hi[i] + lo[i]) / 2
        bu = med + mult * atr[i]
        bl = med - mult * atr[i]
        # arrastre: la banda solo se aprieta mientras la tendencia no cambie
        fu = bu if (fu is None or bu < fu or cl[i - 1] > fu) else fu
        fl = bl if (fl is None or bl > fl or cl[i - 1] < fl) else fl
        if d == 1 and cl[i] < fl:
            d = -1
        elif d == -1 and cl[i] > fu:
            d = 1
        tend[i] = d
    return tend


def correr(dia, p_, mult):
    h, hi, lo, cl, PR = cargar(dia)
    n = len(cl)
    tend = supertrend(hi, lo, cl, p_, mult)

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

    ops, pos, e_i = [], 0, 0
    for i in range(p_ + 2, n):
        t = tend[i]
        if t == 0:
            continue
        if pos == 0:
            pos, e_i = t, i
        elif t != pos:
            ops.append((e_i, i, pos))
            pos, e_i = t, i
    if pos != 0:
        ops.append((e_i, n - 1, pos))

    usd, gan, nops, sinp, det = 0.0, 0, 0, 0, []
    for e, s, lado in ops:
        right = "C" if lado > 0 else "P"
        k = elegir(e, right)
        de = PR.get(h[e], {}).get((k, right)) if k else None
        ds = PR.get(h[s], {}).get((k, right)) if k else None
        if not de or not ds:
            sinp += 1
            continue
        pa, pb = (de[1] or de[2]), (ds[0] or ds[2])
        nc = int(TOPE // (pa * 100)) if pa else 0
        if nc < 1 or not pb:
            sinp += 1
            continue
        g = (pb - pa) * 100 * nc
        usd += g
        nops += 1
        gan += 1 if g > 0 else 0
        det.append((h[e], h[s], right, s - e, g))
    return nops, gan, usd, sinp, det


O = []
def p(s=""):
    O.append(s)


p("SUPERTREND para entrar Y salir  -  los dos dias, en dinero")
p("=" * 100)
p(f"capital {CAPITAL:.0f}$ | tope {TOPE:.0f}$ | contrato ITM que quepa | precios ASK/BID")
p("Se opera SIEMPRE en el lado que marca el Supertrend, girando en cada cambio.")
p("")
p(f"{'ATR':>5} {'mult':>6} {'08-13 ops':>10} {'08-13 USD':>11} {'08-12 ops':>10} "
  f"{'08-12 USD':>11} {'TOTAL':>10}")
MEJOR = None
for p_ in (7, 10, 14, 20):
    for mult in (1.0, 2.0, 3.0, 4.0):
        fila = [f"{p_:5} {mult:6.1f}"]
        s = 0.0
        for dia in ("2026-08-13", "2026-08-12"):
            nops, gan, usd, sinp, det = correr(dia, p_, mult)
            s += usd
            fila.append(f"{nops:10} {usd:+11.2f}")
        fila.append(f"{s:+10.2f}")
        p(" ".join(fila))
        if MEJOR is None or s > MEJOR[0]:
            MEJOR = (s, p_, mult)
    p("")

_, bp, bm = MEJOR
p(f"DETALLE de la mejor combinacion: ATR({bp}), mult {bm}")
p("-" * 100)
for dia in ("2026-08-13", "2026-08-12"):
    nops, gan, usd, sinp, det = correr(dia, bp, bm)
    p(f"  {dia}: {nops} ops, {gan} ganadoras, {usd:+.2f}$")
    p(f"  {'entra':>7} {'sale':>7} {'lado':>5} {'min':>5} {'USD':>10}")
    for e, s_, r, dur, g in det:
        p(f"  {e:>7} {s_:>7} {r:>5} {dur:5} {g:+10.2f}")
    p("")
p("OJO: la mejor celda esta elegida sobre estos mismos 2 dias. Lo que vale es si la REGION")
p("entera (varias combinaciones) es positiva, no el maximo.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
