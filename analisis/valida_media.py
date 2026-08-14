# -*- coding: utf-8 -*-
"""VALIDACION DE LA SEÑAL DE LA MEDIA SOBRE EL HISTORICO (read-only)

Contesta la pregunta que decide el proyecto: el 53.2% de acierto medido en 3 sesiones,
sobre cientos de sesiones, se sostiene o converge a 50%.

NO necesita precios de opciones: la señal se calcula solo con el SPY.

Uso:
    python analisis/valida_media.py                 # umbral 0.20, horizonte 8
    python analisis/valida_media.py 0.20 8
La salida completa se escribe a investigacion/validacion_media_historico.txt
"""
import os
import random
import sqlite3
import statistics as st
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = "historico_spy.db"
UMBRAL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.20
HORIZ = int(sys.argv[2]) if len(sys.argv) > 2 else 8
RETRASO = 1          # el TA de la vela X se conoce en X+1. Con 0 es look-ahead (+29%).
SALIDA = os.path.join("investigacion", "validacion_media_historico.txt")

OUT = []
def p(s=""):
    print(s)
    OUT.append(s)

def mm(h):
    return int(h[:2]) * 60 + int(h[3:5])

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dias = {}
    for f, h, o, hi, lo, cl, v in c.execute(
            "select fecha,hora,open,high,low,close,volume from bars_historico order by fecha,hora"):
        dias.setdefault(f, []).append((h, o, hi, lo, cl, v))
    c.close()
    return dias

def señal_dia(barras):
    """Devuelve [(hora, close, media, dist)] con media = SMA(5) del precio tipico.
    OJO: en ta_minute esta columna se llama 'vwap' pero NO lleva volumen."""
    out = []
    tp = []
    for h, o, hi, lo, cl, v in barras:
        tp.append((hi + lo + cl) / 3.0)
        med = sum(tp[-5:]) / min(5, len(tp))
        out.append((h, cl, med, cl - med))
    return out

def operaciones(serie):
    """Entradas NO solapadas: la siguiente solo tras cerrar la anterior."""
    horas = [x[0] for x in serie]
    idx = {h: i for i, h in enumerate(horas)}
    ops = []
    i = 0
    while i < len(serie):
        h = horas[i]
        if h >= "15:40":
            break
        j = i - RETRASO
        if j < 0:
            i += 1
            continue
        dd = serie[j][3]
        if abs(dd) < UMBRAL:
            i += 1
            continue
        lado = "P" if dd > 0 else "C"          # ARRIBA -> PUT ; ABAJO -> CALL
        fin = [k for k in range(i, len(serie)) if mm(horas[k]) >= mm(h) + HORIZ]
        if not fin:
            break
        k = fin[0]
        ds = serie[k][1] - serie[i][1]
        fav = ds if lado == "C" else -ds
        ops.append((h, horas[k], lado, ds, fav))
        i = k
    return ops

def resumen(ops, etiqueta):
    if not ops:
        p(f"  {etiqueta}: sin operaciones")
        return None
    ok = sum(1 for x in ops if x[4] > 0)
    n = len(ops)
    fa = [x[4] for x in ops if x[4] > 0]
    fc = [-x[4] for x in ops if x[4] <= 0]
    ma = st.mean(fa) if fa else 0.0
    mc = st.mean(fc) if fc else 0.0
    asim = ma / mc if mc else float("inf")
    p(f"  {etiqueta}: acierto {ok}/{n} = {100*ok/n:5.2f}%  |  "
      f"a favor {ma:+.3f}  en contra {-mc:+.3f}  |  ASIMETRIA {asim:.2f}")
    return ok, n, asim

def control_azar(ops, ok, reps=2000, semilla=7):
    rnd = random.Random(semilla)
    n = len(ops)
    sup = 0
    for _ in range(reps):
        a = sum(1 for x in ops if (x[3] > 0 if rnd.random() < 0.5 else x[3] < 0))
        if a >= ok:
            sup += 1
    return sup / reps

def main():
    global UMBRAL, HORIZ
    dias = carga()
    p("=" * 84)
    p(f"VALIDACION DE LA SEÑAL DE LA MEDIA   umbral={UMBRAL}  horizonte={HORIZ} min  retraso={RETRASO}")
    p(f"sesiones cargadas: {len(dias)}   ({min(dias)} a {max(dias)})")
    p("=" * 84)

    todas = []
    por_dia = []
    for f in sorted(dias):
        b = dias[f]
        if len(b) < 100:
            continue
        ops = operaciones(señal_dia(b))
        if not ops:
            continue
        ok = sum(1 for x in ops if x[4] > 0)
        por_dia.append((f, ok, len(ops)))
        todas.extend(ops)

    p("\n--- AGREGADO ---")
    r = resumen(todas, "TODAS las sesiones")
    if not r:
        return
    ok, n, asim = r
    pv = control_azar(todas, ok)
    p(f"  control de azar (misma cantidad de entradas, direccion al azar): p = {pv:.4f}")
    p(f"  PUNTO DE EQUILIBRIO: con asimetria {asim:.2f} hace falta acertar "
      f"{100/(1+asim):5.2f}%  ->  {'GANA' if 100*ok/n > 100/(1+asim) else 'PIERDE'}")

    p("\n--- ESTABILIDAD POR SESION ---")
    tasas = [100 * a / b for _, a, b in por_dia if b >= 5]
    if tasas:
        p(f"  sesiones con >=5 ops: {len(tasas)}")
        p(f"  acierto por sesion: mediana {st.median(tasas):.1f}%  "
          f"media {st.mean(tasas):.1f}%  min {min(tasas):.1f}%  max {max(tasas):.1f}%")
        p(f"  sesiones por encima del 55%: {sum(1 for t in tasas if t>55)}/{len(tasas)} "
          f"= {100*sum(1 for t in tasas if t>55)/len(tasas):.0f}%")

    p("\n--- POR FRANJA HORARIA ---")
    for nom, a, b in (("09:30-11:00", 570, 660), ("11:00-12:30", 660, 750),
                      ("12:30-14:00", 750, 840), ("14:00-15:40", 840, 940)):
        sub = [x for x in todas if a <= mm(x[0]) < b]
        resumen(sub, nom)

    p("\n--- REJILLA umbral x horizonte (acierto %) ---")
    p("  LEE LA REGION, NUNCA LA CELDA MAXIMA")
    u0, h0 = UMBRAL, HORIZ
    cab = "  " + "umbral".rjust(8) + "".join(f"{w:>12}" for w in (5, 8, 12, 20, 30))
    p(cab)
    for u in (0.12, 0.16, 0.20, 0.24, 0.28, 0.32):
        fila = f"  {u:>8.2f}"
        for w in (5, 8, 12, 20, 30):
            UMBRAL, HORIZ = u, w
            t = []
            for f in sorted(dias):
                if len(dias[f]) < 100:
                    continue
                t.extend(operaciones(señal_dia(dias[f])))
            if t:
                fila += f"{100*sum(1 for x in t if x[4]>0)/len(t):11.1f}%"
            else:
                fila += f"{'-':>12}"
        p(fila)
    UMBRAL, HORIZ = u0, h0

    p("\n" + "=" * 84)
    p("COMO LEERLO:")
    p("  acierto ~50%          -> la señal no tiene nada. Linea cerrada.")
    p("  53-55% estable        -> hay algo pero por debajo del equilibrio: atacar la asimetria")
    p("  >=57% estable         -> es real. Entonces si merece comprar datos de opciones.")
    p("=" * 84)

    os.makedirs("investigacion", exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print(f"\nsalida completa en: {os.path.abspath(SALIDA)}")

if __name__ == "__main__":
    main()
