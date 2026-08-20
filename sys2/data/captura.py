# -*- coding: utf-8 -*-
"""CAPTURA minuto a minuto (keepUpToDate) + cadena de opciones con greeks REALES de IBKR.
Persiste en sys2.db: `bars` (SPY, fuente='live') y `premium` (cadena, fuente='live', con
day_vol + iv/delta/gamma/theta/vega reales). Esto ES el espejo backtest↔captura: guarda los
MISMOS campos con que se validó el backtest, pero desde IBKR (frontera de datos del usuario).

⚠️ Requiere IBKR. Se valida en paper. Logs exhaustivos.
"""
from sys2.db import repo
from sys2.vivo import log as L


def guardar_barra_spy(con, fecha, hora, o, hi, lo, cl, vol, vwap=None):
    """Persiste UNA barra de 1 min del SPY (fuente='live'). Idempotente por (fecha,hora)."""
    repo.insertar(con, "bars", [{"fecha": fecha, "hora": hora, "open": o, "high": hi,
                                 "low": lo, "close": cl, "volume": vol, "vwap": vwap,
                                 "fuente": "live"}])
    con.commit()


def guardar_cadena(con, fecha, hora, expiry, cadena):
    """Persiste la cadena capturada (dict {(right,strike): datos}) en `premium` (fuente='live').
    cadena viene de ibkr.IBKR.cadena() con greeks reales."""
    exp = expiry if len(expiry) == 8 else expiry.replace("-", "")   # normaliza a 'YYYYMMDD'
    filas = []
    for (right, strike), d in cadena.items():
        filas.append({
            "fecha": fecha, "hora": hora, "expiry": exp, "strike": strike, "right": right,
            "bid": d.get("bid"), "ask": d.get("ask"), "mid": d.get("mid"), "last": d.get("last"),
            "day_vol": d.get("day_vol"), "open_interest": d.get("oi"),
            "iv": d.get("iv"), "delta": d.get("delta"), "gamma": d.get("gamma"),
            "theta": d.get("theta"), "vega": d.get("vega"),
            "fuente": "live",
        })
    if filas:
        repo.insertar(con, "premium", filas)
        con.commit()
    L.log("cadena persistida %s %s: %d filas (fuente=live)" % (fecha, hora, len(filas)), "DATA")
    return len(filas)


def guardar_tape(con, fecha, ticks):
    """Persiste el tape del SUBYACENTE en `tape_und`. `ticks` viene de ibkr.tape_drenar():
    [(time, seq, price, size, exch, bid, ask, signo)].

    AÑADIDO 2026-08-20: la tabla existía desde el diseño pero nadie escribía en ella (0 filas
    verificadas en sys2.db y sus 7 copias) — seis sesiones de vivo sin capturar tape.

    `ts` se guarda como 'HH:MM:SS.mmm' (hora ET, con milisegundos) igual que hacía el sistema
    anterior en spy_history.tape. `seq` desempata dentro del mismo instante: sin él la PK
    descarta en silencio los trades idénticos del mismo segundo, y MEDIDO sobre el tape real
    del 2026-08-12 eso son 4.491 de 380.778 ticks (1,2%) — que además NO son aleatorios, son
    ejecuciones troceadas de órdenes grandes.
    """
    filas = []
    for t in ticks:
        try:
            ts, seq, px, sz, exch, bid, ask, sg = t
            hh = ts.strftime("%H:%M:%S.") + ("%03d" % (ts.microsecond // 1000)) \
                if hasattr(ts, "strftime") else str(ts)
            filas.append({"fecha": fecha, "ts": hh, "seq": seq, "price": px, "size": sz,
                          "exch": exch, "bid": bid, "ask": ask, "signo": sg})
        except Exception as ex:
            L.log("guardar_tape: tick descartado %r (%r)" % (t, ex), "WARN")
    if filas:
        repo.insertar(con, "tape_und", filas)
        con.commit()
    return len(filas)


def bars_de_bd(con, fecha):
    """Lee las barras 1-min del día (desde 04:00) como [(hora,high,low,close)] para el núcleo."""
    return [(h, hi, lo, cl) for h, hi, lo, cl in con.execute(
        "select hora,high,low,close from bars where fecha=? order by hora", (fecha,))]


def premium_minuto(con, fecha, hora, expiry):
    """Cadena de un minuto como {(right,strike): (mid, day_vol)} — formato PM del motor."""
    exp = expiry if len(expiry) == 8 else expiry.replace("-", "")
    out = {}
    for r, k, mid, dv in con.execute(
            "select right,strike,mid,day_vol from premium where fecha=? and hora=? and expiry=?",
            (fecha, hora, exp)):
        if mid is not None:
            out[(r, k)] = (mid, dv or 0.0)
    return out
