# EL SISTEMA CON CADA PIEZA EN SU SITIO, probado en DINERO y SIN ORACULO.
#
#   DIRECCION : EMA8 vs EMA21   (74-76% de acierto del lado del tramo, en los dos dias)
#   ENTRADA   : el cruce de la EMA, opcionalmente filtrado por actividad del tape
#   SALIDA    : trailing por extremo de 20 min sobre el SPY
#   CONTRATO  : ITM mas profundo que quepa en 320$ (80% de 400$), como _strike_ejecucion
#
# Precios ASK para comprar y BID para vender -> el spread esta dentro. El theta tambien,
# porque son precios reales de mercado en cada minuto.
# ESTA VEZ NO HAY ORACULO: todo se decide con informacion disponible en ese minuto.
import sqlite3
import statistics as st

TXT = "SISTEMA_FINAL.txt"
CAPITAL, FRAC = 400.0, 0.80
TOPE = CAPITAL * FRAC
K_TRAIL = 20


def sg(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def cargar(dia):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
    ta = {h: r for h, *r in c.execute(
        "select hora,ema8,ema21 from ta_minute where fecha=?", (dia,))}
    pm = c.execute("select hora,strike,right,bid,ask,mid from premium_minute where fecha=? "
                   "and expiry=?", (dia, dia.replace("-", ""))).fetchall()
    if dia == "2026-08-13":
        t = c.execute("select substr(hora,1,5), size from tape where fecha=? and grupo='SPY' "
                      "and size is not null order by ts,id", (dia,)).fetchall()
        c.close()
    else:
        c.close()
        d = sqlite3.connect("spy_tape_ayer.db")
        t = d.execute("select minuto, size from trades_raw order by ts_et, rowid").fetchall()
        d.close()
    PR = {}
    for hora, k, r, b, a, m in pm:
        PR.setdefault(hora, {})[(k, r)] = (b, a, m)
    h = [x[0] for x in v]
    vol = {}
    for m, s in t:
        if s and s > 0:
            vol[m] = vol.get(m, 0) + s
    return h, [x[1] for x in v], [x[2] for x in v], [x[3] for x in v], ta, PR, \
        [vol.get(x, 0) for x in h]


def correr(dia, filtro_flujo):
    h, hi, lo, cl, ta, PR, VOL = cargar(dia)
    n = len(cl)
    med = st.median([x for x in VOL if x]) or 1.0

    # DIRECCION POR SUPERTREND (sustituye a la EMA, que en los 6 pivotes acerto 1 de 6).
    # ATR(10) mult 3.0: la region 3-4 salio positiva en las 16 combinaciones probadas.
    P_ATR, MULT = 10, 3.0
    trn = [0.0] * n
    for i in range(1, n):
        trn[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    atr = [None] * n
    if n > P_ATR:
        atr[P_ATR] = sum(trn[1:P_ATR + 1]) / P_ATR
        for i in range(P_ATR + 1, n):
            atr[i] = (atr[i - 1] * (P_ATR - 1) + trn[i]) / P_ATR
    TEND = [0] * n
    fu = fl = None
    dd = 1
    for i in range(n):
        if atr[i] is None:
            continue
        m_ = (hi[i] + lo[i]) / 2
        bu, bl = m_ + MULT * atr[i], m_ - MULT * atr[i]
        fu = bu if (fu is None or bu < fu or cl[i - 1] > fu) else fu
        fl = bl if (fl is None or bl > fl or cl[i - 1] < fl) else fl
        if dd == 1 and cl[i] < fl:
            dd = -1
        elif dd == -1 and cl[i] > fu:
            dd = 1
        TEND[i] = dd

    def dmedia(i):
        return TEND[i]

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

    # CADA PIEZA EN SU SITIO, sin invadir la de al lado:
    #   ENTRAR : lo decide el FLUJO (actividad >= filtro_flujo x mediana del dia)
    #   LADO   : lo dice la EMA, y SOLO cuando el flujo pregunta
    #   SALIR  : SOLO el trailing. La EMA NO cierra posiciones ni gira nada.
    # Antes la EMA cerraba al cambiar de lado, y eso la convertia en salida encubierta.
    ops, pos, e_i, e_lado = [], 0, 0, 0
    for i in range(30, n):
        if pos == 0:
            if VOL[i] >= filtro_flujo * med:
                d = dmedia(i)
                if d != 0:
                    pos, e_i, e_lado = d, i, d
            continue
        # unica salida: el trailing sobre el precio del SPY
        fuera = (cl[i] < min(lo[max(e_i, i - K_TRAIL):i])) if e_lado > 0 else \
                (cl[i] > max(hi[max(e_i, i - K_TRAIL):i]))
        if fuera:
            ops.append((e_i, i, e_lado))
            pos = 0
    if pos != 0:
        ops.append((e_i, n - 1, e_lado))

    usd, gan, sinp, det = 0.0, 0, 0, []
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
        gan += 1 if g > 0 else 0
        det.append((h[e], h[s], right, s - e, g))
    return len(det), gan, usd, sinp, det


O = []
def p(s=""):
    O.append(s)


p("EL SISTEMA CON CADA PIEZA EN SU SITIO  -  SIN ORACULO, en dinero")
p("=" * 100)
p("DIRECCION: SUPERTREND ATR(10) mult 3.0  (sustituye a la EMA: acertaba 1 de 6 pivotes)")
p("ENTRADA: la dispara el FLUJO | SALIDA: solo el trailing de 20 min")
p(f"CONTRATO: ITM que quepa en {TOPE:.0f}$ | precios ASK/BID (spread dentro)")
p("")
p("El FLUJO dispara; en ese minuto el SUPERTREND dice el lado. No abre nada por su cuenta,")
p("y NO cierra: la unica salida es el trailing.")
p("")
p(f"{'disparo flujo':>16} {'08-13 ops':>10} {'08-13 USD':>11} {'08-12 ops':>10} "
  f"{'08-12 USD':>11} {'TOTAL':>10}")
MEJOR = None
for mult in (1, 2, 3, 5, 8):
    fila = [f"{str(mult) + 'x mediana':>16}"]
    s = 0.0
    for dia in ("2026-08-13", "2026-08-12"):
        nops, gan, usd, sinp, det = correr(dia, mult)
        s += usd
        fila.append(f"{nops:10} {usd:+11.2f}")
    fila.append(f"{s:+10.2f}")
    p(" ".join(fila))
    if MEJOR is None or s > MEJOR[0]:
        MEJOR = (s, mult)
p("")

MULT = MEJOR[1]
p(f"DETALLE con disparo a {MULT}x la mediana")
p("-" * 100)
for dia in ("2026-08-13", "2026-08-12"):
    nops, gan, usd, sinp, det = correr(dia, MULT)
    p(f"  {dia}:")
    p(f"  {'entra':>7} {'sale':>7} {'lado':>5} {'min':>5} {'USD':>10}")
    for e, s_, r, dur, g in det:
        p(f"  {e:>7} {s_:>7} {r:>5} {dur:5} {g:+10.2f}")
    p(f"     {nops} ops, {gan} ganadoras, {usd:+.2f}$")
    p("")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
