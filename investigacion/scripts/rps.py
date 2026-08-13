# RPS (Reversal Probability Score) propuesto por ChatGPT, implementado y MEDIDO contra el
# 2026-08-13 real. Lee la BD viva en SOLO-LECTURA y la cierra enseguida.
#
# DOS CORRECCIONES a la formula original, ambas necesarias para que signifique algo:
#  1) T_D y O_D suman terminos de escalas incomparables (centavos vs millones de USD). Se
#     normaliza CADA termino por separado y luego se promedia; si no, el flujo pesa el 99.99%.
#  2) "Normalize" sin definir invita al look-ahead. Aqui es el PERCENTIL del valor dentro de la
#     historia PASADA del propio dia (ventana expansiva, minimo 30 min). Un sistema en vivo solo
#     puede conocer eso. Normalizar con el min/max del dia entero seria mirar el futuro.
import sqlite3
import statistics as st

SRC = "spy_history.db"
TXT = "RPS_HOY.txt"
DIA = "2026-08-13"
MIN_HIST = 30          # minutos de historia antes de puntuar nada
UMBRAL = 1.50          # dolares de SPY que definen "movimiento prolongado"
VENTANA = 60           # minutos por delante para lograrlo

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
velas = src.execute("select hora,open,high,low,close,volume from bars_minute where fecha=? "
                    "order by hora", (DIA,)).fetchall()
ta = {h: (s20, s50, s200, atr) for h, s20, s50, s200, atr in src.execute(
    "select hora,sma20,sma50,sma200,atr from ta_minute where fecha=?", (DIA,))}
tp = {m: (c, v) for m, c, v in src.execute(
    "select substr(hora,1,5), sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo='SPY' group by 1", (DIA,))}
opc = src.execute(
    "select substr(hora,1,5) m, right,"
    " sum(case when agresor='COMPRA' then premium else 0 end),"
    " sum(case when agresor='VENTA' then premium else 0 end) from tape "
    "where fecha=? and grupo<>'SPY' and right is not null group by m, right", (DIA,)).fetchall()
src.close()
C = {m: c - v for m, r, c, v in opc if r == "C"}
P = {m: c - v for m, r, c, v in opc if r == "P"}
print(f"{len(velas)} velas, {len(tp)} minutos de tape SPY, {len(ta)} de TA")

# ---------- series acumuladas por minuto ----------
horas = [x[0] for x in velas]
close = [x[4] for x in velas]
high = [x[2] for x in velas]
low = [x[3] for x in velas]
vol = [x[5] for x in velas]
ac_spy, ac_c, ac_p = [], [], []
a = b = d = 0.0
for h in horas:
    c_, v_ = tp.get(h, (0.0, 0.0))
    a += c_ - v_
    b += C.get(h, 0.0)
    d += P.get(h, 0.0)
    ac_spy.append(a)
    ac_c.append(b)
    ac_p.append(d)


def delta(serie, i, n):
    return serie[i] - serie[i - n] if i >= n else None


def pct_pasado(serie_valores, i):
    """Percentil [0,1] del valor i dentro de los ANTERIORES. Nada de futuro."""
    hist = [x for x in serie_valores[:i] if x is not None]
    v = serie_valores[i]
    if v is None or len(hist) < MIN_HIST:
        return None
    return sum(1 for x in hist if x < v) / len(hist)


# ---------- terminos crudos ----------
n = len(velas)
dP5 = [delta(close, i, 5) for i in range(n)]
dP15 = [delta(close, i, 15) for i in range(n)]
dF5 = [delta(ac_spy, i, 5) for i in range(n)]
dC5 = [delta(ac_c, i, 5) for i in range(n)]
dU5 = [delta(ac_p, i, 5) for i in range(n)]

pos30, decel, mom, estr, valid = [], [], [], [], []
for i in range(n):
    if i >= 30:
        h30, l30 = max(high[i - 30:i + 1]), min(low[i - 30:i + 1])
        pos30.append((close[i] - l30) / (h30 - l30) if h30 > l30 else 0.5)
    else:
        pos30.append(None)
    if dP5[i] is not None and dP15[i] is not None and abs(dP15[i]) > 1e-9:
        decel.append(1 - abs(dP5[i]) / (abs(dP15[i]) / 3 + 1e-9))
    else:
        decel.append(None)
    # momentum: la tendencia larga sigue pero la corta la contradice
    mom.append((dP15[i], dP5[i]) if (dP5[i] is not None and dP15[i] is not None) else None)
    s = ta.get(horas[i], (None,) * 4)
    estr.append((close[i] - s[0]) if s[0] else None)          # distancia a la SMA20
    valid.append(vol[i])

# percentiles pasados de cada termino, por separado (correccion 1)
pdP5 = [pct_pasado(dP5, i) for i in range(n)]
pdF5 = [pct_pasado(dF5, i) for i in range(n)]
pdC5 = [pct_pasado(dC5, i) for i in range(n)]
pdU5 = [pct_pasado(dU5, i) for i in range(n)]
pdec = [pct_pasado(decel, i) for i in range(n)]
pest = [pct_pasado(estr, i) for i in range(n)]
pvol = [pct_pasado(valid, i) for i in range(n)]


def med(vals):
    vals = [v for v in vals if v is not None]
    return st.mean(vals) if vals else None


filas = []
for i in range(n):
    if any(x is None for x in (pdP5[i], pdF5[i], pdC5[i], pdU5[i], pos30[i], pdec[i],
                               pest[i], pvol[i])):
        filas.append(None)
        continue
    # --- T: divergencia tape vs precio (cada termino ya normalizado) ---
    T_bear = med([1 - pdP5[i], pdF5[i], 1 - pdC5[i], pdU5[i]])
    T_bull = med([pdP5[i], 1 - pdF5[i], pdC5[i], 1 - pdU5[i]])
    # --- O: presion de opciones ---
    O_bear = med([1 - pdC5[i], pdU5[i]])
    O_bull = med([pdC5[i], 1 - pdU5[i]])
    # --- P: agotamiento (posicion en rango + deceleracion) ---
    P_bear = med([pos30[i], pdec[i]])
    P_bull = med([1 - pos30[i], pdec[i]])
    # --- M: tendencia larga viva pero corta contradiciendola ---
    l_, c_ = mom[i]
    M_bear = 1.0 if (l_ > 0 and c_ < 0) else (0.5 if l_ > 0 else 0.0)
    M_bull = 1.0 if (l_ < 0 and c_ > 0) else (0.5 if l_ < 0 else 0.0)
    # --- S: estructura respecto a la SMA20 ---
    S_bear, S_bull = pest[i], 1 - pest[i]
    # --- V: energia del movimiento ---
    V_bear = V_bull = pvol[i]

    rps_bear = 100 * (.30 * T_bear + .20 * O_bear + .15 * P_bear + .15 * M_bear
                      + .10 * S_bear + .10 * V_bear)
    rps_bull = 100 * (.30 * T_bull + .20 * O_bull + .15 * P_bull + .15 * M_bull
                      + .10 * S_bull + .10 * V_bull)
    # ruptura estructural: el precio ya esta girando de verdad
    sb_bear = 1 if (i >= 5 and close[i] < min(low[i - 5:i])) else 0
    sb_bull = 1 if (i >= 5 and close[i] > max(high[i - 5:i])) else 0
    filas.append((rps_bear, rps_bull, sb_bear, sb_bull))

# ---------- etiqueta real: ¿ocurrio el movimiento? ----------
def logro(i, direccion):
    fin = min(i + VENTANA, n - 1)
    fut = close[i + 1:fin + 1]
    if not fut:
        return None
    return (max(fut) - close[i] >= UMBRAL) if direccion == "BULL" else \
           (close[i] - min(fut) >= UMBRAL)


O = []
def p(s=""):
    O.append(s)


p(f"RPS (Reversal Probability Score) MEDIDO CONTRA EL {DIA} REAL")
p("=" * 100)
p(f"objetivo: que el SPY recorra >= ${UMBRAL:.2f} en la direccion predicha dentro de "
  f"{VENTANA} minutos")
p(f"normalizacion: percentil sobre la historia PASADA del dia (min {MIN_HIST} min). Sin futuro.")
p("")

base_bull = [logro(i, "BULL") for i in range(n - 1)]
base_bear = [logro(i, "BEAR") for i in range(n - 1)]
tb_bull = sum(1 for x in base_bull if x) / len(base_bull)
tb_bear = sum(1 for x in base_bear if x) / len(base_bear)
p(f"TASA BASE (todos los minutos): BULL {100*tb_bull:.1f}%   BEAR {100*tb_bear:.1f}%")
p("")

p("ACIERTO POR TRAMO DE RPS  (sin exigir ruptura estructural)")
p(f"{'tramo':>10} {'n_bear':>7} {'ac_bear':>8} {'vs base':>8}   {'n_bull':>7} {'ac_bull':>8} {'vs base':>8}")
for lo, hi in ((0, 50), (50, 65), (65, 75), (75, 85), (85, 101)):
    nb = ab = nu = au = 0
    for i in range(n - 1):
        if filas[i] is None:
            continue
        rb, ru, _, _ = filas[i]
        if lo <= rb < hi:
            nb += 1
            ab += 1 if logro(i, "BEAR") else 0
        if lo <= ru < hi:
            nu += 1
            au += 1 if logro(i, "BULL") else 0
    fb = f"{100*ab/nb:7.1f}%" if nb else "      -"
    db = f"{100*(ab/nb-tb_bear):+7.1f}" if nb else "      -"
    fu = f"{100*au/nu:7.1f}%" if nu else "      -"
    du = f"{100*(au/nu-tb_bull):+7.1f}" if nu else "      -"
    p(f"{f'{lo}-{hi-1}':>10} {nb:7} {fb} {db}   {nu:7} {fu} {du}")
p("")

p("LA REGLA COMPLETA: RPS >= 75 **Y** ruptura estructural")
p(f"{'señal':>10} {'n':>5} {'aciertos':>9} {'tasa':>8} {'base':>8} {'lift':>8}")
for nom, dirc in (("BEAR", "BEAR"), ("BULL", "BULL")):
    n_, a_ = 0, 0
    for i in range(n - 1):
        if filas[i] is None:
            continue
        rb, ru, sbb, sbu = filas[i]
        cond = (rb >= 75 and sbb) if nom == "BEAR" else (ru >= 75 and sbu)
        if cond:
            n_ += 1
            a_ += 1 if logro(i, dirc) else 0
    base = tb_bear if nom == "BEAR" else tb_bull
    if n_:
        p(f"{nom:>10} {n_:5} {a_:9} {100*a_/n_:7.1f}% {100*base:7.1f}% "
          f"{100*(a_/n_-base):+7.1f}")
    else:
        p(f"{nom:>10} {0:5} {'-':>9} {'-':>8} {100*base:7.1f}% {'-':>8}")
p("")

p("DETALLE MINUTO A MINUTO (solo donde RPS>=65)")
p(f"{'hora':>7} {'spy':>9} {'rps_bear':>9} {'rps_bull':>9} {'sb_b':>5} {'sb_u':>5} "
  f"{'logro_bear':>11} {'logro_bull':>11}")
for i in range(n - 1):
    if filas[i] is None:
        continue
    rb, ru, sbb, sbu = filas[i]
    if max(rb, ru) < 65:
        continue
    p(f"{horas[i]:>7} {close[i]:9.2f} {rb:9.1f} {ru:9.1f} {sbb:5} {sbu:5} "
      f"{str(logro(i,'BEAR')):>11} {str(logro(i,'BULL')):>11}")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
