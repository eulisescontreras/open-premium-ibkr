# SALIDAS: la regla anterior cortaba a los 4.4 minutos de media y mataba los tramos largos.
# Aqui se prueban salidas que PERMITEN AGUANTAR, y se mide ACIERTOS vs FALLOS (no solo puntos).
#
# Entrada (fija, la que ya funciono): flujo/min del subyacente >= ENT en ventana movil,
# y direccion = signo del movimiento de los ultimos DIR_MIN minutos.
#
# Salidas que se comparan:
#   A) flujo flojo N minutos SEGUIDOS  (no un minuto suelto)
#   B) trailing por extremo: sale si el precio rompe el extremo opuesto de los ultimos K minutos
#   C) A y B a la vez (sale con la primera que salte)
# Lee la BD viva en SOLO-LECTURA.
import sqlite3

SRC = "spy_history.db"
TXT = "SALIDAS_HOY.txt"
DIA = "2026-08-13"
DIR_MIN = 5

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
tp = {m: (c, v) for m, c, v in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
src.close()

horas = [x[0] for x in velas]
high = [x[1] for x in velas]
low = [x[2] for x in velas]
close = [x[3] for x in velas]
n = len(velas)
net = [tp.get(h, (0.0, 0.0))[0] - tp.get(h, (0.0, 0.0))[1] for h in horas]


def fmov(i, v):
    return None if i < v - 1 else sum(net[i - v + 1:i + 1]) / v


def simular(vent, ent, modo, sal=0.3e6, nflojo=3, K=10):
    """modo: 'A' flujo flojo N seguidos | 'B' trailing extremo | 'C' ambas | 'VIEJA' la anterior"""
    pos, flojo, ops = 0, 0, []
    e_p = e_i = 0
    for i in range(DIR_MIN, n):
        f = fmov(i, vent)
        if f is None:
            continue
        d = close[i] - close[i - DIR_MIN]
        sg = 1 if d > 0 else (-1 if d < 0 else 0)
        if pos == 0:
            if f >= ent and sg != 0:
                pos, e_p, e_i, flojo = sg, close[i], i, 0
            continue
        # --- dentro de posicion ---
        flojo = flojo + 1 if f < sal else 0
        salir = False
        if modo == "VIEJA":
            salir = f < sal or (sg != 0 and sg != pos)
        elif modo == "A":
            salir = flojo >= nflojo
        elif modo == "B":
            if pos > 0 and i > e_i:
                salir = close[i] < min(low[max(e_i, i - K):i])
            elif pos < 0 and i > e_i:
                salir = close[i] > max(high[max(e_i, i - K):i])
        elif modo == "C":
            b = False
            if pos > 0 and i > e_i:
                b = close[i] < min(low[max(e_i, i - K):i])
            elif pos < 0 and i > e_i:
                b = close[i] > max(high[max(e_i, i - K):i])
            salir = (flojo >= nflojo) or b
        if salir:
            ops.append(((close[i] - e_p) * pos, i - e_i, horas[e_i], horas[i], pos))
            pos = 0
    if pos != 0:
        ops.append(((close[-1] - e_p) * pos, n - 1 - e_i, horas[e_i], horas[-1], pos))
    return ops


def resumen(ops):
    if not ops:
        return None
    g = [o[0] for o in ops]
    win = [x for x in g if x > 0]
    los = [x for x in g if x < 0]
    dur = sum(o[1] for o in ops) / len(ops)
    return (len(ops), len(win), len(los), 100 * len(win) / len(ops), sum(g),
            sum(win) / len(win) if win else 0, sum(los) / len(los) if los else 0, dur)


O = []
def p(s=""):
    O.append(s)


p(f"REGLAS DE SALIDA  -  {DIA}, {n} minutos")
p("=" * 108)
p("Entrada fija: flujo/min >= ENT (ventana movil) y direccion del precio a 5 min.")
p("El objetivo es que los ACIERTOS superen a los FALLOS y que las operaciones duren.")
p("")
p(f"{'salida':>26} {'vent':>5} {'ent':>5} {'ops':>5} {'gana':>5} {'pierde':>7} "
  f"{'%acierto':>9} {'puntos':>9} {'g.medio':>8} {'p.medio':>8} {'dur':>6}")

filas = []
for vent in (5, 10):
    for ent_m in (1.0, 1.5, 2.0):
        for modo, nom, kw in (
            ("VIEJA", "anterior (oscilacion 5m)", {}),
            ("A", "flujo flojo 3 seguidos", {"nflojo": 3}),
            ("A", "flujo flojo 5 seguidos", {"nflojo": 5}),
            ("B", "trailing extremo 10m", {"K": 10}),
            ("B", "trailing extremo 20m", {"K": 20}),
            ("C", "flojo 5 + trailing 20m", {"nflojo": 5, "K": 20}),
        ):
            ops = simular(vent, ent_m * 1e6, modo, **kw)
            r = resumen(ops)
            if not r:
                continue
            nop, w, l, pw, pts, gm, pm, dur = r
            p(f"{nom:>26} {vent:5} {ent_m:5.1f} {nop:5} {w:5} {l:7} {pw:8.1f}% "
              f"{pts:+9.2f} {gm:+8.2f} {pm:+8.2f} {dur:6.1f}")
            filas.append((pw, pts, nom, vent, ent_m, ops))
p("")

# la mejor por % de acierto, exigiendo un minimo de operaciones para que signifique algo
cand = [f for f in filas if len(f[5]) >= 5]
cand.sort(key=lambda x: (-x[0], -x[1]))
pw, pts, nom, vent, ent_m, ops = cand[0]
p(f"MEJOR POR % DE ACIERTO (con >=5 operaciones): {nom}, ventana {vent}m, entrada {ent_m}")
p("-" * 108)
p(f"{'entra':>7} {'sale':>7} {'lado':>6} {'min':>5} {'puntos':>9}")
for g, dur, e, s, lado in ops:
    p(f"{e:>7} {s:>7} {'LARGO' if lado>0 else 'CORTO':>6} {dur:5} {g:+9.2f}")
p("")
p("OJO: es la mejor celda de UN dia, elegida a posteriori. Lo que vale es si el patron se")
p("repite en varias filas de la tabla de arriba, no esta combinacion concreta.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
