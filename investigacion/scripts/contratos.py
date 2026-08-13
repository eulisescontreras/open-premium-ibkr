# ¿AYUDA EL PRECIO DE LOS CONTRATOS? Dos metricas que NO dependen del agresor:
#
#  1) DESVIACION DE PARIDAD:  (C - P) - (S - K)
#     Por paridad put-call, C-P deberia igualar S-K (con 0DTE el descuento es despreciable).
#     Lo que sobra o falta es demanda neta real por un lado -> candidato DIRECCIONAL.
#
#  2) STRADDLE ATM: C + P
#     Lo que el mercado cobra por el movimiento futuro -> candidato de AMPLITUD, y de una
#     fuente independiente del tape.
#
# Se usa el strike con datos MAS CERCANO al SPY en cada minuto. Lee la BD en SOLO-LECTURA.
import sqlite3
import statistics as st

SRC = "spy_history.db"
TXT = "CONTRATOS_HOY.txt"
DIA = "2026-08-13"

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
pm = src.execute("select hora,strike,right,mid from premium_minute where fecha=? "
                 "and expiry='20260813' and mid is not null", (DIA,)).fetchall()
tp = {m: (a, b) for m, a, b in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
src.close()

P = {}
for hora, strike, right, mid in pm:
    P.setdefault(hora, {}).setdefault(strike, {})[right] = mid

h = [x[0] for x in velas]
cl = [x[1] for x in velas]
n = len(velas)
net = [tp.get(x, (0, 0))[0] - tp.get(x, (0, 0))[1] for x in h]
med = st.median([abs(x) for x in net])

# serie de paridad y straddle usando el strike con C y P mas cercano al precio
par, strad, katm = [None] * n, [None] * n, [None] * n
for i in range(n):
    d = P.get(h[i], {})
    cands = [(abs(k - cl[i]), k) for k, v in d.items() if "C" in v and "P" in v]
    if not cands:
        continue
    _, k = min(cands)
    C, Pu = d[k]["C"], d[k]["P"]
    par[i] = (C - Pu) - (cl[i] - k)
    strad[i] = C + Pu
    katm[i] = k

ok = [i for i in range(n) if par[i] is not None]
O = []
def p(s=""):
    O.append(s)


p(f"PRECIO DE LOS CONTRATOS COMO SEÑAL  -  {DIA}")
p("=" * 100)
p(f"minutos con call y put del mismo strike: {len(ok)} de {n}")
if ok:
    pv = [par[i] for i in ok]
    sv = [strad[i] for i in ok]
    p(f"desviacion de paridad (C-P)-(S-K):  media {st.mean(pv):+.4f}  mediana "
      f"{st.median(pv):+.4f}  rango {min(pv):+.3f} .. {max(pv):+.3f}")
    p(f"straddle ATM (C+P):                 media {st.mean(sv):.3f}  rango "
      f"{min(sv):.3f} .. {max(sv):.3f}")
p("")


def pear(x, y):
    m = len(x)
    if m < 5:
        return 0
    mx, my = sum(x) / m, sum(y) / m
    sx = sum((a - mx) ** 2 for a in x) ** .5
    sy = sum((b - my) ** 2 for b in y) ** .5
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else 0


def sg(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


# ---------- test del cronometro primero: si deriva con la hora, esta muerta ----------
p("TEST DEL CRONOMETRO (tu regla nº1: |rho| >= 0.30 -> MUERTA)")
p("-" * 100)
for nom, serie in (("desviacion paridad", par), ("straddle ATM", strad)):
    idx = [i for i in ok]
    r = pear(idx, [serie[i] for i in idx])
    p(f"  {nom:>22}: rho con el minuto del dia = {r:+.3f}   "
      f"{'MUERTA' if abs(r) >= .30 else 'sobrevive'}")
# y su delta, por si el nivel deriva
for W in (5, 15, 30):
    dp = [None] * n
    for i in ok:
        if i - W in ok:
            dp[i] = par[i] - par[i - W]
    idx = [i for i in range(n) if dp[i] is not None]
    if len(idx) > 20:
        p(f"  {'delta' + str(W) + 'm paridad':>22}: rho = {pear(idx, [dp[i] for i in idx]):+.3f}")
p("")

# ---------- direccion ----------
p("1) DESVIACION DE PARIDAD COMO DIRECCION")
p("-" * 100)
p(f"{'filtro':>26} {'n':>5} {'acierta +30m':>13} {'acierta +60m':>13}")
for nom, sel in (
    ("todos los minutos", [i for i in ok if i < n - 60]),
    ("solo con salto >=3x", [i for i in ok if i < n - 60 and abs(net[i]) >= 3 * med]),
    ("|desviacion| grande", None),
):
    if sel is None:
        pv = sorted((abs(par[i]), i) for i in ok if i < n - 60)
        sel = [i for _, i in pv[-40:]]
    if len(sel) < 8:
        continue
    fila = [f"{nom:>26} {len(sel):5}"]
    for fut in (30, 60):
        okk = sum(1 for i in sel if sg(cl[min(i + fut, n - 1)] - cl[i]) == sg(par[i]))
        fila.append(f"{100*okk/len(sel):12.1f}%")
    p(" ".join(fila))
p("")

# ---------- amplitud ----------
p("2) STRADDLE ATM COMO AMPLITUD  (¿cobra el mercado el movimiento que viene?)")
p("-" * 100)
sv = sorted((strad[i], i) for i in ok if i < n - 30)
q = len(sv) // 4
p(f"{'cuartil de straddle':>26} {'n':>5} {'straddle medio':>15} {'|mov| 30m real':>15}")
for j, nom in enumerate(("Q1 mas barato", "Q2", "Q3", "Q4 mas caro")):
    sub = sv[j * q:(j + 1) * q] if j < 3 else sv[3 * q:]
    if not sub:
        continue
    mv = [abs(cl[min(i + 30, n - 1)] - cl[i]) for _, i in sub]
    p(f"{nom:>26} {len(sub):5} {st.mean([s for s, _ in sub]):15.3f} {st.mean(mv):15.3f}")
p("")
p("Si el straddle midiera bien, Q4 deberia tener |mov| claramente mayor que Q1.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
