# -*- coding: utf-8 -*-
"""RECONSTRUYE ta_minute HISTORICO reusando el TA REAL del bot (TAEngine.compute).

NO reimplementa el TA (Regla 9): importa TAEngine de spy_direction.py y lo alimenta
igual que en produccion -> ventana EXPANSIVA intradia (desde 09:30 hasta el minuto t),
una sesion a la vez, exactamente como corre la app en vivo.

Fuente:  historico_spy.db / bars_historico   (las 255 sesiones ya validadas)
Destino: historico_spy.db / ta_historico     (tabla NUEVA, no toca nada de produccion)

Uso:
    python analisis/reconstruye_ta.py validar   # solo 08-11 y 08-12, compara vs prod ta_minute
    python analisis/reconstruye_ta.py           # reconstruye las 255 sesiones a ta_historico
"""
import os
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd

# --- reuso del TA REAL del bot (Regla 9: conectar, no duplicar) ---
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz del repo
_default_excepthook = sys.excepthook
from spy_direction import TAEngine
sys.excepthook = _default_excepthook   # spy_direction pisa el excepthook; lo devuelvo (no contaminar spy_direction.log)

DB = "historico_spy.db"
ENGINE = TAEngine()

# columnas que devuelve TAEngine.compute() y que persistimos
CAMPOS = ["close", "rsi", "ema8", "ema21", "ema50", "sma20", "sma50", "sma200",
          "macd_line", "macd_signal", "macd_hist", "bb_up", "bb_mid", "bb_low",
          "atr", "atr_pct", "vwap", "obv_trend", "score", "dir", "bull", "bear"]


def carga_sesiones(con):
    dias = {}
    for f, h, o, hi, lo, cl, v in con.execute(
            "select fecha,hora,open,high,low,close,volume from bars_historico order by fecha,hora"):
        dias.setdefault(f, []).append((h, o, hi, lo, cl, v))
    return dias


def ta_de_sesion(barras, prev_barras=None):
    """Devuelve [(hora, dict_ta)] calculando el TA REAL sobre ventana expansiva.
    Si prev_barras (la sesion anterior) se pasa, se antepone como WARMUP para sembrar
    las EMAs igual que prod (BARS_DURATION='2 D'); solo se EMITEN filas de `barras`."""
    warm = list(prev_barras) if prev_barras else []
    off = len(warm)
    serie = warm + list(barras)
    horas = [b[0] for b in barras]
    df = pd.DataFrame(serie, columns=["hora", "open", "high", "low", "close", "volume"])
    filas = []
    for t in range(off, len(serie)):
        r = ENGINE.compute(df.iloc[:t + 1])   # <-- FUNCION REAL del bot
        if r is None:
            continue
        filas.append((horas[t - off], r))
    return filas


def ensure_tabla(con):
    cols = "fecha TEXT, hora TEXT, " + ", ".join(
        (c + (" TEXT" if c in ("obv_trend", "dir") else " REAL")) for c in CAMPOS)
    con.execute(f"CREATE TABLE IF NOT EXISTS ta_historico ({cols}, PRIMARY KEY(fecha,hora))")
    con.commit()


def reconstruir_todo():
    con = sqlite3.connect(DB)
    ensure_tabla(con)
    dias = carga_sesiones(con)
    orden = sorted(dias)
    total = 0
    for i, f in enumerate(orden, 1):
        b = dias[f]
        if len(b) < 26:
            continue
        prev = dias[orden[i - 2]] if i >= 2 else None   # sesion anterior como warmup (2 D)
        filas = ta_de_sesion(b, prev)
        for hora, r in filas:
            vals = [f, hora] + [r.get(c) for c in CAMPOS]
            con.execute(
                f"INSERT OR REPLACE INTO ta_historico VALUES({','.join('?' * (len(CAMPOS)+2))})",
                vals)
        con.commit()
        total += len(filas)
        if i % 25 == 0 or i == len(dias):
            print(f"[{i}/{len(dias)}] {f}  {len(filas)} filas TA  (acumulado {total})")
    n = con.execute("select count(*) from ta_historico").fetchone()[0]
    d = con.execute("select count(distinct fecha) from ta_historico").fetchone()[0]
    print(f"\nLISTO: ta_historico -> {d} sesiones, {n} filas. BD: {os.path.abspath(DB)}")


def validar():
    """Reconstruye 08-11 y 08-12 y compara vs prod ta_minute (Regla 8, diferencial)."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.execute("ATTACH 'file:spy_history.db?mode=ro' AS prod")
    dias = carga_sesiones(con)
    orden = sorted(dias)
    # columnas puras del precio que DEBEN coincidir con prod
    pares = [("rsi", "rsi"), ("ema8", "ema8"), ("ema21", "ema21"), ("ema50", "ema50"),
             ("macd_line", "macd_line"), ("macd_signal", "macd_signal"), ("macd_hist", "macd_hist"),
             ("bb_up", "bb_up"), ("bb_mid", "bb_mid"), ("bb_low", "bb_low"),
             ("atr", "atr"), ("atr_pct", "atr_pct"), ("vwap", "vwap"),
             ("sma20", "sma20"), ("sma50", "sma50"), ("sma200", "sma200"),
             ("score", "ta_score")]
    for fecha in ("2026-08-11", "2026-08-12"):
        if fecha not in dias:
            print(f"{fecha}: no esta en historico"); continue
        ix = orden.index(fecha)
        prev = dias[orden[ix - 1]] if ix >= 1 else None   # warmup = sesion previa (2 D)
        rec = {h: r for h, r in ta_de_sesion(dias[fecha], prev)}
        prod = {}
        for row in con.execute(
                "select hora,rsi,ema8,ema21,ema50,macd_line,macd_signal,macd_hist,"
                "bb_up,bb_mid,bb_low,atr,atr_pct,vwap,sma20,sma50,sma200,ta_score "
                "from prod.ta_minute where fecha=?", (fecha,)):
            prod[row[0]] = row
        comunes = sorted(set(rec) & set(prod))
        print(f"\n=== {fecha} ===  minutos rec={len(rec)} prod={len(prod)} comunes={len(comunes)}")
        colmap = ["rsi", "ema8", "ema21", "ema50", "macd_line", "macd_signal", "macd_hist",
                  "bb_up", "bb_mid", "bb_low", "atr", "atr_pct", "vwap", "sma20", "sma50", "sma200", "score"]
        peor = {}
        for h in comunes:
            pr = prod[h]
            for idx, (rk, _pk) in enumerate(pares):
                pv = pr[idx + 1]           # prod value (col 0 es hora)
                rv = rec[h].get(rk)
                if pv is None or rv is None:
                    continue
                d = abs(float(rv) - float(pv))
                if d > peor.get(rk, -1):
                    peor[rk] = d
        for rk in colmap:
            if rk in peor:
                marca = "OK" if peor[rk] < 0.01 else ("~" if peor[rk] < 0.1 else "XXX")
                print(f"   {rk:12s} maxdif={peor[rk]:.5f}  {marca}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "validar":
        validar()
    else:
        reconstruir_todo()
