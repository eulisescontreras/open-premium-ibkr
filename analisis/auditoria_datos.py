# -*- coding: utf-8 -*-
"""AUDITORIA de calidad de la BD (solo lectura). No opina: contrasta unas tablas contra otras."""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)
F = "2026-08-10"


def one(sql, *a):
    r = c.execute(sql, a).fetchone()
    return r[0] if r else None


print("=" * 70)
print("1) CONGRUENCIA CRUZADA: precio del SPY en ta_minute vs spot en walls_snapshot")
print("=" * 70)
rows = c.execute(
    "SELECT w.hora, w.spot, t.spy, ABS(w.spot - t.spy) d FROM walls_snapshot w "
    "JOIN ta_minute t ON t.fecha=w.fecha AND t.hora=w.hora "
    "WHERE w.fecha=? ORDER BY w.hora", (F,)).fetchall()
print("snapshots comparables: %d" % len(rows))
if rows:
    malos = [r for r in rows if r[3] > 0.30]
    peor = max(rows, key=lambda r: r[3])
    print("  diferencia media : %.3f" % (sum(r[3] for r in rows) / len(rows)))
    print("  peor caso        : %s  spot=%.2f vs ta=%.2f  dif=%.2f" % peor)
    print("  con dif > 0.30   : %d (%.0f%%)" % (len(malos), len(malos) / len(rows) * 100))
    for r in malos[:6]:
        print("     %s spot=%.2f ta=%.2f dif=%.2f" % r)

print()
print("=" * 70)
print("2) CONTAMINACION CONOCIDA: spot congelado (GAP 17)")
print("=" * 70)
rep = c.execute(
    "SELECT spot, COUNT(*) n, MIN(hora), MAX(hora) FROM walls_snapshot WHERE fecha=? "
    "GROUP BY spot HAVING n > 2 ORDER BY n DESC LIMIT 5", (F,)).fetchall()
for spot, n, h0, h1 in rep:
    print("  spot=%.2f repetido %d veces  (%s -> %s)" % (spot, n, h0, h1))
n_stale = one("SELECT COUNT(*) FROM walls_snapshot WHERE fecha=? AND spot_stale=1", F)
n_null = one("SELECT COUNT(*) FROM walls_snapshot WHERE fecha=? AND spot_stale IS NULL", F)
n_ok = one("SELECT COUNT(*) FROM walls_snapshot WHERE fecha=? AND spot_stale=0", F)
print("  marcadas stale=1: %s | stale=0: %s | SIN MARCA (codigo viejo): %s" % (n_stale, n_ok, n_null))

print()
print("=" * 70)
print("3) HUECOS Y CORTES en la serie por minuto")
print("=" * 70)
horas = [r[0] for r in c.execute("SELECT hora FROM ta_minute WHERE fecha=? ORDER BY hora", (F,))]
def m(h):
    a = h.split(":")
    return int(a[0]) * 60 + int(a[1])
hue = [(horas[i - 1], horas[i], m(horas[i]) - m(horas[i - 1]) - 1)
       for i in range(1, len(horas)) if m(horas[i]) - m(horas[i - 1]) > 1]
print("  minutos con TA: %d  (%s -> %s)" % (len(horas), horas[0], horas[-1]))
print("  minutos esperados 09:30-ahora: %d" % (m(horas[-1]) - m("09:30") + 1))
print("  HUECOS: %d" % len(hue))
for a, b, n in hue:
    print("     %s -> %s  (faltan %d)" % (a, b, n))

print()
print("=" * 70)
print("4) DISCONTINUIDADES en net_call/net_put (los 9 reinicios de hoy)")
print("=" * 70)
serie = c.execute("SELECT hora,net_call,net_put FROM ta_minute WHERE fecha=? ORDER BY hora",
                  (F,)).fetchall()
saltos = []
for i in range(1, len(serie)):
    h, nc, np_ = serie[i]
    h0, nc0, np0 = serie[i - 1]
    if nc0 is None or nc is None:
        continue
    # un reinicio pone los acumuladores a 0 o los restaura: salto brutal
    if abs(nc) < abs(nc0) * 0.2 and abs(nc0) > 100000:
        saltos.append((h0, h, nc0, nc))
print("  caidas bruscas del acumulado (=reinicio): %d" % len(saltos))
for s in saltos:
    print("     %s -> %s : net_call %.0f -> %.0f" % s)

print()
print("=" * 70)
print("5) RANGOS: valores imposibles?")
print("=" * 70)
print("  rsi fuera de 0-100 :", one("SELECT COUNT(*) FROM ta_minute WHERE rsi<0 OR rsi>100"))
print("  spy <=0 o NULL     :", one("SELECT COUNT(*) FROM ta_minute WHERE spy IS NULL OR spy<=0"))
print("  gamma negativa     :", one("SELECT COUNT(*) FROM premium_minute WHERE gamma<0"))
print("  open_interest <0   :", one("SELECT COUNT(*) FROM premium_minute WHERE open_interest<0"))
print("  cum_prem negativo  :", one("SELECT COUNT(*) FROM strike_accum WHERE cum_prem<0"))
print("  gex_total NULL     :", one("SELECT COUNT(*) FROM walls_snapshot WHERE gex_total IS NULL"))
print("  regime distinto de LONG/SHORT:",
      one("SELECT COUNT(*) FROM walls_snapshot WHERE regime NOT IN ('LONG','SHORT')"))

print()
print("=" * 70)
print("6) COHERENCIA transitions vs ta_minute (el estado UP/DOWN cuadra?)")
print("=" * 70)
mal = 0
tot = 0
for hora, estado in c.execute("SELECT hora,estado FROM transitions WHERE fecha=? AND tipo='FLIP' "
                              "ORDER BY id", (F,)):
    hm = hora[:5]
    r = c.execute("SELECT prem_state FROM ta_minute WHERE fecha=? AND hora>? ORDER BY hora LIMIT 1",
                  (F, hm)).fetchone()
    if r and r[0]:
        tot += 1
        if r[0] != estado:
            mal += 1
print("  flips comparables: %d | el minuto SIGUIENTE no coincide con el estado: %d (%.0f%%)"
      % (tot, mal, (mal / tot * 100) if tot else 0))

print()
print("=" * 70)
print("7) GAP 2 (doble conteo ATM): premium de los 2 strikes ATM vs sus vecinos")
print("=" * 70)
ult = one("SELECT MAX(hora) FROM premium_minute WHERE fecha=? AND expiry='20260810' "
          "AND gamma IS NOT NULL", F)
rows = c.execute("SELECT strike,right,day_prem FROM premium_minute WHERE fecha=? AND hora=? "
                 "AND expiry='20260810' AND right='C' ORDER BY strike", (F, ult)).fetchall()
print("  foto %s (calls 0DTE):" % ult)
for s, r, dp in rows:
    print("     %6.0f%s  day_prem=%14.0f" % (s, r, dp or 0))

print()
print("=" * 70)
print("8) VOLUMEN DE DATOS por tabla")
print("=" * 70)
for t in ("ta_minute", "premium_minute", "walls_snapshot", "transitions",
          "strike_accum", "strike_daily", "trades", "posicion_minuto", "sesion_config"):
    print("  %-16s %6d" % (t, one("SELECT COUNT(*) FROM %s" % t)))
