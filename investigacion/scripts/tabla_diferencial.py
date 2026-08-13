# Tabla simple: par a par, el diferencial de cierres EN CENTAVOS con signo.
#   +4 = la vela cerro 4 centavos por encima de la anterior
#   -5 = cerro 5 centavos por debajo
# Lee SOLO spy_velas.db (copia). No toca la BD viva ni IBKR.
import sqlite3
from collections import Counter

DB = "spy_velas.db"
TXT = "TABLA_DIFERENCIAL.txt"

O = []
def p(s=""):
    O.append(s)


c = sqlite3.connect(DB)
dias = [r[0] for r in c.execute("select distinct fecha from bars_minute order by fecha")]
datos = {d: c.execute("select hora,open,close from bars_minute where fecha=? order by hora",
                      (d,)).fetchall() for d in dias}
c.close()

p("TABLA DEL DIFERENCIAL DE CIERRES, PAR A PAR, EN CENTAVOS")
p("=" * 72)
p(f"fuente: {DB}")
p("")
p("dif   = (close - close_anterior) en CENTAVOS.  +4 = cerro 4 centavos por encima.")
p("color = VERDE si close>open, ROJA si close<open, DOJI si iguales.")
p("acum  = suma de los dif desde la apertura, en centavos.")
p("")

for d in dias:
    filas = datos[d]
    p("=" * 72)
    p(f"=== {d} ===   {len(filas)} velas, {len(filas)-1} pares")
    p("=" * 72)
    p(f"{'par':>5} {'hora':>7} {'close':>9} {'dif':>6} {'color':>6} {'acum':>7}")
    acum = 0
    cnt = Counter()
    difs = []
    for i in range(1, len(filas)):
        hora, o_, cl = filas[i]
        dif = round((cl - filas[i - 1][2]) * 100)
        acum += dif
        difs.append(dif)
        col = "VERDE" if cl > o_ else ("ROJA" if cl < o_ else "DOJI")
        cnt[col] += 1
        p(f"{i:5} {hora:>7} {cl:9.2f} {dif:+6d} {col:>6} {acum:+7d}")

    pos = [x for x in difs if x > 0]
    neg = [x for x in difs if x < 0]
    p("")
    p(f"  RESUMEN {d}")
    p(f"    pares            : {len(difs)}")
    p(f"    verdes/rojas/doji: {cnt['VERDE']} / {cnt['ROJA']} / {cnt['DOJI']}")
    p(f"    dif > 0          : {len(pos):4}  suman {sum(pos):+6d} centavos")
    p(f"    dif < 0          : {len(neg):4}  suman {sum(neg):+6d} centavos")
    p(f"    dif = 0          : {len(difs)-len(pos)-len(neg):4}")
    p(f"    acumulado final  : {acum:+d} centavos  ({acum/100:+.2f} puntos de SPY)")
    p(f"    recorrido total  : {sum(abs(x) for x in difs)} centavos "
      f"({sum(abs(x) for x in difs)/100:.2f} puntos)")
    p(f"    mayor subida={max(difs):+d}   mayor bajada={min(difs):+d}")
    p("")
    p(f"  DISTRIBUCION DEL DIFERENCIAL {d}  (cuantas veces sale cada valor)")
    p(f"    {'dif':>6} {'veces':>7} {'%':>7}")
    for v, n in sorted(Counter(difs).items()):
        p(f"    {v:+6d} {n:7} {100.0*n/len(difs):6.1f}%")
    p("")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT}  ({len(O)} lineas)")
