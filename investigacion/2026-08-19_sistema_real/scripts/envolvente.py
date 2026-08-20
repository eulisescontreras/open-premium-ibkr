# -*- coding: utf-8 -*-
# ENVOLVENTE — superficie de percentiles del EXTRÍNSECO. Test de robustez a regímenes de precios.
#
# QUÉ ES (descrito por el agente del motor original, reconstruido aquí): NO son datos nuevos ni
# más histórico — son las MISMAS 485 sesiones. Para cada barra de opción calcula
#     extrínseco_normalizado = (precio - intrínseco) / rango_del_día
# y lo agrupa en celdas (moneyness, minutos_a_vencimiento, C/P) guardando los percentiles
# 10/25/50/75/90. Luego se sustituyen los precios reales por los del percentil N y se re-corre
# el sistema: da cómo rendiría con las MISMAS señales pero con las opciones más caras o más
# baratas de lo que realmente estuvieron.
#
# ⚠️ AVISO CRÍTICO DEL AGENTE ORIGINAL: su primera versión MEZCLABA CALLS Y PUTS en la misma
# celda y daba -37.332$ en el p90. Separándolos da +34.054$. Estuvo tres sesiones marcado como
# "el riesgo principal del sistema" y era un ARTEFACTO. Aquí se separan desde el principio.
#
# POR QUÉ IMPORTA: es donde la composición al 18% se rompía en sus pruebas (al 2% de coste moría
# en 4 de 6 regímenes). Si la compresión sube el drawdown, es aquí donde puede hacer daño.
import sqlite3, sys, os, json, math

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2.backtest import greeks as G
from sys2.core.supertrend import mm
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
MASSIVE = os.path.join(RAIZ, "massive_premium.db")
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resultados",
                      "envolvente.json")
PCTS = (10, 25, 50, 75, 90)


def celda(mny, minutos):
    """(moneyness redondeado, tramo de minutos a vencimiento). Granularidad suficiente para
    tener muestras en cada celda sin diluir la estructura."""
    m = max(-10, min(10, int(round(mny))))
    t = min(6, int(minutos // 60))          # tramos de 1 hora hasta el cierre
    return (m, t)


def construir():
    mv = sqlite3.connect(MASSIVE)
    con = sqlite3.connect(os.path.join(RAIZ, "sys2.db"))
    # rango del día del SPY (denominador de la normalización)
    rangos = {}
    for f, hi, lo in con.execute(
            "select fecha, max(high), min(low) from bars where hora>='09:30' and hora<='16:00' "
            "group by fecha"):
        if hi and lo and hi > lo:
            rangos[f] = hi - lo
    # spot por (fecha,hora)
    spot = {}
    for f, h, cl in con.execute(
            "select fecha,hora,close from bars where hora>='09:30' and hora<='16:00'"):
        spot[(f, h)] = cl
    con.close()

    acum = {}
    n = 0
    for tk, fecha, ts, close in mv.execute("select ticker,fecha,ts,close from aggs"):
        p = G.parse_occ(tk)
        if p is None or p[0] != fecha:
            continue
        _, right, strike = p
        rango = rangos.get(fecha)
        if not rango:
            continue
        hora = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).astimezone(_ET).strftime("%H:%M")
        S = spot.get((fecha, hora))
        if S is None or close is None or close <= 0:
            continue
        intr = max(0.0, (S - strike) if right == "C" else (strike - S))
        ext = (close - intr) / rango
        if ext < -0.5 or ext > 5:            # descartar precios imposibles
            continue
        mny = (S - strike) if right == "C" else (strike - S)
        minutos = max(0, 960 - mm(hora))
        # ⚠️ el `right` va DENTRO de la clave: mezclar calls y puts fue el artefacto de -37.332$
        acum.setdefault((right,) + celda(mny, minutos), []).append(ext)
        n += 1
    mv.close()

    tabla = {}
    for k, v in acum.items():
        if len(v) < 30:
            continue
        v.sort()
        tabla["%s|%d|%d" % k] = {str(p): v[min(len(v) - 1, int(len(v) * p / 100.0))] for p in PCTS}
    json.dump({"tabla": tabla, "rangos": rangos}, open(SALIDA, "w"))
    print("ENVOLVENTE construida: %d celdas, %d observaciones" % (len(tabla), n))
    print("guardada en %s" % SALIDA)
    # cobertura por percentil (comprobación de cordura)
    for p in PCTS:
        vs = [c[str(p)] for c in tabla.values()]
        vs.sort()
        print("  p%-3d  extrinseco/rango:  min %.4f  mediana %.4f  max %.4f"
              % (p, vs[0], vs[len(vs) // 2], vs[-1]))
    # y separado por lado, para ver que NO son iguales (si lo fueran, separar no serviría)
    for r in ("C", "P"):
        vs = [c["50"] for k, c in tabla.items() if k.startswith(r)]
        if vs:
            vs.sort()
            print("  %s  p50 mediano: %.4f  (n=%d celdas)" % (r, vs[len(vs) // 2], len(vs)))


if __name__ == "__main__":
    construir()
