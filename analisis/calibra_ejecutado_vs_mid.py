# -*- coding: utf-8 -*-
"""¿DONDE cae el precio EJECUTADO respecto al bid/ask real? (riesgo de contar el spread 2 veces)

EL PROBLEMA, que planteo el agente de investigacion: los minute_aggs de Massive son precios de
OPERACIONES EJECUTADAS. Una operacion ocurre en el bid o en el ask, no en el mid. Si el cierre
de la vela ya viene sesgado hacia un lado y encima se le aplica el +-1% de `build_tmp`, se cobra
el spread ENCIMA de un precio que ya lo lleva dentro. Eso inflaria el coste y haria que el
premium real pareciera PEOR de lo que es, justo al reves del sesgo que buscamos.

COMO SE MIDE: hay 4 dias (2026-08-11..14) con bid/ask REAL guardado en `premium_minute` por la
app. Para los contratos que tambien estan en massive_premium.db, se compara minuto a minuto:

    close del minute_agg   vs   (bid+ask)/2 del mismo minuto y contrato

posicion = (close - bid) / (ask - bid)
    0.5 -> el ejecutado cae en el MID  -> aplicar +-1% es correcto
    ~1  -> pegado al ASK               -> aplicar el spread encima lo cuenta dos veces
    ~0  -> pegado al BID

OJO CON LA HORA: Massive da el timestamp en ms UTC; la app guarda hora ET. Se convierte.
"""
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
DIAS = ["2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]


def ro(p):
    return sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True, timeout=20)


def hora_et(ms):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone(ET).strftime("%H:%M")


def main():
    mp = os.path.join(RAIZ, "massive_premium.db")
    if not os.path.exists(mp):
        print("no existe massive_premium.db"); return 1
    m = ro(mp)

    print("=" * 84)
    print("PRECIO EJECUTADO (Massive) vs BID/ASK REAL (la app)")
    print("=" * 84)

    total = []
    por_dia = {}
    for fk in DIAS:
        db = os.path.join(RAIZ, "spy_history_%s.db" % fk.replace("-", ""))
        if not os.path.exists(db):
            continue
        # contratos de ese dia que tenemos en Massive
        ticks = [r[0] for r in m.execute("select ticker from hechos where fecha=? and estado='OK'",
                                         (fk,))]
        if not ticks:
            continue
        a = ro(db)
        pares = []
        for t in ticks:
            # O:SPY YYMMDD C 00778000  -> strike y right
            right = t[11]
            strike = int(t[12:]) / 1000.0
            # bid/ask reales por minuto
            reales = {h: (b, k) for h, b, k in a.execute(
                "select hora,bid,ask from premium_minute where fecha=? and expiry=? and right=? "
                "and strike=? and bid is not null and ask is not null and ask>bid",
                (fk, fk.replace("-", ""), right, strike))}
            if not reales:
                continue
            for ts, cl in m.execute("select ts,close from aggs where ticker=? and close is not null",
                                    (t,)):
                h = hora_et(ts)
                if h in reales:
                    b, k = reales[h]
                    if k > b:
                        pares.append((cl - b) / (k - b))
        if pares:
            por_dia[fk] = pares
            total.extend(pares)
        a.close()

    if not total:
        print("\nTodavia no hay solapamiento entre Massive y los dias con bid/ask real.")
        print("La descarga va del 2026-08-13 hacia atras; en cuanto cubra 08-11/12/13")
        print("esta comparacion tendra datos. Volver a correrlo entonces.")
        m.close()
        return 0

    print("\n  %-12s %8s %9s %9s %9s %9s" % ("dia", "n", "mediana", "media", "p10", "p90"))
    print("  " + "-" * 62)
    for fk in sorted(por_dia):
        v = sorted(por_dia[fk])
        n = len(v)
        print("  %-12s %8d %9.2f %9.2f %9.2f %9.2f"
              % (fk, n, st.median(v), st.mean(v), v[int(0.1 * (n - 1))], v[int(0.9 * (n - 1))]))
    v = sorted(total)
    n = len(v)
    print("  " + "-" * 62)
    print("  %-12s %8d %9.2f %9.2f %9.2f %9.2f"
          % ("TOTAL", n, st.median(v), st.mean(v), v[int(0.1 * (n - 1))], v[int(0.9 * (n - 1))]))

    med = st.median(v)
    print("\n" + "=" * 84)
    print("LECTURA  (0 = pegado al BID, 0.5 = MID, 1 = pegado al ASK)")
    print("=" * 84)
    print("  mediana de la posicion: %.3f" % med)
    if 0.40 <= med <= 0.60:
        print("  -> El precio ejecutado cae cerca del MID.")
        print("     APLICAR el +-1% de build_tmp es CORRECTO: el agregado no lleva spread dentro.")
    elif med > 0.60:
        print("  -> El precio ejecutado esta sesgado hacia el ASK (%.0f%% del camino)." % (med * 100))
        print("     Aplicar el spread encima lo cuenta DOS VECES en las compras.")
        print("     Ajuste sugerido: usar el agregado tal cual como precio de COMPRA.")
    else:
        print("  -> El precio ejecutado esta sesgado hacia el BID (%.0f%%)." % (med * 100))
        print("     Aplicar el spread encima lo cuenta DOS VECES en las ventas.")
    fuera = sum(1 for x in v if x < 0 or x > 1)
    print("\n  fuera del rango [bid, ask]: %d de %d (%.1f%%)  <- operaciones fuera del spread"
          % (fuera, n, 100.0 * fuera / n))
    m.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
