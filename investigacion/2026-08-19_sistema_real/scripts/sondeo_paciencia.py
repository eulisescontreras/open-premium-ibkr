# -*- coding: utf-8 -*-
# SONDEO CON PACIENCIA — ¿se llena AL MID si esperas, o hay que cruzar el spread?
#
# POR QUÉ ESTE SCRIPT (corrección del 2026-08-20, observación del usuario):
#   `sondeo_margen.py` cerraba con `ibkr.cerrar_todo`, que es una función de EMERGENCIA: su
#   cascada acaba vendiendo A MERCADO si el mid no llena en 8 s. Resultado: vendió a 0,490 con
#   mid 0,550 (-11%) y lo apunté como "coste de ejecución". NO LO ERA: era el coste de cruzar
#   el spread con prisa. Toda la tabla de sensibilidad (2%->129x, 5%->100x, 10%->muere) puede
#   estar midiendo el escenario equivocado.
#
# LO QUE DICE EL USUARIO (operando en real, hipótesis a medir): IBKR/el market maker NO llena
#   de inmediato cuando el spread es mínimo; si te desesperas y persigues el precio cancelando
#   y reponiendo, el spread se aleja y pierdes. Si pones la orden al mid y ESPERAS, el precio
#   normalmente acaba llegando.
#
# LA PREGUNTA REAL, Y LA QUE DECIDE SI EL BACKTEST VALE: el backtest asume MID. Si al mid con
#   paciencia se llena, el backtest es realista. Si no se llena nunca, no lo es. Con
#   `cerrar_todo` era imposible saberlo porque siempre acababa a mercado.
#
# MÉTODO: comprar al MID y esperar hasta PACIENCIA segundos SIN cancelar ni reponer. Si llena,
#   vender al MID con la misma paciencia. Se mide el TIEMPO HASTA EL FILL, que es la variable
#   que de verdad importa. Solo si no llena tras toda la espera se cierra a mercado, y ESE caso
#   se marca aparte (`forzado=1`) para no mezclar los dos escenarios.
#
# USO:  python sondeo_paciencia.py [min_entre_rondas] [seg_paciencia]     (por defecto 30 y 120)
import sys, os, json, time, datetime, sqlite3, io

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
C.IBKR_CLIENT_ID = 34
from sys2.data.ibkr import IBKR
from sys2.core import instrumento as I, autocalibra as AC

INTERVALO = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
PACIENCIA = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 120
ANCHO = 2.0
EXP = datetime.date.today().strftime("%Y%m%d")
FECHA = datetime.date.today().strftime("%Y-%m-%d")
_RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resultados")
BD = os.path.join(_RES, "fills_reales.db")
LOG = os.path.join(_RES, "paciencia_%s.log" % FECHA)
ABRE, CIERRA = "09:30", "15:50"


def _bd():
    c = sqlite3.connect(BD)
    c.execute("""create table if not exists paciencia (
        id integer primary key autoincrement, fecha text, hora text, spot real,
        right text, k_long real, k_short real, etiqueta text, moneyness real,
        mid real, bid_vert real, ask_vert real, spread real, spread_pct real,
        compra_estado text, compra_precio real, compra_seg real, compra_motivo text,
        venta_estado text, venta_precio real, venta_seg real, venta_mid real,
        forzado int, slip_compra_pct real, slip_venta_pct real, ida_vuelta_pct real,
        log_ibkr text)""")
    c.commit()
    return c


def _guardar(r, log_ibkr=""):
    c = _bd()
    cols = ["hora", "spot", "right", "k_long", "k_short", "etiqueta", "moneyness", "mid",
            "bid_vert", "ask_vert", "spread", "spread_pct", "compra_estado", "compra_precio",
            "compra_seg", "compra_motivo", "venta_estado", "venta_precio", "venta_seg",
            "venta_mid", "forzado", "slip_compra_pct", "slip_venta_pct", "ida_vuelta_pct"]
    c.execute("insert into paciencia (fecha,%s,log_ibkr) values (%s)"
              % (",".join(cols), ",".join(["?"] * (len(cols) + 2))),
              [FECHA] + [r.get(x) for x in cols] + [log_ibkr])
    c.commit()
    c.close()
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write("%s | %-13s mny %+5.2f | mid %.3f (spread %s%%) | COMPRA %s %s en %ss | "
                "VENTA %s %s en %ss | ida-vuelta %s%% %s\n"
                % (r.get("hora"), r.get("etiqueta"), r.get("moneyness") or 0, r.get("mid") or 0,
                   r.get("spread_pct"), r.get("compra_estado"), r.get("compra_precio"),
                   r.get("compra_seg"), r.get("venta_estado"), r.get("venta_precio"),
                   r.get("venta_seg"), r.get("ida_vuelta_pct"),
                   "[FORZADO A MERCADO]" if r.get("forzado") else ""))


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


def _error_real(tr):
    """True solo si IBKR RECHAZA de verdad. OJO: el aviso 10349 ('Order TIF was set to DAY
    based on order preset') hace que ib_insync marque el estado como 'Cancelled' de forma
    TRANSITORIA — la orden sigue viva y puede llenarse después. Salir ahí era un artefacto que
    hacía parecer que IBKR rechazaba todo (2026-08-20: las 4 órdenes 'canceladas' en 0,5 s)."""
    for e in tr.log:
        m = (e.message or "")
        if "Error 201" in m or "MARGIN" in m.upper() or "not accepted" in m.lower():
            return True
    return False


def esperar(k, tr, seg):
    """Espera SIN cancelar ni reponer (esa es LA variable que se mide: la paciencia).
    Devuelve (estado, segundos)."""
    t0 = time.time()
    for _ in range(seg * 2):
        k.ib.sleep(0.5)
        if tr.orderStatus.status == "Filled":
            return "Filled", round(time.time() - t0, 1)
        if _error_real(tr):
            return "RECHAZADA", round(time.time() - t0, 1)
    return ("NO_LLENA" if tr.orderStatus.status != "Filled" else "Filled",
            round(time.time() - t0, 1))


def vender_al_mid(k, right, kl, ks, mid_obj):
    """Vende el vertical al MID con paciencia. Devuelve (estado, precio, seg, forzado)."""
    from ib_insync import Contract, ComboLeg, LimitOrder, MarketOrder
    cl = k._opt(EXP, float(kl), right)
    cs = k._opt(EXP, float(ks), right)
    k.ib.qualifyContracts(cl, cs)
    bag = Contract(symbol=C.SYMBOL, secType="BAG", exchange="SMART", currency="USD",
                   comboLegs=[ComboLeg(conId=cl.conId, ratio=1, action="SELL", exchange="SMART"),
                              ComboLeg(conId=cs.conId, ratio=1, action="BUY", exchange="SMART")])
    tr = k.ib.placeOrder(bag, LimitOrder("SELL", 1, round(mid_obj, 2)))
    est, seg = esperar(k, tr, PACIENCIA)
    if est == "Filled":
        return est, float(tr.orderStatus.avgFillPrice or 0), seg, 0
    try:
        k.ib.cancelOrder(tr.order)
    except Exception:
        pass
    k.ib.sleep(1)
    plana, precios = k.cerrar_todo(EXP, right=right, qty=1)      # último recurso
    cob = None
    if precios and float(kl) in precios and float(ks) in precios:
        cob = precios[float(kl)] - precios[float(ks)]
    return ("FORZADO" if plana else "NO_PLANA"), cob, seg, 1


def limpiar_ordenes(k):
    """Cancela TODA orden viva antes de empezar. IMPRESCINDIBLE: si queda una venta pendiente
    de la ronda anterior, IBKR rechaza la compra del mismo contrato con
    "Error 201: Cannot have open orders on both sides of the same US Option contract"
    — un rechazo que NO es del mercado sino del propio sondeo (2026-08-20 09:50)."""
    n = 0
    for t in list(k.ib.openTrades() or []):
        try:
            k.ib.cancelOrder(t.order)
            n += 1
        except Exception:
            pass
    if n:
        k.ib.sleep(2)
        print("  (canceladas %d órdenes vivas antes de la ronda)" % n, flush=True)
    return n


def ronda(k):
    limpiar_ordenes(k)
    S = spot_actual(k)
    if S is None:
        print("  %s sin spot" % ahora(), flush=True)
        return
    cad = k.cadena(EXP, S, n=22)          # ancho suficiente para el ITM profundo del nivel alto
    base = round(S)
    # LOS CASOS QUE EL SISTEMA COMPRA DE VERDAD (usa la FUNCIÓN REAL `elegir_vert`, no strikes
    # inventados). El sistema CAMBIA de ancho al escalar (autocalibra.sizing):
    #   saldo 490-1.000 -> ancho 3   |   saldo 1.500+ -> ancho 4   |   ancho 2 NUNCA se usa
    # y compra el largo ITM MÁS PROFUNDO que quepa en el tope, así que el nivel alto acaba en
    # moneyness +20 — justo lo que IBKR bloquea por margen. Se prueban TODOS los niveles aunque
    # la cuenta no tenga ese capital: lo que se mide es si el BROKER acepta ese contrato.
    _cadmid = {(r_, kk): (v["mid"], 0.0) for (r_, kk), v in cad.items() if v.get("mid")}
    PRUEBAS, _vistos = [], set()
    for _saldo in (600, 1000, 1500, 3600, 5400):
        _cf = AC.sizing(_saldo)
        if not _cf:
            continue
        for _rt in ("C", "P"):
            _cd = [(kk, vv) for (r_, kk), vv in _cadmid.items() if r_ == _rt]
            _cd2 = [(kk, I.suelo(kk, vv, S, _rt)) for kk, vv in _cd]
            _ev = I.elegir_vert(_cd2, S, ahora()[:5], _rt, _cf["tope"], _cf["ancho"])
            if not _ev:
                continue
            _kl, _pl, _ks, _ps = _ev
            if (_rt, _kl, _ks) in _vistos:
                continue
            _vistos.add((_rt, _kl, _ks))
            PRUEBAS.append((_rt, _kl, _ks,
                            "niv%d a%.0f m%+.1f" % (_saldo, _cf["ancho"], (S - _kl) if _rt == "C" else (_kl - S))))
    # controles: OTM y ATM con ancho 3 (para comparar contra lo que el sistema NO compra)
    PRUEBAS.append(("C", base + 3, base + 3 + 3, "ctrl OTM a3"))
    PRUEBAS.append(("C", base, base + 3, "ctrl ATM a3"))
    for right, kl, ks, etiq in PRUEBAS:
        dl, ds = cad.get((right, float(kl))), cad.get((right, float(ks)))
        if not dl or not ds or None in (dl["bid"], dl["ask"], ds["bid"], ds["ask"]):
            continue
        mid = (dl["mid"] or 0) - (ds["mid"] or 0)
        if mid <= 0.02:
            continue
        bidv, askv = dl["bid"] - ds["ask"], dl["ask"] - ds["bid"]
        r = {"hora": ahora(), "spot": S, "right": right, "k_long": kl, "k_short": ks,
             "etiqueta": etiq, "moneyness": round((S - kl) if right == "C" else (kl - S), 2),
             "mid": round(mid, 3), "bid_vert": round(bidv, 3), "ask_vert": round(askv, 3),
             "spread": round(askv - bidv, 3),
             "spread_pct": round(100.0 * (askv - bidv) / mid, 1) if mid else None}
        print("  %s %-13s mny %+5.2f  mid %.3f (bid %.2f/ask %.2f, spread %.1f%%)"
              % (r["hora"], etiq, r["moneyness"], mid, bidv, askv, r["spread_pct"] or 0), flush=True)

        tr = k.comprar_vertical(EXP, kl, ks, right, mid / 1.01, qty=1)
        est, seg = esperar(k, tr, PACIENCIA)
        _logib = " || ".join("%s %s %s" % (e.time.strftime("%H:%M:%S"), e.status,
                                           (e.message or "")[:120]) for e in tr.log)
        mot = "MARGEN" if "MARGIN" in _logib.upper() else ("RECHAZO" if est == "RECHAZADA" else "")
        r.update(compra_estado=est, compra_seg=seg, compra_motivo=mot,
                 compra_precio=float(tr.orderStatus.avgFillPrice or 0) if est == "Filled" else None)
        if est != "Filled":
            try:
                k.ib.cancelOrder(tr.order)
            except Exception:
                pass
            print("     compra: %s en %ss %s" % (est, seg, ("(%s)" % mot) if mot else ""), flush=True)
            _guardar(r, _logib)
            k.ib.sleep(1)
            continue
        r["slip_compra_pct"] = round(100.0 * (r["compra_precio"] - mid) / mid, 2)
        print("     compra: LLENA a %.3f en %ss (%+.1f%% vs mid)"
              % (r["compra_precio"], seg, r["slip_compra_pct"]), flush=True)

        k.ib.sleep(2)
        cad2 = k.cadena(EXP, S, n=3)
        d2l = cad2.get((right, float(kl))) or dl
        d2s = cad2.get((right, float(ks))) or ds
        mid2 = (d2l["mid"] or 0) - (d2s["mid"] or 0)
        vest, vpre, vseg, forz = vender_al_mid(k, right, kl, ks, mid2)
        r.update(venta_estado=vest, venta_precio=vpre, venta_seg=vseg,
                 venta_mid=round(mid2, 3), forzado=forz)
        if vpre is not None and mid2:
            r["slip_venta_pct"] = round(100.0 * (vpre - mid2) / abs(mid2), 2)
            r["ida_vuelta_pct"] = round(100.0 * (vpre - r["compra_precio"]) / r["compra_precio"], 2)
        print("     venta:  %s a %s en %ss (mid %.3f) %s"
              % (vest, ("%.3f" % vpre) if vpre is not None else "?", vseg, mid2,
                 "[FORZADO A MERCADO]" if forz else ""), flush=True)
        _guardar(r, _logib)
        limpiar_ordenes(k)
        k.ib.sleep(2)


def main():
    k = IBKR()
    k.conectar()
    print("SONDEO CON PACIENCIA | ronda cada %d min | espera al mid %d s | saldo %.2f\n"
          % (INTERVALO, PACIENCIA, k.saldo()), flush=True)
    try:
        while True:
            hm = datetime.datetime.now().strftime("%H:%M")
            if hm < ABRE:
                k.ib.sleep(60)
                continue
            if hm > CIERRA:
                print("\nfin de sesión", flush=True)
                break
            print("── RONDA %s ──" % hm, flush=True)
            try:
                ronda(k)
            except Exception as e:
                print("  ERROR: %s" % e, flush=True)
            ab = k.abiertas(EXP)
            if ab:
                print("  ⚠️ quedan abiertas %s — cerrando" % ab, flush=True)
                k.cerrar_todo(EXP)
            k.ib.sleep(INTERVALO * 60)
    except KeyboardInterrupt:
        print("\ninterrumpido", flush=True)
    finally:
        try:
            ab = k.abiertas(EXP)
            if ab:
                print("cerrando abiertas: %s" % ab, flush=True)
                k.cerrar_todo(EXP)
        except Exception:
            pass
        print("datos en %s (tabla `paciencia`)" % BD, flush=True)
        k.desconectar()


if __name__ == "__main__":
    main()
