# EL METODO DE LOS DIGITOS: ¿avisa de que un movimiento se esta desvaneciendo?
#
# digitos(|net_spy del minuto|) es una medida LOGARITMICA de la magnitud absoluta -> la unica
# familia que ha sobrevivido a los cambios de columna y de agresor.
#
# SEÑAL: los digitos del minuto caen >=1 nivel respecto a la MEDIA de los 15 minutos previos.
# TEST : tras esa señal, ¿el precio sigue avanzando en la direccion vigente, o se para?
#        Se compara contra la base (todos los minutos con la misma direccion vigente).
# Ambos dias con la MISMA regla del tick. Lee las BD en SOLO-LECTURA.
import sqlite3
import statistics as st

TXT = "DIGITOS.txt"
DIR_MIN = 5


def cargar(dia):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    velas = c.execute("select hora,close from bars_minute where fecha=? order by hora",
                      (dia,)).fetchall()
    if dia == "2026-08-13":
        t = c.execute("select substr(hora,1,5), last, size from tape where fecha=? "
                      "and grupo='SPY' and last is not null order by ts,id", (dia,)).fetchall()
        c.close()
    else:
        c.close()
        d = sqlite3.connect("spy_tape_ayer.db")
        t = d.execute("select minuto, price, size from trades_raw "
                      "order by ts_et, rowid").fetchall()
        d.close()
    acc, pp, ps = {}, None, None
    for m, last, mag in t:
        if last is None or mag is None or mag <= 0:
            continue
        ag = None if pp is None else (1 if last > pp else (-1 if last < pp else ps))
        if ag:
            ps = ag
        pp = last
        if ag:
            acc[m] = acc.get(m, 0.0) + ag * last * mag
    h = [x[0] for x in velas]
    cl = [x[1] for x in velas]
    return h, cl, [acc.get(x, 0.0) for x in h]


def dig(v):
    return len(str(abs(int(round(v))))) if v else 0


O = []
def p(s=""):
    O.append(s)


p("EL METODO DE LOS DIGITOS: ¿avisa del agotamiento de un movimiento?")
p("=" * 100)
p("digitos(|net_spy del minuto|) = magnitud logaritmica del flujo. Señal = caida de >=1 nivel")
p("respecto a la media de los 15 minutos previos.")
p("Se mide el AVANCE POSTERIOR EN LA DIRECCION VIGENTE: si la señal detecta agotamiento,")
p("tras ella el avance deberia ser MENOR que la base.")
p("")

for dia in ("2026-08-13", "2026-08-12"):
    h, cl, net = cargar(dia)
    n = len(cl)
    D = [dig(x) for x in net]
    p(f"--- {dia} ---   {n} minutos   digitos: min {min(D)}  max {max(D)}  "
      f"mediana {st.median(D):.0f}")

    base, senal = [], []
    for i in range(15, n - 30):
        d = cl[i] - cl[i - DIR_MIN]
        sg = 1 if d > 0 else (-1 if d < 0 else 0)
        if sg == 0:
            continue
        prev = [D[j] for j in range(i - 15, i) if D[j]]
        if len(prev) < 8 or not D[i]:
            continue
        # avance POSTERIOR en la direccion vigente (positivo = el movimiento sigue)
        av10 = (cl[min(i + 10, n - 1)] - cl[i]) * sg
        av30 = (cl[min(i + 30, n - 1)] - cl[i]) * sg
        fila = (av10, av30)
        base.append(fila)
        if D[i] <= st.mean(prev) - 1:
            senal.append(fila)

    p(f"{'grupo':>28} {'n':>5} {'avance +10m':>13} {'avance +30m':>13} {'% que sigue 30m':>16}")
    for nom, sub in (("TODOS (base)", base), ("caida de digitos >=1", senal)):
        if len(sub) < 5:
            p(f"{nom:>28} {len(sub):5} {'pocos casos':>13}")
            continue
        a10 = st.mean([x[0] for x in sub])
        a30 = st.mean([x[1] for x in sub])
        pos = 100 * sum(1 for x in sub if x[1] > 0) / len(sub)
        p(f"{nom:>28} {len(sub):5} {a10:+13.3f} {a30:+13.3f} {pos:15.0f}%")
    p("")

p("Si 'caida de digitos' tuviera valor, su avance deberia ser CLARAMENTE menor que la base")
p("(idealmente negativo: el movimiento no solo se para, se da la vuelta).")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
