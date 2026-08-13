# ¿EL TRAIL % PIERDE EN TODOS LOS GIROS O SOLO EN EL AGREGADO?
# Se fijan las MISMAS entradas y se compara, ENTRADA POR ENTRADA, que habria dado cada salida.
# Asi se ve si una regla gana siempre o si cada una gana en un tipo de tramo distinto.
# Lee la BD viva en SOLO-LECTURA.
import sqlite3

SRC = "spy_history.db"
TXT = "SALIDA_POR_GIRO.txt"
DIA = "2026-08-13"
DIR_MIN, VENT, ENT = 5, 5, 1.0e6

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
tp = {m: (a, b) for m, a, b in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
src.close()

h = [x[0] for x in velas]
hi = [x[1] for x in velas]
lo = [x[2] for x in velas]
cl = [x[3] for x in velas]
n = len(velas)
net = [tp.get(x, (0, 0))[0] - tp.get(x, (0, 0))[1] for x in h]


def fmov(i, v=VENT):
    return None if i < v - 1 else sum(net[i - v + 1:i + 1]) / v


def salida(e_i, lado, modo, par):
    """Desde la entrada e_i, devuelve (i_salida, puntos) segun la regla."""
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
            return i, (cl[i] - cl[e_i]) * lado
    return n - 1, (cl[-1] - cl[e_i]) * lado


# entradas: se usan las del sistema con trailing de extremo 20 (las 5 conocidas), pero
# recalculadas para no depender de una lista fija
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

REGLAS = [("extremo 20m", "EXT", 20), ("extremo 10m", "EXT", 10),
          ("trail 0.096%", "PCT", 0.096), ("trail 0.11%", "PCT", 0.11),
          ("trail 0.06%", "PCT", 0.06)]

O = []
def p(s=""):
    O.append(s)


p(f"MISMA ENTRADA, DISTINTA SALIDA  -  {DIA}")
p("=" * 104)
p(f"{len(entradas)} entradas. Para cada una se aplica cada regla de salida por separado.")
p("")
p(f"{'entrada':>8} {'lado':>6} " + " ".join(f"{r[0]:>14}" for r in REGLAS))
tot = {r[0]: 0.0 for r in REGLAS}
gana = {r[0]: 0 for r in REGLAS}
for e_i, lado in entradas:
    fila = [f"{h[e_i]:>8} {'LARGO' if lado > 0 else 'CORTO':>6}"]
    res = {}
    for nom, modo, par in REGLAS:
        i_s, pts = salida(e_i, lado, modo, par)
        res[nom] = (pts, i_s - e_i)
        tot[nom] += pts
    mejor = max(res.values(), key=lambda x: x[0])[0]
    for nom, _, _ in REGLAS:
        pts, dur = res[nom]
        marca = "*" if pts == mejor else " "
        if pts == mejor:
            gana[nom] += 1
        fila.append(f"{pts:+8.2f}/{dur:3}{marca}")
    p(" ".join(fila))
p("")
p(f"{'TOTAL':>8} {'':>6} " + " ".join(f"{tot[r[0]]:+13.2f} " for r in REGLAS))
p(f"{'gana en':>8} {'':>6} " + " ".join(f"{gana[r[0]]:>10} giros " for r in REGLAS))
p("")
p("* = la mejor salida DE ESE GIRO.  El formato es puntos/minutos dentro.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
