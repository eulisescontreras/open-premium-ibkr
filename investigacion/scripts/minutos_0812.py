# EL 08-12 MINUTO A MINUTO: ¿en que minutos dice ENTRA el flujo, y coinciden con los 3 giros?
# Columnas: hora, spy, volumen del minuto, ratio vs mediana, si dispara a cada umbral,
#           tramo real vigente y lo que dice la EMA. Los 3 pivotes van marcados.
import sqlite3
import statistics as st

TXT = "MINUTOS_0812.txt"
DIA = "2026-08-12"
UMBRAL_ZZ = 1.50

c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
v = c.execute("select hora,close from bars_minute where fecha=? order by hora", (DIA,)).fetchall()
ta = {h: r for h, *r in c.execute("select hora,ema8,ema21 from ta_minute where fecha=?", (DIA,))}
c.close()
d = sqlite3.connect("spy_tape_ayer.db")
t = d.execute("select minuto, size from trades_raw").fetchall()
d.close()

h = [x[0] for x in v]
cl = [x[1] for x in v]
n = len(v)
vol = {}
for m, s in t:
    if s and s > 0:
        vol[m] = vol.get(m, 0) + s
VOL = [vol.get(x, 0) for x in h]
med = st.median([x for x in VOL if x]) or 1.0

piv, d_, hi, lo = [0], 0, 0, 0
for i in range(1, n):
    if cl[i] > cl[hi]:
        hi = i
    if cl[i] < cl[lo]:
        lo = i
    if d_ >= 0 and cl[hi] - cl[i] >= UMBRAL_ZZ:
        piv.append(hi); d_ = -1; lo = i
    elif d_ <= 0 and cl[i] - cl[lo] >= UMBRAL_ZZ:
        piv.append(lo); d_ = 1; hi = i
piv.append(n - 1)
piv = sorted(set(piv))
tramo = [0] * n
lado = [0] * n
for k in range(len(piv) - 1):
    a, b = piv[k], piv[k + 1]
    s = 1 if cl[b] > cl[a] else -1
    for i in range(a, b + 1):
        tramo[i] = k + 1
        lado[i] = s


def sg(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


O = []
def p(s):
    O.append(s)


p(f"EL {DIA} MINUTO A MINUTO  -  ¿cuando dice ENTRA el flujo?")
p("=" * 104)
p(f"mediana del volumen por minuto: {med:,.0f} acciones")
p(f"los 3 giros reales (ZigZag ${UMBRAL_ZZ:.2f}): " +
  ", ".join(f"{h[piv[k]]}" for k in range(len(piv))))
p("")
p("dispara = el volumen del minuto supera N veces la mediana -> el sistema abriria posicion")
p("")
p(f"{'hora':>7} {'spy':>9} {'volumen':>10} {'ratio':>7} {'1x':>4} {'2x':>4} {'3x':>4} "
  f"{'5x':>4} {'tramo':>6} {'lado':>6} {'EMA':>5}  giro")
for i in range(n):
    r = VOL[i] / med if med else 0
    t_ = ta.get(h[i])
    e = sg(t_[0] - t_[1]) if (t_ and t_[0] and t_[1]) else 0
    marca = ""
    if i in piv:
        marca = "  <<<<<< GIRO"
    p(f"{h[i]:>7} {cl[i]:9.2f} {VOL[i]:10,} {r:7.2f} "
      f"{'SI' if r >= 1 else '.':>4} {'SI' if r >= 2 else '.':>4} "
      f"{'SI' if r >= 3 else '.':>4} {'SI' if r >= 5 else '.':>4} "
      f"{tramo[i]:6} {'UP' if lado[i] > 0 else 'DOWN':>6} "
      f"{'UP' if e > 0 else ('DOWN' if e < 0 else '-'):>5}{marca}")

p("")
p("RESUMEN: ¿cuantos minutos disparan a cada umbral?")
p("-" * 104)
for u in (1, 2, 3, 5, 8):
    ss = [i for i in range(n) if VOL[i] >= u * med]
    p(f"   {u}x mediana: {len(ss):3} minutos de {n} ({100*len(ss)/n:4.1f}% del dia)")
p("")
p("¿DISPARA EL FLUJO EN LOS GIROS? (minutos alrededor de cada pivote)")
p("-" * 104)
p(f"{'giro':>7} {'ratio en el giro':>18} {'max ratio +-5 min':>20}")
for k in piv:
    if k >= n:
        continue
    ventana = [VOL[j] / med for j in range(max(0, k - 5), min(n, k + 6))]
    p(f"{h[k]:>7} {VOL[k]/med:18.2f} {max(ventana):20.2f}")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
