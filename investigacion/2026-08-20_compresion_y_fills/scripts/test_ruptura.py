# -*- coding: utf-8 -*-
# ¿LA RUPTURA DE LA PLANITUD DA IMPULSO A FAVOR DEL ST?  (observación del usuario, 2026-08-20)
#
# LO QUE DICE EL USUARIO: "cuando el precio se mantiene en un rango o se va en contra de lo que
# dice el supertrend, la línea se aplana; y cuando esa planicie TERMINA, eso indica RUPTURA y el
# precio coge impulso HACIA DONDE DICE EL SUPERTREND".
#
# ES DISTINTO DE LO YA MEDIDO. `test_tiempo_muerto.py` midió lo que pasa DURANTE el tramo plano
# y encontró que `plana>=8` anticipa el FLIP del ST (17,5% -> 36,3%), o sea el precio yendo
# CONTRA el ST previo. El usuario señala la otra rama: la salida A FAVOR. Pueden convivir.
#
# ⚠️ TRAMPA 1 — MECÁNICA (la que puede inventar el hallazgo entero).
# En `st_lin_p` (VERIFICADO, rebote.py:61-76) con d=1 la línea es `fl` y solo sube cuando
# `lb > fl`, es decir CUANDO EL PRECIO ACABA DE SUBIR. Con d=-1, simétrico. Entonces
# "la línea rompe la planitud" y "el precio acaba de moverse a favor del ST" son casi la misma
# cosa POR CONSTRUCCIÓN. Sin control, sale un efecto brillante que solo es momentum trivial.
# CONTROL: comparar contra buckets con el MISMO movimiento propio pero SIN ruptura (mismo decil
# de |cl-o|/atr). Si el efecto desaparece, es mecánico.
#
# ⚠️ TRAMPA 2 — LOOK-AHEAD. Saber que un tramo plano "terminó" en el bucket i exige ver i+1.
# Aquí la detección se hace EN el bucket j que YA rompió (observable a su cierre) y el objetivo
# se mide desde cl[j] hacia delante. Nada del futuro entra en el predictor.
#
# OBJETIVO (con SIGNO, no valor absoluto): (cl[j+k] - cl[j]) * d[j] / atr.
# Positivo = el precio avanzó A FAVOR del ST. El valor absoluto NO sirve: mediría "se movió",
# que es justo lo que ya sabemos, no "se movió hacia donde dice el ST".
import sqlite3, sys, statistics as stt

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import st_lin_p
from sys2.core.supertrend import hhmm

con = sqlite3.connect(RAIZ + r"\sys2.db")
FECHAS = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")][-485:]
CORTE = FECHAS[len(FECHAS) // 2]

R = []
for f in FECHAS:
    bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                       (f,)).fetchall()
    if len(bars) < 100:
        continue
    try:
        L, ks, Dd = st_lin_p(bars, C.ST_PER, C.ST_MULT)
    except Exception:
        continue
    # planitud acumulada hasta cada bucket (solo pasado)
    plana = {}
    p = 0
    for q in range(1, len(ks)):
        p = (p + 1) if abs(L[ks[q]]['linea'] - L[ks[q - 1]]['linea']) < 1e-9 else 0
        plana[q] = p
    for j in range(12, len(ks) - 13):
        h = hhmm(ks[j])
        if not ("09:45" <= h <= "15:30"):
            continue
        atr = sum(L[ks[z]]['hi'] - L[ks[z]]['lo'] for z in range(j - 10, j + 1)) / 11.0
        if atr <= 0:
            continue
        dj = L[ks[j]]['d']
        if dj == 0:
            continue
        rompe = plana[j] == 0                      # la línea SE MOVIÓ en este bucket
        previa = plana[j - 1]                      # cuántos buckets llevaba plana ANTES
        # movimiento del PROPIO bucket j, con signo a favor del ST -> el control de la trampa 1
        propio = (L[ks[j]]['cl'] - L[ks[j]]['o']) * dj / atr
        # ¿la línea SALTÓ DE LADO (flip) o solo avanzó en su lado? Son dos rupturas distintas
        # y promediarlas mezcla dos fenómenos opuestos: con flip, `dj` YA es el lado nuevo.
        flip = dj != L[ks[j - 1]]['d']
        # TENDENCIA EN MARCHA (foto del usuario, 2026-08-20 14:00): sus escalones planos ocurren
        # con el ST YA bajando en escalones sucesivos — son PAUSAS dentro de una tendencia, no
        # rangos largos. Se mide con cuántos de los 12 buckets previos movieron la línea y con
        # cuántos lleva el ST en el mismo lado. Ambas cosas son SOLO PASADO.
        escal = sum(1 for z in range(j - 11, j + 1) if plana.get(z, 0) == 0)
        edad = 0
        for z in range(j, max(0, j - 60), -1):
            if L[ks[z]]['d'] == dj:
                edad += 1
            else:
                break
        reg = dict(f=f, rompe=rompe, previa=previa, propio=propio, d=dj, flip=flip,
                   escal=escal, edad=edad)
        for k_, etiq in ((4, "4b"), (12, "12b")):
            reg[etiq] = (L[ks[j + k_]]['cl'] - L[ks[j]]['cl']) * dj / atr
        R.append(reg)

print("buckets analizados: %d   |   corte A1/A2: %s\n" % (len(R), CORTE))
b4 = stt.mean(x['4b'] for x in R)
b12 = stt.mean(x['12b'] for x in R)
print("BASE (todos los buckets): a favor del ST  4b %+.4f ATR   12b %+.4f ATR" % (b4, b12))
print("  ^ este es el drift de fondo. Todo lo de abajo se compara CONTRA esto, no contra cero.\n")


def fila(etiq, sub):
    if len(sub) < 40:
        return
    a1 = [x for x in sub if x['f'] < CORTE]
    a2 = [x for x in sub if x['f'] >= CORTE]
    print("%-28s %7d %+9.4f %+9.4f %+9.4f %+9.4f"
          % (etiq, len(sub), stt.mean(x['4b'] for x in sub), stt.mean(x['12b'] for x in sub),
             stt.mean(x['12b'] for x in a1) if len(a1) >= 20 else float('nan'),
             stt.mean(x['12b'] for x in a2) if len(a2) >= 20 else float('nan')))


print("=== 1. RUPTURA (la línea se movió en este bucket) POR LONGITUD DEL TRAMO PLANO PREVIO ===")
print("%-28s %7s %9s %9s %9s %9s" % ("", "n", "4b", "12b", "12b A1", "12b A2"))
fila("NO rompe (línea quieta)", [x for x in R if not x['rompe']])
fila("ROMPE (cualquier tramo)", [x for x in R if x['rompe']])
for lo, hi in ((0, 1), (1, 3), (3, 6), (6, 11), (11, 16), (16, 21), (21, 999)):
    fila("  rompe tras plana %d-%d" % (lo, hi - 1),
         [x for x in R if x['rompe'] and lo <= x['previa'] < hi])
print()

print("=== 2. DENTRO del tramo plano (control: estar plano NO es romper) ===")
print("%-28s %7s %9s %9s %9s %9s" % ("", "n", "4b", "12b", "12b A1", "12b A2"))
for lo, hi in ((1, 3), (3, 6), (6, 11), (11, 16), (16, 21), (21, 999)):
    fila("  plano en curso %d-%d" % (lo, hi - 1),
         [x for x in R if not x['rompe'] and lo <= x['previa'] < hi])
print()

print("=== 3. CONTROL DE LA TRAMPA MECÁNICA: mismo movimiento propio, rompe vs no rompe ===")
print("El bucket que rompe es, por construcción, un bucket que se movió a favor del ST.")
print("Si al fijar el movimiento propio el efecto desaparece -> es mecánico, no predictivo.\n")
prop = sorted(x['propio'] for x in R)
cortes = [prop[int(len(prop) * q)] for q in (0.2, 0.4, 0.6, 0.8)]


def decil(x):
    for i_, c in enumerate(cortes):
        if x['propio'] < c:
            return i_
    return len(cortes)


print("%-28s %7s %9s %9s   %7s %9s %9s" % ("quintil mov. propio", "n rmp", "4b", "12b",
                                           "n no", "4b", "12b"))
for q in range(len(cortes) + 1):
    rr = [x for x in R if decil(x) == q and x['rompe']]
    nn = [x for x in R if decil(x) == q and not x['rompe']]
    if len(rr) < 40 or len(nn) < 40:
        continue
    print("Q%d  propio<=%+.2f          %7d %+9.4f %+9.4f   %7d %+9.4f %+9.4f"
          % (q + 1, cortes[q] if q < len(cortes) else prop[-1], len(rr),
             stt.mean(x['4b'] for x in rr), stt.mean(x['12b'] for x in rr), len(nn),
             stt.mean(x['4b'] for x in nn), stt.mean(x['12b'] for x in nn)))
print()

print("=== 5. DOS RUPTURAS DISTINTAS: la línea AVANZA en su lado  vs  SALTA de lado (flip) ===")
print("Con flip, `d` ya es el lado NUEVO: 'a favor del ST' significa a favor de la tendencia")
print("recién nacida. Promediarlo con el avance normal mezcla dos cosas opuestas.\n")
print("%-28s %7s %9s %9s %9s %9s" % ("", "n", "4b", "12b", "12b A1", "12b A2"))
fila("rompe SIN flip (avanza)", [x for x in R if x['rompe'] and not x['flip']])
fila("rompe CON flip (salta)", [x for x in R if x['rompe'] and x['flip']])
print()
for et, cond in (("SIN flip", False), ("CON flip", True)):
    for lo, hi in ((0, 3), (3, 8), (8, 16), (16, 999)):
        fila("  %s tras plana %d-%d" % (et, lo, hi - 1),
             [x for x in R if x['rompe'] and x['flip'] == cond and lo <= x['previa'] < hi])
    print()

print("=== 6. IMPULSO VIVO vs AGOTADO (2ª formulación del usuario, foto de las 11:09) ===")
print("\"el impulso se agota cuando la línea SE COMIENZA A APLANAR; mientras el impulso se")
print(" mantiene, el ST-3 NO está plano\".  escal = de los 12 buckets previos, cuántos MOVIERON")
print(" la línea (12 = línea avanzando en escalones sin parar; 0 = línea congelada).")
print("Si la observación es cierta, el avance a favor del ST debe CRECER con escal.\n")
print("%-28s %7s %9s %9s %9s %9s" % ("", "n", "4b", "12b", "12b A1", "12b A2"))
for lo, hi in ((0, 1), (1, 3), (3, 5), (5, 7), (7, 9), (9, 11), (11, 13)):
    fila("  escal %d-%d de 12" % (lo, hi - 1), [x for x in R if lo <= x['escal'] < hi])
print()

print("=== 7. EL MOMENTO EXACTO: la línea EMPEZABA a aplanarse tras venir moviéndose ===")
print("previa 1-3 (acaba de aplanarse) y escal >= 7 (venía activa) = el agotamiento que")
print("describe el usuario. Se compara contra escal >= 7 con la línea aún en movimiento.\n")
print("%-28s %7s %9s %9s %9s %9s" % ("", "n", "4b", "12b", "12b A1", "12b A2"))
fila("activa y SIGUE moviéndose", [x for x in R if x['escal'] >= 7 and x['rompe']])
fila("activa y ACABA de aplanarse", [x for x in R if x['escal'] >= 7 and 1 <= x['previa'] <= 3
                                     and not x['rompe']])
fila("activa y lleva 4-7 plana", [x for x in R if x['escal'] >= 7 and 4 <= x['previa'] <= 7
                                  and not x['rompe']])
print()

print("=== 8. DISTRIBUCIÓN, NO MEDIA (la media cancela colas opuestas) ===")
print("En la foto cada tramo son 2-3 ATR. Una media de +0,06 es compatible con eso si los")
print("casos grandes a favor se cancelan con los grandes en contra. Aquí se CUENTAN los dos.\n")
print("%-28s %7s %8s %8s %8s" % ("", "n", ">=+1ATR", "<=-1ATR", "ratio"))
for et, sub in (("BASE (todos)", R),
                ("rompe tras plana >=8", [x for x in R if x['rompe'] and x['previa'] >= 8]),
                ("escal >= 9 (impulso vivo)", [x for x in R if x['escal'] >= 9]),
                ("escal <= 2 (congelada)", [x for x in R if x['escal'] <= 2]),
                ("activa y ACABA de aplanarse",
                 [x for x in R if x['escal'] >= 7 and 1 <= x['previa'] <= 3 and not x['rompe']])):
    if len(sub) < 40:
        continue
    bien = sum(1 for x in sub if x['12b'] >= 1.0)
    mal = sum(1 for x in sub if x['12b'] <= -1.0)
    print("%-28s %7d %7.1f%% %7.1f%% %8s"
          % (et, len(sub), 100.0 * bien / len(sub), 100.0 * mal / len(sub),
             ("%.2f" % (float(bien) / mal)) if mal else "-"))
print()

print("=== 4. LO MISMO PERO SOLO RUPTURAS DE TRAMOS LARGOS (previa >= 8) ===")
print("%-28s %7s %9s %9s   %7s %9s %9s" % ("quintil mov. propio", "n rmp", "4b", "12b",
                                           "n no", "4b", "12b"))
for q in range(len(cortes) + 1):
    rr = [x for x in R if decil(x) == q and x['rompe'] and x['previa'] >= 8]
    nn = [x for x in R if decil(x) == q and not x['rompe'] and x['previa'] >= 8]
    if len(rr) < 30 or len(nn) < 30:
        continue
    print("Q%d  propio<=%+.2f          %7d %+9.4f %+9.4f   %7d %+9.4f %+9.4f"
          % (q + 1, cortes[q] if q < len(cortes) else prop[-1], len(rr),
             stt.mean(x['4b'] for x in rr), stt.mean(x['12b'] for x in rr), len(nn),
             stt.mean(x['4b'] for x in nn), stt.mean(x['12b'] for x in nn)))
