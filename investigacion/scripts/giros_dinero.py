# TABLA EN DINERO: columnas = giros, filas = regla de salida.
# Contrato = el que elige el sistema REAL (_strike_ejecucion): el ITM mas profundo que quepa
# en el 80% del capital (320$ de 400$). Precios reales de premium_minute -> el THETA ya esta
# dentro, porque son precios de mercado en cada minuto.
# Se dan DOS versiones: MID (referencia) y ASK/BID (realista: se compra al ask, se vende al bid).
# Lee la BD viva en SOLO-LECTURA.
import sqlite3

SRC = "spy_history.db"
TXT = "GIROS_DINERO.txt"
DIA = "2026-08-13"
DIR_MIN, VENT, ENT = 5, 5, 1.0e6
CAPITAL, FRAC = 400.0, 0.80
TOPE = CAPITAL * FRAC

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
tp = {m: (a, b) for m, a, b in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
pm = src.execute("select hora,strike,right,bid,ask,mid from premium_minute where fecha=? "
                 "and expiry='20260813'", (DIA,)).fetchall()
src.close()
PR = {}
for hora, k, r, b, a, m in pm:
    PR.setdefault(hora, {})[(k, r)] = (b, a, m)

h = [x[0] for x in velas]
hi = [x[1] for x in velas]
lo = [x[2] for x in velas]
cl = [x[3] for x in velas]
n = len(velas)
net = [tp.get(x, (0, 0))[0] - tp.get(x, (0, 0))[1] for x in h]


def fmov(i, v=VENT):
    return None if i < v - 1 else sum(net[i - v + 1:i + 1]) / v


def elegir_itm(i, right):
    """MISMO criterio que _strike_ejecucion: el ITM mas profundo que quepa en TOPE."""
    d = PR.get(h[i], {})
    px = cl[i]
    # ITM: call por DEBAJO del precio, put por ENCIMA. Se recorre del mas profundo al mas
    # superficial -> call ascendente (strike menor = mas dentro), put descendente.
    ks = sorted([k for (k, r) in d if r == right and (k < px if right == "C" else k > px)],
                reverse=(right == "P"))
    for k in ks:
        b, a, m = d[(k, right)]
        coste = a or m
        if coste and coste > 0 and coste * 100 <= TOPE:
            return k
    # ninguno cabe -> ATM, como hace el sistema
    cands = [k for (k, r) in d if r == right]
    return min(cands, key=lambda k: abs(k - px)) if cands else None


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


def dinero(e_i, s_i, lado, realista):
    right = "C" if lado > 0 else "P"
    k = elegir_itm(e_i, right)
    if k is None:
        return None
    de = PR.get(h[e_i], {}).get((k, right))
    ds = PR.get(h[s_i], {}).get((k, right))
    if not de or not ds:
        return None
    p_ent = (de[1] or de[2]) if realista else de[2]      # ask / mid
    p_sal = (ds[0] or ds[2]) if realista else ds[2]      # bid / mid
    if not p_ent or not p_sal or p_ent <= 0:
        return None
    nc = int(TOPE // (p_ent * 100))
    if nc < 1:
        return None
    return (p_sal - p_ent) * 100 * nc, k, nc, p_ent, p_sal


# ---------- entradas ----------
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
    if (cl[i] < min(lo[max(e_i, i - 20):i])) if pos > 0 else (cl[i] > max(hi[max(e_i, i - 20):i])):
        pos = 0
entradas = [e for e in entradas if e[0] < n - 5]     # descartar las de los ultimos minutos

REGLAS = [("extremo 20 min", "EXT", 20), ("extremo 10 min", "EXT", 10),
          ("trail 0.096%", "PCT", 0.096), ("trail 0.11%", "PCT", 0.11),
          ("trail 0.06%", "PCT", 0.06)]

O = []
def p(s=""):
    O.append(s)


p(f"RESULTADO EN DINERO POR GIRO  -  {DIA}")
p("=" * 118)
p(f"capital {CAPITAL:.0f}$ | tope por operacion {TOPE:.0f}$ ({FRAC:.0%})")
p("contrato: el ITM mas profundo que quepa, MISMO criterio que _strike_ejecucion del sistema")
p("el THETA esta incluido: son precios reales del mercado en cada minuto")
p("")

for realista, titulo in ((False, "A) precios MID (referencia, sin spread)"),
                         (True, "B) precios ASK/BID (realista: compra al ask, vende al bid)")):
    p(titulo)
    p("-" * 118)
    cab = f"{'salida':>16}"
    for e_i, lado in entradas:
        cab += f" {h[e_i] + ('/C' if lado > 0 else '/P'):>13}"
    p(cab + f" {'TOTAL':>10}")
    for nom, modo, par in REGLAS:
        fila = f"{nom:>16}"
        tot = 0.0
        for e_i, lado in entradas:
            s_i = salida(e_i, lado, modo, par)
            r = dinero(e_i, s_i, lado, realista)
            if r is None:
                fila += f" {'sin datos':>13}"
                continue
            pl, k, nc, pe, ps = r
            tot += pl
            fila += f" {pl:+9.2f}/{nc:<3}"
        p(fila + f" {tot:+10.2f}")
    p("")
    # detalle del contrato usado
    p(f"   {'contrato elegido en cada entrada:':<40}")
    for e_i, lado in entradas:
        right = "C" if lado > 0 else "P"
        k = elegir_itm(e_i, right)
        d = PR.get(h[e_i], {}).get((k, right)) if k else None
        if d:
            pe = (d[1] or d[2]) if realista else d[2]
            nc = int(TOPE // (pe * 100)) if pe else 0
            p(f"   {h[e_i]}  SPY {cl[e_i]:7.2f}  ->  {k:.0f}{right} a {pe:.2f}  "
              f"x{nc} contratos = {pe*100*nc:.0f}$")
    p("")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
