# -*- coding: utf-8 -*-
"""SIMULADOR ST + TRAIL + MAGNITUD  —  version consolidada y reproducible

Reproduce EXACTAMENTE:
    2026-08-12  ->  +43.56$
    2026-08-13  -> +480.84$
    config: senales del usuario, trail 0.10%, magnitud >= 0.8, capital compuesto

⚠️ AVISO CRITICO PARA REPRODUCIR
El 08-12 NO se puede reproducir con un Supertrend calculado desde las 09:30.
Sus 7 senales las leyo el usuario de su Webull y las dicto a mano (SENALES_MANUALES).
Mi ST(7,3) calculado sin premarket da solo 4 senales ese dia y otro resultado.
El 08-13 SI coincide: las senales manuales == las calculadas por ST(7,3).
Hasta tener velas con useRTH=False, el 08-12 solo es reproducible con las manuales.

LAS 3 PIEZAS CABLEADAS
  1. SENAL PENDIENTE   si el ST gira estando DENTRO, se guarda y se entra al salir
  2. PERMANENCIA       el trail salta pero NO sale si |net_spy|/mediana >= umbral
  3. CAPITAL COMPUESTO tras cada operacion se recalcula el tope (80% del capital)

PRECIOS: compra al ASK, vende al BID. Nunca mid.

Uso:
    python simulador_st.py                 # reproduce los 2 dias
    python simulador_st.py barrido         # rejilla completa
"""
import os
import sqlite3
import statistics as st
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------- configuracion
CAPITAL_0 = 400.0
FRAC_TOPE = 0.80          # tope por contrato = FRAC_TOPE * capital
COMISION = 1.72           # por operacion (ida y vuelta)
STOP_NEW = "15:40"        # no abrir despues
CIERRE = "15:59"          # aplanar

P_ATR = 7
MULT = 3.0
TRAIL_PCT = 0.10
MAG_UMBRAL = 0.8          # None = magnitud desactivada
MODO_ENTRADA = "pendiente"   # 'pendiente' | 'nueva'

RAIZ = os.path.dirname(os.path.abspath(__file__))
def R(p): return os.path.join(RAIZ, p)

# fecha -> (db de velas+premium, db de tape del subyacente, expiry)
FUENTES = {
    "2026-08-12": (R("spy_history.db"), R("spy_tape_ayer.db"), "20260812"),
    "2026-08-13": (R("spy_history_20260813.db"), R("spy_tape_20260813.db"), "20260813"),
}

# Senales leidas por el usuario de su broker (Webull, ST(7,3))
SENALES_MANUALES = {
    "2026-08-12": [("09:30", "P"), ("10:27", "C"), ("10:33", "P"), ("12:02", "C"),
                   ("13:12", "P"), ("14:12", "C"), ("14:57", "P")],
    "2026-08-13": [("09:36", "C"), ("10:44", "P"), ("12:05", "C"),
                   ("13:37", "P"), ("14:34", "C"), ("15:17", "P")],
}


def mm(h):
    return int(h[:2]) * 60 + int(h[3:5])


# ---------------------------------------------------------------------- carga
def carga(fecha, db_velas=None, db_tape=None, expiry=None, tabla_velas="bars_minute"):
    """Devuelve (B, P, NET).
       B    = [(hora,o,h,l,c)] velas de 1 min, RECONSTRUIDAS DEL TAPE si hay tape.
       P    = {(strike,right,hora): (bid,ask)}
       NET  = {hora: flujo neto del subyacente por regla del tick}
    """
    if db_velas is None:
        db_velas, db_tape, expiry = FUENTES[fecha]

    NET = {}
    B = None
    if db_tape and os.path.exists(db_tape):
        c = sqlite3.connect(f"file:{db_tape}?mode=ro", uri=True)
        V = {}
        prev = None
        for m, p, s in c.execute("select minuto,price,size from trades_raw order by ts_et"):
            h = m[-5:] if len(m) > 5 else m
            a = V.setdefault(h, {"o": p, "h": p, "l": p, "c": p})
            a["h"] = max(a["h"], p); a["l"] = min(a["l"], p); a["c"] = p
            sg = 0 if prev is None else (1 if p > prev else (-1 if p < prev else 0))
            prev = p
            NET[h] = NET.get(h, 0.0) + sg * s * p
        c.close()
        hs = sorted(h for h in V if h <= "16:00")
        B = [(h, V[h]["o"], V[h]["h"], V[h]["l"], V[h]["c"]) for h in hs]

    c2 = sqlite3.connect(f"file:{db_velas}?mode=ro", uri=True)
    if B is None:
        B = [(h[:5], o, hi, lo, cl) for h, o, hi, lo, cl in c2.execute(
            f"select hora,open,high,low,close from {tabla_velas} where fecha=? order by hora",
            (fecha,))]
    P = {}
    if expiry:
        for k, r, h, bid, ask in c2.execute(
                "select strike,right,hora,bid,ask from premium_minute "
                "where fecha=? and expiry=? and bid is not null and ask is not null",
                (fecha, expiry)):
            P[(k, r, h[:5])] = (bid, ask)
    c2.close()
    return B, P, NET


# ----------------------------------------------------------------- supertrend
def supertrend(b, per=P_ATR, mult=MULT, d0=-1):
    """Wilder. d0 = estado inicial (-1 bajista, +1 alcista).
       Devuelve lista de direccion por vela (+1 CALL / -1 PUT)."""
    tr = []; atr = []
    for i, (h, o, hi, lo, cl) in enumerate(b):
        t = hi - lo if i == 0 else max(hi - lo, abs(hi - b[i-1][4]), abs(lo - b[i-1][4]))
        tr.append(t)
        atr.append(sum(tr) / len(tr) if i < per else atr[-1] + (t - atr[-1]) / per)
    d = d0; fu = fl = None; D = []
    for i, (h, o, hi, lo, cl) in enumerate(b):
        m = (hi + lo) / 2.0
        ub = m + mult * atr[i]; lb = m - mult * atr[i]
        if i == 0:
            fu, fl = ub, lb
        else:
            fu = ub if (ub < fu or b[i-1][4] > fu) else fu
            fl = lb if (lb > fl or b[i-1][4] < fl) else fl
            if d == 1 and cl < fl: d = -1
            elif d == -1 and cl > fu: d = 1
        D.append(d)
    return D


def elegir_contrato(P, hora, right, tope, mid=False):
    """ITM mas profundo que quepa: el de precio mas alto por debajo del tope.
       mid=True -> precio = (bid+ask)/2 ; si no -> ASK (compra pesimista)."""
    def px(v):
        return (v[0] + v[1]) / 2.0 if mid else v[1]
    cand = [(k, v) for (k, r, h), v in P.items() if r == right and h == hora and px(v) * 100 <= tope]
    if not cand:
        return None
    return max(cand, key=lambda x: px(x[1]))     # (strike, (bid, ask))


# ------------------------------------------------------------------ simulador
def simular(fecha, senales=None, trail=TRAIL_PCT, mag_umbral=MAG_UMBRAL,
            modo=MODO_ENTRADA, per=P_ATR, mult=MULT, cap0=CAPITAL_0,
            db_velas=None, db_tape=None, expiry=None, verbose=False, mid=False, net_ext=None,
            size_cap=None, cooldown=0, hora_min=None, ventana_no=None,
            stop_opt=None, max_trades=None, stop_racha=None):
    """senales: [(hora,'C'|'P')] fijas, o None para calcular el Supertrend.
       net_ext: dict {hora: magnitud} para INYECTAR una magnitud externa (p.ej. ficticia
       derivada del volumen), sobreescribiendo el NET del tape. None = usar el del tape."""
    B, P, NET = carga(fecha, db_velas, db_tape, expiry)
    if not B:
        return [], cap0
    if net_ext is not None:
        NET = net_ext
    cl = {h: c for h, o, hi, lo, c in B}
    hs = [h for h, _, _, _, _ in B]

    if senales is not None:
        E = dict(senales)
        cambio_en = {h: (1 if d == "C" else -1) for h, d in senales}
    else:
        D = supertrend(B, per, mult, -1)
        cambio_en = {B[i][0]: D[i] for i in range(1, len(B)) if D[i] != D[i-1]}

    med = st.median([abs(v) for v in NET.values() if v]) if NET else None

    cap = cap0
    ops = []
    pos = None
    pendiente = None
    ult_salida = -10**9   # minuto de la ultima salida (para cooldown)
    ntr = 0               # trades hechos en el dia (para max_trades)
    racha = 0             # perdidas consecutivas (para stop_racha)

    for h in hs:
        c = cl[h]
        gira = h in cambio_en

        # 1) SENAL PENDIENTE: el giro llega estando dentro -> se guarda
        if gira and pos is not None:
            pendiente = cambio_en[h]

        # salida
        if pos is not None:
            pos["ext"] = max(pos["ext"], c) if pos["lado"] == 1 else min(pos["ext"], c)
            retro = ((pos["ext"] - c) / pos["ext"]) if pos["lado"] == 1 else ((c - pos["ext"]) / pos["ext"])
            salta = retro >= trail / 100.0

            # 2) PERMANENCIA POR MAGNITUD
            if salta and mag_umbral is not None and med:
                if abs(NET.get(h, 0.0)) / med >= mag_umbral:
                    salta = False

            # STOP-LOSS POR TRADE (sobre la opcion): fuerza salida, no lo tapa la magnitud
            if stop_opt is not None:
                q2 = P.get((pos["k"], pos["rt"], h))
                if q2:
                    valnow = (q2[0] + q2[1]) / 2.0 if mid else q2[0]
                    if valnow <= pos["px_in"] * (1 - stop_opt):
                        salta = True

            if salta or h >= CIERRE:
                q = P.get((pos["k"], pos["rt"], h))
                # venta: mid=(bid+ask)/2 ; si no, al BID (pesimista)
                venta = ((q[0] + q[1]) / 2.0 if mid else q[0]) if q else pos["px_in"]
                g = (venta - pos["px_in"]) * 100.0 - COMISION
                cap += g                                       # 3) CAPITAL COMPUESTO
                ops.append(dict(entrada=pos["h0"], salida=h, strike=pos["k"], right=pos["rt"],
                                compra=pos["px_in"], venta=venta, pnl=g, capital=cap,
                                dur=mm(h) - mm(pos["h0"])))
                pos = None
                ult_salida = mm(h)
                ntr += 1
                racha = racha + 1 if g <= 0 else 0

        # entrada
        if (pos is None and h < STOP_NEW
                and (hora_min is None or h >= hora_min)          # saltar apertura
                and mm(h) >= ult_salida + cooldown               # cooldown tras salir
                and not (ventana_no and ventana_no[0] <= h < ventana_no[1])  # blackout
                and (max_trades is None or ntr < max_trades)     # max trades/dia
                and (stop_racha is None or racha < stop_racha)): # corte por racha
            lado = None
            if gira:
                lado = cambio_en[h]
            elif modo == "pendiente" and pendiente is not None:
                lado = pendiente
            if lado is not None:
                rt = "C" if lado == 1 else "P"
                tope = (size_cap if size_cap is not None else cap) * FRAC_TOPE  # sizing fijo si size_cap
                el = elegir_contrato(P, h, rt, tope, mid)
                if el:
                    k, (bid, ask) = el
                    px_in = (bid + ask) / 2.0 if mid else ask   # compra: mid o ASK
                    pos = {"h0": h, "lado": lado, "ext": c, "k": k, "rt": rt, "px_in": px_in}
                    pendiente = None

    if verbose:
        for o in ops:
            print(f"   {o['entrada']}-{o['salida']} {o['dur']:3d}min {o['strike']:.0f}{o['right']} "
                  f"{o['compra']:.2f}->{o['venta']:.2f} {o['pnl']:+9.2f}$  cap {o['capital']:.0f}")
    return ops, cap


# --------------------------------------------------------------------- main
def reproducir():
    print("=" * 88)
    print("REPRODUCCION DE REFERENCIA  ·  senales del usuario · trail 0.10% · magnitud 0.8")
    print("=" * 88)
    esperado = {"2026-08-12": 43.56, "2026-08-13": 480.84}
    total = 0.0
    for f in ("2026-08-12", "2026-08-13"):
        ops, cap = simular(f, senales=SENALES_MANUALES[f], verbose=True)
        g = cap - CAPITAL_0
        total += g
        ok = "OK" if abs(g - esperado[f]) < 0.01 else f"*** DIFIERE (esperado {esperado[f]:+.2f}) ***"
        print(f"   {f}: {len(ops)} ops   {g:+.2f}$   {ok}\n")
    print(f"   TOTAL {total:+.2f}$   (esperado +524.40)")
    print("=" * 88)


def barrido():
    print("BARRIDO  ·  senales del usuario  ·  los 2 dias")
    print(f"{'trail':>7} {'mag':>6} {'modo':>10} {'08-12':>11} {'08-13':>11} {'TOTAL':>11} {'2 dias +':>9}")
    for modo in ("pendiente", "nueva"):
        for tr in (0.08, 0.10, 0.11, 0.12, 0.14):
            for umb in (None, 0.6, 0.8, 1.0, 1.2):
                a = simular("2026-08-12", SENALES_MANUALES["2026-08-12"], tr, umb, modo)[1] - CAPITAL_0
                b = simular("2026-08-13", SENALES_MANUALES["2026-08-13"], tr, umb, modo)[1] - CAPITAL_0
                print(f"{tr:>6.2f}% {str(umb):>6} {modo:>10} {a:>10.2f}$ {b:>10.2f}$ "
                      f"{a+b:>10.2f}$ {'SI' if a > 0 and b > 0 else '':>9}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "barrido":
        barrido()
    else:
        reproducir()
