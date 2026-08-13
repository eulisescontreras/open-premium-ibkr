# DIAGNOSTICO TRAMO A TRAMO: todos los cambios de tendencia de hoy vs lo que hace el sistema.
# Para cada tramo real dice si el sistema lo CAPTURA, lo PIERDE o entra en FALSO, y por que.
#
# Sistema evaluado (el que salio de SALIDAS_HOY): ventana 5m, entrada flujo/min >= 1.0 M$,
# direccion = movimiento de los ultimos 5 min, salida = trailing por extremo de 20 min.
# Lee la BD viva en SOLO-LECTURA.
import sqlite3

SRC = "spy_history.db"
TXT = "DIAGNOSTICO_HOY.txt"
DIA = "2026-08-13"
DIR_MIN, VENT, ENT, K = 5, 5, 1.0e6, 20
UMBRAL_ZZ = 0.40      # mas fino que 0.75: se quieren TODOS los cambios, no solo los grandes

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


def fmov(i, v=VENT):
    return None if i < v - 1 else sum(net[i - v + 1:i + 1]) / v


# ---------- tramos ----------
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
tramos = [(piv[k], piv[k + 1]) for k in range(len(piv) - 1) if piv[k + 1] - piv[k] >= 2]

# ---------- simulacion del sistema ----------
ops, pos, e_p, e_i = [], 0, 0.0, 0
for i in range(DIR_MIN, n):
    f = fmov(i)
    if f is None:
        continue
    d = close[i] - close[i - DIR_MIN]
    sg = 1 if d > 0 else (-1 if d < 0 else 0)
    if pos == 0:
        if f >= ENT and sg != 0:
            pos, e_p, e_i = sg, close[i], i
        continue
    salir = False
    if pos > 0 and i > e_i:
        salir = close[i] < min(low[max(e_i, i - K):i])
    elif pos < 0 and i > e_i:
        salir = close[i] > max(high[max(e_i, i - K):i])
    if salir:
        ops.append((e_i, i, pos, (close[i] - e_p) * pos))
        pos = 0
if pos != 0:
    ops.append((e_i, n - 1, pos, (close[-1] - e_p) * pos))

O = []
def p(s=""):
    O.append(s)


p(f"DIAGNOSTICO TRAMO A TRAMO  -  {DIA}, {n} minutos (09:30 - {horas[-1]})")
p("=" * 116)
p(f"tramos detectados con ZigZag sobre cierres, umbral ${UMBRAL_ZZ:.2f}  ->  {len(tramos)} tramos")
p(f"sistema: ventana {VENT}m, entrar si flujo/min >= {ENT/1e6:.1f} M$, direccion {DIR_MIN}m, "
  f"salida trailing extremo {K}m")
p("")
p("VEREDICTO POR TRAMO")
p("-" * 116)
p(f"{'#':>3} {'desde':>7} {'hasta':>7} {'min':>4} {'dir':>5} {'recorr':>8} {'flujo M$/min':>13} "
  f"{'que hace el sistema':>22} {'captura':>9} {'% tramo':>8}")

# posicion del sistema en CADA minuto: asi cada tramo se lleva solo SUS minutos.
# Contar la operacion entera en cada tramo que atraviesa inflaba el total (daba +34 cuando
# las 5 operaciones suman +7.79) y producia capturas del 400%.
posm = [0] * n
for a_, b_, lado, _ in ops:
    for i in range(a_, b_ + 1):
        posm[i] = lado

res = []
for j, (a, b) in enumerate(tramos, 1):
    rec = close[b] - close[a]
    dirn = 1 if rec > 0 else -1
    dur = b - a
    fl = sum(net[a + 1:b + 1]) / dur / 1e6 if dur else 0
    # P&L del sistema SOLO en los minutos de este tramo (mark to market)
    cap = sum(posm[i - 1] * (close[i] - close[i - 1]) for i in range(a + 1, b + 1))
    # cuantos minutos del tramo estuvo a favor / en contra / fuera
    afav = sum(1 for i in range(a + 1, b + 1) if posm[i - 1] == dirn)
    acon = sum(1 for i in range(a + 1, b + 1) if posm[i - 1] == -dirn)
    fuera = dur - afav - acon
    if fuera == dur:
        fmax = max([fmov(i) or 0 for i in range(a, b + 1)] or [0]) / 1e6
        veredicto = "FUERA (flujo bajo)" if fmax < ENT / 1e6 else "FUERA (direccion)"
    elif afav >= acon and afav > 0:
        veredicto = f"A FAVOR {afav}/{dur} min"
    elif acon > 0:
        veredicto = f"EN CONTRA {acon}/{dur} min"
    else:
        veredicto = "FUERA"
    pctt = 100 * cap / abs(rec) if rec else 0
    res.append((j, veredicto, cap, rec, fl))
    p(f"{j:>3} {horas[a]:>7} {horas[b]:>7} {dur:4} {'UP' if dirn>0 else 'DOWN':>5} "
      f"{rec:+8.2f} {fl:13.3f} {veredicto:>22} {cap:+9.2f} {pctt:7.1f}%")
p("")
p(f"   COMPROBACION: la suma de las capturas por tramo debe dar el total de las operaciones.")
p(f"   suma por tramo = {sum(r[2] for r in res):+.2f}   |   suma de las {len(ops)} operaciones "
  f"= {sum(o[3] for o in ops):+.2f}")
p("")

# ---------- resumen ----------
cap_ok = [r for r in res if r[1].startswith("A FAVOR")]
no_ent = [r for r in res if r[1].startswith("FUERA")]
contra_ = [r for r in res if r[1].startswith("EN CONTRA")]
p("RESUMEN")
p("-" * 116)
p(f"  tramos totales            : {len(res)}")
p(f"  A FAVOR (bien posicionado): {len(cap_ok):3}   aportan {sum(r[2] for r in cap_ok):+7.2f}")
p(f"  EN CONTRA (mal colocado)  : {len(contra_):3}   cuestan {sum(r[2] for r in contra_):+7.2f}")
p(f"  FUERA (sin posicion)      : {len(no_ent):3}   dejando {sum(abs(r[3]) for r in no_ent):7.2f} "
  f"puntos sin tocar")
p(f"  RESULTADO NETO            : {sum(r[2] for r in res):+7.2f} puntos")
p("")

p("DONDE FALLA  (tramos en contra o no tocados, ordenados por lo que cuestan)")
p("-" * 116)
p(f"{'#':>3} {'que paso':>22} {'recorrido':>10} {'coste':>9} {'flujo M$/min':>13}")
malos = sorted([r for r in res if r[1].startswith(("FUERA", "EN CONTRA"))],
               key=lambda r: (abs(r[3]) if r[1].startswith("FUERA") else r[2]))
for j, ver, cap, rec, fl in malos[:12]:
    coste = abs(rec) if ver.startswith("FUERA") else cap
    p(f"{j:>3} {ver:>22} {rec:+10.2f} {coste:+9.2f} {fl:13.3f}")
p("")

p("EL FLUJO COMO FILTRO: ¿separa los tramos donde el sistema esta bien colocado?")
p("-" * 116)
for nom, sub in (("a favor", cap_ok), ("en contra", contra_), ("fuera", no_ent)):
    if not sub:
        continue
    fs = [r[4] for r in sub]
    p(f"  {nom:>12}: n={len(sub):2}  flujo/min medio={sum(fs)/len(fs):7.3f}  "
      f"min={min(fs):7.3f}  max={max(fs):7.3f}")

p("")
p("OPERACIONES DEL SISTEMA (todas)")
p("-" * 116)
p(f"{'entra':>7} {'sale':>7} {'lado':>6} {'min':>5} {'puntos':>9}")
for a, b, lado, g in ops:
    p(f"{horas[a]:>7} {horas[b]:>7} {'LARGO' if lado>0 else 'CORTO':>6} {b-a:5} {g:+9.2f}")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
