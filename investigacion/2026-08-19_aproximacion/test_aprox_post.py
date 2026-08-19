# ¿SE VE VENIR EL TOQUE?  Tras un flip, con solo k velas YA FORMADAS, ¿se anticipa el veredicto?
# (485 sesiones). Esto NO es look-ahead: en el minuto en que se decide, esas k velas ya existen.
# Lo que se mide, vela a vela DESPUES del flip:
#   d[j] = distancia (en ATR) de la mecha del lado de la linea a la linea del ST
#   pend   : pendiente de esa distancia (negativa = se esta acercando)
#   d_ult  : distancia en la ultima vela disponible
#   n_acerca: velas consecutivas reduciendo distancia
#   ya_toco: alguna vela con la mecha a <=1.0 ATR (el mismo criterio de reb2)
# Se compara contra el veredicto FINAL de reb2 (ventana 12), que es lo que se quiere anticipar.
import sqlite3, sys, statistics as st
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C
from sys2.core.rebote import sen_p, reb2
from sys2.core.supertrend import mm

con = sqlite3.connect(r"C:\Users\eulis\proyectos\open-premium-ibkr\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
K = [2, 3, 4, 6]                      # velas posteriores disponibles al decidir

res = {k: [] for k in K}
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
        malo = (not r) or (r[0][1] != d)
        lado = 1 if d == 'C' else -1
        atrs = [L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)]
        atr = (sum(atrs) / len(atrs)) or 0.5
        for k in K:
            V = [L[ks[j]] for j in range(i + 1, i + 1 + k)]
            if len(V) < k:
                continue
            dd = [abs((x['lo'] if lado > 0 else x['hi']) - x['linea']) / atr for x in V]
            n = len(dd)
            mx = st.mean(range(n)); my = st.mean(dd)
            den = sum((q - mx) ** 2 for q in range(n)) or 1
            pend = sum((q - mx) * (dd[q] - my) for q in range(n)) / den
            nac = 0
            for q in range(1, n):
                if dd[q] < dd[q - 1]: nac += 1
                else: nac = 0
            res[k].append(dict(malo=malo, pend=pend, d_ult=dd[-1], n_acerca=nac,
                               ya_toco=1 if min(dd) <= 1.0 else 0))

for k in K:
    D = res[k]
    if not D:
        continue
    base = 100.0 * sum(x['malo'] for x in D) / len(D)
    B = [x for x in D if not x['malo']]; M = [x for x in D if x['malo']]
    print("=" * 74)
    print("CON %d VELAS POSTERIORES  (n=%d, malos %.1f%%)" % (k, len(D), base))
    print("%-10s %-11s %-11s %-10s" % ("variable", "BUENOS", "MALOS", "separacion"))
    for v in ("pend", "d_ult", "n_acerca", "ya_toco"):
        mb, mm_ = st.mean(x[v] for x in B), st.mean(x[v] for x in M)
        sd = st.pstdev([x[v] for x in D]) or 1
        print("%-10s %-11.3f %-11.3f %+.3f" % (v, mb, mm_, (mb - mm_) / sd))
    t = [x for x in D if x['ya_toco']]
    nt = [x for x in D if not x['ya_toco']]
    if t and nt:
        print("  YA TOCO la linea: %.1f%% malos (n=%d)   |   NO toco: %.1f%% malos (n=%d)"
              % (100.0*sum(x['malo'] for x in t)/len(t), len(t),
                 100.0*sum(x['malo'] for x in nt)/len(nt), len(nt)))
