# -*- coding: utf-8 -*-
"""READ-ONLY. Pregunta: los datos guardados EXPLICAN los movimientos del dia?
Metodo: localizar los mayores movimientos del SPY y ver que decian los datos ANTES y DURANTE.
"""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)
F = "2026-08-10"

rows = c.execute("SELECT hora,spy,net_call,net_put,rsi,atr_pct,vwap,bb_up,bb_low,bb_mid,"
                 "prem_state FROM ta_minute WHERE fecha=? ORDER BY hora", (F,)).fetchall()
print("minutos: %d (%s -> %s)" % (len(rows), rows[0][0], rows[-1][0]))


def m(h):
    a = h.split(":")
    return int(a[0]) * 60 + int(a[1])


print("\n" + "=" * 72)
print("1) LOS 8 MAYORES MOVIMIENTOS DE 5 MINUTOS DEL DIA")
print("=" * 72)
movs = []
for i in range(len(rows)):
    for j in range(i + 1, len(rows)):
        if m(rows[j][0]) - m(rows[i][0]) == 5:
            movs.append((rows[j][1] - rows[i][1], rows[i][0], rows[j][0],
                         rows[i][1], rows[j][1]))
            break
movs.sort(key=lambda x: -abs(x[0]))
print("  desde -> hasta      SPY            mov     estado_premium_al_inicio")
idx = {r[0]: r for r in rows}
for d, h0, h1, p0, p1 in movs[:8]:
    st = idx[h0][10]
    print("  %s -> %s   %.2f -> %.2f   %+.2f   estado=%s" % (h0, h1, p0, p1, d, st))

print("\n" + "=" * 72)
print("2) ESOS MOVIMIENTOS, SE VEIAN VENIR EN EL GEX / WALLS?")
print("=" * 72)
w = c.execute("SELECT hora,spot,gex_total,regime,gamma_flip,call_wall,put_wall,prem_center,"
              "spot_stale FROM walls_snapshot WHERE fecha=? ORDER BY hora", (F,)).fetchall()
wd = {r[0]: r for r in w}
print("  (se busca el snapshot de walls mas cercano ANTES del movimiento)")
for d, h0, h1, p0, p1 in movs[:5]:
    cand = [x for x in w if m(x[0]) <= m(h0)]
    if not cand:
        continue
    x = cand[-1]
    stale = " [SPOT STALE]" if x[8] == 1 else ""
    print("  mov %+.2f en %s | walls %s: GEX=%+.0fBn %s flip=%.2f CW=%.0f PW=%.0f peso=%.2f%s"
          % (d, h0, x[0], (x[2] or 0) / 1e9, x[3], x[4] or 0, x[5] or 0, x[6] or 0,
             x[7] or 0, stale))

print("\n" + "=" * 72)
print("3) EL PREMIUM POR VELA ANTICIPA EL MOVIMIENTO DEL MINUTO SIGUIENTE?")
print("=" * 72)
pv = c.execute("SELECT hora,spy,prem_call_min,prem_put_min,net_call_min,net_put_min "
               "FROM ta_minute WHERE fecha=? AND prem_call_min IS NOT NULL ORDER BY hora",
               (F,)).fetchall()
print("  velas con premium propio: %d  (empezo a las %s)"
      % (len(pv), pv[0][0] if pv else "-"))
if len(pv) >= 3:
    print("  hora   SPY      brutoC     brutoP   sesgo   netC       netP     movimiento_siguiente")
    for i in range(len(pv) - 1):
        h, spy, bc, bp, nc, np_ = pv[i]
        sig = pv[i + 1][1] - spy
        sesgo = "CALL" if bc > bp else "PUT"
        print("  %s %7.2f %10.0f %10.0f  %-5s %+9.0f %+9.0f   %+.2f"
              % (h, spy, bc, bp, sesgo, nc, np_, sig))
    aciertos = 0
    tot = 0
    for i in range(len(pv) - 1):
        h, spy, bc, bp, nc, np_ = pv[i]
        sig = pv[i + 1][1] - spy
        if abs(sig) < 0.005:
            continue
        tot += 1
        # sesgo por NETO firmado (la direccion), no por bruto
        if (nc - np_) * sig > 0:
            aciertos += 1
    print("\n  el NETO de la vela acierta la direccion del minuto siguiente: %d de %d"
          % (aciertos, tot))
    print("  (MUESTRA RIDICULA - no concluye nada, solo demuestra que el dato ya se puede cruzar)")
else:
    print("  aun no hay suficientes velas (arrancaron a las 14:28)")

print("\n" + "=" * 72)
print("4) QUE PASO EN EL MOVIMIENTO GRANDE DE LAS 12:31 (la noticia)")
print("=" * 72)
for h, spy, nc, np_, rsi, atr, vwap, bu, bl, bm, st in rows:
    if "12:26" <= h <= "12:40":
        anch = ((bu - bl) / bm * 100.0) if (bu and bl and bm) else 0
        print("  %s SPY=%.2f rsi=%4.1f atr=%.3f%% bb_ancho=%.3f%% dist_vwap=%+.2f estado=%s "
              "| netC=%.0f netP=%.0f" % (h, spy, rsi or 0, (atr or 0), anch,
                                         spy - (vwap or spy), st, nc or 0, np_ or 0))
