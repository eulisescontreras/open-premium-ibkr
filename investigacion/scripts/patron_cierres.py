# Teoria del usuario (2026-08-13): rachas de cierres consecutivos en la misma direccion.
#   A) continuacion: k cierres seguidos al alza -> el siguiente tambien, mas que por azar
#   B) el diferencial close-close crece al acelerar y decae al agotarse
#   C) "vela verde" (close>open) vs "cierra por encima del cierre previo" NO son lo mismo
# Lee SOLO spy_velas.db (copia). No toca la BD viva ni IBKR.
import random
import sqlite3
import statistics as st

DB = "spy_velas.db"
TXT = "PATRON_CIERRES.txt"
NPERM = 300
SEED = 20260813

O = []
def p(s=""):
    O.append(s)


def signo(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def rachas_de(signos):
    """Corta la serie en tramos consecutivos del MISMO signo. El 0 rompe y no forma racha.

    Devuelve listas de INDICES (no de signos): asi el bloque B puede leer el |delta| de
    cada posicion sin recalcular offsets. Con signos se desalineaba en cuanto habia un 0.
    """
    out, act = [], []
    for i, s in enumerate(signos):
        if s == 0:
            if act:
                out.append(act)
            act = []
            continue
        if act and signos[act[0]] == s:
            act.append(i)
        else:
            if act:
                out.append(act)
            act = [i]
    if act:
        out.append(act)
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def spearman(xs, ys):
    def rk(v):
        orden = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(orden):
            j = i
            while j + 1 < len(orden) and v[orden[j + 1]] == v[orden[i]]:
                j += 1
            med = (i + j) / 2.0 + 1
            for t in range(i, j + 1):
                r[orden[t]] = med
            i = j + 1
        return r
    return pearson(rk(xs), rk(ys))


# ------------------------------------------------------------------ datos
c = sqlite3.connect(DB)
dias = [r[0] for r in c.execute("select distinct fecha from bars_minute order by fecha")]
datos = {}
for d in dias:
    datos[d] = c.execute(
        "select hora,open,close from bars_minute where fecha=? order by hora", (d,)).fetchall()
c.close()

p("PATRON DE CIERRES CONSECUTIVOS  -  teoria del usuario")
p("=" * 96)
p(f"fuente: {DB}   dias: {', '.join(dias)}   nula: {NPERM} permutaciones (semilla {SEED})")
p("delta = close[i] - close[i-1]. Racha = deltas consecutivos del mismo signo.")
p("")

# ================================================================== C) color vs delta
p("C) 'VELA VERDE' vs 'CIERRA POR ENCIMA DEL CIERRE ANTERIOR' -- ¿son lo mismo?")
p("-" * 96)
p(f"{'fecha':12} {'velas':>6} {'coinciden':>10} {'%':>7} {'verde_pero_baja':>16} {'roja_pero_sube':>15}")
tot = [0, 0, 0, 0]
for d in dias:
    filas = datos[d]
    n = coin = vpb = rps = 0
    for i in range(1, len(filas)):
        _, o_, cl = filas[i]
        prev = filas[i - 1][2]
        col = signo(cl - o_)          # verde/roja
        dlt = signo(cl - prev)        # cierra por encima/debajo del cierre previo
        if col == 0 or dlt == 0:
            continue
        n += 1
        if col == dlt:
            coin += 1
        elif col > 0:
            vpb += 1
        else:
            rps += 1
    tot = [tot[0] + n, tot[1] + coin, tot[2] + vpb, tot[3] + rps]
    p(f"{d:12} {n:6} {coin:10} {100.0*coin/n:6.1f}% {vpb:16} {rps:15}")
p(f"{'TOTAL':12} {tot[0]:6} {tot[1]:10} {100.0*tot[1]/tot[0]:6.1f}% {tot[2]:16} {tot[3]:15}")
p("")
p("  verde_pero_baja = vela verde (close>open) que cierra POR DEBAJO del cierre anterior")
p("  roja_pero_sube  = vela roja  (close<open) que cierra POR ENCIMA del cierre anterior")
p("")

# ================================================================== diferencial del dia
p("DIFERENCIAL TOTAL POR DIA (lo que pediste: 'cuanto es el diferencial en todo un dia')")
p("-" * 96)
p(f"{'fecha':12} {'velas':>6} {'suma|delta|':>12} {'neto':>9} {'eficien':>8} "
  f"{'|d|medio':>9} {'|d|max':>8} {'d=0':>5}")
for d in dias:
    cl = [r[2] for r in datos[d]]
    dl = [cl[i] - cl[i - 1] for i in range(1, len(cl))]
    ad = [abs(x) for x in dl]
    suma, neto = sum(ad), cl[-1] - cl[0]
    ef = abs(neto) / suma if suma else 0.0
    p(f"{d:12} {len(cl):6} {suma:12.2f} {neto:9.2f} {ef:8.3f} {st.mean(ad):9.4f} "
      f"{max(ad):8.2f} {sum(1 for x in dl if x==0):5}")
p("")
p("  suma|delta| = recorrido total minuto a minuto (lo que el precio 'anduvo')")
p("  neto        = close final - close inicial (lo que el precio 'avanzo')")
p("  eficiencia  = |neto|/suma. 1.0 = linea recta.  ~0 = todo ida y vuelta.")
p("")

# ================================================================== A) continuacion
p("A) DE DOS EN DOS: si esta vela cerro por encima de la anterior, ¿la siguiente tambien?")
p("-" * 96)
p("   Se compara cada par consecutivo. NO hay parametro k: es la vela actual y la siguiente.")
p("   P_nula = mismos deltas barajados 300 veces (mediana). Si P_real ~ P_nula -> es azar.")
p("")
p(f"{'fecha':12} {'pares':>7} {'repite':>7} {'P_real':>8} {'P_nula':>8} {'dif':>8} "
  f"{'P(sube|subio)':>14} {'P(baja|bajo)':>13}")
rnd = random.Random(SEED)


def repeticion(deltas):
    """Fraccion de pares consecutivos en los que el signo se REPITE. Los 0 no cuentan."""
    n = rep = 0
    su = sun = ba = ban = 0
    for i in range(1, len(deltas)):
        a, b = signo(deltas[i - 1]), signo(deltas[i])
        if a == 0 or b == 0:
            continue
        n += 1
        if a == b:
            rep += 1
        if a > 0:
            sun += 1
            su += 1 if b > 0 else 0
        else:
            ban += 1
            ba += 1 if b < 0 else 0
    return n, rep, (rep / n if n else None), (su / sun if sun else None), (ba / ban if ban else None)


for d in dias:
    cl = [r[2] for r in datos[d]]
    dl = [cl[i] - cl[i - 1] for i in range(1, len(cl))]
    n_, rep, pr, psu, pba = repeticion(dl)
    nul = []
    for _ in range(NPERM):
        m = dl[:]
        rnd.shuffle(m)
        nul.append(repeticion(m)[2])
    nul = [x for x in nul if x is not None]
    pn = st.median(nul) if nul else None
    p(f"{d:12} {n_:7} {rep:7} {pr:8.3f} {pn:8.3f} {pr-pn:+8.3f} "
      f"{psu:14.3f} {pba:13.3f}")
p("")
p("   0.500 = moneda. Por debajo de 0.500 = REVERSION (tiende a alternar, no a seguir).")
p("")

# ================================================================== B) aceleracion
p("B) ACELERACION Y AGOTAMIENTO: |delta| segun la POSICION dentro de la racha")
p("-" * 96)
p("   Solo rachas de longitud >=3. Si tu teoria es cierta, |delta| sube y luego cae.")
p(f"{'fecha':12} {'rachas>=3':>10} {'pos1':>8} {'pos2':>8} {'pos3':>8} {'pos4':>8} "
  f"{'ultima':>8} {'penult':>8}")
for d in dias:
    cl = [r[2] for r in datos[d]]
    dl = [cl[i] - cl[i - 1] for i in range(1, len(cl))]
    sg = [signo(x) for x in dl]
    pos = {1: [], 2: [], 3: [], 4: []}
    ult, pen, decae, nr = [], [], 0, 0
    for r in rachas_de(sg):
        L = len(r)
        # r son los INDICES reales dentro de dl: inmune a los delta=0 que rompen racha
        seg = [abs(dl[j]) for j in r]
        if L < 3:
            continue
        nr += 1
        for k in (1, 2, 3, 4):
            if L >= k:
                pos[k].append(seg[k - 1])
        ult.append(seg[-1])
        pen.append(seg[-2])
        if seg[-1] < seg[-2]:
            decae += 1
    def m(v):
        return f"{st.mean(v):8.4f}" if v else "       -"
    p(f"{d:12} {nr:10} {m(pos[1])} {m(pos[2])} {m(pos[3])} {m(pos[4])} {m(ult)} {m(pen)}")
    if nr:
        p(f"{'':12} rachas donde la ULTIMA vela es menor que la penultima: "
          f"{decae}/{nr} = {100.0*decae/nr:.1f}%  (azar ~50%)")
p("")
p("  pos1..pos4 = |delta| medio de la 1a, 2a, 3a y 4a vela del tramo. Si tu teoria es")
p("  cierta, deberian crecer y luego caer en 'ultima'.")
p("")

# ================================================================== cronometro
p("TEST DEL CRONOMETRO: |rho(variable, minuto del dia)| >= 0.30 -> variable MUERTA")
p("-" * 96)
p(f"{'fecha':12} {'variable':>16} {'pearson':>9} {'spearman':>9} {'veredicto':>12}")
for d in dias:
    filas = datos[d]
    cl = [r[2] for r in filas]
    dl = [abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))]
    mins = list(range(1, len(dl) + 1))
    for nom, serie in (("|delta| close", dl),):
        rp, rs = pearson(mins, serie), spearman(mins, serie)
        peor = max(abs(rp or 0), abs(rs or 0))
        p(f"{d:12} {nom:>16} {rp:9.3f} {rs:9.3f} {'MUERTA' if peor>=0.30 else 'sobrevive':>12}")
p("")
p("=" * 96)
p("n pequeno: 2 dias completos + 1 parcial. Cualquier resultado es INDICIO, no prueba.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT}  ({len(O)} lineas)")
