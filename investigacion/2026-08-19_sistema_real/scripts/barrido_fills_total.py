# -*- coding: utf-8 -*-
# BARRIDO EXHAUSTIVO DE FILLS — TODOS los casos que el sistema puede operar, todo el día.
#
# OBJETIVO: no volver a decir "no tenemos suficientes datos". Cubre el espacio COMPLETO:
#     moneyness  -5,-3,-1,0,+1,+2,+3,+5,+10,+20   (de OTM profundo a ITM profundo)
#   x ancho      2, 3, 4                          (el sistema usa 3 con 490-1.000$ y 4 con 1.500+)
#   x dirección  CALL, PUT
#   = 60 combinaciones por pasada, repetidas hasta el cierre -> efecto HORA incluido.
#
# QUÉ MIDE, por prueba:
#   - si la COMPRA al mid se llena, a qué precio y EN CUÁNTOS SEGUNDOS
#   - si la VENTA al mid se llena, a qué precio y en cuántos segundos
#   - si IBKR RECHAZA (y el motivo exacto: margen, órdenes cruzadas, etc.)
#   - el spread real del vertical y su % sobre el mid
#   - el coste de ida y vuelta REAL
#
# POR QUÉ LA PACIENCIA ES LA VARIABLE: `ibkr.cerrar_todo` es una función de EMERGENCIA que
# acaba vendiendo A MERCADO en 8 s; con ella medí -11% y lo llamé "coste de ejecución". Falso.
# Al mid CON PACIENCIA, las 7 primeras operaciones completas dieron una media de -0,0$.
#
# COSTE: ~0$ en media (la varianza es movimiento del subyacente, no spread). No agota la cuenta.
#
# USO:  python barrido_fills_total.py [seg_paciencia]      (por defecto 45)
import sys, os, time, datetime, sqlite3, io

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
C.IBKR_CLIENT_ID = 34
from sys2.data.ibkr import IBKR

PACIENCIA = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 45
# MONEYNESS AJUSTADO (2026-08-20 12:30, tras 176 pruebas): se quitan +10 y +20 porque están
# MEDIDOS y NO LLENAN NUNCA (0 de 41 pruebas, spreads del 14,6% y 26,2%). Seguir probándolos
# es gastar capital sin obtener información. Se afina en cambio la ZONA OPERABLE (-1 a +3),
# donde el fill va del 62% al 82%, que es donde el sistema opera de verdad.
MONEYNESS = [-5, -3, -2, -1, 0, 1, 2, 3, 4, 5]
ANCHOS = [2, 3, 4]
DIRS = ["C", "P"]
EXP = datetime.date.today().strftime("%Y%m%d")
FECHA = datetime.date.today().strftime("%Y-%m-%d")
_RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resultados")
BD = os.path.join(_RES, "fills_reales.db")
LOG = os.path.join(_RES, "barrido_fills_%s.log" % FECHA)
ABRE, CIERRA = "09:30", "15:45"


def _bd():
    c = sqlite3.connect(BD)
    c.execute("""create table if not exists barrido (
        id integer primary key autoincrement, fecha text, hora text, pasada int, spot real,
        right text, ancho real, mny_obj real, k_long real, k_short real, mny_real real,
        mid real, bid_vert real, ask_vert real, spread real, spread_pct real,
        largo_bid real, largo_ask real, corto_bid real, corto_ask real,
        compra_estado text, compra_precio real, compra_seg real, compra_motivo text,
        venta_estado text, venta_precio real, venta_seg real, venta_mid real, venta_motivo text,
        forzado int, slip_compra_pct real, slip_venta_pct real, ida_vuelta_usd real,
        log_compra text, log_venta text,
        combo_bid real, combo_ask real, combo_mid real, desfase_mid real)""")
    c.execute("create index if not exists ix_bar on barrido(fecha,hora)")
    c.commit()
    return c


def guardar(r):
    c = _bd()
    cols = ["hora", "pasada", "spot", "right", "ancho", "mny_obj", "k_long", "k_short",
            "mny_real", "mid", "bid_vert", "ask_vert", "spread", "spread_pct", "largo_bid",
            "largo_ask", "corto_bid", "corto_ask", "compra_estado", "compra_precio",
            "compra_seg", "compra_motivo", "venta_estado", "venta_precio", "venta_seg",
            "venta_mid", "venta_motivo", "forzado", "slip_compra_pct", "slip_venta_pct",
            "ida_vuelta_usd", "log_compra", "log_venta", "combo_bid", "combo_ask",
            "combo_mid", "desfase_mid"]
    c.execute("insert into barrido (fecha,%s) values (%s)"
              % (",".join(cols), ",".join(["?"] * (len(cols) + 1))),
              [FECHA] + [r.get(x) for x in cols])
    c.commit()
    c.close()
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write("%s p%s | %s a%s mny%+d (real %+.2f) %s/%s | mid %.3f spr %s%% | "
                "C:%s %s %ss | V:%s %s %ss | ida-vuelta %s$\n"
                % (r.get("hora"), r.get("pasada"), r.get("right"), r.get("ancho"),
                   r.get("mny_obj"), r.get("mny_real") or 0, r.get("k_long"), r.get("k_short"),
                   r.get("mid") or 0, r.get("spread_pct"), r.get("compra_estado"),
                   r.get("compra_precio"), r.get("compra_seg"), r.get("venta_estado"),
                   r.get("venta_precio"), r.get("venta_seg"), r.get("ida_vuelta_usd")))


def ahora():
    return datetime.datetime.now().strftime("%H:%M:%S")


def spot_actual(k):
    c = sqlite3.connect(os.path.join(RAIZ, "sys2.db"))
    r = c.execute("select close from bars where fecha=? order by hora desc limit 1",
                  (FECHA,)).fetchone()
    c.close()
    if r:
        return float(r[0])
    b = k.backfill_spy(dur="120 S")
    return float(b[-1][4]) if b else None


def rechazo(tr):
    """Motivo del rechazo REAL. El aviso 10349 ('TIF was set to DAY') NO es rechazo: hace que
    ib_insync marque 'Cancelled' de forma transitoria y la orden sigue viva."""
    for e in tr.log:
        m = (e.message or "")
        if "MARGIN" in m.upper():
            return "MARGEN"
        if "both sides" in m.lower():
            return "ORDEN_CRUZADA"
        if "Error 201" in m or "not accepted" in m.lower():
            return m[:60]
    return ""


def esperar(k, tr, seg):
    t0 = time.time()
    for _ in range(seg * 2):
        k.ib.sleep(0.5)
        if tr.orderStatus.status == "Filled":
            return "Filled", round(time.time() - t0, 1), ""
        mot = rechazo(tr)
        if mot:
            return "RECHAZADA", round(time.time() - t0, 1), mot
    return "NO_LLENA", round(time.time() - t0, 1), ""


def libro_combo(k, right, kl, ks, accion="BUY"):
    """bid/ask REALES del combo BAG. HALLAZGO 2026-08-20: el combo tiene su PROPIO libro,
    DESPLAZADO respecto a la suma de las patas — mismo spread (0,020) pero desplazado 0,03:
        C 767/770  patas bid 0,990/ask 1,010   COMBO bid 0,96/ask 0,98
        P 767/764  patas bid 0,770/ask 0,790   COMBO bid 0,82/ask 0,84
    Consecuencia: poner la venta al mid de las patas (1,000) la deja POR ENCIMA del ask real
    del combo (0,98) -> NO PUEDE llenar nunca. Explica 14 de 14 ventas forzadas.
    Y al comprar, ese mismo mid queda por ENCIMA del ask -> cruza y llena al instante, o sea
    el sistema entra PAGANDO DE MÁS sin saberlo."""
    from ib_insync import Contract, ComboLeg
    cl, cs = k._opt(EXP, float(kl), right), k._opt(EXP, float(ks), right)
    k.ib.qualifyContracts(cl, cs)
    a1, a2 = ("BUY", "SELL") if accion == "BUY" else ("SELL", "BUY")
    bag = Contract(symbol=C.SYMBOL, secType="BAG", exchange="SMART", currency="USD",
                   comboLegs=[ComboLeg(conId=cl.conId, ratio=1, action=a1, exchange="SMART"),
                              ComboLeg(conId=cs.conId, ratio=1, action=a2, exchange="SMART")])
    t = k.ib.reqMktData(bag, "", False, False)
    k.ib.sleep(2.5)
    b = t.bid if (t.bid is not None and t.bid > -100) else None
    a = t.ask if (t.ask is not None and t.ask > -100) else None
    try:
        k.ib.cancelMktData(bag)
    except Exception:
        pass
    return b, a, bag


def limpiar(k):
    """Cancela toda orden viva. Sin esto IBKR rechaza con 'Cannot have open orders on both
    sides of the same US Option contract' — un rechazo del propio sondeo, no del mercado."""
    n = 0
    for t in list(k.ib.openTrades() or []):
        try:
            k.ib.cancelOrder(t.order)
            n += 1
        except Exception:
            pass
    if n:
        k.ib.sleep(1.5)
    return n


def vender(k, right, kl, ks, mid_obj, bidv=None):
    """ESCALERA DE SALIDA (2026-08-20): el sistema real cierra con `cerrar_todo(espera=8)` y,
    cuando cierra por flip, tiene que abrir la contraria acto seguido — NO puede esperar minutos.
    Medido: 0 de 7 ventas llenaron al mid en 45 s, mientras 7 de 7 compras llenaron en segundos.
    Así que la pregunta útil NO es "¿llena si espero más?" sino "¿A QUÉ PRECIO llena en 8 s?".
    Se baja el límite por escalones (mid, -25%, -50%, -75% del semi-spread, bid) con 8 s cada uno
    y se registra EN QUÉ ESCALÓN llenó: eso es el descuento real que el sistema debe aplicar."""
    from ib_insync import Contract, ComboLeg, LimitOrder
    cl, cs = k._opt(EXP, float(kl), right), k._opt(EXP, float(ks), right)
    k.ib.qualifyContracts(cl, cs)
    bag = Contract(symbol=C.SYMBOL, secType="BAG", exchange="SMART", currency="USD",
                   comboLegs=[ComboLeg(conId=cl.conId, ratio=1, action="SELL", exchange="SMART"),
                              ComboLeg(conId=cs.conId, ratio=1, action="BUY", exchange="SMART")])
    cb, ca, _ = libro_combo(k, right, kl, ks, "SELL")     # libro REAL del combo al vender
    if cb is not None and ca is not None and ca > cb:
        cmid = (cb + ca) / 2.0
        escalones = [("cmid", cmid), ("-25%", cmid - (cmid - cb) * 0.25),
                     ("-50%", cmid - (cmid - cb) * 0.5), ("cbid", cb), ("cbid-1", cb - 0.01)]
    else:                                                 # sin libro del combo: patas (peor caso)
        semi = (mid_obj - bidv) if (bidv is not None and bidv < mid_obj) else max(0.02, mid_obj * 0.05)
        escalones = [("mid", mid_obj), ("-50%", mid_obj - semi * 0.5), ("bid", mid_obj - semi)]
    t_ini = time.time()
    logs = []
    for etiq, px in escalones:
        if px <= 0.01:
            continue
        tr = k.ib.placeOrder(bag, LimitOrder("SELL", 1, round(px, 2)))
        est, seg, mot = esperar(k, tr, 8)          # 8 s = lo que espera el sistema real
        logs.append("%s@%.2f:%s" % (etiq, px, est))
        if est == "Filled":
            return ("Filled@" + etiq), float(tr.orderStatus.avgFillPrice or 0),                    round(time.time() - t_ini, 1), mot, 0, " || ".join(logs)
        limpiar(k)
    plana, precios = k.cerrar_todo(EXP, right=right, qty=1)
    cob = None
    if precios and float(kl) in precios and float(ks) in precios:
        cob = precios[float(kl)] - precios[float(ks)]
    return ("FORZADO" if plana else "NO_PLANA"), cob, round(time.time() - t_ini, 1), "", 1,            " || ".join(logs)


def prueba(k, cad, S, right, ancho, mny, pasada):
    """Una combinación (dirección, ancho, moneyness). Devuelve True si se pudo medir."""
    kl = round(S - mny) if right == "C" else round(S + mny)
    ks = kl + ancho if right == "C" else kl - ancho
    dl, ds = cad.get((right, float(kl))), cad.get((right, float(ks)))
    if not dl or not ds or None in (dl["bid"], dl["ask"], ds["bid"], ds["ask"]):
        return False
    mid = (dl["mid"] or 0) - (ds["mid"] or 0)
    if mid <= 0.02:
        return False
    bidv, askv = dl["bid"] - ds["ask"], dl["ask"] - ds["bid"]
    r = {"hora": ahora(), "pasada": pasada, "spot": S, "right": right, "ancho": ancho,
         "mny_obj": mny, "k_long": kl, "k_short": ks,
         "mny_real": round((S - kl) if right == "C" else (kl - S), 2),
         "mid": round(mid, 3), "bid_vert": round(bidv, 3), "ask_vert": round(askv, 3),
         "spread": round(askv - bidv, 3),
         "spread_pct": round(100.0 * (askv - bidv) / mid, 1) if mid else None,
         "largo_bid": dl["bid"], "largo_ask": dl["ask"],
         "corto_bid": ds["bid"], "corto_ask": ds["ask"]}

    limpiar(k)
    _cb, _ca, _ = libro_combo(k, right, kl, ks, "BUY")    # libro REAL del combo al comprar
    r["combo_bid"], r["combo_ask"] = _cb, _ca
    if _cb is not None and _ca is not None and _ca > _cb:
        r["combo_mid"] = round((_cb + _ca) / 2.0, 3)
        r["desfase_mid"] = round(r["combo_mid"] - mid, 3)   # cuánto miente el mid de las patas
        _px = r["combo_mid"]
    else:
        _px = mid
    tr = k.comprar_vertical(EXP, kl, ks, right, _px / 1.01, qty=1)
    est, seg, mot = esperar(k, tr, PACIENCIA)
    r["log_compra"] = " || ".join("%s %s %s" % (e.time.strftime("%H:%M:%S"), e.status,
                                                (e.message or "")[:90]) for e in tr.log)
    r.update(compra_estado=est, compra_seg=seg, compra_motivo=mot)
    if est != "Filled":
        limpiar(k)
        print("  %s %s a%d mny%+3d -> %-10s %s (mid %.3f, spr %s%%)"
              % (r["hora"], right, ancho, mny, est, mot, mid, r["spread_pct"]), flush=True)
        guardar(r)
        return True
    r["compra_precio"] = float(tr.orderStatus.avgFillPrice or 0)
    r["slip_compra_pct"] = round(100.0 * (r["compra_precio"] - mid) / mid, 2)

    k.ib.sleep(1)
    cad2 = k.cadena(EXP, S, n=3)
    d2l = cad2.get((right, float(kl))) or dl
    d2s = cad2.get((right, float(ks))) or ds
    mid2 = (d2l["mid"] or 0) - (d2s["mid"] or 0)
    _bid2 = (d2l['bid'] or 0) - (d2s['ask'] or 0)
    vest, vpre, vseg, vmot, forz, logv = vender(k, right, kl, ks, mid2, _bid2)
    r.update(venta_estado=vest, venta_precio=vpre, venta_seg=vseg, venta_mid=round(mid2, 3),
             venta_motivo=vmot, forzado=forz, log_venta=logv)
    if vpre is not None:
        r["ida_vuelta_usd"] = round((vpre - r["compra_precio"]) * 100, 2)
        if mid2:
            r["slip_venta_pct"] = round(100.0 * (vpre - mid2) / abs(mid2), 2)
    print("  %s %s a%d mny%+3d -> C %.3f en %4.1fs (%+.1f%%) | V %s en %4.1fs %s | %s$"
          % (r["hora"], right, ancho, mny, r["compra_precio"], seg, r["slip_compra_pct"],
             ("%.3f" % vpre) if vpre is not None else "?", vseg,
             "FORZ" if forz else "    ", r.get("ida_vuelta_usd")), flush=True)
    guardar(r)
    return True


def main():
    k = IBKR()
    k.conectar()
    print("BARRIDO EXHAUSTIVO | paciencia %ds | %d combinaciones/pasada | saldo %.2f\n"
          % (PACIENCIA, len(MONEYNESS) * len(ANCHOS) * len(DIRS), k.saldo()), flush=True)
    pasada = 0
    try:
        while True:
            hm = datetime.datetime.now().strftime("%H:%M")
            if hm < ABRE:
                k.ib.sleep(60)
                continue
            if hm > CIERRA:
                break
            pasada += 1
            print("\n═══ PASADA %d — %s ═══" % (pasada, hm), flush=True)
            S = spot_actual(k)
            if S is None:
                k.ib.sleep(30)
                continue
            cad = k.cadena(EXP, S, n=24)
            hechas = 0
            for mny in MONEYNESS:                  # el moneyness manda: cada pasada barre todo
                for ancho in ANCHOS:
                    for right in DIRS:
                        if datetime.datetime.now().strftime("%H:%M") > CIERRA:
                            break
                        try:
                            if prueba(k, cad, S, right, ancho, mny, pasada):
                                hechas += 1
                        except Exception as e:
                            print("  ERROR %s a%d mny%+d: %s" % (right, ancho, mny, e), flush=True)
                            limpiar(k)
                        if hechas % 6 == 0:        # refrescar cadena y spot cada 6 pruebas
                            S = spot_actual(k) or S
                            cad = k.cadena(EXP, S, n=24)
                            ab = k.abiertas(EXP)
                            if ab:
                                print("  ⚠️ abiertas %s — cerrando" % ab, flush=True)
                                k.cerrar_todo(EXP)
            print("  -> pasada %d: %d pruebas" % (pasada, hechas), flush=True)
    except KeyboardInterrupt:
        print("\ninterrumpido", flush=True)
    finally:
        try:
            limpiar(k)
            ab = k.abiertas(EXP)
            if ab:
                print("cerrando abiertas: %s" % ab, flush=True)
                k.cerrar_todo(EXP)
        except Exception:
            pass
        print("\ndatos en %s (tabla `barrido`)" % BD, flush=True)
        k.desconectar()


if __name__ == "__main__":
    main()
