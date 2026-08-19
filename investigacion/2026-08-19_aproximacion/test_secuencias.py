# ¿LA SECUENCIA DE VELAS PREVIAS ANTICIPA UN FLIP FALSO?  (485 sesiones, 2 años)
# Ayer se probaron variables SUELTAS del momento del flip: la mejor separo 0.33 -> insuficiente.
# Aqui se prueba lo que NO se habia probado: el PATRON de las N velas anteriores (secuencia de
# direcciones, aceleracion del cuerpo, expansion del rango, posicion del cierre en el rango).
# Todo se mide con velas ANTERIORES al flip (solo pasado). El veredicto de reb2 usa el futuro,
# pero SOLO para etiquetar: es la variable a predecir, no una entrada.
import sqlite3, sys, statistics as st
from collections import Counter, defaultdict
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C
from sys2.core.rebote import sen_p, reb2
from sys2.core.supertrend import mm

con = sqlite3.connect(r"C:\Users\eulis\proyectos\open-premium-ibkr\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]

datos = []
for f in FECHAS:
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                       (f,)).fetchall()
    if len(bars) < 100:
        continue
    try:
        sp, L, ks = sen_p(bars, C.ST_PER, C.ST_MULT)
    except Exception:
        continue
    ik = {k: i for i, k in enumerate(ks)}
    for h, d in sp:
        if h < "09:45":
            continue
        i = ik.get((mm(h) // 3) * 3)
        if i is None or i < 11 or i + 12 > len(ks) - 1:
            continue
        r = reb2(L, ks, ik, h, d)
        malo = (not r) or (r[0][1] != d)          # DESCARTA o INVIERTE
        lado = 1 if d == 'C' else -1
        V = [L[ks[j]] for j in range(i - 4, i + 1)]   # 5 velas: -4..0 (la del flip incluida)
        atr = st.mean(x['hi'] - x['lo'] for x in V) or 0.5
        cuerpos = [((x['cl'] - x['o']) * lado) / atr for x in V]
        rangos = [(x['hi'] - x['lo']) / atr for x in V]
        # secuencia de direcciones de las 3 velas PREVIAS (sin la del flip)
        seq = "".join("+" if c > 0.05 else ("-" if c < -0.05 else "0") for c in cuerpos[1:4])
        # posicion del cierre dentro del rango de la vela del flip (0=minimo,1=maximo)
        x = V[-1]
        rng = (x['hi'] - x['lo']) or 0.01
        pos = ((x['cl'] - x['lo']) / rng) if lado > 0 else ((x['hi'] - x['cl']) / rng)
        datos.append(dict(
            malo=malo, seq=seq,
            acel=cuerpos[-1] - st.mean(cuerpos[1:4]),      # aceleracion del cuerpo
            exp=rangos[-1] / (st.mean(rangos[1:4]) or 1),  # expansion del rango
            pos=pos,
            n_favor=sum(1 for c in cuerpos[1:4] if c > 0.05),
        ))

print("flips: %d   malos: %d (%.1f%%)" % (len(datos), sum(d['malo'] for d in datos),
                                          100.0*sum(d['malo'] for d in datos)/len(datos)))
base = 100.0*sum(d['malo'] for d in datos)/len(datos)
print()
print("=== 1) SECUENCIA de las 3 velas previas (+ a favor, - en contra, 0 neutra) ===")
print("%-8s %-7s %-9s %-8s" % ("patron", "n", "% malos", "vs base"))
g = defaultdict(list)
for d in datos:
    g[d['seq']].append(d['malo'])
for s, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
    if len(v) < 30:
        continue
    pm = 100.0*sum(v)/len(v)
    print("%-8s %-7d %-9.1f %+-8.1f" % (s, len(v), pm, pm - base))

print()
print("=== 2) VARIABLES DE SECUENCIA (media buenos vs malos) ===")
B = [d for d in datos if not d['malo']]
M = [d for d in datos if d['malo']]
print("%-10s %-12s %-12s %-10s" % ("variable", "BUENOS", "MALOS", "separacion"))
for k in ("acel", "exp", "pos", "n_favor"):
    mb, mm_ = st.mean(x[k] for x in B), st.mean(x[k] for x in M)
    sd = st.pstdev([x[k] for x in datos]) or 1
    print("%-10s %-12.3f %-12.3f %+.3f" % (k, mb, mm_, (mb - mm_) / sd))
