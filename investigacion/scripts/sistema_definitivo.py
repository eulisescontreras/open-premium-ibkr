# SISTEMA DEFINITIVO, tal como quedo definido:
#   ENTRADA      Supertrend ATR(10) mult 3.0  -> se entra en cada CAMBIO de tendencia
#   SALIDA       trail sobre el SPY           -> extremo 20m y 0.11%, comparados
#   PERMANENCIA  lo que salga del trail       -> no hay parametro de tiempo
#   CONTRATO     ITM mas profundo que quepa en 320$ (80% de 400$)
#
# La magnitud del tape NO se usa (en las pruebas restaba: retrasaba entradas buenas).
# Si el trail saca antes de que el Supertrend gire, se espera al SIGUIENTE cambio: no se
# reentra en la misma señal.
# Precios ASK para comprar y BID para vender -> spread dentro. Theta dentro (precios reales).
import sqlite3

TXT = "SISTEMA_DEFINITIVO.txt"
CAPITAL, FRAC = 400.0, 0.80
TOPE = CAPITAL * FRAC
P_ATR, MULT = 10, 3.0


def cargar(dia):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
    pm = c.execute("select hora,strike,right,bid,ask,mid from premium_minute where fecha=? "
                   "and expiry=?", (dia, dia.replace("-", ""))).fetchall()
    if dia == "2026-08-13":
        t = c.execute("select substr(hora,1,5), size from tape where fecha=? and grupo='SPY' "
                      "and size is not null order by ts,id", (dia,)).fetchall()
        c.close()
    else:
        c.close()
        d = sqlite3.connect("spy_tape_ayer.db")
        t = d.execute("select minuto, size from trades_raw").fetchall()
        d.close()
    PR = {}
    for hora, k, r, b, a, m in pm:
        PR.setdefault(hora, {})[(k, r)] = (b, a, m)
    h = [x[0] for x in v]
    vol = {}
    for m, s in t:
        if s and s > 0:
            vol[m] = vol.get(m, 0) + s
    return h, [x[1] for x in v], [x[2] for x in v], [x[3] for x in v], PR, \
        [vol.get(x, 0) for x in h]


def supertrend(hi, lo, cl, p, mult):
    n = len(cl)
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    atr = [None] * n
    if n > p:
        atr[p] = sum(tr[1:p + 1]) / p
        for i in range(p + 1, n):
            atr[i] = (atr[i - 1] * (p - 1) + tr[i]) / p
    tend = [0] * n
    fu = fl = None
    d = 1
    for i in range(n):
        if atr[i] is None:
            continue
        m_ = (hi[i] + lo[i]) / 2
        bu, bl = m_ + mult * atr[i], m_ - mult * atr[i]
        fu = bu if (fu is None or bu < fu or cl[i - 1] > fu) else fu
        fl = bl if (fl is None or bl > fl or cl[i - 1] < fl) else fl
        if d == 1 and cl[i] < fl:
            d = -1
        elif d == -1 and cl[i] > fu:
            d = 1
        tend[i] = d
    return tend


def correr(dia, modo, par, veto=0.0):
    """veto: si >0, el giro del Supertrend se IGNORA cuando el volumen del minuto supera
    veto x la mediana del dia. Idea: magnitud alta = el movimiento NO se esta desvaneciendo,
    asi que no se le hace caso al giro. Medido el 08-13: con flujo >=3x, solo el 32% de los
    casos giran (contra 41% en calma). veto=0 -> desactivado."""
    h, hi, lo, cl, PR, VOL = cargar(dia)
    n = len(cl)
    tend = supertrend(hi, lo, cl, P_ATR, MULT)
    med = sorted(x for x in VOL if x)[len(  [x for x in VOL if x]) // 2] if any(VOL) else 1.0

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

    ops, pos, e_i, e_lado, mejor = [], 0, 0, 0, 0.0
    ult = 0
    for i in range(P_ATR + 2, n):
        t = tend[i]
        if t == 0:
            continue
        cambio = (t != ult and ult != 0)
        ult = t
        if pos == 0:
            # se entra SOLO en el cambio de Supertrend (o en la primera señal valida)
            if cambio or (e_i == 0 and i == P_ATR + 2):
                pos, e_i, e_lado, mejor = t, i, t, cl[i]
            continue
        mejor = max(mejor, cl[i]) if e_lado > 0 else min(mejor, cl[i])
        if modo == "PCT":
            fuera = (cl[i] <= mejor * (1 - par / 100)) if e_lado > 0 else \
                    (cl[i] >= mejor * (1 + par / 100))
        else:
            fuera = (cl[i] < min(lo[max(e_i, i - par):i])) if e_lado > 0 else \
                    (cl[i] > max(hi[max(e_i, i - par):i]))
        if fuera:
            ops.append((e_i, i, e_lado))
            pos = 0
        elif cambio:
            # VETO POR MAGNITUD: si el volumen del minuto es alto, el movimiento NO se esta
            # desvaneciendo -> se ignora el giro del Supertrend y se mantiene la posicion.
            if veto > 0 and VOL[i] >= veto * med:
                ult = e_lado          # se descarta el giro: el Supertrend "no ha hablado"
                continue
            ops.append((e_i, i, e_lado))
            pos, e_i, e_lado, mejor = t, i, t, cl[i]
    if pos != 0:
        ops.append((e_i, n - 1, e_lado))

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
        det.append((h[e], h[s], right, s - e, k, pa, pb, nc, g))
    return nops, gan, usd, sinp, det


O = []
def p(s=""):
    O.append(s)


p("SISTEMA DEFINITIVO  -  simulacion de los dos dias")
p("=" * 104)
p(f"ENTRADA      Supertrend ATR({P_ATR}) mult {MULT}  (se entra en cada CAMBIO)")
p("SALIDA       trail sobre el SPY")
p("PERMANENCIA  lo que salga del trail (sin parametro de tiempo)")
p(f"CONTRATO     ITM mas profundo que quepa en {TOPE:.0f}$  |  precios ASK/BID")
p("La magnitud del tape NO interviene.")
p("")
p(f"{'salida':>22} {'08-13 ops':>10} {'08-13 USD':>11} {'08-12 ops':>10} "
  f"{'08-12 USD':>11} {'TOTAL':>10}")
for nom, modo, par in (("extremo 20 min", "EXT", 20),
                       ("extremo 30 min", "EXT", 30),
                       ("0.096% (1.9%/1min)", "PCT", 0.096),
                       ("0.11%", "PCT", 0.11),
                       ("0.14%", "PCT", 0.14)):
    fila = [f"{nom:>22}"]
    s = 0.0
    for dia in ("2026-08-13", "2026-08-12"):
        nops, gan, usd, sinp, det = correr(dia, modo, par)
        s += usd
        fila.append(f"{nops:10} {usd:+11.2f}")
    fila.append(f"{s:+10.2f}")
    p(" ".join(fila))
p("")

p("VETO POR MAGNITUD: ignorar el giro del Supertrend si el volumen del minuto es alto")
p("(idea: magnitud alta = el movimiento NO se desvanece -> el giro es falso)")
p("-" * 104)
p(f"{'salida':>10} {'veto':>10} {'08-13 ops':>10} {'08-13 USD':>11} {'08-12 ops':>10} "
  f"{'08-12 USD':>11} {'TOTAL':>10}")
for nom, modo, par in (("0.11%", "PCT", 0.11), ("0.14%", "PCT", 0.14)):
    for veto in (0.0, 1.0, 1.5, 2.0, 3.0):
        fila = [f"{nom:>10} {('sin veto' if veto == 0 else f'{veto}x'):>10}"]
        s = 0.0
        for dia in ("2026-08-13", "2026-08-12"):
            nops, gan, usd, sinp, det = correr(dia, modo, par, veto)
            s += usd
            fila.append(f"{nops:10} {usd:+11.2f}")
        fila.append(f"{s:+10.2f}")
        p(" ".join(fila))
    p("")

for nom, modo, par in (("extremo 20 min", "EXT", 20), ("0.11%", "PCT", 0.11)):
    p(f"DETALLE con salida {nom}")
    p("-" * 104)
    for dia in ("2026-08-13", "2026-08-12"):
        nops, gan, usd, sinp, det = correr(dia, modo, par)
        p(f"  {dia}: {nops} operaciones, {gan} ganadoras, {usd:+.2f}$  "
          f"({100*usd/CAPITAL:+.0f}% del capital)")
        p(f"  {'entra':>7} {'sale':>7} {'min':>5} {'contrato':>10} {'compra':>7} "
          f"{'vende':>7} {'x':>3} {'USD':>10}")
        for e, s_, r, dur, k, pa, pb, nc, g in det:
            p(f"  {e:>7} {s_:>7} {dur:5} {k:8.0f}{r} {pa:7.2f} {pb:7.2f} {nc:3} {g:+10.2f}")
        p("")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
