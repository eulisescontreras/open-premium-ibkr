# A vs B: ¿sobrevive el patron del "millon por minuto" al cambiar la columna de premium?
#
#   A) premium      = last * lastSize   -> capta el 22.9% del volumen real (lo usado todo el dia)
#   B) premium_dvol = last * dvol       -> capta el 129.3% (delta del volumen acumulado)
#
# Se repite EL MISMO analisis con ambas: tramos del dia, flujo por minuto de cada tramo, y la
# separacion entre tramos con empuje y sin el. Si el patron solo aparece con A, era un artefacto
# del muestreo. Lee la BD viva en SOLO-LECTURA.
import sqlite3
import statistics as st

SRC = "spy_history.db"
TXT = "AB_COLUMNA.txt"
DIA = "2026-08-13"
UMBRAL_ZZ = 0.75

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
# tick a tick, con las DOS magnitudes, para clasificar con la MISMA regla del tick
ticks = src.execute(
    "select substr(hora,1,5), last, size, dvol from tape "
    "where fecha=? and grupo='SPY' and last is not null order by ts, id", (DIA,)).fetchall()
src.close()

h = [x[0] for x in velas]
cl = [x[1] for x in velas]
n = len(velas)

# ---------- flujo neto por minuto con cada columna, misma regla del tick ----------
def flujo(col):
    """col 0 = size (premium), col 1 = dvol (premium_dvol)."""
    acc = {}
    pp = ps = None
    for minuto, last, size, dvol in ticks:
        mag = size if col == 0 else dvol
        if last is None or mag is None or mag <= 0:
            continue
        if pp is None:
            ag = None
        elif last > pp:
            ag = 1
        elif last < pp:
            ag = -1
        else:
            ag = ps
        if ag:
            ps = ag
        pp = last
        if ag:
            acc[minuto] = acc.get(minuto, 0.0) + ag * last * mag
    return [acc.get(x, 0.0) for x in h]


NET = {"A size (22.9%)": flujo(0), "B dvol (129.3%)": flujo(1)}

# ---------- tramos (identicos para ambas: solo dependen del precio) ----------
piv, dir_, hi_i, lo_i = [0], 0, 0, 0
for i in range(1, n):
    if cl[i] > cl[hi_i]:
        hi_i = i
    if cl[i] < cl[lo_i]:
        lo_i = i
    if dir_ >= 0 and cl[hi_i] - cl[i] >= UMBRAL_ZZ:
        piv.append(hi_i); dir_ = -1; lo_i = i
    elif dir_ <= 0 and cl[i] - cl[lo_i] >= UMBRAL_ZZ:
        piv.append(lo_i); dir_ = 1; hi_i = i
piv.append(n - 1)
piv = sorted(set(piv))
tramos = [(piv[k], piv[k + 1]) for k in range(len(piv) - 1) if piv[k + 1] - piv[k] >= 3]

O = []
def p(s=""):
    O.append(s)


p(f"A vs B: ¿el patron depende de la columna de premium?  -  {DIA}")
p("=" * 104)
p("A) premium      = last * lastSize  -> 22.9% del volumen real (la usada todo el dia)")
p("B) premium_dvol = last * dvol      -> 129.3% del volumen real")
p("Misma regla del tick, mismos tramos: lo UNICO que cambia es la magnitud de cada operacion.")
p("")

for nom, net in NET.items():
    ab = [abs(x) for x in net if x]
    p(f"--- {nom} ---   mediana |neto/min| = {st.median(ab) if ab else 0:,.0f}")
    p(f"{'#':>3} {'desde':>7} {'hasta':>7} {'min':>5} {'dir':>5} {'recorr':>8} "
      f"{'flujo/min M$':>14}")
    vals = []
    for j, (a, b) in enumerate(tramos, 1):
        rec = cl[b] - cl[a]
        dur = b - a
        fl = sum(net[a + 1:b + 1]) / dur / 1e6
        vals.append((abs(rec), dur, fl))
        p(f"{j:>3} {h[a]:>7} {h[b]:>7} {dur:5} {'UP' if rec > 0 else 'DOWN':>5} "
          f"{rec:+8.2f} {fl:14.3f}")
    # separacion: tramos grandes (>=1.5 pts) vs pequeños
    gr = [v[2] for v in vals if v[0] >= 1.5]
    pe = [v[2] for v in vals if v[0] < 1.5]
    if gr and pe:
        p(f"    tramos GRANDES (>=1.5 pts): flujo/min medio {st.mean(gr):+.3f}  "
          f"(n={len(gr)})")
        p(f"    tramos pequeños  (<1.5 pts): flujo/min medio {st.mean(pe):+.3f}  "
          f"(n={len(pe)})")
        p(f"    separacion: {abs(st.mean(gr)) / (abs(st.mean(pe)) + 1e-9):.1f}x")
    p("")

# ---------- amplitud: |flujo| grande -> movimiento grande ----------
p("¿SIGUE PREDICIENDO AMPLITUD?  P(mover >=0.50 en 30 min) segun el multiplo de la mediana")
p("-" * 104)
p(f"{'columna':>18} {'calma <2x':>11} {'>=3x':>9} {'>=5x':>9} {'>=10x':>9}")
for nom, net in NET.items():
    med = st.median([abs(x) for x in net if x]) or 1.0
    fila = [f"{nom:>18}"]
    for cond in (("calma", lambda r: r < 2), (">=3", lambda r: r >= 3),
                 (">=5", lambda r: r >= 5), (">=10", lambda r: r >= 10)):
        sel = [i for i in range(n - 30) if cond[1](abs(net[i]) / med)]
        if len(sel) < 5:
            fila.append(f"{'-':>9}")
            continue
        ok = sum(1 for i in sel if abs(cl[min(i + 30, n - 1)] - cl[i]) >= 0.50)
        fila.append(f"{100*ok/len(sel):8.0f}%")
    p(" ".join(fila))

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
