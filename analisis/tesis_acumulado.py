# -*- coding: utf-8 -*-
"""READ-ONLY. Tesis del usuario: el flip llega TARDE porque el diff es ACUMULADO
y el umbral CRECE con el dia. Se mide con ta_minute (net_call/net_put por minuto).
OJO: hoy hubo 8 reinicios que resetean/restauran los acumuladores -> se detectan
como saltos y se marcan, no se ocultan.
"""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)
FECHA = "2026-08-10"
ADAPT_FRAC = 0.15
PISO = 5000.0

rows = c.execute("SELECT hora, net_call, net_put, prem_state, spy FROM ta_minute "
                 "WHERE fecha=? ORDER BY hora", (FECHA,)).fetchall()
print("minutos: %d  (%s -> %s)" % (len(rows), rows[0][0], rows[-1][0]))

print("\n== Evolucion del diff acumulado y del umbral (1 de cada 12 min) ==")
print("  hora   net_call     net_put        diff       umbral   distancia al giro contrario")
for i, (h, nc, np_, st, spy) in enumerate(rows):
    if i % 12 and i != len(rows) - 1:
        continue
    nc = nc or 0.0
    np_ = np_ or 0.0
    diff = nc - np_
    thr = max(PISO, ADAPT_FRAC * (abs(nc) + abs(np_)))
    # cuanto flujo NUEVO hace falta para girar al lado contrario
    if diff >= 0:
        falta = abs(-thr - diff)     # de UP a DOWN
        lado = "-> DOWN"
    else:
        falta = abs(thr - diff)      # de DOWN a UP
        lado = "-> UP  "
    print("  %s %10.0f %11.0f %12.0f %11.0f   %s  %+.0f" % (h, nc, np_, diff, thr, lado, falta))

print("\n== Cuanto CUESTA girar, por hora del dia ==")
print("  (flujo neto nuevo necesario = |diff| + umbral, en millones)")
por_hora = {}
for h, nc, np_, st, spy in rows:
    nc = nc or 0.0
    np_ = np_ or 0.0
    diff = nc - np_
    thr = max(PISO, ADAPT_FRAC * (abs(nc) + abs(np_)))
    coste = abs(diff) + thr
    por_hora.setdefault(h[:2], []).append(coste)
for hh in sorted(por_hora):
    v = sorted(por_hora[hh])
    print("   %s:00  n=%3d  mediana %8.2f M   max %8.2f M"
          % (hh, len(v), v[len(v) // 2] / 1e6, v[-1] / 1e6))

print("\n== Frecuencia de giros por hora (transitions) ==")
for hh, n in c.execute(
        "SELECT substr(hora,1,2), COUNT(*) FROM transitions WHERE fecha=? AND tipo='FLIP' "
        "GROUP BY substr(hora,1,2) ORDER BY 1", (FECHA,)):
    print("   %s:00  %2d giros" % (hh, n))

print("\n== La tesis: antes de cada FLIP, el diff YA venia cayendo? ==")
idx = {h: i for i, (h, _, _, _, _) in enumerate(rows)}
flips = c.execute("SELECT hora, estado FROM transitions WHERE fecha=? AND tipo='FLIP' "
                  "ORDER BY id", (FECHA,)).fetchall()
ok = tarde = 0
detalle = []
for hora, estado in flips:
    hm = hora[:5]
    if hm not in idx:
        continue
    i = idx[hm]
    if i < 4:
        continue
    serie = []
    for j in range(i - 4, i + 1):
        nc = rows[j][1] or 0.0
        np_ = rows[j][2] or 0.0
        serie.append(nc - np_)
    # reinicio? salto brutal de signo/magnitud entre minutos consecutivos
    salto = any(abs(serie[k + 1] - serie[k]) > 3 * (abs(serie[k]) + 1e5) for k in range(len(serie) - 1))
    if salto:
        continue
    sig = 1.0 if estado == "UP" else -1.0
    # cuantos de los 4 minutos previos ya iban EN LA DIRECCION del giro
    pasos = sum(1 for k in range(4) if (serie[k + 1] - serie[k]) * sig > 0)
    detalle.append((hora, estado, pasos, serie[0] * sig, serie[-1] * sig))
    if pasos >= 3:
        ok += 1
    else:
        tarde += 1
print("  episodios limpios (sin reinicio en la ventana): %d" % len(detalle))
if detalle:
    print("  el diff venia moviendose hacia el giro en >=3 de los 4 minutos previos: %d (%.0f%%)"
          % (ok, ok / len(detalle) * 100.0))
    print("\n   hora      dir   minutos previos a favor (de 4)")
    for hora, estado, pasos, a, b in detalle[-14:]:
        print("   %s %5s        %d/4" % (hora, estado, pasos))
