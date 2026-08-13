# ¿DAN LAS MEDIAS MOVILES LA DIRECCION? Test contra la verdad que importa: el lado del TRAMO
# vigente (ZigZag 1.50, los 3 tramos reales de cada dia), no un horizonte fijo arbitrario.
#
# Se prueba en LOS DOS DIAS. Un indicador solo vale si acierta en ambos: en un solo dia,
# cualquier cosa que siga a la tendencia acierta por construccion.
# Se incluye el TEST DEL CRONOMETRO para descartar los que solo derivan con la hora.
import sqlite3
import statistics as st

TXT = "MEDIAS.txt"
UMBRAL_ZZ = 1.50

O = []
def p(s=""):
    O.append(s)


def pear(x, y):
    m = len(x)
    if m < 5:
        return 0
    mx, my = sum(x) / m, sum(y) / m
    sx = sum((a - mx) ** 2 for a in x) ** .5
    sy = sum((b - my) ** 2 for b in y) ** .5
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else 0


def sg(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


p("¿DAN LAS MEDIAS MOVILES LA DIRECCION?")
p("=" * 100)
p(f"Verdad = lado del TRAMO vigente (ZigZag ${UMBRAL_ZZ:.2f}: 3 tramos por dia).")
p("Un indicador solo cuenta si acierta en LOS DOS dias.")
p("")

RES = {}
for dia in ("2026-08-13", "2026-08-12"):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
    ta = {h: r for h, *r in c.execute(
        "select hora,sma20,sma50,sma200,ema8,ema21,vwap,rsi,macd_hist "
        "from ta_minute where fecha=?", (dia,))}
    c.close()
    h = [x[0] for x in v]
    cl = [x[1] for x in v]
    n = len(v)

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
    # verdad por minuto: el lado del tramo al que pertenece
    verdad = [0] * n
    for k in range(len(piv) - 1):
        a, b = piv[k], piv[k + 1]
        s = 1 if cl[b] > cl[a] else -1
        for i in range(a, b):
            verdad[i] = s

    def val(i, nom):
        t = ta.get(h[i])
        if not t:
            return 0
        s20, s50, s200, e8, e21, vw, rsi, mh = t
        if nom == "precio vs SMA20":
            return sg(cl[i] - s20) if s20 else 0
        if nom == "precio vs SMA50":
            return sg(cl[i] - s50) if s50 else 0
        if nom == "precio vs SMA200":
            return sg(cl[i] - s200) if s200 else 0
        if nom == "SMA20 vs SMA50":
            return sg(s20 - s50) if (s20 and s50) else 0
        if nom == "SMA50 vs SMA200":
            return sg(s50 - s200) if (s50 and s200) else 0
        if nom == "EMA8 vs EMA21":
            return sg(e8 - e21) if (e8 and e21) else 0
        if nom == "precio vs SMA5":
            return sg(cl[i] - vw) if vw else 0
        if nom == "pendiente SMA20 (5m)":
            t2 = ta.get(h[i - 5]) if i >= 5 else None
            return sg(s20 - t2[0]) if (s20 and t2 and t2[0]) else 0
        if nom == "pendiente SMA50 (10m)":
            t2 = ta.get(h[i - 10]) if i >= 10 else None
            return sg(s50 - t2[1]) if (s50 and t2 and t2[1]) else 0
        if nom == "MACD hist":
            return sg(mh) if mh is not None else 0
        if nom == "RSI-50":
            return sg(rsi - 50) if rsi is not None else 0
        return 0

    NOMS = ["precio vs SMA5", "precio vs SMA20", "precio vs SMA50", "precio vs SMA200",
            "SMA20 vs SMA50", "SMA50 vs SMA200", "EMA8 vs EMA21",
            "pendiente SMA20 (5m)", "pendiente SMA50 (10m)", "MACD hist", "RSI-50"]
    RES[dia] = {}
    for nom in NOMS:
        ok = tot = 0
        serie, idx = [], []
        for i in range(30, n):
            s = val(i, nom)
            if s == 0 or verdad[i] == 0:
                continue
            tot += 1
            ok += 1 if s == verdad[i] else 0
            serie.append(s)
            idx.append(i)
        rho = pear(idx, serie) if len(serie) > 20 else 0
        RES[dia][nom] = (tot, 100 * ok / tot if tot else 0, rho)

p(f"{'indicador':>24} {'08-13 n':>9} {'08-13 %':>9} {'08-12 n':>9} {'08-12 %':>9} "
  f"{'peor':>7} {'rho max':>8}")
filas = []
for nom in RES["2026-08-13"]:
    a = RES["2026-08-13"][nom]
    b = RES["2026-08-12"][nom]
    peor = min(a[1], b[1])
    rho = max(abs(a[2]), abs(b[2]))
    filas.append((peor, nom, a, b, rho))
for peor, nom, a, b, rho in sorted(filas, reverse=True):
    marca = "  MUERTA(reloj)" if rho >= 0.30 else ""
    p(f"{nom:>24} {a[0]:9} {a[1]:8.1f}% {b[0]:9} {b[1]:8.1f}% {peor:6.1f}% {rho:8.3f}{marca}")
p("")
p("'peor' = el acierto en el dia MENOS favorable. Es lo unico que importa: un indicador que")
p("acierta 80% un dia y 30% el otro no sirve. 50% = moneda.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
