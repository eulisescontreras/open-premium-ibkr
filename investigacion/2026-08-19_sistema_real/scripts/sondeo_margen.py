# -*- coding: utf-8 -*-
# SONDEO DE MARGEN + FILLS — la medición que decide si el sistema vale 149x o no vale nada.
#
# PREGUNTA 1 (crítica): ¿A QUÉ HORA empieza IBKR a rechazar con "PROJECTED POST EXPIRATION
#   MARGIN DEFICIT"? Medido el 2026-08-19: aceptó a las 09:31-09:52 y rechazó a las 15:17
#   (5 de 6 órdenes, incluso cruzando el spread). Impacto sobre 485 sesiones:
#     solo OTM desde las 14:00 -> -7%  |  solo OTM todo el día -> EL SISTEMA MUERE (340$)
#   Con 2 puntos sueltos no hay curva. Este script sondea CADA `INTERVALO` minutos.
#
# PREGUNTA 2: ¿cuánto cuesta la EJECUCIÓN de verdad? 2% -> 129x | 5% -> 100x | 10% -> MUERE.
#   Se manda la orden al MID (lo que asume el backtest) y se mide el precio conseguido.
#
# MÉTODO: en cada ronda prueba 4 verticales con moneyness CRECIENTE del largo (de muy OTM a
# ITM profundo). Así no solo se sabe SI rechaza, sino DÓNDE está la frontera en cada momento.
# Todo con las FUNCIONES REALES (ibkr.cadena / comprar_vertical / cerrar_todo), clientId 34.
#
# USO:  python sondeo_margen.py [minutos_entre_rondas]     (por defecto 30)
#       python sondeo_margen.py 30 --seco                  (NO envía órdenes, solo lee cadena)
import sys, os, json, time, datetime, sqlite3

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
C.IBKR_CLIENT_ID = 34
from sys2.data.ibkr import IBKR

INTERVALO = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
SECO = "--seco" in sys.argv
ANCHO = 2.0
ESPERA_FILL = 10                 # segundos antes de dar la orden por no llenada
EXP = datetime.date.today().strftime("%Y%m%d")
FECHA = datetime.date.today().strftime("%Y-%m-%d")
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resultados",
                      "sondeo_margen_%s.json" % FECHA)
ABRE, CIERRA = "09:30", "15:55"


def ahora():
    return datetime.datetime.now().strftime("%H:%M:%S")


def spot_actual(k):
    """Último close de SPY en sys2.db; si no hay, lo pide a IBKR."""
    c = sqlite3.connect(os.path.join(RAIZ, "sys2.db"))
    r = c.execute("select close from bars where fecha=? order by hora desc limit 1",
                  (FECHA,)).fetchone()
    c.close()
    if r:
        return float(r[0])
    b = k.backfill_spy(dur="120 S")
    return float(b[-1][4]) if b else None


def ronda(k, res):
    """Una ronda de sondeo: 4 verticales de moneyness creciente. Devuelve nº de pruebas."""
    S = spot_actual(k)
    if S is None:
        print("  %s  sin spot todavía" % ahora(), flush=True)
        return 0
    cad = k.cadena(EXP, S, n=5)
    base = round(S)
    # largo de MUY OTM a ITM PROFUNDO -> localiza la frontera del rechazo
    PRUEBAS = [("C", base + 2, base + 2 + ANCHO, "OTM lejos"),
               ("C", base, base + ANCHO, "ATM"),
               ("P", base + 1, base + 1 - ANCHO, "ITM leve"),
               ("P", base + 3, base + 3 - ANCHO, "ITM profundo")]
    n = 0
    for right, kl, ks, etiq in PRUEBAS:
        dl, ds = cad.get((right, float(kl))), cad.get((right, float(ks)))
        if not dl or not ds or None in (dl["bid"], dl["ask"], ds["bid"], ds["ask"]):
            continue
        mid = (dl["mid"] or 0) - (ds["mid"] or 0)
        if mid <= 0.02:
            continue
        mny = (S - kl) if right == "C" else (kl - S)
        spread = (dl["ask"] - ds["bid"]) - (dl["bid"] - ds["ask"])
        r = {"hora": ahora(), "spot": S, "right": right, "k_long": kl, "k_short": ks,
             "etiqueta": etiq, "moneyness": round(mny, 2), "mid": round(mid, 3),
             "spread": round(spread, 3),
             "spread_pct": round(100.0 * spread / mid, 1) if mid else None,
             "largo_bid": dl["bid"], "largo_ask": dl["ask"],
             "corto_bid": ds["bid"], "corto_ask": ds["ask"]}
        if SECO:
            res.append(r); n += 1
            print("  %s %-13s mny %+5.2f  mid %.3f  spread %.1f%%  [SECO]"
                  % (r["hora"], etiq, mny, mid, r["spread_pct"] or 0), flush=True)
            continue

        t0 = time.time()
        tr = k.comprar_vertical(EXP, kl, ks, right, mid / 1.01, qty=1)
        for _ in range(ESPERA_FILL * 2):
            k.ib.sleep(0.5)
            if tr.orderStatus.status in ("Filled", "Cancelled", "Inactive", "ApiCancelled"):
                if tr.orderStatus.status == "Filled":
                    break
        dt = round(time.time() - t0, 1)
        est = tr.orderStatus.status
        precio = float(tr.orderStatus.avgFillPrice or 0)
        # motivo del rechazo (lo que de verdad queremos saber)
        motivo = ""
        for e in tr.log:
            m = (e.message or "")
            if "MARGIN" in m.upper():
                motivo = "MARGEN"
            elif "Error 201" in m and not motivo:
                motivo = m[:70]
        r.update(estado=est, precio=precio, segundos=dt, motivo=motivo,
                 slippage_pct=(round(100.0 * (precio - mid) / mid, 2)
                               if (est == "Filled" and mid) else None))
        marca = "LLENO" if est == "Filled" else ("RECHAZO-MARGEN" if motivo == "MARGEN" else est)
        print("  %s %-13s mny %+5.2f  mid %.3f  -> %-15s %s"
              % (r["hora"], etiq, mny, mid,
                 marca, ("%.3f (%+.1f%%) en %.1fs" % (precio, r["slippage_pct"] or 0, dt))
                 if est == "Filled" else ""), flush=True)

        if est == "Filled":                      # cerrar y medir también la SALIDA
            k.ib.sleep(1)
            cad2 = k.cadena(EXP, S, n=2)
            d2l = cad2.get((right, float(kl))) or dl
            d2s = cad2.get((right, float(ks))) or ds
            mid2 = (d2l["mid"] or 0) - (d2s["mid"] or 0)
            t1 = time.time()
            plana, precios = k.cerrar_todo(EXP, right=right, qty=1)
            cobrado = None
            if precios and float(kl) in precios and float(ks) in precios:
                cobrado = precios[float(kl)] - precios[float(ks)]
            r.update(venta_plana=plana, venta_cobrado=cobrado, venta_mid=round(mid2, 3),
                     venta_seg=round(time.time() - t1, 1),
                     venta_slippage_pct=(round(100.0 * (cobrado - mid2) / abs(mid2), 2)
                                         if (cobrado is not None and mid2) else None))
            print("       cierre: cobrado %s (mid %.3f) %s"
                  % (("%.3f" % cobrado) if cobrado is not None else "?", mid2,
                     "" if plana else "*** NO QUEDÓ PLANA ***"), flush=True)
        else:
            try:
                k.ib.cancelOrder(tr.order)
            except Exception:
                pass
        res.append(r); n += 1
        k.ib.sleep(1)
    return n


def main():
    res = []
    if os.path.exists(SALIDA):
        try:
            res = json.load(open(SALIDA))
            print("continuando: %d pruebas previas" % len(res))
        except Exception:
            res = []
    k = IBKR()
    k.conectar()
    print("SONDEO DE MARGEN  |  cada %d min  |  %s  |  saldo %.2f\n"
          % (INTERVALO, "SECO (sin órdenes)" if SECO else "ÓRDENES REALES", k.saldo()), flush=True)
    try:
        while True:
            hm = datetime.datetime.now().strftime("%H:%M")
            if hm < ABRE:
                print("  %s  mercado cerrado, esperando a las %s..." % (ahora(), ABRE), flush=True)
                k.ib.sleep(60)
                continue
            if hm > CIERRA:
                print("\n%s  fin de sesión." % ahora(), flush=True)
                break
            print("── RONDA %s ──" % hm, flush=True)
            try:
                ronda(k, res)
            except Exception as e:
                print("  ERROR en la ronda: %s" % e, flush=True)
            json.dump(res, open(SALIDA, "w"), indent=1)
            ab = k.abiertas(EXP)
            if ab:
                print("  ⚠️ quedan posiciones abiertas %s — cerrando" % ab, flush=True)
                k.cerrar_todo(EXP)
            k.ib.sleep(INTERVALO * 60)
    except KeyboardInterrupt:
        print("\ninterrumpido por el usuario", flush=True)
    finally:
        json.dump(res, open(SALIDA, "w"), indent=1)
        try:
            ab = k.abiertas(EXP)
            if ab:
                print("cerrando posiciones abiertas: %s" % ab, flush=True)
                k.cerrar_todo(EXP)
        except Exception:
            pass
        print("\n%d pruebas guardadas en %s" % (len(res), SALIDA), flush=True)
        k.desconectar()


if __name__ == "__main__":
    main()
