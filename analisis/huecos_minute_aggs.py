# -*- coding: utf-8 -*-
"""¿CUANTAS operaciones caen en un minuto SIN barra en los minute_aggs?

EL PROBLEMA, planteado por el agente de investigacion: los minute_aggs solo traen minutos en
los que hubo alguna operacion en ESE contrato. Se observaron ~343 barras de 390 posibles, o sea
un 12% de minutos vacios, y los huecos NO son aleatorios: se concentran en contratos poco
liquidos y en los tramos tranquilos del dia.

Si el backtest necesita el precio en el minuto EXACTO de entrada o de salida y no hay barra,
cada salida cambia el resultado:
    saltar la operacion  -> se filtra por liquidez sin querer, sesga hacia contratos activos
    usar la barra previa -> precio obsoleto, puede ser de varios minutos antes
    interpolar           -> se inventa un precio que nadie pago
Por eso hay que MEDIR el porcentaje antes de interpretar el resultado final: si es el 2%, da
igual; si es el 15%, el numero no es interpretable sin decidir antes que hacer con esos casos.

Cruza las operaciones del plan (massive_plan_contratos.json, que sale del backtest real) con
las barras realmente descargadas en massive_premium.db.
"""
import json
import os
import sqlite3
import statistics as st
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
ET = ZoneInfo("America/New_York")


def hora_et(ms):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone(ET).strftime("%H:%M")


def main():
    mp = os.path.join(RAIZ, "massive_premium.db")
    pl = os.path.join(RAIZ, "massive_plan_contratos.json")
    if not (os.path.exists(mp) and os.path.exists(pl)):
        print("faltan massive_premium.db o massive_plan_contratos.json"); return 1
    with open(pl, encoding="utf-8") as f:
        plan = json.load(f)
    c = sqlite3.connect("file:%s?mode=ro" % mp.replace("\\", "/"), uri=True, timeout=20)
    bajados = {r[0] for r in c.execute("select ticker from hechos where estado='OK'")}

    ops = [p for p in plan if p["ticker"] in bajados]
    if not ops:
        print("todavia no hay contratos descargados que cruzar"); return 0

    print("=" * 80)
    print("HUECOS EN LOS MINUTE_AGGS  (%d contratos descargados de %d del plan)"
          % (len(bajados), len(plan)))
    print("=" * 80)

    sin_ent = sin_sal = tot = 0
    cobertura = []
    ejemplos = []
    for p in ops:
        minutos = {hora_et(r[0]) for r in c.execute(
            "select ts from aggs where ticker=?", (p["ticker"],))}
        if not minutos:
            continue
        cobertura.append(len(minutos))
        e = (p.get("entrada") or "")[:5]
        s = (p.get("salida") or "")[:5]
        tot += 1
        fe = e and e not in minutos
        fs = s and s not in minutos
        if fe:
            sin_ent += 1
        if fs:
            sin_sal += 1
        if (fe or fs) and len(ejemplos) < 6:
            ejemplos.append((p["fecha"], p["ticker"], e, s,
                             "ENTRADA" if fe else "", "SALIDA" if fs else ""))

    print("\n  operaciones evaluadas          : %d" % tot)
    print("  barras por contrato (mediana)  : %d de ~390 minutos RTH" % st.median(cobertura))
    print("  cobertura mediana              : %.0f%%" % (100.0 * st.median(cobertura) / 390))
    print("\n  minuto de ENTRADA sin barra    : %d  (%.1f%%)" % (sin_ent, 100.0 * sin_ent / tot))
    print("  minuto de SALIDA  sin barra    : %d  (%.1f%%)" % (sin_sal, 100.0 * sin_sal / tot))
    afect = sum(1 for p in ops
                if True) and (sin_ent + sin_sal)
    print("  operaciones afectadas (aprox)  : %.1f%% de los extremos"
          % (100.0 * (sin_ent + sin_sal) / (2.0 * tot)))

    if ejemplos:
        print("\n  ejemplos:")
        for f, t, e, s, me, ms in ejemplos:
            print("    %s %-22s entrada=%s salida=%s  falta: %s %s" % (f, t, e, s, me, ms))

    pct = 100.0 * (sin_ent + sin_sal) / (2.0 * tot)
    print("\n" + "=" * 80)
    print("VEREDICTO")
    print("=" * 80)
    if pct < 3:
        print("  %.1f%% -> DESPRECIABLE. Se puede usar la barra mas cercana sin que mueva el" % pct)
        print("  resultado, pero hay que DECIRLO igualmente al publicar el numero.")
    elif pct < 10:
        print("  %.1f%% -> MODERADO. Hay que fijar una regla explicita (barra previa dentro de" % pct)
        print("  N minutos, y si no, descartar la operacion) y reportar cuantas se descartan.")
    else:
        print("  %.1f%% -> ALTO. El resultado NO es interpretable sin decidir antes que hacer" % pct)
        print("  con estos casos: saltarlos sesga hacia contratos liquidos.")
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
