# PERMANENCIA: ¿sirve el flujo del subyacente para decidir CUANTO se aguanta una posicion?
#
# Regla que se prueba:
#   direccion = la que ya lleva el precio (signo del movimiento de los ultimos DIR_MIN minutos)
#   se ENTRA   cuando flujo/min en ventana movil >= UMBRAL
#   se AGUANTA mientras siga >= UMBRAL_SALIDA
#   se SALE    cuando cae por debajo, o cuando la direccion del precio se da la vuelta
#
# Se mide contra el maximo disponible: la suma de los recorridos de los tramos reales del dia.
# Se prueban VARIOS umbrales para leer la REGION, nunca la celda maxima.
# Lee la BD viva en SOLO-LECTURA.
import sqlite3
import statistics as st

SRC = "spy_history.db"
TXT = "PERMANENCIA_HOY.txt"
DIA = "2026-08-13"
DIR_MIN = 5           # minutos que definen la direccion vigente del precio

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
tp = {m: (c, v) for m, c, v in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
src.close()

horas = [x[0] for x in velas]
close = [x[1] for x in velas]
n = len(velas)
net = [tp.get(h, (0.0, 0.0))[0] - tp.get(h, (0.0, 0.0))[1] for h in horas]

O = []
def p(s=""):
    O.append(s)


p(f"PERMANENCIA: ¿cuanto se aguanta segun el flujo?  {DIA}, {n} minutos")
p("=" * 104)
p("El flujo del subyacente NO da direccion (net_spy es positivo casi siempre): da ENERGIA.")
p(f"La direccion la pone el precio (movimiento de los ultimos {DIR_MIN} min).")
p("")


def flujo_movil(i, v):
    if i < v - 1:
        return None
    return sum(net[i - v + 1:i + 1]) / v


# ---------- referencia: cuanto habia disponible ----------
# tramos del ZigZag corregido (mismo criterio que GIROS_HOY)
UMBRAL_ZZ = 0.75
piv, dir_, hi_i, lo_i = [0], 0, 0, 0
for i in range(1, n):
    if close[i] > close[hi_i]:
        hi_i = i
    if close[i] < close[lo_i]:
        lo_i = i
    if dir_ >= 0 and close[hi_i] - close[i] >= UMBRAL_ZZ:
        piv.append(hi_i); dir_ = -1; lo_i = i
    elif dir_ <= 0 and close[i] - close[lo_i] >= UMBRAL_ZZ:
        piv.append(lo_i); dir_ = 1; hi_i = i
piv.append(n - 1)
piv = sorted(set(piv))
disp = sum(abs(close[piv[k + 1]] - close[piv[k]]) for k in range(len(piv) - 1))
p(f"MAXIMO DISPONIBLE (suma de los tramos del dia): {disp:.2f} puntos de SPY")
p("")


def simular(vent, ent, sal):
    """Devuelve (puntos, n_ops, minutos_dentro, detalle)."""
    pos = 0            # +1 largo, -1 corto, 0 fuera
    e_precio = 0.0
    pts, ops, dentro, det = 0.0, 0, 0, []
    for i in range(n):
        f = flujo_movil(i, vent)
        if f is None or i < DIR_MIN:
            continue
        d = close[i] - close[i - DIR_MIN]
        sg = 1 if d > 0 else (-1 if d < 0 else 0)
        if pos == 0:
            if f >= ent and sg != 0:
                pos, e_precio, e_i = sg, close[i], i
                ops += 1
        else:
            # salir por flujo agotado o por giro de la direccion del precio
            if f < sal or (sg != 0 and sg != pos):
                g = (close[i] - e_precio) * pos
                pts += g
                dentro += i - e_i
                det.append((horas[e_i], horas[i], pos, g))
                pos = 0
    if pos != 0:
        g = (close[-1] - e_precio) * pos
        pts += g
        dentro += n - 1 - e_i
        det.append((horas[e_i], horas[-1], pos, g))
    return pts, ops, dentro, det


p("REGION DE UMBRALES  (flujo en M$/min).  ent = entrar, sal = aguantar mientras >=")
p("-" * 104)
p(f"{'ventana':>8} {'ent':>6} {'sal':>6} {'puntos':>9} {'% del max':>10} {'ops':>5} "
  f"{'min dentro':>11} {'pts/op':>8}")
mejor = None
for vent in (5, 10, 15):
    for ent_m in (0.3, 0.5, 1.0, 1.5):
        for sal_m in (0.0, 0.1, 0.3):
            if sal_m >= ent_m:
                continue
            pts, ops, dentro, det = simular(vent, ent_m * 1e6, sal_m * 1e6)
            p(f"{vent:8} {ent_m:6.1f} {sal_m:6.1f} {pts:+9.2f} {100*pts/disp:9.1f}% "
              f"{ops:5} {dentro:11} {pts/ops if ops else 0:+8.2f}")
            if mejor is None or pts > mejor[0]:
                mejor = (pts, vent, ent_m, sal_m, det)
p("")

pts, vent, ent_m, sal_m, det = mejor
p(f"DETALLE DE LA MEJOR COMBINACION (ventana {vent}m, entrar >={ent_m}, aguantar >={sal_m})")
p("-" * 104)
p("OJO: es la celda MAXIMA de la rejilla, elegida a posteriori sobre UN dia. Sirve para ver")
p("como se comporta, NO como parametros validados. Lo que vale es la REGION de arriba.")
p(f"{'entra':>7} {'sale':>7} {'lado':>6} {'puntos':>9}")
for e, s, lado, g in det:
    p(f"{e:>7} {s:>7} {'LARGO' if lado>0 else 'CORTO':>6} {g:+9.2f}")
p("")

# ---------- comparacion: aguantar SIN mirar el flujo ----------
p("CONTROL: la misma entrada pero SIN la regla de flujo (solo direccion del precio)")
p("-" * 104)
pos, pts0, ops0 = 0, 0.0, 0
for i in range(DIR_MIN, n):
    d = close[i] - close[i - DIR_MIN]
    sg = 1 if d > 0 else (-1 if d < 0 else 0)
    if pos == 0 and sg != 0:
        pos, e_precio = sg, close[i]
        ops0 += 1
    elif pos != 0 and sg != 0 and sg != pos:
        pts0 += (close[i] - e_precio) * pos
        pos = sg
        e_precio = close[i]
        ops0 += 1
p(f"solo direccion del precio: {pts0:+.2f} puntos en {ops0} operaciones "
  f"({100*pts0/disp:.1f}% del maximo)")
p("")
p("Si la mejor combinacion con flujo no bate CLARAMENTE a este control, el flujo no")
p("esta aportando nada: la ganancia vendria de la regla de direccion, no del tape.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
