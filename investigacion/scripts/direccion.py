# ¿QUE DA LA DIRECCION? El flujo ya predice AMPLITUD (verificado). Falta el SIGNO.
# Test acotado: solo en los minutos con salto de flujo >= Nx la mediana, se mide que candidato
# acierta el signo del movimiento posterior. Un candidato por fila, misma metrica para todos.
# Lee la BD viva en SOLO-LECTURA.
import sqlite3
import statistics as st

SRC = "spy_history.db"
TXT = "DIRECCION_HOY.txt"
DIA = "2026-08-13"

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
ta = {h: r for h, *r in src.execute(
    "select hora,sma20,sma50,sma200,rsi,macd_hist,ema8,ema21,bb_up,bb_low,vwap "
    "from ta_minute where fecha=?", (DIA,))}
tp = {m: (a, b) for m, a, b in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
opc = src.execute(
    "select substr(hora,1,5) m, right,"
    " sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo<>'SPY' and right is not null group by m, right", (DIA,)).fetchall()
src.close()
NC = {m: c - v for m, r, c, v in opc if r == "C"}
NP = {m: c - v for m, r, c, v in opc if r == "P"}

h = [x[0] for x in velas]
cl = [x[1] for x in velas]
n = len(velas)
net = [tp.get(x, (0, 0))[0] - tp.get(x, (0, 0))[1] for x in h]
nc = [NC.get(x, 0.0) for x in h]
npu = [NP.get(x, 0.0) for x in h]
med = st.median([abs(x) for x in net])

acum_c, acum_p = [], []
a = b = 0.0
for i in range(n):
    a += nc[i]
    b += npu[i]
    acum_c.append(a)
    acum_p.append(b)


def sg(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def cand(i):
    """Devuelve {nombre: signo predicho} para el minuto i. None = no opina."""
    t = ta.get(h[i], [None] * 10)
    s20, s50, s200, rsi, mh, e8, e21, bbu, bbl, vw = t
    d = {}
    d["precio 5m"] = sg(cl[i] - cl[i - 5]) if i >= 5 else 0
    d["precio 15m"] = sg(cl[i] - cl[i - 15]) if i >= 15 else 0
    d["precio 30m"] = sg(cl[i] - cl[i - 30]) if i >= 30 else 0
    d["signo net_spy"] = sg(net[i])
    d["net_call - net_put"] = sg(nc[i] - npu[i])
    d["acum_call - acum_put"] = sg(acum_c[i] - acum_p[i])
    d["net_call solo"] = sg(nc[i])
    d["net_put invertido"] = -sg(npu[i])
    d["precio vs SMA20"] = sg(cl[i] - s20) if s20 else 0
    d["precio vs SMA50"] = sg(cl[i] - s50) if s50 else 0
    d["precio vs SMA200"] = sg(cl[i] - s200) if s200 else 0
    d["SMA20 vs SMA50"] = sg(s20 - s50) if (s20 and s50) else 0
    d["precio vs media5(vwap)"] = sg(cl[i] - vw) if vw else 0
    d["EMA8 vs EMA21"] = sg(e8 - e21) if (e8 and e21) else 0
    d["MACD hist"] = sg(mh) if mh is not None else 0
    d["RSI - 50"] = sg(rsi - 50) if rsi is not None else 0
    return d


O = []
def p(s=""):
    O.append(s)


p(f"¿QUE DA LA DIRECCION?  -  {DIA}, {n} minutos")
p("=" * 100)
p(f"mediana |net_spy| = {med:,.0f}")
p("El flujo ya predice AMPLITUD. Aqui se busca quien acierta el SIGNO del movimiento.")
p("Se evalua SOLO en los minutos con salto de flujo, que es cuando importa.")
p("")

for mult, fut in ((3, 30), (3, 60), (5, 30), (1, 30)):
    sel = [i for i in range(30, n - fut) if abs(net[i]) >= mult * med]
    if len(sel) < 8:
        continue
    p(f"SALTO >= {mult}x mediana,  horizonte {fut} min   ->   {len(sel)} casos")
    p("-" * 100)
    p(f"{'candidato':>24} {'opina':>6} {'acierta':>8} {'%':>7} {'pts si se sigue':>16}")
    filas = []
    for nom in cand(50):
        op = ok = 0
        pts = 0.0
        for i in sel:
            s = cand(i).get(nom, 0)
            if s == 0:
                continue
            op += 1
            mov = cl[min(i + fut, n - 1)] - cl[i]
            if sg(mov) == s:
                ok += 1
            pts += s * mov
        if op >= 5:
            filas.append((100 * ok / op, nom, op, ok, pts))
    for pc, nom, op, ok, pts in sorted(filas, reverse=True):
        p(f"{nom:>24} {op:6} {ok:8} {pc:6.1f}% {pts:+16.2f}")
    p("")

p("50% = moneda. Lo que importa es que un candidato repita por encima de 50 en VARIOS")
p("bloques, no que gane en uno. Con estos n, +-10 puntos es ruido.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
