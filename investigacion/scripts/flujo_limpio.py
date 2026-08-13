# FLUJO LIMPIO del 08-12: se quita lo que NO es flujo direccional antes de inferir el agresor.
#
# QUE SE QUITA Y POR QUE:
#  - exchange FINRA (41% del volumen): dark pools / OTC. Se cruzan DENTRO del spread, asi que
#    su precio no dice quien tenia prisa. La regla del tick ahi es un volado.
#  - condicion con 'I' (odd lot, <100 acciones): 169.396 operaciones que son solo el 6.8% del
#    volumen. Inflan el conteo de ticks sin aportar direccion.
#  - condicion con '7' o 'V' (385 ops, 1.3M acciones): cruces y operaciones fuera de secuencia.
#    Son los bloques que producian los saltos de 300 M.
#
# Se comparan CUATRO versiones para ver que aporta cada filtro (corrida diferencial, regla 8).
import sqlite3
import statistics as st

TXT = "FLUJO_LIMPIO.txt"
DIA = "2026-08-12"

d = sqlite3.connect("spy_tape_ayer.db")
filas = d.execute("select ts_et, minuto, price, size, exchange, cond from trades_raw "
                  "order by ts_et, rowid").fetchall()
d.close()
c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
velas = c.execute("select hora,close from bars_minute where fecha=? order by hora",
                  (DIA,)).fetchall()
c.close()
h = [x[0] for x in velas]
cl = [x[1] for x in velas]
n = len(velas)


def acumulado(sel):
    """Regla del tick sobre el subconjunto elegido. Devuelve neto por minuto."""
    acc, pp, ps = {}, None, None
    for ts, minuto, price, size, ex, cd in sel:
        ag = None if pp is None else (1 if price > pp else (-1 if price < pp else ps))
        if ag:
            ps = ag
        pp = price
        if ag:
            acc[minuto] = acc.get(minuto, 0.0) + ag * price * size
    return [acc.get(x, 0.0) for x in h]


def es_odd(cd):
    return cd is not None and "I" in cd


def es_cruce(cd):
    return cd is not None and ("7" in cd or "V" in cd)


VERSIONES = {
    "1 TODO (como estaba)": filas,
    "2 sin odd lots": [f for f in filas if not es_odd(f[5])],
    "3 sin odd ni FINRA": [f for f in filas if not es_odd(f[5]) and f[4] != "FINRA"],
    "4 solo regular publico": [f for f in filas if not es_odd(f[5]) and f[4] != "FINRA"
                               and not es_cruce(f[5])],
}

O = []
def p(s=""):
    O.append(s)


p(f"FLUJO LIMPIO  -  {DIA}: ¿desaparecen los saltos al quitar lo que no es flujo?")
p("=" * 108)
p("La regla del tick se aplica SOLO sobre las operaciones que quedan en cada version.")
p("")
p(f"{'version':>24} {'ops':>9} {'acciones':>13} {'mayor op':>10} {'|salto| max':>15} "
  f"{'acum final':>15}")
NETS = {}
for nom, sel in VERSIONES.items():
    net = acumulado(sel)
    NETS[nom] = net
    vol = sum(f[3] for f in sel)
    mx = max((f[3] for f in sel), default=0)
    salto = max((abs(x) for x in net), default=0)
    p(f"{nom:>24} {len(sel):9,} {vol:13,.0f} {mx:10,.0f} {salto:15,.0f} {sum(net):15,.0f}")
p("")

p("EL MINUTO QUE NO CUADRABA (11:22) EN CADA VERSION")
p("-" * 108)
i22 = h.index("11:22") if "11:22" in h else None
if i22 is not None:
    p(f"{'version':>24} {'neto del minuto':>18} {'acum hasta ahi':>18}")
    for nom, net in NETS.items():
        p(f"{nom:>24} {net[i22]:18,.0f} {sum(net[:i22+1]):18,.0f}")
p("")

p("ACUMULADO MINUTO A MINUTO, 11:18 a 11:42  (la zona que señalaste)")
p("-" * 108)
p(f"{'hora':>7} {'spy':>9} " + " ".join(f"{k.split()[0]:>16}" for k in VERSIONES))
ac = {k: 0.0 for k in VERSIONES}
for i in range(n):
    for k in VERSIONES:
        ac[k] += NETS[k][i]
    if "11:18" <= h[i] <= "11:42":
        p(f"{h[i]:>7} {cl[i]:9.2f} " + " ".join(f"{ac[k]:16,.0f}" for k in VERSIONES))
p("")

p("¿MEJORA LA PREDICCION DE AMPLITUD?  P(mover >=0.50 en 30 min)")
p("-" * 108)
p(f"{'version':>24} {'mediana':>14} {'calma <2x':>11} {'>=3x':>9} {'>=5x':>9}")
for nom, net in NETS.items():
    med = st.median([abs(x) for x in net if x]) or 1.0
    fila = [f"{nom:>24} {med:14,.0f}"]
    for cond in ((lambda r: r < 2), (lambda r: r >= 3), (lambda r: r >= 5)):
        sel = [i for i in range(n - 30) if cond(abs(net[i]) / med)]
        if len(sel) < 5:
            fila.append(f"{'-':>9}")
            continue
        ok = sum(1 for i in sel if abs(cl[i + 30] - cl[i]) >= 0.50)
        fila.append(f"{100*ok/len(sel):8.0f}%")
    p(" ".join(fila))

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
