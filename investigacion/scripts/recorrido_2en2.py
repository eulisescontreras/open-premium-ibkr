# Recorrido de inicio a fin, vela a vela, con el diferencial de cada par de cierres.
# Dos lecturas de "de 2 en 2":
#   1) DESLIZANTE: cada vela contra la anterior  (i-1,i), (i,i+1), (i+1,i+2)...
#   2) DISJUNTO  : bloques de 2 sin solapar      (1,2), (3,4), (5,6)...
# Lee SOLO spy_velas.db (copia). No toca la BD viva ni IBKR.
import sqlite3
import statistics as st

DB = "spy_velas.db"
TXT = "RECORRIDO_2EN2.txt"

O = []
def p(s=""):
    O.append(s)


c = sqlite3.connect(DB)
dias = [r[0] for r in c.execute("select distinct fecha from bars_minute order by fecha")]
datos = {d: c.execute("select hora,open,close from bars_minute where fecha=? order by hora",
                      (d,)).fetchall() for d in dias}
c.close()

p("RECORRIDO DE CIERRES DE 2 EN 2  -  todas las velas, de inicio a fin")
p("=" * 88)
p(f"fuente: {DB}   dias: {', '.join(dias)}")
p("")
p("delta      = close[i] - close[i-1]   (el diferencial de cada par)")
p("recorrido  = suma acumulada de |delta|  -> lo que el precio ANDUVO desde la apertura")
p("neto       = close[i] - close[apertura] -> lo que el precio AVANZO desde la apertura")
p("")

# ============================================================ 1) DESLIZANTE
p("#" * 88)
p("# 1) PARES DESLIZANTES: cada vela contra la anterior")
p("#" * 88)
for d in dias:
    filas = datos[d]
    p("")
    p(f"=== {d} ===   {len(filas)} velas")
    p(f"{'hora':>6} {'open':>8} {'close':>8} {'delta':>8} {'color':>6} {'recorrido':>10} {'neto':>8}")
    ini = filas[0][2]
    rec = 0.0
    for i, (hora, o_, cl) in enumerate(filas):
        if i == 0:
            p(f"{hora:>6} {o_:8.2f} {cl:8.2f} {'-':>8} {'-':>6} {0.0:10.2f} {0.0:8.2f}")
            continue
        dlt = cl - filas[i - 1][2]
        rec += abs(dlt)
        col = "VERDE" if cl > o_ else ("ROJA" if cl < o_ else "DOJI")
        p(f"{hora:>6} {o_:8.2f} {cl:8.2f} {dlt:+8.2f} {col:>6} {rec:10.2f} {cl-ini:+8.2f}")

    dl = [filas[i][2] - filas[i - 1][2] for i in range(1, len(filas))]
    ad = [abs(x) for x in dl]
    pos = [x for x in dl if x > 0]
    neg = [x for x in dl if x < 0]
    p("")
    p(f"  RESUMEN {d}")
    p(f"    velas={len(filas)}  pares={len(dl)}")
    p(f"    recorrido total (suma|delta|) = {sum(ad):8.2f} puntos")
    p(f"    neto (close_fin - close_ini)  = {filas[-1][2]-ini:+8.2f} puntos")
    p(f"    eficiencia |neto|/recorrido   = {abs(filas[-1][2]-ini)/sum(ad):8.3f}")
    p(f"    |delta| medio={st.mean(ad):.4f}  mediana={st.median(ad):.4f}  max={max(ad):.2f}")
    p(f"    pares al alza={len(pos)} (suman {sum(pos):+.2f})  a la baja={len(neg)} "
      f"(suman {sum(neg):+.2f})  planos={len(dl)-len(pos)-len(neg)}")

# ============================================================ 2) DISJUNTO
p("")
p("#" * 88)
p("# 2) BLOQUES DISJUNTOS DE 2 VELAS: (1,2) (3,4) (5,6)... sin solapar")
p("#" * 88)
p("   dif_bloque = close de la 2a vela - close de la 1a vela del bloque")
for d in dias:
    filas = datos[d]
    p("")
    p(f"=== {d} ===")
    p(f"{'bloque':>7} {'desde':>6} {'hasta':>6} {'close_ini':>10} {'close_fin':>10} {'dif':>8} {'acum':>9}")
    difs, acum, nb = [], 0.0, 0
    for i in range(0, len(filas) - 1, 2):
        a, b = filas[i], filas[i + 1]
        dif = b[2] - a[2]
        difs.append(dif)
        acum += dif
        nb += 1
        p(f"{nb:7} {a[0]:>6} {b[0]:>6} {a[2]:10.2f} {b[2]:10.2f} {dif:+8.2f} {acum:+9.2f}")
    if difs:
        ad = [abs(x) for x in difs]
        p("")
        p(f"  RESUMEN bloques {d}: n={len(difs)}  suma|dif|={sum(ad):.2f}  neto={sum(difs):+.2f}  "
          f"|dif|medio={st.mean(ad):.4f}  max={max(ad):.2f}")
        p(f"    bloques al alza={sum(1 for x in difs if x>0)}  "
          f"a la baja={sum(1 for x in difs if x<0)}  planos={sum(1 for x in difs if x==0)}")
        if len(filas) % 2:
            p(f"    NOTA: {len(filas)} velas es impar -> la ultima ({filas[-1][0]}) queda fuera.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT}  ({len(O)} lineas)")
