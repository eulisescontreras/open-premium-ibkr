# SALTOS BRUSCOS DEL ACUMULADO: la observacion del usuario sobre el conteo de digitos.
# El 11:27 el acum_spy cayo de 123.946.411 a 85.883.614 (-38 M en UN minuto, cuando el minuto
# tipico mueve ~1 M) y el precio se desplomo despues. ¿Es un patron o fue una vez?
#
# Se buscan TODOS los minutos con net_spy extremo y se mide que hizo el precio DESPUES.
# Lee la BD viva en SOLO-LECTURA.
import sqlite3
import statistics as st

SRC = "spy_history.db"
TXT = "SALTOS_HOY.txt"
DIA = "2026-08-13"

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
tp = {m: (c, v, n) for m, c, v, n in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end), count(*) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
src.close()

horas = [x[0] for x in velas]
close = [x[1] for x in velas]
n = len(velas)
net = [tp.get(h, (0.0, 0.0, 0))[0] - tp.get(h, (0.0, 0.0, 0))[1] for h in horas]
tks = [tp.get(h, (0.0, 0.0, 0))[2] for h in horas]
acum, a = [], 0.0
for x in net:
    a += x
    acum.append(a)

O = []
def p(s=""):
    O.append(s)


p(f"SALTOS BRUSCOS DEL ACUMULADO  -  {DIA}, {n} minutos")
p("=" * 108)
ab = [abs(x) for x in net]
p(f"net_spy por minuto:  mediana {st.median(ab):,.0f}   media {st.mean(ab):,.0f}   "
  f"max {max(ab):,.0f}")
p("")

# ---------- 1) cambios de digitos ----------
def dig(v):
    return len(str(abs(int(round(v)))))


p("1) MINUTOS DONDE CAMBIA EL NUMERO DE DIGITOS DEL ACUMULADO")
p("-" * 108)
p(f"{'hora':>7} {'digitos':>8} {'acum antes':>15} {'acum despues':>15} {'salto':>15} "
  f"{'spy':>9} {'+10min':>8} {'+30min':>8}")
for i in range(1, n):
    if dig(acum[i]) != dig(acum[i - 1]):
        d10 = close[min(i + 10, n - 1)] - close[i]
        d30 = close[min(i + 30, n - 1)] - close[i]
        p(f"{horas[i]:>7} {dig(acum[i-1])}->{dig(acum[i]):<5} {acum[i-1]:15,.0f} "
          f"{acum[i]:15,.0f} {net[i]:+15,.0f} {close[i]:9.2f} {d10:+8.2f} {d30:+8.2f}")
p("")

# ---------- 2) los saltos mas grandes, en las dos direcciones ----------
idx = sorted(range(n), key=lambda i: -abs(net[i]))[:15]
p("2) LOS 15 MINUTOS CON MAYOR |net_spy|  (que hizo el precio DESPUES)")
p("-" * 108)
p(f"{'hora':>7} {'net_spy':>16} {'x mediana':>10} {'ticks':>6} {'spy':>9} "
  f"{'+5min':>8} {'+10min':>8} {'+30min':>8} {'+60min':>8}")
med = st.median(ab)
for i in sorted(idx):
    d5 = close[min(i + 5, n - 1)] - close[i]
    d10 = close[min(i + 10, n - 1)] - close[i]
    d30 = close[min(i + 30, n - 1)] - close[i]
    d60 = close[min(i + 60, n - 1)] - close[i]
    p(f"{horas[i]:>7} {net[i]:+16,.0f} {abs(net[i])/med:10.1f} {tks[i]:6} {close[i]:9.2f} "
      f"{d5:+8.2f} {d10:+8.2f} {d30:+8.2f} {d60:+8.2f}")
p("")

# ---------- 3) ¿los saltos NEGATIVOS anticipan caidas? ----------
p("3) SALTOS NEGATIVOS vs POSITIVOS: movimiento medio del precio despues")
p("-" * 108)
p(f"{'grupo':>26} {'n':>4} {'+5min':>9} {'+10min':>9} {'+30min':>9} {'+60min':>9}")


def resumen(sel, nom):
    if not sel:
        return
    fila = [f"{nom:>26} {len(sel):4}"]
    for fut in (5, 10, 30, 60):
        ds = [close[min(i + fut, n - 1)] - close[i] for i in sel]
        fila.append(f"{st.mean(ds):+9.3f}")
    p(" ".join(fila))


umbrales = (5, 10, 20)
for u in umbrales:
    resumen([i for i in range(n) if net[i] <= -u * med], f"net_spy <= -{u}x mediana")
for u in umbrales:
    resumen([i for i in range(n) if net[i] >= u * med], f"net_spy >= +{u}x mediana")
resumen(list(range(n)), "TODOS (referencia)")
p("")
p("Si los saltos negativos grandes anticiparan caidas, sus filas deberian ser NEGATIVAS")
p("y mas negativas que la referencia. Si no, el salto es solo actividad, no direccion.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
