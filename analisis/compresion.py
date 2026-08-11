# -*- coding: utf-8 -*-
"""READ-ONLY. HIPOTESIS A REFUTAR: la compresion del ancho de Bollinger precede a movimientos
grandes del SPY.

Se mide sobre TODAS las compresiones del dia, no solo las que funcionaron (evitar el sesgo de
seleccion). Se compara contra la TASA BASE: cuanto se mueve el SPY en un minuto cualquiera.
"""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _fecha import fecha_analisis   # fecha por argumento; por defecto, la ultima con datos

F = fecha_analisis()
rows = c.execute("SELECT hora,spy,bb_up,bb_low,bb_mid,atr_pct FROM ta_minute WHERE fecha=? "
                 "AND spy IS NOT NULL AND bb_up IS NOT NULL ORDER BY hora", (F,)).fetchall()


def m(h):
    a = h.split(":")
    return int(a[0]) * 60 + int(a[1])


serie = []
for h, spy, bu, bl, bm, atr in rows:
    if not bm:
        continue
    serie.append({"h": h, "t": m(h), "spy": spy, "bb": (bu - bl) / bm * 100.0, "atr": atr})
print("minutos con Bollinger: %d (%s -> %s)" % (len(serie), serie[0]["h"], serie[-1]["h"]))

idx = {s["t"]: s for s in serie}


def mov_max(t0, mins):
    """Maximo movimiento ABSOLUTO del SPY en los siguientes `mins` minutos."""
    p0 = idx[t0]["spy"]
    vals = [abs(idx[t]["spy"] - p0) for t in range(t0 + 1, t0 + mins + 1) if t in idx]
    return max(vals) if vals else None


# ---------- percentil MOVIL: comprimido respecto a su propia historia reciente ----------
VENTANA = 30
for PCT, etiqueta in ((20, "percentil 20 (muy comprimido)"), (10, "percentil 10 (extremo)")):
    print("\n" + "=" * 74)
    print("COMPRESION = bb_ancho en el %s de los ultimos %d min" % (etiqueta, VENTANA))
    print("=" * 74)
    comprimidos = []
    normales = []
    for i, s in enumerate(serie):
        hist = [x["bb"] for x in serie[max(0, i - VENTANA):i] if x["t"] > s["t"] - VENTANA - 5]
        if len(hist) < 20:
            continue
        hist_ord = sorted(hist)
        umbral = hist_ord[max(0, int(len(hist_ord) * PCT / 100.0) - 1)]
        (comprimidos if s["bb"] <= umbral else normales).append(s["t"])

    print("  minutos comprimidos: %d | normales: %d" % (len(comprimidos), len(normales)))
    print()
    print("  horizonte |  tras COMPRESION      |  tras NORMAL          | ratio")
    for H in (3, 5, 10, 15):
        a = [mov_max(t, H) for t in comprimidos]
        a = [x for x in a if x is not None]
        b = [mov_max(t, H) for t in normales]
        b = [x for x in b if x is not None]
        if not a or not b:
            continue
        ma = sum(a) / len(a)
        mb = sum(b) / len(b)
        a_s = sorted(a)
        b_s = sorted(b)
        print("   %2d min   |  media %.3f  med %.3f |  media %.3f  med %.3f | %.2fx"
              % (H, ma, a_s[len(a_s) // 2], mb, b_s[len(b_s) // 2],
                 (ma / mb) if mb else 0))

    # cuantas compresiones NO fueron seguidas de movimiento (falsos positivos)
    UMBRAL_MOV = 0.20
    a10 = [(t, mov_max(t, 10)) for t in comprimidos]
    a10 = [(t, v) for t, v in a10 if v is not None]
    ok = sum(1 for _, v in a10 if v >= UMBRAL_MOV)
    b10 = [(t, mov_max(t, 10)) for t in normales]
    b10 = [(t, v) for t, v in b10 if v is not None]
    okb = sum(1 for _, v in b10 if v >= UMBRAL_MOV)
    print()
    print("  movimiento >= %.2f en 10 min:" % UMBRAL_MOV)
    print("     tras COMPRESION : %d de %d = %.0f%%" % (ok, len(a10), ok / len(a10) * 100))
    print("     tras NORMAL     : %d de %d = %.0f%%" % (okb, len(b10), okb / len(b10) * 100))
    print("     -> FALSOS POSITIVOS de la compresion: %d de %d = %.0f%%"
          % (len(a10) - ok, len(a10), (len(a10) - ok) / len(a10) * 100))

print("\n" + "=" * 74)
print("LOS 10 MINUTOS MAS COMPRIMIDOS DEL DIA Y QUE PASO DESPUES")
print("=" * 74)
top = sorted(serie, key=lambda s: s["bb"])[:10]
print("  hora   bb_ancho%  SPY      mov_max_10min   funciono?")
for s in sorted(top, key=lambda x: x["h"]):
    mv = mov_max(s["t"], 10)
    print("  %s  %.4f  %7.2f      %s        %s"
          % (s["h"], s["bb"], s["spy"],
             ("%.2f" % mv) if mv is not None else " -  ",
             "SI" if (mv or 0) >= 0.20 else "no"))

print("\n" + "=" * 74)
print("AHORA MISMO")
print("=" * 74)
for s in serie[-8:]:
    print("  %s  bb_ancho=%.4f  atr=%.4f%%  SPY=%.2f" % (s["h"], s["bb"], s["atr"] or 0, s["spy"]))
