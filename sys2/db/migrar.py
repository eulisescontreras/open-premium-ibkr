# -*- coding: utf-8 -*-
"""Migracion: rescata TODA la data del sistema anterior a la BD nueva (sys2.db).
Decision del usuario: no perder nada, por minima que sea la data.
Idempotente (INSERT OR REPLACE por PK). Cada funcion informa filas migradas.

Fuentes verificadas (R5, columnas reales):
  spy_bars_year.db / year2 : bars(fecha,hora,open,high,low,close,volume,wap)
  dia_/tlt_bars_year*.db   : idem  -> bars_etf
  spy_history*.db          : trades, bars_minute, premium_minute (gamma+day_vol, sin delta/iv)
  massive_premium.db       : aggs(ticker,fecha,ts,ohlc,volume,vwap)  [greeks por BS -> paso aparte]

NO cubre aqui: premium historica masiva con greeks Black-Scholes (massive_premium.aggs).
Eso va en migrar_premium_bs.py (costoso: 2.6M filas, requiere greeks.py + spot/min).
OBLIGATORIO: antes de modificar, leer el plan aprobado.
"""
import os
import sqlite3
import glob

from sys2.db import repo

RAIZ = repo.RAIZ


def _ro(db):
    return sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)


def _existe(db):
    return os.path.exists(os.path.join(RAIZ, db))


def migrar_bars(con):
    """SPY 1-min: 2 anos backtest (wap->vwap) + los pocos dias live (sin vwap)."""
    total = 0
    for db in ("spy_bars_year2.db", "spy_bars_year.db"):   # year2 (anterior) primero
        p = os.path.join(RAIZ, db)
        if not os.path.exists(p):
            continue
        src = _ro(p)
        filas = [dict(fecha=f, hora=h, open=o, high=hi, low=lo, close=cl,
                      volume=v, vwap=w, fuente="hist")
                 for f, h, o, hi, lo, cl, v, w in
                 src.execute("select fecha,hora,open,high,low,close,volume,wap from bars")]
        src.close()
        n = repo.insertar(con, "bars", filas)
        repo.log_migracion(con, db + ":bars", "bars", n)
        total += n
    # dias live (spy_history*.bars_minute) — sin vwap
    for p in sorted(glob.glob(os.path.join(RAIZ, "spy_history*.db"))):
        src = _ro(p)
        try:
            rows = list(src.execute(
                "select fecha,hora,open,high,low,close,volume from bars_minute"))
        except sqlite3.OperationalError:
            rows = []
        src.close()
        filas = [dict(fecha=f, hora=h, open=o, high=hi, low=lo, close=cl,
                      volume=v, vwap=None, fuente="live") for f, h, o, hi, lo, cl, v in rows]
        # NO pisar barras 'hist' con live vacio: solo insertar OR IGNORE aqui
        n = repo.insertar(con, "bars", filas, reemplaza=False)
        if n:
            repo.log_migracion(con, os.path.basename(p) + ":bars_minute", "bars", n)
        total += n
    con.commit()
    return total


def migrar_bars_etf(con):
    """DIA y TLT (regla 5). Solo close por minuto."""
    total = 0
    for ticker, patron in (("DIA", "dia_bars_year*.db"), ("TLT", "tlt_bars_year*.db")):
        for p in sorted(glob.glob(os.path.join(RAIZ, patron))):
            src = _ro(p)
            try:
                rows = list(src.execute("select fecha,hora,close from bars"))
            except sqlite3.OperationalError:
                rows = []
            src.close()
            filas = [dict(ticker=ticker, fecha=f, hora=h, close=cl) for f, h, cl in rows]
            n = repo.insertar(con, "bars_etf", filas)
            if n:
                repo.log_migracion(con, os.path.basename(p), "bars_etf", n)
            total += n
    con.commit()
    return total


def derivar_dia_anterior(con):
    """dia_anterior = cierre/max/min RTH (09:30-16:00) de CADA fecha en bars.
    ayer_rev/gap_fade consultaran la fecha del dia habil previo."""
    q = ("select fecha, max(high), min(low), "
         "(select close from bars b2 where b2.fecha=b1.fecha and b2.hora<='16:00' "
         " order by b2.hora desc limit 1) "
         "from bars b1 where hora>='09:30' and hora<='16:00' group by fecha")
    filas = [dict(fecha=f, maximo=mx, minimo=mn, cierre=cl)
             for f, mx, mn, cl in con.execute(q)]
    n = repo.insertar(con, "dia_anterior", filas)
    repo.log_migracion(con, "bars(agg)", "dia_anterior", n)
    con.commit()
    return n


def migrar_operaciones(con):
    """spy_history*.trades -> operaciones (mapeo directo de las columnas disponibles)."""
    total = 0
    for p in sorted(glob.glob(os.path.join(RAIZ, "spy_history*.db"))):
        src = _ro(p)
        try:
            rows = list(src.execute(
                "select fecha,side,right,strike,qty,hora_entrada,spy_entrada,entry_price,"
                "delta_entrada,iv_entrada,hora_salida,spy_salida,exit_price,razon_salida,"
                "segundos,profit,comision,mfe,mae from trades"))
        except sqlite3.OperationalError:
            rows = []
        src.close()
        filas = []
        for (fecha, side, right, strike, qty, he, spe, ep, de, ie, hs, sps, xp,
             rs, seg, prof, com, mfe, mae) in rows:
            filas.append(dict(
                fecha=fecha, senal_id=None, n_op_dia=None, tipo="single",
                right=right, strike_largo=strike, strike_corto=None, ancho=None,
                qty=qty, nivel=None, modo="legacy", tope=None, unidades=1,
                hora_entrada=he, spy_entrada=spe, precio_largo_pagado=ep,
                precio_corto_cobrado=None, debito_neto=ep,
                bid_largo=None, ask_largo=None, bid_corto=None, ask_corto=None,
                delta_entrada=de, iv_entrada=ie, moneyness=None,
                hora_salida=hs, spy_salida=sps, precio_largo_venta=xp,
                precio_corto_recompra=None, credito_neto=xp,
                razon_salida=rs, duracion_min=(seg // 60 if seg else None),
                pnl=prof, comision=com, mfe=mfe, mae=mae))
        n = repo.insertar(con, "operaciones", filas, reemplaza=False)
        if n:
            repo.log_migracion(con, os.path.basename(p) + ":trades", "operaciones", n)
        total += n
    con.commit()
    return total


def migrar_premium_live(con):
    """spy_history*.premium_minute -> premium (fuente='live'). gamma+day_vol reales;
    delta/theta/vega/iv NO existen en esa tabla -> quedan NULL (se calculan por BS si hace falta)."""
    total = 0
    for p in sorted(glob.glob(os.path.join(RAIZ, "spy_history*.db"))):
        src = _ro(p)
        try:
            rows = list(src.execute(
                "select fecha,hora,expiry,strike,right,bid,ask,mid,last,day_vol,"
                "open_interest,gamma from premium_minute"))
        except sqlite3.OperationalError:
            rows = []
        src.close()
        filas = [dict(fecha=f, hora=h, expiry=e, strike=k, right=r, bid=b, ask=a,
                      mid=m, last=l, day_vol=dv, open_interest=oi, iv=None,
                      delta=None, gamma=g, theta=None, vega=None, fuente="live")
                 for f, h, e, k, r, b, a, m, l, dv, oi, g in rows]
        n = repo.insertar(con, "premium", filas)
        if n:
            repo.log_migracion(con, os.path.basename(p) + ":premium_minute", "premium", n)
        total += n
    con.commit()
    return total


def migrar_todo(con):
    return {
        "bars": migrar_bars(con),
        "bars_etf": migrar_bars_etf(con),
        "dia_anterior": derivar_dia_anterior(con),
        "operaciones": migrar_operaciones(con),
        "premium_live": migrar_premium_live(con),
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    c = repo.abrir()
    res = migrar_todo(c)
    print("Migracion completada:")
    for k, v in res.items():
        print("  %-14s %d filas" % (k, v))
    for t in ("bars", "bars_etf", "dia_anterior", "operaciones", "premium"):
        print("  total %-12s %d" % (t, repo.contar(c, t)))
    c.close()
