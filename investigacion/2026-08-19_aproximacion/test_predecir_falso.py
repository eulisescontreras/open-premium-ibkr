# ¿SE PUEDE ANTICIPAR UN FLIP FALSO SIN VER EL FUTURO?
# Extrae TODOS los flips del ST-3 de las 485 sesiones, su VEREDICTO final (reb2 con ventana
# completa = lo que el backtest sabe) y variables medibles EN EL MINUTO DEL FLIP (lo que el vivo
# tiene). Si alguna variable separa NORMAL de DESCARTA, se puede filtrar sin esperar.
# Solo lee: no toca el motor ni el sistema.
import sqlite3, sys, statistics as st
sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
from sys2 import config as C
from sys2.core.rebote import st_lin_p, sen_p, reb2
from sys2.core.st1 import st_full, giros
from sys2.core.supertrend import mm

con = sqlite3.connect(r"C:\Users\eulis\proyectos\open-premium-ibkr\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
print("sesiones: %d" % len(FECHAS))

filas = []
for f in FECHAS:
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                       (f,)).fetchall()
    if len(bars) < 100:
        continue
    try:
        sp, L, ks = sen_p(bars, C.ST_PER, C.ST_MULT)
        ik = {k: i for i, k in enumerate(ks)}
        S1, k1 = st_full(bars, 1, C.ST_PER, C.ST_MULT)
    except Exception:
        continue
    for h, d in sp:
        if h < "09:45":
            continue
        i = ik.get((mm(h) // 3) * 3)
        if i is None or i < 11 or i + 12 > len(ks) - 1:
            continue
        # VEREDICTO (usa el futuro: solo para etiquetar)
        r = reb2(L, ks, ik, h, d)
        veredicto = "NORMAL" if (r and r[0][0] == h and r[0][1] == d) else (
            "DESCARTA" if not r else ("INVIERTE" if r[0][1] != d else "RETRASA"))
        # VARIABLES DEL MOMENTO (solo pasado: buckets <= i)
        x = L[ks[i]]
        atrs = [L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)]
        atr = sum(atrs) / len(atrs) if atrs else 0.5
        lado = 1 if d == 'C' else -1
        cuerpo = (x['cl'] - x['o']) * lado                  # fuerza de la vela del flip
        dist = abs(x['cl'] - x['linea']) / atr              # separacion del cierre a la linea
        mecha = abs((x['lo'] if lado > 0 else x['hi']) - x['linea']) / atr
        rango = (x['hi'] - x['lo']) / atr
        g1 = giros(S1, k1, h, C.ST1_VENTANA)                # giros del ST-1 (ya lo usa el sistema)
        prev = [L[ks[j]] for j in range(i - 3, i)]
        emp = sum(1 for p in prev if abs(p['cl'] - p['linea']) <= 1.0 * atr)  # buckets pegados antes
        filas.append(dict(f=f, h=h, d=d, v=veredicto, cuerpo=cuerpo / atr, dist=dist,
                          mecha=mecha, rango=rango, g1=g1, emp=emp, hora=mm(h), atr=atr))

print("flips analizados: %d" % len(filas))
from collections import Counter
print("veredictos:", dict(Counter(x['v'] for x in filas)))
print()

BUENO = ("NORMAL", "RETRASA")          # el backtest acaba entrando
MALO = ("DESCARTA", "INVIERTE")        # el backtest NO entra en la direccion del flip
b = [x for x in filas if x['v'] in BUENO]
m = [x for x in filas if x['v'] in MALO]
print("BUENOS (entra): %d   |   MALOS (no entra): %d" % (len(b), len(m)))
print()
print("%-10s %-12s %-12s %-10s" % ("variable", "media BUENOS", "media MALOS", "separacion"))
print("-" * 50)
for k in ("cuerpo", "dist", "mecha", "rango", "g1", "emp", "hora", "atr"):
    mb, mm_ = st.mean(x[k] for x in b), st.mean(x[k] for x in m)
    sb = st.pstdev([x[k] for x in b] + [x[k] for x in m]) or 1
    print("%-10s %-12.3f %-12.3f %+.3f" % (k, mb, mm_, (mb - mm_) / sb))

print()
print("=" * 78)
print("PRECISION DE FILTROS SIMPLES (solo datos del momento del flip)")
print("=" * 78)
print("%-34s %-8s %-9s %-9s %-8s" % ("filtro (entra solo si...)", "entra", "% malos", "malos", "buenos"))
print("-" * 78)
tb, tm = len(b), len(m)
print("%-34s %-8d %-9.1f %-9s %-8s" % ("SIN filtro (hoy)", len(filas), 100.0*tm/len(filas),
                                        "%d/%d" % (tm, tm), "%d/%d" % (tb, tb)))
FILTROS = [
    ("cuerpo > 0", lambda x: x['cuerpo'] > 0),
    ("dist > 2.5", lambda x: x['dist'] > 2.5),
    ("dist > 3.0", lambda x: x['dist'] > 3.0),
    ("hora < 13:00", lambda x: x['hora'] < 780),
    ("cuerpo>0 y dist>2.5", lambda x: x['cuerpo'] > 0 and x['dist'] > 2.5),
    ("cuerpo>0 y hora<13:00", lambda x: x['cuerpo'] > 0 and x['hora'] < 780),
    ("cuerpo>0 y dist>2.5 y h<13", lambda x: x['cuerpo'] > 0 and x['dist'] > 2.5 and x['hora'] < 780),
    ("g1==0 y cuerpo>0", lambda x: x['g1'] == 0 and x['cuerpo'] > 0),
]
for nom, fn in FILTROS:
    pasa = [x for x in filas if fn(x)]
    pb = sum(1 for x in pasa if x['v'] in BUENO)
    pm = sum(1 for x in pasa if x['v'] in MALO)
    if not pasa:
        continue
    print("%-34s %-8d %-9.1f %-9s %-8s" % (nom, len(pasa), 100.0*pm/len(pasa),
          "%d/%d" % (pm, tm), "%d/%d" % (pb, tb)))
