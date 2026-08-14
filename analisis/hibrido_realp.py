# -*- coding: utf-8 -*-
"""METODO REAL (VWAP/MEDIA) con P&L REAL en $ sobre 08-11 y 08-12 (dias con option prices).

Replica _senal_media() de spy_direction.py (regla 9/3): d = precio - vwap(SMA5 precio tipico);
d>=MEDIA_DIST -> PUT, d<=-MEDIA_DIST -> CALL (hacia la media), sin retardo, MINUTOS_POS min.
Señal (vwap, precio) tomada de ta_historico (byte-fiel a prod). Precios de opcion de premium_minute.
Contrato = el ITM mas profundo que quepa en CAPITAL*FRAC (como _strike_ejecucion).

Objetivo: ¿el metodo VWAP desplegado, con capital REAL $400 y contrato ITM real, saca profit en
estos 2 dias? Compara ITM vs ATM y contra el techo (zigzag perfecto). 2 dias = HIPOTESIS.
Uso: python analisis/hibrido_realp.py
"""
import os, sqlite3, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
HIST = "historico_spy.db"      # ta_historico (vwap byte-fiel) + bars
PROD = "spy_history.db"        # premium_minute (precios opcion reales)
COMISION = 1.72
CAPITAL = 400.0                # capital REAL que se pondra
FRAC = 0.80
QTY = 1
MEDIA_DIST = 0.20              # = spy_direction.MEDIA_DIST
HORIZ = 8                      # = MINUTOS_POS
DIAS = ("2026-08-11", "2026-08-12")
def mm(h): return int(h[:2]) * 60 + int(h[3:5])

def carga_senal():
    """(fecha)-> [(hora, precio, vwap)] desde ta_historico (vwap real byte-fiel)."""
    c = sqlite3.connect(f"file:{HIST}?mode=ro", uri=True)
    d = {}
    for f, h, close, vwap in c.execute(
            "select fecha,hora,close,vwap from ta_historico where fecha in (?,?) order by fecha,hora", DIAS):
        d.setdefault(f, []).append((h, close, vwap))
    c.close()
    return d

def carga_precios():
    """SOLO 0DTE: expiry == fecha (YYYYMMDD). premium_minute mezcla varios vencimientos."""
    c = sqlite3.connect(f"file:{PROD}?mode=ro", uri=True)
    px = {}
    for f, h, exp, s, r, bid, ask, mid, spr in c.execute(
            "select fecha,hora,expiry,strike,right,bid,ask,mid,spread from premium_minute "
            "where mid is not null and mid>0 and fecha in (?,?)", DIAS):
        if str(exp) != f.replace("-", ""):     # descartar vencimientos que NO son 0DTE
            continue
        k = (f, h, s, r)
        cand = (spr if spr is not None else 9e9, mid)
        if k not in px or cand[0] < px[k][0]:
            px[k] = cand
    c.close()
    return px

def mid_at(px, f, h, s, r):
    v = px.get((f, h, s, r)); return v[1] if v else None

def elige_strike(px, f, h, right, spy, modo):
    strikes = sorted({s for (ff, hh, s, rr) in px if ff == f and hh == h and rr == right})
    if not strikes:
        return None
    if modo == "ATM":
        return min(strikes, key=lambda s: abs(s - spy))
    tope = CAPITAL * FRAC
    cands = sorted([s for s in strikes if s < spy]) if right == "C" else sorted([s for s in strikes if s > spy], reverse=True)
    for s in cands:                       # del mas profundo que quepa
        m = mid_at(px, f, h, s, right)
        if m and m * 100 * QTY <= tope:
            return s
    return min(strikes, key=lambda s: abs(s - spy))   # cae a ATM si ninguno cabe

def backtest(dias, px, modo_entrada, modo_contrato):
    trades = []
    for f in DIAS:
        serie = dias.get(f, [])
        horas = [x[0] for x in serie]; precio = [x[1] for x in serie]; vwap = [x[2] for x in serie]
        i = 0; n = len(serie)
        while i < n:
            h = horas[i]
            if h >= "15:40": break
            if modo_entrada == "media":                  # _senal_media REAL (sin retardo)
                if vwap[i] is None: i += 1; continue
                d = precio[i] - vwap[i]
                if d >= MEDIA_DIST: lado = "P"
                elif d <= -MEDIA_DIST: lado = "C"
                else: i += 1; continue
            else:                                        # oraculo: direccion perfecta del tramo
                fin0 = [k for k in range(i, n) if mm(horas[k]) >= mm(h) + HORIZ]
                if not fin0: break
                lado = "C" if precio[fin0[0]] > precio[i] else "P"
            fin = [k for k in range(i, n) if mm(horas[k]) >= mm(h) + HORIZ]
            if not fin: break
            k = fin[0]
            strike = elige_strike(px, f, h, lado, precio[i], modo_contrato)
            if strike is None: i += 1; continue
            e = mid_at(px, f, h, strike, lado); x = mid_at(px, f, horas[k], strike, lado)
            if e is None or x is None or e <= 0: i = k if k > i else i + 1; continue
            trades.append((f, h, lado, strike, e, x, (x - e) * 100 * QTY - COMISION))
            i = k
    return trades

def resume(tr):
    if not tr: return "sin trades"
    pn = [t[6] for t in tr]; tot = sum(pn); n = len(pn); w = sum(1 for p in pn if p > 0)
    porf = {}
    for t in tr: porf[t[0]] = porf.get(t[0], 0) + t[6]
    detalle = " ".join(f"{d[5:]}:{v:+.0f}" for d, v in sorted(porf.items()))
    return f"n={n:3d} win={100*w/n:4.0f}% P&L=${tot:+8.2f} medio=${tot/n:+6.2f} | por dia {detalle}"

def main():
    dias = carga_senal(); px = carga_precios()
    print("=" * 96)
    print(f"METODO VWAP/MEDIA real, P&L REAL $ — 08-11/08-12 | capital ${CAPITAL:.0f} | MEDIA_DIST {MEDIA_DIST} | {HORIZ}min")
    print("  (vwap byte-fiel de ta_historico; precios opcion reales de premium_minute) — HIPOTESIS (2 dias)")
    print("=" * 96)
    for etq, ent, con in (
        ("VWAP/MEDIA + ITM (metodo real)", "media", "ITM"),
        ("VWAP/MEDIA + ATM",               "media", "ATM"),
        ("TECHO zigzag perfecto + ITM",    "oraculo", "ITM"),
        ("TECHO zigzag perfecto + ATM",    "oraculo", "ATM"),
    ):
        print(f"  {etq:32s} | {resume(backtest(dias, px, ent, con))}")
    print("=" * 96)

if __name__ == "__main__":
    main()
