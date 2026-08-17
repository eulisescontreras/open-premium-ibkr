# -*- coding: utf-8 -*-
"""BACKFILL de arranque (restricción del usuario: el sistema no está activo desde las 4am).
Al arrancar (a la hora que sea) trae DE GOLPE: (1) barras SPY 1-min con premarket desde las
04:00 (reqHistoricalData useRTH=False "2 D"), (2) DIA/TLT 09:25-10:05, (3) día anterior.
Persiste TODO en sys2.db (bars fuente='backfill', bars_etf, dia_anterior). Idempotente.

⚠️ Requiere IBKR (data/ibkr.py). Se valida en paper. Logs exhaustivos.
"""
from sys2 import config as C
from sys2.db import repo
from sys2.vivo import log as L


def _hora(bar):
    """BarData.date -> 'HH:MM' (ib_insync entrega hora local de la cuenta, ET con formatDate=1)."""
    d = bar.date
    if hasattr(d, "strftime"):
        return d.strftime("%H:%M")
    return str(d)[11:16]


def _fecha(bar):
    d = bar.date
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def backfill(ibkr, con, fecha_hoy):
    """Corre el backfill completo para la sesión `fecha_hoy` ('YYYY-MM-DD'). Devuelve nº de barras SPY."""
    L.notificar("BACKFILL de arranque (SPY premarket + ETF + día anterior)", "ARRANQUE")

    # 1) SPY 1-min con premarket (desde las 04:00 del día de hoy queda cubierto por "2 D")
    bars = ibkr.backfill_spy(dur=C.BACKFILL_DUR, bar="1 min")
    filas = []
    for b in bars:
        fk = _fecha(b)
        h = _hora(b)
        # HOY + la sesión ANTERIOR: `repo.prev_sesion` (ayer_rev/gap_fade) necesita los CIERRES
        # del RTH de ayer, y ya vienen en este mismo "2 D" -> no hace falta otra llamada a IBKR.
        if fk > fecha_hoy:
            continue
        if h < "04:00" or h > "16:00":
            continue
        filas.append({"fecha": fk, "hora": h, "open": b.open, "high": b.high,
                      "low": b.low, "close": b.close, "volume": b.volume,
                      "vwap": getattr(b, "average", None), "fuente": "backfill"})
    if filas:
        repo.insertar(con, "bars", filas)
        con.commit()
    L.log("backfill SPY: %d barras persistidas (fecha %s)" % (len(filas), fecha_hoy), "DATA")

    # 2) DIA / TLT (para la regla del día bueno)
    for tk in C.ETFS:
        try:
            eb = ibkr.backfill_etf(tk, dur="1 D", bar="1 min")
            fetf = [{"ticker": tk, "fecha": _fecha(b), "hora": _hora(b), "close": b.close}
                    for b in eb if _fecha(b) == fecha_hoy and "09:25" <= _hora(b) <= "10:05"]
            if fetf:
                repo.insertar(con, "bars_etf", fetf)
                con.commit()
            L.log("backfill %s: %d barras" % (tk, len(fetf)), "DATA")
        except Exception as ex:
            L.log("backfill ETF %s: %r" % (tk, ex), "WARN")

    # 3) día anterior -> gap_fade / ayer_rev.
    # Se DERIVA de las barras de 1 min que acabamos de guardar (max/min de los CIERRES del RTH),
    # que es la definición del motor (motor.py:255-256). NO se usa ibkr.dia_anterior_spy(): esa
    # devuelve el high/low de la barra DIARIA (rango más ancho -> menos señales que el backtest)
    # y además, arrancando en premarket, devolvía ANTEAYER (bars[-2] sobre una serie sin hoy).
    # Semántica de la tabla = la de schema.sql:21: `fecha` es la fecha CUYOS valores se guardan.
    try:
        mx, mn, cl = repo.prev_sesion(con, fecha_hoy)
        if mx is not None:
            f_prev = con.execute(
                "select max(fecha) from bars where fecha < ? and hora >= '09:30' and hora <= '16:00'",
                (fecha_hoy,)).fetchone()[0]
            repo.insertar(con, "dia_anterior",
                          [{"fecha": f_prev, "cierre": cl, "maximo": mx, "minimo": mn}])
            con.commit()
            L.log("día anterior (%s, cierres RTH): cierre=%.2f máx=%.2f mín=%.2f"
                  % (f_prev, cl, mx, mn), "DATA")
        else:
            L.log("día anterior: sin barras RTH de una sesión previa en la BD", "WARN")
    except Exception as ex:
        L.log("día anterior: %r" % ex, "WARN")

    return len(filas)
