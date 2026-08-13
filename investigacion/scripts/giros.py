# ¿Que hace el TAPE en los giros largos del SPY de hoy?
# 1) detecta los tramos largos (ZigZag por CIERRES, no por extremos: las mechas son ruido)
# 2) mide el flujo en cada FASE del tramo (arranque / medio / final) -> amplificacion vs agotamiento
# 3) mira los minutos ALREDEDOR de cada giro -> ¿avisa el tape antes de que gire el precio?
# 4) correlaciona el flujo con lo que hace el precio DESPUES, a varios horizontes
# Lee la BD viva en SOLO-LECTURA y la cierra enseguida.
import sqlite3
import statistics as st

SRC = "spy_history.db"
TXT = "GIROS_HOY.txt"
DIA = "2026-08-13"
UMBRAL_ZZ = 0.75      # dolares de SPY para considerar que hay un tramo nuevo

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,open,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
tp = {m: (c, v, n) for m, c, v, n in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end), count(*) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
opc = src.execute(
    "select substr(hora,1,5) m, right,"
    " sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo<>'SPY' and right is not null group by m, right", (DIA,)).fetchall()
src.close()
NC = {m: c - v for m, r, c, v in opc if r == "C"}
NP = {m: c - v for m, r, c, v in opc if r == "P"}

horas = [x[0] for x in velas]
close = [x[2] for x in velas]
n = len(velas)
net = [tp.get(h, (0.0, 0.0, 0))[0] - tp.get(h, (0.0, 0.0, 0))[1] for h in horas]
tks = [tp.get(h, (0.0, 0.0, 0))[2] for h in horas]
nc = [NC.get(h, 0.0) for h in horas]
np_ = [NP.get(h, 0.0) for h in horas]

O = []
def p(s=""):
    O.append(s)


p(f"GIROS DEL SPY DEL {DIA} Y QUE HACIA EL TAPE")
p("=" * 104)
p(f"{n} minutos (09:30 - {horas[-1]}).  ZigZag por CIERRES, umbral ${UMBRAL_ZZ:.2f}")
p("net_spy = COMPRA - VENTA del tape del subyacente, en USD de ese minuto")
p("")

# ---------- 1) tramos por ZigZag sobre cierres ----------
piv = [0]
dir_ = 0
hi_i = lo_i = 0
for i in range(1, n):
    # maximo y minimo se siguen POR SEPARADO. Con un solo `ext_i` y dir_=0 el extremo se movia
    # en ambos sentidos y la distancia al extremo era siempre 0: no disparaba nunca.
    if close[i] > close[hi_i]:
        hi_i = i
    if close[i] < close[lo_i]:
        lo_i = i
    if dir_ >= 0 and close[hi_i] - close[i] >= UMBRAL_ZZ:
        piv.append(hi_i)
        dir_ = -1
        lo_i = i
    elif dir_ <= 0 and close[i] - close[lo_i] >= UMBRAL_ZZ:
        piv.append(lo_i)
        dir_ = 1
        hi_i = i
piv.append(n - 1)
piv = sorted(set(piv))

p("1) TRAMOS LARGOS DEL DIA")
p("-" * 104)
p(f"{'#':>3} {'desde':>7} {'hasta':>7} {'min':>5} {'precio':>16} {'recorrido':>10} "
  f"{'net_spy total':>15} {'net_call':>12} {'net_put':>12}")
tramos = []
for k in range(len(piv) - 1):
    a, b = piv[k], piv[k + 1]
    if b - a < 3:
        continue
    rec = close[b] - close[a]
    fspy = sum(net[a + 1:b + 1])
    fc = sum(nc[a + 1:b + 1])
    fp = sum(np_[a + 1:b + 1])
    tramos.append((a, b, rec, fspy))
    p(f"{len(tramos):>3} {horas[a]:>7} {horas[b]:>7} {b-a:5} "
      f"{close[a]:7.2f}->{close[b]:7.2f} {rec:+10.2f} {fspy:+15.0f} {fc:+12.0f} {fp:+12.0f}")
p("")

# ---------- 2) fases del tramo: ¿amplifica o se agota? ----------
p("2) EL FLUJO POR FASES DEL TRAMO  (tercio inicial / central / final)")
p("-" * 104)
p("   Si el movimiento se amplifica, el net_spy por minuto deberia CRECER del 1er al 2o tercio")
p("   y CAER en el 3o cuando se agota. Signo alineado = el flujo empuja en la direccion del tramo.")
p("")
p(f"{'#':>3} {'dir':>5} {'f1/min':>13} {'f2/min':>13} {'f3/min':>13} {'patron':>22}")
for j, (a, b, rec, _) in enumerate(tramos, 1):
    L = b - a
    if L < 6:
        continue
    t = L // 3
    f1 = st.mean(net[a + 1:a + 1 + t]) if t else 0
    f2 = st.mean(net[a + 1 + t:a + 1 + 2 * t]) if t else 0
    f3 = st.mean(net[a + 1 + 2 * t:b + 1]) if t else 0
    sg = 1 if rec > 0 else -1
    # alineado con la direccion del tramo
    a1, a2, a3 = sg * f1, sg * f2, sg * f3
    if a2 > a1 and a3 < a2:
        pat = "amplifica y se agota"
    elif a3 > a2 > a1:
        pat = "acelera hasta el final"
    elif a1 > a2 > a3:
        pat = "pierde fuerza desde el 1o"
    else:
        pat = "irregular"
    p(f"{j:>3} {'UP' if rec>0 else 'DOWN':>5} {f1:+13.0f} {f2:+13.0f} {f3:+13.0f} {pat:>22}")
p("")

# ---------- 3) alrededor del giro ----------
p("3) LOS 10 MINUTOS ANTES Y DESPUES DE CADA GIRO")
p("-" * 104)
p("   ¿El tape cambia de signo ANTES que el precio? Si avisa, el flujo del lado nuevo")
p("   deberia aparecer ya en los minutos previos al pivote.")
p("")
p(f"{'giro':>7} {'tipo':>10} {'net_spy -10a-1':>16} {'net_spy +1a+10':>16} "
  f"{'call -10':>11} {'call +10':>11} {'put -10':>11} {'put +10':>11}")
for k in range(1, len(piv) - 1):
    i = piv[k]
    if i < 10 or i > n - 11:
        continue
    antes = sum(net[i - 10:i])
    desp = sum(net[i + 1:i + 11])
    ca, cd = sum(nc[i - 10:i]), sum(nc[i + 1:i + 11])
    pa, pd = sum(np_[i - 10:i]), sum(np_[i + 1:i + 11])
    tipo = "techo" if close[i] > close[i - 1] else "suelo"
    p(f"{horas[i]:>7} {tipo:>10} {antes:+16.0f} {desp:+16.0f} "
      f"{ca:+11.0f} {cd:+11.0f} {pa:+11.0f} {pd:+11.0f}")
p("")

# ---------- 4) ¿el flujo anticipa al precio? ----------
def pearson(xs, ys):
    m = len(xs)
    if m < 5:
        return None
    mx, my = sum(xs) / m, sum(ys) / m
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


p("4) ¿EL FLUJO ANTICIPA AL PRECIO?  correlacion flujo(ventana) vs movimiento POSTERIOR")
p("-" * 104)
p(f"{'flujo':>12} {'-> +5min':>10} {'-> +10min':>10} {'-> +15min':>10} {'-> +30min':>10} "
  f"{'-> +60min':>10}")
for vent, nom in ((5, "net_spy 5m"), (10, "net_spy 10m"), (15, "net_spy 15m")):
    fila = [f"{nom:>12}"]
    for fut in (5, 10, 15, 30, 60):
        xs, ys = [], []
        for i in range(vent, n - fut):
            xs.append(sum(net[i - vent + 1:i + 1]))
            ys.append(close[i + fut] - close[i])
        r = pearson(xs, ys)
        fila.append(f"{r:10.3f}" if r is not None else f"{'-':>10}")
    p(" ".join(fila))
for vent, serie, nom in ((5, nc, "net_call 5m"), (5, np_, "net_put 5m")):
    fila = [f"{nom:>12}"]
    for fut in (5, 10, 15, 30, 60):
        xs, ys = [], []
        for i in range(vent, n - fut):
            xs.append(sum(serie[i - vent + 1:i + 1]))
            ys.append(close[i + fut] - close[i])
        r = pearson(xs, ys)
        fila.append(f"{r:10.3f}" if r is not None else f"{'-':>10}")
    p(" ".join(fila))
p("")
p("   |r| < 0.10 = nada.  0.10-0.20 = debil.  > 0.30 = merece mirarse en mas dias.")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
