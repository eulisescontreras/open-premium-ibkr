# -*- coding: utf-8 -*-
# ¿EL 1DTE ESQUIVA EL RECHAZO POR MARGEN?  (idea del usuario, 2026-08-20 tarde)
#
# LA IDEA: IBKR rechaza con "PROJECTED POST EXPIRATION MARGIN DEFICIT" — proyecta el ejercicio
# AL VENCIMIENTO DE HOY. Si el contrato vence MAÑANA, hoy no hay expiración que proyectar.
#
# LA MECÁNICA LA RESPALDA (mapa medido el 2026-08-20 con 587 órdenes reales):
#   antes de las 12h  0% de rechazo · 12h empieza el ITM · 14h llega al ATM · 15h casi todo
#   el OTM (<=-2) NUNCA se rechaza  <- nunca se proyecta ejercido
# Eso no es "IBKR se pone nervioso por la tarde": es la PROXIMIDAD AL VENCIMIENTO, que es
# exactamente lo que el 1DTE elimina.
#
# ⚠️ ESTO SOLO RESPONDE LA PREGUNTA DEL MARGEN. NO responde si el sistema sigue siendo rentable
# con 1DTE, y ese es el riesgo de verdad: el sistema gana porque el vertical SATURA en el ancho
# (medido: el objetivo al 95% del ancho da 139,7x, y por % del débito DESTRUYE -> 479$). Un 0DTE
# satura porque el tiempo se acaba HOY; un 1DTE tiene un día entero de valor temporal por delante
# y puede no llegar nunca al 95% intradía. Eso necesita datos de 1DTE en el backtest —
# VERIFICADO que `massive_premium.db` NO tiene ni uno: 2.616.094 filas, el 100% es 0DTE.
#
# POR QUÉ ESTA PRUEBA PRIMERO: es barata y puede MATAR la idea en una tarde. Si el 1DTE también
# se rechaza, no hace falta descargar ni analizar nada.
#
# MÉTODO: PAREADO. La MISMA combinación (dirección, ancho, moneyness) se lanza en 0DTE y en 1DTE
# una detrás de otra, en segundos. Así la comparación no depende de la hora ni del mercado —
# que es justo el error que se cometió hoy al confundir "hora" con "saldo".
#
# ⚠️ SEGURIDAD: si un 1DTE LLENA y no se cierra, queda posición ABIERTA DURANTE LA NOCHE. El
# script cierra tras cada prueba y el `finally` cierra AMBOS vencimientos pase lo que pase.
#
# USO:  python barrido_0dte_vs_1dte.py [hora_inicio]     (por defecto 13:00)
import sys, os, time, datetime, sqlite3, io

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "investigacion", "2026-08-19_sistema_real", "scripts"))

from sys2 import config as C
C.IBKR_CLIENT_ID = 34
# se REUTILIZAN las piezas ya probadas del barrido de fills (regla 9: conectar, no duplicar):
# rechazo() sabe distinguir el aviso 10349 de un rechazo real, esperar() y limpiar() evitan el
# "Cannot have open orders on both sides" que contaminó el sondeo del 19.
import barrido_fills_total as BF
from sys2.data.ibkr import IBKR

# TODO EL DÍA, como el barrido del 20. Empezar por la tarde sería un error: el mapa del día 20
# dice que ANTES DE LAS 12:00 NO HAY NI UN RECHAZO, así que sin la mañana no hay curva horaria
# con la que comparar. Y sobre todo: el 49,7% de las operaciones del sistema son a las 09:xx —
# el fill del otro vencimiento POR LA MAÑANA es el dato que más importa.
DESDE = sys.argv[1] if len(sys.argv) > 1 and ":" in sys.argv[1] else "09:30"
HASTA = "15:45"
# el ITM es donde IBKR rechaza; los OTM van de CONTROL (nunca se rechazan: si aquí saliera
# rechazo, el problema no sería el vencimiento y habría que parar y mirar otra cosa).
MONEYNESS = [3, 4, 5, 2, 1, 0, -2]
ANCHOS = [2, 4]
DIRS = ["C", "P"]
FECHA = datetime.date.today().strftime("%Y-%m-%d")
_RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resultados")
BD = os.path.join(RAIZ, "investigacion", "2026-08-19_sistema_real", "resultados", "fills_reales.db")
LOG = os.path.join(_RES, "dte_cmp_%s.log" % FECHA)


def exp_0dte():
    return datetime.date.today().strftime("%Y%m%d")


def exp_1dte():
    """SIGUIENTE vencimiento disponible (el SPY vence de lunes a viernes).

    ⚠️ OJO CON EL NOMBRE (lo señaló el usuario, 2026-08-20): NO siempre es "1DTE". Un VIERNES el
    siguiente vencimiento es el LUNES, o sea **3 días naturales**, no 1. Por eso `dias_dte()`
    registra los días REALES en la BD: llamarlo 1DTE a secas sería mentir en el registro.
    Consecuencia asimétrica:
      - para el MARGEN es MEJOR (más lejos del vencimiento = menos razón para proyectar ejercicio)
      - para la RENTABILIDAD es PEOR (3 días de valor temporal están aún más lejos de saturar
        en el ancho, que es de donde el sistema saca el dinero) -> un VIERNES es el peor día
        para juzgar la rentabilidad, aunque sea un buen día para juzgar el margen.
    """
    d = datetime.date.today() + datetime.timedelta(days=1)
    while d.weekday() >= 5:                    # 5=sáb, 6=dom
        d += datetime.timedelta(days=1)
    return d.strftime("%Y%m%d")


def dias_dte(exp):
    """Días NATURALES hasta el vencimiento (0 para el 0DTE, 1 de lu-ju, 3 el viernes)."""
    d = datetime.datetime.strptime(exp, "%Y%m%d").date()
    return (d - datetime.date.today()).days


def _bd():
    c = sqlite3.connect(BD)
    c.execute("""create table if not exists dte_cmp (
        id integer primary key autoincrement, fecha text, hora text, pasada int, spot real,
        dte int, expiry text, right text, ancho real, mny_obj real, k_long real, k_short real,
        mid real, spread_pct real, estado text, motivo text, precio real, segundos real,
        saldo real, log text,
        venta_estado text, venta_precio real, venta_seg real, venta_mid real, forzado int,
        ida_vuelta_usd real, slip_venta_pct real)""")
    # por si la tabla ya existía de una versión anterior sin columnas de venta
    for col, tipo in (("venta_estado", "text"), ("venta_precio", "real"), ("venta_seg", "real"),
                      ("venta_mid", "real"), ("forzado", "int"), ("ida_vuelta_usd", "real"),
                      ("slip_venta_pct", "real")):
        try:
            c.execute("alter table dte_cmp add column %s %s" % (col, tipo))
        except Exception:
            pass
    c.execute("create index if not exists ix_dte on dte_cmp(fecha,hora)")
    c.commit()
    return c


def guardar(r):
    c = _bd()
    cols = ["fecha", "hora", "pasada", "spot", "dte", "expiry", "right", "ancho", "mny_obj",
            "k_long", "k_short", "mid", "spread_pct", "estado", "motivo", "precio", "segundos",
            "saldo", "log", "venta_estado", "venta_precio", "venta_seg", "venta_mid", "forzado",
            "ida_vuelta_usd", "slip_venta_pct"]
    c.execute("insert into dte_cmp (%s) values (%s)" % (",".join(cols), ",".join(["?"] * len(cols))),
              [r.get(x) for x in cols])
    c.commit()
    c.close()
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write("%s p%s | %dDTE %s a%s mny%+d | mid %.2f spr %s%% | %s %s\n"
                % (r.get("hora"), r.get("pasada"), r.get("dte"), r.get("right"), r.get("ancho"),
                   r.get("mny_obj"), (r.get("mid") or 0) * 100, r.get("spread_pct"),
                   r.get("estado"), r.get("motivo") or ""))


def vender_single(k, exp, kl, right, mid_obj, bid):
    """Escalera de salida para UNA pata. Mismo criterio que `BF.vender` para el vertical: el
    sistema real cierra con `cerrar_todo(espera=8)`, así que la pregunta útil no es "¿llena si
    espero?" sino "¿a qué PRECIO llena en 8 s?". No existía equivalente para single en el repo.
    Termina SIEMPRE a mercado si nada llenó: nunca se deja una pata viva."""
    from ib_insync import LimitOrder
    t0 = time.time()
    logs = []
    semi = max(0.02, (mid_obj - bid)) if (bid is not None and bid < mid_obj) else max(0.02, mid_obj * 0.05)
    for etiq, px in (("mid", mid_obj), ("-50%", mid_obj - semi * 0.5), ("bid", mid_obj - semi)):
        if px <= 0.01:
            continue
        c = k._opt(exp, float(kl), right)
        k.ib.qualifyContracts(c)
        tr = k.ib.placeOrder(c, LimitOrder("SELL", 1, round(px, 2)))
        est, seg, mot = BF.esperar(k, tr, 8)
        logs.append("%s@%.2f:%s" % (etiq, px, est))
        if est == "Filled":
            return ("Filled@" + etiq), float(tr.orderStatus.avgFillPrice or 0), \
                round(time.time() - t0, 1), 0, " || ".join(logs)
        BF.limpiar(k)
    tr = k.cerrar_single(exp, kl, right, qty=1, a_mercado=True)      # nunca dejar la pata viva
    est, seg, mot = BF.esperar(k, tr, 15)
    return ("FORZADO" if est == "Filled" else est), \
        (float(tr.orderStatus.avgFillPrice or 0) if est == "Filled" else None), \
        round(time.time() - t0, 1), 1, " || ".join(logs)


def una(k, exp, dte, S, right, ancho, mny, pasada, saldo, single=False):
    """Una compra concreta en un vencimiento. Devuelve el registro. NO vende: solo mide si IBKR
    ACEPTA y si LLENA. Lo que llene se cierra inmediatamente en el llamador.

    `single=True` compra UNA SOLA PATA (pregunta del usuario 2026-08-20: ¿el bloqueo por margen
    es solo de spreads o también de singles?). NO HAY NI UN DATO: las 606 pruebas del día 20
    fueron todas verticales.
    HIPÓTESIS a contrastar: debería bloquear IGUAL o PEOR. El mensaje es "PROJECTED POST
    EXPIRATION": IBKR simula el vencimiento, y ahí un largo ITM suelto y un vertical cuyo largo
    acaba ITM producen el MISMO ejercicio (100 acciones ≈ 76.400$). Y el single es peor: en el
    vertical, si el precio pasa del strike corto las dos patas se compensan y la exposición
    queda limitada al ancho; en el single no hay nada que compense.
    Importa porque el sistema TIENE modo SINGLE (`instrumento.elegir`) para piramidar y rodar.
    """
    BF.EXP = exp                     # las piezas reutilizadas leen EXP del módulo
    kl = round(S - mny) if right == "C" else round(S + mny)
    ks = None if single else (kl + ancho if right == "C" else kl - ancho)
    r = {"fecha": FECHA, "hora": BF.ahora(), "pasada": pasada, "spot": S, "dte": dte,
         "expiry": exp, "right": right, "ancho": (0 if single else ancho), "mny_obj": mny,
         "k_long": kl, "k_short": ks, "saldo": saldo}
    if single:
        try:
            cad = k.cadena(exp, S, n=8)
            d = cad.get((right, float(kl)))
            if not d or d.get("mid") is None:
                r.update(estado="SIN_LIBRO")
                return r
            r["mid"] = round(d["mid"], 3)
            if d.get("bid") is not None and d.get("ask") is not None and d["mid"]:
                r["spread_pct"] = round(100.0 * (d["ask"] - d["bid"]) / d["mid"], 1)
            BF.limpiar(k)
            tr = k.comprar_single(exp, kl, right, d["mid"], qty=1)
            est, seg, mot = BF.esperar(k, tr, 25)
            r.update(estado=est, motivo=mot, segundos=seg)
            r["log"] = " || ".join("%s %s" % (e.status, (e.message or "")[:60]) for e in tr.log)
            if est == "Filled":
                r["precio"] = float(tr.orderStatus.avgFillPrice or 0)
                # IDA Y VUELTA COMPLETA: sin vender no se mide el coste de SALIDA, que es lo que
                # dispara el drawdown (-23.673$ del 21,1% al 36,9%). Si el otro vencimiento se
                # vende peor, habríamos cambiado un problema por otro sin enterarnos.
                k.ib.sleep(1)
                c2 = k.cadena(exp, S, n=4).get((right, float(kl))) or d
                m2 = c2.get("mid") or d["mid"]
                vest, vpre, vseg, forz, vlog = vender_single(k, exp, kl, right, m2, c2.get("bid"))
                r.update(venta_estado=vest, venta_precio=vpre, venta_seg=vseg,
                         venta_mid=round(m2, 3), forzado=forz)
                if vpre is not None:
                    r["ida_vuelta_usd"] = round((vpre - r["precio"]) * 100, 2)
                    if m2:
                        r["slip_venta_pct"] = round(100.0 * (vpre - m2) / abs(m2), 2)
        except Exception as ex:
            r.update(estado="ERROR", motivo=str(ex)[:60])
        BF.limpiar(k)
        return r
    try:
        cad = k.cadena(exp, S, n=8)
    except Exception as ex:
        r.update(estado="SIN_CADENA", motivo=str(ex)[:60])
        return r
    dl, ds = cad.get((right, float(kl))), cad.get((right, float(ks)))
    if not dl or not ds or None in (dl.get("bid"), dl.get("ask"), ds.get("bid"), ds.get("ask")):
        r.update(estado="SIN_LIBRO")
        return r
    mid = (dl["mid"] or 0) - (ds["mid"] or 0)
    if mid <= 0.02:
        r.update(estado="MID_NULO", mid=mid)
        return r
    bidv, askv = dl["bid"] - ds["ask"], dl["ask"] - ds["bid"]
    r["mid"] = round(mid, 3)
    r["spread_pct"] = round(100.0 * (askv - bidv) / mid, 1) if mid else None

    BF.limpiar(k)
    try:
        tr = k.comprar_vertical(exp, kl, ks, right, mid / 1.01, qty=1)
        est, seg, mot = BF.esperar(k, tr, 25)
        r.update(estado=est, motivo=mot, segundos=seg)
        r["log"] = " || ".join("%s %s" % (e.status, (e.message or "")[:60]) for e in tr.log)
        if est == "Filled":
            r["precio"] = float(tr.orderStatus.avgFillPrice or 0)
            # IDA Y VUELTA COMPLETA con la escalera YA PROBADA del barrido del 20 (regla 9):
            # baja por escalones (mid del combo, -25%, -50%, bid, bid-1) con 8 s cada uno, que es
            # lo que espera el sistema real, y registra EN QUÉ ESCALÓN llenó. Ese es el descuento
            # verdadero. El 20 de agosto: 139 de 139 ventas acabaron forzadas a mercado.
            k.ib.sleep(1)
            cad2 = k.cadena(exp, S, n=8)
            d2l = cad2.get((right, float(kl))) or dl
            d2s = cad2.get((right, float(ks))) or ds
            mid2 = (d2l["mid"] or 0) - (d2s["mid"] or 0)
            bid2 = (d2l.get("bid") or 0) - (d2s.get("ask") or 0)
            vest, vpre, vseg, vmot, forz, vlog = BF.vender(k, right, kl, ks, mid2, bid2)
            r.update(venta_estado=vest, venta_precio=vpre, venta_seg=vseg,
                     venta_mid=round(mid2, 3), forzado=forz)
            if vpre is not None:
                r["ida_vuelta_usd"] = round((vpre - r["precio"]) * 100, 2)
                if mid2:
                    r["slip_venta_pct"] = round(100.0 * (vpre - mid2) / abs(mid2), 2)
    except Exception as ex:
        r.update(estado="ERROR", motivo=str(ex)[:60])
    BF.limpiar(k)
    return r


def main():
    e0, e1 = exp_0dte(), exp_1dte()
    k = IBKR()
    k.conectar()
    print("COMPARATIVA 0DTE vs 1DTE | 0DTE=%s  1DTE=%s | desde %s hasta %s | saldo %.2f\n"
          % (e0, e1, DESDE, HASTA, k.saldo()), flush=True)
    pasada = 0
    try:
        while True:
            hm = datetime.datetime.now().strftime("%H:%M")
            if hm < DESDE:
                print("  esperando a %s (ahora %s)" % (DESDE, hm), flush=True)
                k.ib.sleep(30)
                continue
            if hm > HASTA:
                break
            pasada += 1
            S = BF.spot_actual(k)
            if S is None:
                k.ib.sleep(20)
                continue
            saldo = k.saldo()
            print("\n═══ PASADA %d — %s — spot %.2f — saldo %.0f ═══" % (pasada, hm, S, saldo),
                  flush=True)
            for mny in MONEYNESS:
                for ancho in ANCHOS:
                    for right in DIRS:
                        if datetime.datetime.now().strftime("%H:%M") > HASTA:
                            break
                        par = []
                        # PAREADO A TRES: 0DTE vertical, siguiente vencimiento vertical, y 0DTE
                        # SINGLE — los tres seguidos, en segundos, para que la comparación no
                        # dependa de la hora ni del estado del mercado.
                        # `dias_dte` registra los DÍAS REALES: un viernes el siguiente es el
                        # LUNES (3 días), no 1.
                        # El SINGLE responde la otra pregunta del usuario: ¿el bloqueo por margen
                        # es cosa de spreads o también pasa con una sola pata? NO HAY NI UN DATO.
                        # MATRIZ COMPLETA 2x2: vencimiento (0DTE / siguiente) x tipo (vertical /
                        # single). Responde LAS DOS preguntas y además su interacción: si el
                        # bloqueo fuera cosa del vencimiento, las dos filas de "siguiente"
                        # pasarían; si fuera cosa de tener DOS patas, pasarían las dos de single.
                        casos = ((e0, dias_dte(e0), False),      # vertical 0DTE   (el de hoy)
                                 (e1, dias_dte(e1), False),      # vertical siguiente vencimiento
                                 (e0, dias_dte(e0), True),       # SINGLE 0DTE
                                 (e1, dias_dte(e1), True))       # SINGLE siguiente vencimiento
                        for exp, dte, es_single in casos:
                            if es_single and ancho != ANCHOS[0]:
                                continue      # el single no depende del ancho: una vez por mny
                            try:
                                r = una(k, exp, dte, S, right, ancho, mny, pasada, saldo,
                                        single=es_single)
                            except Exception as ex:
                                r = {"fecha": FECHA, "hora": BF.ahora(), "pasada": pasada,
                                     "dte": dte, "expiry": exp, "right": right,
                                     "ancho": (0 if es_single else ancho),
                                     "mny_obj": mny, "estado": "EXCEPCION",
                                     "motivo": str(ex)[:60], "saldo": saldo}
                            guardar(r)
                            par.append(r)
                            # RED DE SEGURIDAD: `una()` ya vende, pero si la venta no llenó hay
                            # que cerrar igual. Un contrato del vencimiento siguiente que se
                            # quede abierto es exposición TODA LA NOCHE (o el fin de semana).
                            vok = str(r.get("venta_estado") or "")
                            if r.get("estado") == "Filled" and not (
                                    vok.startswith("Filled") or vok == "FORZADO"):
                                try:
                                    k.cerrar_todo(exp)
                                    print("  ⚠️ venta no llenó (%s) -> cerrado a mercado" % vok,
                                          flush=True)
                                except Exception as ex:
                                    print("  ⚠️ NO SE PUDO CERRAR %s: %r — REVISAR" % (exp, ex),
                                          flush=True)
                        def _et(x):
                            return "%s%dDTE" % ("SGL " if not x.get("k_short") else "vert",
                                                x.get("dte", 0))

                        def _tx(x):
                            m = x.get("motivo") or ""
                            return "%s:%s%s" % (_et(x), x.get("estado"),
                                                ("/" + m) if m else "")
                        base = par[0]
                        alt = [x for x in par[1:] if x.get("motivo") != "MARGEN"]
                        marca = ""
                        if base.get("motivo") == "MARGEN":
                            marca = ("   <<< PASAN: %s" % ", ".join(_et(x) for x in alt)) if alt \
                                else "   <-- RECHAZADAS TODAS: no es el vencimiento ni las patas"
                        print("  %s %s a%d mny%+d | %s%s"
                              % (base.get("hora"), right, ancho, mny,
                                 "  ".join(_tx(x) for x in par), marca), flush=True)
            print("  -> fin de la pasada %d" % pasada, flush=True)
    except KeyboardInterrupt:
        print("\ninterrumpido", flush=True)
    finally:
        # SEGURIDAD: cerrar AMBOS vencimientos pase lo que pase. Un 1DTE olvidado es
        # exposición durante toda la noche.
        for exp in (e0, e1):
            try:
                BF.limpiar(k)
                ab = k.abiertas(exp)
                if ab:
                    print("cerrando abiertas en %s: %s" % (exp, ab), flush=True)
                    k.cerrar_todo(exp)
            except Exception as ex:
                print("⚠️ ERROR cerrando %s: %r — REVISAR A MANO" % (exp, ex), flush=True)
        try:
            for exp in (e0, e1):
                ab = k.abiertas(exp)
                if ab:
                    print("🚨 QUEDAN POSICIONES ABIERTAS EN %s: %s — CERRAR A MANO" % (exp, ab),
                          flush=True)
        except Exception:
            pass
        resumen()
        print("\ndatos en %s (tabla `dte_cmp`)" % BD, flush=True)
        k.desconectar()


def resumen():
    """QUÉ OPCIÓN ES VIABLE. Se imprime SIEMPRE al terminar, incluso si se interrumpe."""
    try:
        c = sqlite3.connect(BD)
        c.row_factory = sqlite3.Row
        filas = [dict(r) for r in c.execute("select * from dte_cmp where fecha=?", (FECHA,))]
        c.close()
        if not filas:
            print("\n(sin datos que resumir)", flush=True)
            return
        print("\n" + "=" * 96, flush=True)
        print("¿QUÉ OPCIÓN ES VIABLE? — %d pruebas del %s" % (len(filas), FECHA), flush=True)
        print("=" * 96, flush=True)
        print("%-22s %6s %9s %9s %9s %9s"
              % ("opción", "n", "%rechazo", "%fill", "spread~", "n ITM"), flush=True)
        grupos = {}
        for f in filas:
            tipo = "SINGLE" if not f.get("k_short") else "vertical"
            grupos.setdefault("%-8s %dDTE" % (tipo, f.get("dte") or 0), []).append(f)
        for et in sorted(grupos):
            g = grupos[et]
            rech = sum(1 for x in g if x.get("motivo") == "MARGEN")
            noR = [x for x in g if x.get("motivo") != "MARGEN"]
            fill = sum(1 for x in noR if x.get("estado") == "Filled")
            sp = [x["spread_pct"] for x in g if x.get("spread_pct") is not None]
            itm = sum(1 for x in g if (x.get("mny_obj") or 0) > 0)
            print("%-22s %6d %8.0f%% %8s %8s%% %9d"
                  % (et, len(g), 100.0 * rech / len(g),
                     ("%.0f%%" % (100.0 * fill / len(noR))) if noR else "-",
                     ("%.1f" % (sum(sp) / len(sp))) if sp else "-", itm), flush=True)
        print("\nCOSTE DE EJECUCIÓN (ida y vuelta REAL) — el 20/08 fue -2,12$ y 139 de 139", flush=True)
        print("ventas acabaron FORZADAS a mercado. Aquí se ve si el otro vencimiento es mejor o peor:",
              flush=True)
        print("%-22s %6s %11s %11s %10s" % ("opción", "n ops", "ida-vuelta~", "slip venta~",
                                            "%forzadas"), flush=True)
        for et in sorted(grupos):
            g = [x for x in grupos[et] if x.get("ida_vuelta_usd") is not None]
            if not g:
                print("%-22s %6s %11s %11s %10s" % (et, 0, "-", "-", "-"), flush=True)
                continue
            iv = sum(x["ida_vuelta_usd"] for x in g) / len(g)
            sv = [x["slip_venta_pct"] for x in g if x.get("slip_venta_pct") is not None]
            fz = sum(1 for x in g if x.get("forzado"))
            print("%-22s %6d %+10.2f$ %10s%% %9.0f%%"
                  % (et, len(g), iv, ("%.2f" % (sum(sv) / len(sv))) if sv else "-",
                     100.0 * fz / len(g)), flush=True)

        print("\nSOLO ITM (mny>0), que es donde el 0DTE se bloquea por la tarde:", flush=True)
        for et in sorted(grupos):
            g = [x for x in grupos[et] if (x.get("mny_obj") or 0) > 0]
            if not g:
                continue
            rech = sum(1 for x in g if x.get("motivo") == "MARGEN")
            print("   %-22s n=%-4d rechazo %.0f%%" % (et, len(g), 100.0 * rech / len(g)),
                  flush=True)
        print("\nLECTURA: si el bloqueo fuese cosa del VENCIMIENTO, las dos filas del vencimiento",
              flush=True)
        print("siguiente irían a 0%. Si fuese cosa de tener DOS PATAS, irían a 0% las de SINGLE.",
              flush=True)
        print("Si NINGUNA baja, el bloqueo es del LARGO ITM y no lo esquiva ningún instrumento.",
              flush=True)
    except Exception as ex:
        print("\nresumen(): %r" % ex, flush=True)


if __name__ == "__main__":
    main()
