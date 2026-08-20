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

DESDE = sys.argv[1] if len(sys.argv) > 1 and ":" in sys.argv[1] else "13:00"
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
        saldo real, log text)""")
    c.execute("create index if not exists ix_dte on dte_cmp(fecha,hora)")
    c.commit()
    return c


def guardar(r):
    c = _bd()
    cols = ["fecha", "hora", "pasada", "spot", "dte", "expiry", "right", "ancho", "mny_obj",
            "k_long", "k_short", "mid", "spread_pct", "estado", "motivo", "precio", "segundos",
            "saldo", "log"]
    c.execute("insert into dte_cmp (%s) values (%s)" % (",".join(cols), ",".join(["?"] * len(cols))),
              [r.get(x) for x in cols])
    c.commit()
    c.close()
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write("%s p%s | %dDTE %s a%s mny%+d | mid %.2f spr %s%% | %s %s\n"
                % (r.get("hora"), r.get("pasada"), r.get("dte"), r.get("right"), r.get("ancho"),
                   r.get("mny_obj"), (r.get("mid") or 0) * 100, r.get("spread_pct"),
                   r.get("estado"), r.get("motivo") or ""))


def una(k, exp, dte, S, right, ancho, mny, pasada, saldo):
    """Una compra concreta en un vencimiento. Devuelve el registro. NO vende: solo mide si IBKR
    ACEPTA y si LLENA. Lo que llene se cierra inmediatamente en el llamador."""
    BF.EXP = exp                     # las piezas reutilizadas leen EXP del módulo
    kl = round(S - mny) if right == "C" else round(S + mny)
    ks = kl + ancho if right == "C" else kl - ancho
    r = {"fecha": FECHA, "hora": BF.ahora(), "pasada": pasada, "spot": S, "dte": dte,
         "expiry": exp, "right": right, "ancho": ancho, "mny_obj": mny,
         "k_long": kl, "k_short": ks, "saldo": saldo}
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
                        # PAREADO: el 0DTE y el siguiente vencimiento, seguidos. `dias_dte`
                        # registra los DÍAS REALES: un viernes el siguiente es el LUNES (3 días).
                        for exp, dte in ((e0, dias_dte(e0)), (e1, dias_dte(e1))):
                            try:
                                r = una(k, exp, dte, S, right, ancho, mny, pasada, saldo)
                            except Exception as ex:
                                r = {"fecha": FECHA, "hora": BF.ahora(), "pasada": pasada,
                                     "dte": dte, "expiry": exp, "right": right, "ancho": ancho,
                                     "mny_obj": mny, "estado": "EXCEPCION",
                                     "motivo": str(ex)[:60], "saldo": saldo}
                            guardar(r)
                            par.append(r)
                            # lo que haya llenado se cierra YA (un 1DTE abierto = riesgo nocturno)
                            if r.get("estado") == "Filled":
                                try:
                                    k.cerrar_todo(exp)
                                except Exception as ex:
                                    print("  ⚠️ no se pudo cerrar %s: %r" % (exp, ex), flush=True)
                        a, b = par[0], par[1]
                        marca = ""
                        if a.get("motivo") == "MARGEN" and b.get("motivo") != "MARGEN":
                            marca = "   <<< EL %dDTE PASA Y EL 0DTE NO" % b.get("dte", 1)
                        elif a.get("motivo") == "MARGEN" and b.get("motivo") == "MARGEN":
                            marca = "   <-- los DOS rechazados: no es el vencimiento"
                        print("  %s %s a%d mny%+d | 0DTE %-10s %-8s (spr %s%%) | %dDTE %-10s %-8s (spr %s%%)%s"
                              % (a.get("hora"), right, ancho, mny,
                                 a.get("estado"), a.get("motivo") or "", a.get("spread_pct"),
                                 b.get("dte", 1),
                                 b.get("estado"), b.get("motivo") or "", b.get("spread_pct"),
                                 marca), flush=True)
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
        print("\ndatos en %s (tabla `dte_cmp`)" % BD, flush=True)
        k.desconectar()


if __name__ == "__main__":
    main()
