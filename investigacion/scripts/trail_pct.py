# TRAILING POR PORCENTAJE vs TRAILING POR EXTREMO DE N MINUTOS.
# El usuario propone un trail del 1.9% (volatilidad diaria 0.55-0.95% x2). En intradia eso
# hay que escalarlo: la volatilidad va con la RAIZ del tiempo, sigma(W) = sigma(dia)*sqrt(W/390).
# Aqui se MIDE la volatilidad real del dia y se prueban trailings porcentuales de varios
# tamaños contra el de extremo de 20 min, que es el que va ganando.
# Lee la BD viva en SOLO-LECTURA.
import sqlite3
import statistics as st

SRC = "spy_history.db"
TXT = "TRAIL_PCT_HOY.txt"
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

O = []
def p(s=""):
    O.append(s)


# ---------- volatilidad REAL medida ----------
rets = [(cl[i] / cl[i - 1] - 1) for i in range(1, n)]
sig_min = st.stdev(rets)
sig_dia_teo = sig_min * (390 ** 0.5)
p(f"VOLATILIDAD MEDIDA HOY  -  {DIA}, {n} minutos")
p("=" * 100)
p(f"  sigma por minuto (medida)      : {100*sig_min:.4f}%   ({sig_min*cl[-1]:.3f} puntos)")
p(f"  -> extrapolada al dia (x sqrt390): {100*sig_dia_teo:.3f}%  "
  f"({sig_dia_teo*cl[-1]:.2f} puntos)")
p(f"  rango real del dia             : {max(hi)-min(lo):.2f} puntos "
  f"({100*(max(hi)-min(lo))/cl[0]:.2f}%)")
p("")
p("EQUIVALENCIA de un % DIARIO a ventanas intradia:  pct(W) = pct(dia) * sqrt(W/390)")
p("-" * 100)
p(f"{'% diario':>10} {'1 min':>10} {'5 min':>10} {'20 min':>10} {'60 min':>10} "
  f"{'20min en pts':>13}")
for pd in (0.55, 0.95, 1.9):
    fila = [f"{pd:9.2f}%"]
    for W in (1, 5, 20, 60):
        fila.append(f"{pd*(W/390)**0.5:9.3f}%")
    fila.append(f"{cl[-1]*pd*(20/390)**0.5/100:12.2f}")
    p(" ".join(fila))
p("")
p("OJO: 1.9% diario en una ventana de 20 min son ~3.3 puntos de SPY. El rango ENTERO de hoy")
p("fue de 4.96. Un trail de ese tamaño no saltaria casi nunca.")
p("")


def fmov(i, v=VENT):
    return None if i < v - 1 else sum(net[i - v + 1:i + 1]) / v


def simular(modo, par):
    """modo 'PCT': par = % de retroceso desde el mejor precio. 'EXT': par = ventana en min."""
    ops, pos = [], 0
    e_p = e_i = 0
    mejor = 0.0
    for i in range(DIR_MIN, n):
        f = fmov(i)
        if f is None:
            continue
        d = cl[i] - cl[i - DIR_MIN]
        sg = 1 if d > 0 else (-1 if d < 0 else 0)
        if pos == 0:
            if f >= ENT and sg != 0:
                pos, e_p, e_i = sg, cl[i], i
                mejor = cl[i]
            continue
        mejor = max(mejor, cl[i]) if pos > 0 else min(mejor, cl[i])
        if modo == "PCT":
            salir = (cl[i] <= mejor * (1 - par / 100)) if pos > 0 else \
                    (cl[i] >= mejor * (1 + par / 100))
        else:
            K = par
            salir = (cl[i] < min(lo[max(e_i, i - K):i])) if pos > 0 else \
                    (cl[i] > max(hi[max(e_i, i - K):i]))
        if salir:
            ops.append(((cl[i] - e_p) * pos, i - e_i))
            pos = 0
    if pos != 0:
        ops.append(((cl[-1] - e_p) * pos, n - 1 - e_i))
    return ops


p("COMPARATIVA  (misma entrada: flujo >= 1.0 M$/min y direccion 5m)")
p("-" * 100)
p(f"{'salida':>34} {'ops':>5} {'gana':>5} {'%':>7} {'puntos':>9} {'g.medio':>8} "
  f"{'p.medio':>8} {'dur':>6}")


def linea(nom, ops):
    if not ops:
        p(f"{nom:>34} {'0':>5}")
        return
    g = [o[0] for o in ops]
    w = [x for x in g if x > 0]
    l = [x for x in g if x < 0]
    p(f"{nom:>34} {len(ops):5} {len(w):5} {100*len(w)/len(ops):6.1f}% {sum(g):+9.2f} "
      f"{sum(w)/len(w) if w else 0:+8.2f} {sum(l)/len(l) if l else 0:+8.2f} "
      f"{sum(o[1] for o in ops)/len(ops):6.1f}")


p("   TRAILING STOP CLASICO: guarda el mejor precio, lo actualiza CADA MINUTO y sale cuando")
p("   el precio retrocede ese % desde el mejor. 0.096% = 1.9% diario escalado a 1 minuto.")
for pct in (0.06, 0.07, 0.08, 0.096, 0.11, 0.12, 0.14, 0.16, 0.20):
    linea(f"trail {pct:.3f}% ({cl[-1]*pct/100:.2f} pts)", simular("PCT", pct))
p("")
for K in (10, 20, 30):
    linea(f"trail extremo {K} min", simular("EXT", K))

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
