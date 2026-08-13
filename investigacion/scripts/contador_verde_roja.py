# Dos contadores EN PARALELO sobre el cuerpo (close-open) de cada vela, minuto a minuto:
#   VERDE -> acumula los cuerpos positivos    ROJA -> acumula los cuerpos negativos (en abs)
# La columna dif = sum_verde - sum_roja debe coincidir con el acumulado de TABLA_CUERPOS.txt
# (comprobacion cruzada al final de cada dia).
# Lee SOLO spy_velas.db (copia). No toca la BD viva ni IBKR.
import sqlite3

DB = "spy_velas.db"
TXT = "CONTADOR_VERDE_ROJA.txt"

O = []
def p(s=""):
    O.append(s)


c = sqlite3.connect(DB)
dias = [r[0] for r in c.execute("select distinct fecha from bars_minute order by fecha")]
datos = {d: c.execute("select hora,open,close from bars_minute where fecha=? order by hora",
                      (d,)).fetchall() for d in dias}
c.close()

p("CONTADORES EN PARALELO: VERDES vs ROJAS, MINUTO A MINUTO")
p("=" * 104)
p(f"fuente: {DB}   cuerpo = (close - open) en centavos")
p("")
p("n_ver / n_roj    = cuantas velas verdes / rojas llevamos acumuladas")
p("sum_ver / sum_roj= suma de los cuerpos de cada lado, EN VALOR ABSOLUTO (centavos)")
p("dif              = sum_ver - sum_roj  ->  positivo = mandan las verdes")
p("med_ver / med_roj= cuerpo medio de cada lado hasta ese minuto")
p("dom              = quien domina en ese instante")
p("")

for d in dias:
    filas = datos[d]
    p("=" * 104)
    p(f"=== {d} ===   {len(filas)} velas")
    p("=" * 104)
    p(f"{'vela':>5} {'hora':>7} {'cuerpo':>7} {'color':>6} "
      f"{'n_ver':>6} {'sum_ver':>8} {'med_ver':>8} "
      f"{'n_roj':>6} {'sum_roj':>8} {'med_roj':>8} {'dif':>8} {'dom':>6}")
    nv = nr = sv = sr = 0
    ndoji = 0
    control = 0
    for i, (hora, o_, cl) in enumerate(filas, 1):
        cu = round((cl - o_) * 100)
        control += cu
        if cu > 0:
            nv += 1
            sv += cu
            col = "VERDE"
        elif cu < 0:
            nr += 1
            sr += -cu
            col = "ROJA"
        else:
            ndoji += 1
            col = "DOJI"
        dif = sv - sr
        mv = sv / nv if nv else 0.0
        mr = sr / nr if nr else 0.0
        dom = "VERDE" if dif > 0 else ("ROJA" if dif < 0 else "=")
        p(f"{i:5} {hora:>7} {cu:+7d} {col:>6} "
          f"{nv:6} {sv:8d} {mv:8.2f} "
          f"{nr:6} {sr:8d} {mr:8.2f} {dif:+8d} {dom:>6}")

    p("")
    p(f"  RESUMEN {d}")
    p(f"    verdes : {nv:4} velas, {sv:6d} centavos, cuerpo medio {sv/nv if nv else 0:6.2f}")
    p(f"    rojas  : {nr:4} velas, {sr:6d} centavos, cuerpo medio {sr/nr if nr else 0:6.2f}")
    p(f"    dojis  : {ndoji:4}")
    p(f"    dif final (ver-roj) = {sv-sr:+d} centavos ({(sv-sr)/100:+.2f} puntos)")
    p(f"    COMPROBACION CRUZADA: suma directa de cuerpos = {control:+d}  ->  "
      f"{'CUADRA' if control == sv - sr else 'DESCUADRE'}")
    # cuantas veces cambia de manos el dominio a lo largo del dia
    nv2 = nr2 = sv2 = sr2 = 0
    ant = None
    cambios = []
    for i, (hora, o_, cl) in enumerate(filas, 1):
        cu = round((cl - o_) * 100)
        if cu > 0:
            sv2 += cu
        elif cu < 0:
            sr2 += -cu
        dd = sv2 - sr2
        act = "VERDE" if dd > 0 else ("ROJA" if dd < 0 else None)
        if act and act != ant:
            if ant is not None:
                cambios.append((hora, act, dd))
            ant = act
    p(f"    el dominio cambia de manos {len(cambios)} veces en el dia")
    if cambios:
        p(f"    {'hora':>7} {'pasa a':>7} {'dif':>8}")
        for hora, act, dd in cambios:
            p(f"    {hora:>7} {act:>7} {dd:+8d}")
    p("")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT}  ({len(O)} lineas)")
