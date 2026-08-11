"""
direccion_premium.py — READ-ONLY

Pregunta unica: ¿hay algun patron en el PREMIUM POR STRIKE que anticipe la direccion
del SPY? Cruza `premium_minute` (flujo por strike) contra `ta_minute.spy` (el movimiento
real del subyacente) en varios horizontes.

Metodo (las trampas ya documentadas en ANALISIS_ENTRADA_SALIDA.md):
  - Nunca se juzga por % de acierto. Se juzga por LIFT sobre la TASA BASE del dia.
  - El lift se mide CONDICIONADO a cada direccion por separado:
        lift_UP   = P(sube | senal>0) - P(sube)
        lift_DOWN = P(baja | senal<0) - P(baja)
    Una senal que solo dispara hacia un lado infla el acierto global; asi no.
  - Se reporta n TOTAL y n NO SOLAPADO (ventanas independientes). Con solape, la
    significancia aparente es falsa.
  - Nada de mirar primero los casos buenos: se corren TODAS las variables de golpe.

Uso:
    python analisis\direccion_premium.py                 # todas las fechas con datos
    python analisis\direccion_premium.py 2026-08-10      # una fecha
    python analisis\direccion_premium.py --sin-contaminar  # excluye 08-11 despues de 12:24
"""
import sqlite3
import sys
import os
import math
from collections import defaultdict

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spy_history.db")

HORIZONTES = [1, 3, 5, 10, 15, 30]      # minutos hacia adelante
CONTAMINADO_DESDE = "12:24"             # premium fantasma del recentrado (2026-08-11)


# ---------------------------------------------------------------- utilidades
def hhmm_a_min(h):
    return int(h[:2]) * 60 + int(h[3:5])


def spearman(xs, ys):
    """Correlacion de rangos, sin scipy. Devuelve None si no hay varianza."""
    n = len(xs)
    if n < 10:
        return None

    def rangos(v):
        orden = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[orden[j + 1]] == v[orden[i]]:
                j += 1
            medio = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[orden[k]] = medio
            i = j + 1
        return r

    rx, ry = rangos(xs), rangos(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


# ---------------------------------------------------------------- carga
def cargar_precio(c, fecha):
    """minuto -> spy. Fuente: ta_minute (la unica serie de precio por minuto)."""
    filas = c.execute(
        "SELECT hora, spy FROM ta_minute WHERE fecha=? AND spy IS NOT NULL ORDER BY hora",
        (fecha,)).fetchall()
    return {hhmm_a_min(h): s for h, s in filas}


def cargar_premium(c, fecha, expiry):
    """hora -> {(strike,right): dict}. Solo la expiry pedida."""
    filas = c.execute(
        "SELECT hora, strike, right, day_prem, net_prem, day_vol, gamma, open_interest "
        "FROM premium_minute WHERE fecha=? AND expiry=? ORDER BY hora", (fecha, expiry)).fetchall()
    snaps = defaultdict(dict)
    for h, k, r, dp, np_, dv, g, oi in filas:
        snaps[h][(k, r)] = {"day_prem": dp, "net_prem": np_, "day_vol": dv,
                            "gamma": g, "oi": oi}
    return snaps


# ---------------------------------------------------------------- features
def features_de_snapshot(actual, previo, spot, previo_neto=None):
    """
    Todas las variables direccionales que se pueden construir con el premium
    POR STRIKE de un snapshot. `previo` da el flujo NUEVO (delta).
    Devuelve dict nombre -> valor (o None si no se puede calcular).
    """
    f = {}

    # --- flujo NUEVO por strike (delta de day_prem contra el snapshot anterior)
    nuevo = {}
    resets = 0
    for key, d in actual.items():
        dp = d["day_prem"]
        if dp is None:
            continue
        antes = previo.get(key, {}).get("day_prem") if previo else None
        if antes is None:
            continue
        delta = dp - antes
        if delta < 0:            # reinicio de la app / reset: no es flujo
            resets += 1
            continue
        nuevo[key] = delta
    f["_resets"] = resets
    f["_n_strikes"] = len(nuevo)

    if not nuevo:
        return f

    # particiones por tipo y por moneyness (regla del codigo: OTM call = strike>spot)
    cal_otm = sum(v for (k, r), v in nuevo.items() if r == "C" and k > spot)
    cal_itm = sum(v for (k, r), v in nuevo.items() if r == "C" and k <= spot)
    put_otm = sum(v for (k, r), v in nuevo.items() if r == "P" and k < spot)
    put_itm = sum(v for (k, r), v in nuevo.items() if r == "P" and k >= spot)
    cal_tot, put_tot = cal_otm + cal_itm, put_otm + put_itm
    tot = cal_tot + put_tot

    # --- 1. BRUTO: call vs put (lo que hace hoy la senal, pero con flujo nuevo)
    f["bruto_C_menos_P"] = cal_tot - put_tot
    f["bruto_ratio_CP"] = (cal_tot / put_tot - 1.0) if put_tot > 0 else None

    # --- 2. BRUTO solo OTM: la apuesta direccional pura (lo que se compra para ganar)
    f["bruto_OTM_C_menos_P"] = cal_otm - put_otm
    f["bruto_OTM_ratio"] = (cal_otm / put_otm - 1.0) if put_otm > 0 else None

    # --- 3. BRUTO solo ITM (cobertura / cierre de posiciones)
    f["bruto_ITM_C_menos_P"] = cal_itm - put_itm

    # --- 4. DINERO POR ENCIMA vs POR DEBAJO del precio (ignora call/put)
    arriba = sum(v for (k, r), v in nuevo.items() if k > spot)
    abajo = sum(v for (k, r), v in nuevo.items() if k < spot)
    f["dinero_arriba_menos_abajo"] = arriba - abajo

    # --- 5. CENTRO DE GRAVEDAD del flujo nuevo, relativo al precio
    if tot > 0:
        centro = sum(k * v for (k, r), v in nuevo.items()) / tot
        f["centro_flujo_menos_spot"] = centro - spot
    else:
        f["centro_flujo_menos_spot"] = None

    # --- 6. Centro de gravedad SOLO calls y SOLO puts (hacia donde apunta cada lado)
    if cal_tot > 0:
        f["centro_calls_menos_spot"] = \
            sum(k * v for (k, r), v in nuevo.items() if r == "C") / cal_tot - spot
    if put_tot > 0:
        f["centro_puts_menos_spot"] = \
            sum(k * v for (k, r), v in nuevo.items() if r == "P") / put_tot - spot

    # --- 7. Flujo ponderado por DISTANCIA al spot (premia las apuestas lejanas)
    f["flujo_pond_distancia"] = sum((k - spot) * v for (k, r), v in nuevo.items())

    # --- 8. Flujo ponderado por GAMMA (donde el dealer tiene que cubrirse)
    g = 0.0
    hay_g = False
    for (k, r), v in nuevo.items():
        gam = actual[(k, r)].get("gamma")
        if gam:
            hay_g = True
            g += gam * v * (1 if r == "C" else -1)
    f["flujo_pond_gamma"] = g if hay_g else None

    # --- 9. NETO firmado (roto al 92%, se mide igual para comparar)
    #     OJO: net_prem solo existe en las filas de walls (cada 3 min). Si no hay
    #     NINGUNA en este snapshot la variable es None, NO cero: tratar el ausente
    #     como 0 metia 371 falsos empates y contaminaba la tasa base.
    hay_neto = any(d["net_prem"] is not None for d in actual.values())
    if hay_neto:
        # OJO: net_prem es ACUMULADO del dia (spy_direction.py:1458 lo suma sobre
        # si mismo), NO el flujo del intervalo. Como NIVEL es un cronometro.
        nc = sum(d["net_prem"] or 0 for (k, r), d in actual.items() if r == "C")
        npu = sum(d["net_prem"] or 0 for (k, r), d in actual.items() if r == "P")
        f["netoNIVEL_C_menos_P"] = nc - npu
        nc_otm = sum(d["net_prem"] or 0 for (k, r), d in actual.items() if r == "C" and k > spot)
        np_otm = sum(d["net_prem"] or 0 for (k, r), d in actual.items() if r == "P" and k < spot)
        f["netoNIVEL_OTM_C_menos_P"] = nc_otm - np_otm

        # --- NETO NUEVO: la diferencia contra el snapshot anterior. Esto SI es
        #     flujo firmado del intervalo: "quien esta cruzando el spread AHORA".
        #     Es la unica variable del barrido que lleva direccion de verdad.
        # El snapshot inmediatamente anterior suele ser una fila de minuto SIN
        # net_prem (solo lo traen las de walls, cada 3 min). Hay que restar contra
        # el ultimo que SI lo tenia, o el delta no existe nunca.
        ref = previo_neto if previo_neto else previo
        dnet = {}
        for key, d in actual.items():
            v = d["net_prem"]
            if v is None:
                continue
            antes = ref.get(key, {}).get("net_prem") if ref else None
            if antes is None:
                continue
            dnet[key] = v - antes
        if dnet:
            f["_n_neto_nuevo"] = len(dnet)
            nc = sum(v for (k, r), v in dnet.items() if r == "C")
            npu = sum(v for (k, r), v in dnet.items() if r == "P")
            f["netoNUEVO_C_menos_P"] = nc - npu
            f["netoNUEVO_suma"] = nc + npu          # dinero neto entrando, sin distinguir lado
            # por zona respecto al precio
            cerca_c = sum(v for (k, r), v in dnet.items() if r == "C" and abs(k - spot) <= 1)
            cerca_p = sum(v for (k, r), v in dnet.items() if r == "P" and abs(k - spot) <= 1)
            f["netoNUEVO_atm_C_menos_P"] = cerca_c - cerca_p
            otm_c = sum(v for (k, r), v in dnet.items() if r == "C" and k > spot)
            otm_p = sum(v for (k, r), v in dnet.items() if r == "P" and k < spot)
            f["netoNUEVO_OTM_C_menos_P"] = otm_c - otm_p

    # --- 13. CUBOS DE DISTANCIA CON SIGNO: donde se pone el dinero respecto al precio.
    #     Con distancia ABSOLUTA un call a +1.5 (OTM, apuesta alcista) caia en el
    #     mismo cubo que uno a -1.5 (ITM, casi siempre cierre) y se cancelaban.
    #     d>0 = strike POR ENCIMA del precio; d<0 = por debajo.
    def zona(lo, hi):
        """flujo call y put con (k-spot) en [lo,hi)."""
        cc = sum(v for (k, r), v in nuevo.items() if r == "C" and lo <= (k - spot) < hi)
        pp = sum(v for (k, r), v in nuevo.items() if r == "P" and lo <= (k - spot) < hi)
        return cc, pp

    zonas = {}
    for lo, hi, eti in ((0, 1, "sup0a1"), (1, 2, "sup1a2"), (2, 4, "sup2a4"),
                        (-1, 0, "inf0a1"), (-2, -1, "inf1a2"), (-4, -2, "inf2a4")):
        cc, pp = zona(lo, hi)
        zonas[eti] = (cc, pp)
        f["z_%s_C_menos_P" % eti] = cc - pp
        if pp > 0 and cc > 0:
            f["z_%s_ratio" % eti] = cc / pp - 1.0

    # --- 14. ATM estricto (+-1 strike alrededor del precio): las dos mitades juntas
    cc = zonas["sup0a1"][0] + zonas["inf0a1"][0]
    pp = zonas["sup0a1"][1] + zonas["inf0a1"][1]
    f["atm_C_menos_P"] = cc - pp
    if cc > 0 and pp > 0:
        f["atm_ratio"] = cc / pp - 1.0

    # --- 15. CERCA vs LEJOS: la hipotesis de que las dos zonas dicen cosas
    #     OPUESTAS y por eso el agregado total se cancela.
    cerca = (zonas["sup0a1"][0] + zonas["inf0a1"][0]) - \
            (zonas["sup0a1"][1] + zonas["inf0a1"][1])
    lejos = (zonas["sup1a2"][0] + zonas["sup2a4"][0] +
             zonas["inf1a2"][0] + zonas["inf2a4"][0]) - \
            (zonas["sup1a2"][1] + zonas["sup2a4"][1] +
             zonas["inf1a2"][1] + zonas["inf2a4"][1])
    f["cerca_menos_lejos"] = cerca - lejos
    tot_cl = abs(cerca) + abs(lejos)
    if tot_cl > 0:
        f["cerca_menos_lejos_norm"] = (cerca - lejos) / tot_cl

    # --- 10. ACUMULADO del dia (nivel, no flujo): centro de gravedad de day_prem
    acu = {key: d["day_prem"] for key, d in actual.items() if d["day_prem"]}
    if acu:
        ta = sum(acu.values())
        if ta > 0:
            f["centro_acum_menos_spot"] = \
                sum(k * v for (k, r), v in acu.items()) / ta - spot
        ac = sum(v for (k, r), v in acu.items() if r == "C")
        ap = sum(v for (k, r), v in acu.items() if r == "P")
        f["acum_C_menos_P"] = ac - ap
        f["acum_ratio_CP"] = (ac / ap - 1.0) if ap > 0 else None

    # --- 11. STRIKE MAS ACTIVO del intervalo, relativo al precio
    top = max(nuevo.items(), key=lambda kv: kv[1])
    f["strike_top_menos_spot"] = top[0][0] - spot
    f["strike_top_es_call"] = 1.0 if top[0][1] == "C" else -1.0
    f["concentracion_top"] = top[1] / tot if tot > 0 else None

    # --- 12. VOLUMEN (contratos, no dinero): mismo corte direccional
    vc = sum(d["day_vol"] or 0 for (k, r), d in actual.items() if r == "C")
    vp = sum(d["day_vol"] or 0 for (k, r), d in actual.items() if r == "P")
    if vc or vp:
        f["vol_C_menos_P"] = vc - vp

    return f


# ---------------------------------------------------------------- evaluacion
class Evaluador:
    """Acumula (valor_feature, retorno_futuro) y calcula lift contra tasa base."""

    def __init__(self):
        self.datos = defaultdict(lambda: defaultdict(list))  # feat -> horiz -> [(v,ret,min)]

    def add(self, feat, horiz, valor, ret, minuto):
        self.datos[feat][horiz].append((valor, ret, minuto))

    def informe(self, horiz, min_n=30):
        out = []
        for feat, porh in self.datos.items():
            pares = porh.get(horiz, [])
            # v==0 no es prediccion: fuera del conjunto Y de la tasa base, o la
            # base se calcularia sobre una ventana temporal distinta a la evaluada.
            pares = [(v, r, m) for v, r, m in pares
                     if v is not None and r is not None and r != 0 and v != 0]
            if len(pares) < min_n:
                continue
            n = len(pares)
            sube = sum(1 for _, r, _ in pares if r > 0)
            base_up = sube / n
            base_dn = 1.0 - base_up

            up = [(v, r, m) for v, r, m in pares if v > 0]
            dn = [(v, r, m) for v, r, m in pares if v < 0]
            if len(up) < 10 or len(dn) < 10:
                continue
            p_up = sum(1 for _, r, _ in up if r > 0) / len(up)
            p_dn = sum(1 for _, r, _ in dn if r < 0) / len(dn)
            lift_up = (p_up - base_up) * 100
            lift_dn = (p_dn - base_dn) * 100

            # n no solapado: minutos separados al menos `horiz`
            nosol_up = nosol_dn = 0
            ult = -10 ** 9
            for _, r, m in sorted(up, key=lambda t: t[2]):
                if m - ult >= horiz:
                    nosol_up += 1
                    ult = m
            ult = -10 ** 9
            for _, r, m in sorted(dn, key=lambda t: t[2]):
                if m - ult >= horiz:
                    nosol_dn += 1
                    ult = m

            rho = spearman([v for v, _, _ in pares], [r for _, r, _ in pares])
            out.append({
                "feat": feat, "n": n, "base_up": base_up * 100,
                "n_up": len(up), "p_up": p_up * 100, "lift_up": lift_up,
                "n_dn": len(dn), "p_dn": p_dn * 100, "lift_dn": lift_dn,
                "lift_medio": (lift_up + lift_dn) / 2,
                "nosol": nosol_up + nosol_dn,
                "rho": rho,
            })
        # Ordena por MAGNITUD: un lift consistentemente NEGATIVO es tan explotable
        # como uno positivo (se invierte la senal). Lo que no sirve es el ruido en 0.
        out.sort(key=lambda d: -abs(d["lift_medio"]))
        return out


# ---------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:]]
    sin_cont = "--sin-contaminar" in args
    args = [a for a in args if not a.startswith("--")]

    db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    c = db.cursor()
    fechas = [f for (f,) in c.execute(
        "SELECT DISTINCT fecha FROM premium_minute ORDER BY fecha")]
    if args:
        fechas = [f for f in fechas if f in args]
    if not fechas:
        print("Sin datos para esas fechas.")
        sys.exit(2)

    print("=" * 78)
    print("DIRECCION DEL SPY A PARTIR DEL PREMIUM POR STRIKE")
    print("Fechas:", ", ".join(fechas), "| contaminado excluido:", sin_cont)
    print("=" * 78)

    ev_global = Evaluador()
    ev_dia = {f: Evaluador() for f in fechas}
    resumen_mov = {}

    for fecha in fechas:
        expiry = fecha.replace("-", "")          # 0DTE del dia
        precio = cargar_precio(c, fecha)
        snaps = cargar_premium(c, fecha, expiry)
        if not precio or not snaps:
            print("\n[%s] sin precio o sin premium 0DTE -> saltada" % fecha)
            continue

        horas = sorted(snaps.keys())
        mins_precio = sorted(precio.keys())

        # movimiento del SPY: cuanto se mueve tras cada minuto
        movs = []
        for m in mins_precio:
            if m + 1 in precio:
                movs.append(precio[m + 1] - precio[m])
        movs_abs = sorted(abs(x) for x in movs)
        resumen_mov[fecha] = {
            "n_min": len(precio), "desde": min(precio), "hasta": max(precio),
            "rango": max(precio.values()) - min(precio.values()),
            "abs_med": movs_abs[len(movs_abs) // 2] if movs_abs else 0,
            "abs_p90": movs_abs[int(len(movs_abs) * 0.9)] if movs_abs else 0,
            "sube_1m": sum(1 for x in movs if x > 0) / len(movs) * 100 if movs else 0,
            "cero_1m": sum(1 for x in movs if x == 0) / len(movs) * 100 if movs else 0,
            "primero": precio[min(precio)], "ultimo": precio[max(precio)],
        }

        previo_hora = None
        previo_neto = None
        usados = 0
        for h in horas:
            m = hhmm_a_min(h)
            tiene_neto = any(d["net_prem"] is not None for d in snaps[h].values())
            if m not in precio:
                previo_hora = h
                if tiene_neto:
                    previo_neto = h
                continue
            if sin_cont and fecha == "2026-08-11" and h >= CONTAMINADO_DESDE:
                previo_hora = h
                if tiene_neto:
                    previo_neto = h
                continue
            spot = precio[m]
            prev = snaps.get(previo_hora, {}) if previo_hora else {}
            feats = features_de_snapshot(
                snaps[h], prev, spot,
                snaps.get(previo_neto, {}) if previo_neto else None)
            previo_hora = h
            if tiene_neto:
                previo_neto = h
            if feats.get("_n_strikes", 0) == 0:
                continue
            usados += 1
            for k in HORIZONTES:
                if (m + k) not in precio:
                    continue
                ret = precio[m + k] - spot
                for nombre, val in feats.items():
                    if nombre.startswith("_"):
                        continue
                    ev_global.add(nombre, k, val, ret, m)
                    ev_dia[fecha].add(nombre, k, val, ret, m)
        print("\n[%s] expiry %s | snapshots=%d con precio y flujo=%d | minutos de precio=%d"
              % (fecha, expiry, len(horas), usados, len(precio)))

    # ---------------- movimiento del SPY (lo que hay que predecir)
    print("\n" + "=" * 78)
    print("EL MOVIMIENTO DEL SPY — que es lo que hay que acertar")
    print("=" * 78)
    print("%-12s %6s %7s %7s %8s %8s %8s %7s" %
          ("fecha", "min", "apert", "cierre", "rango", "|mov|med", "|mov|p90", "%sube"))
    for f, d in resumen_mov.items():
        print("%-12s %6d %7.2f %7.2f %8.2f %8.3f %8.3f %6.1f%%" %
              (f, d["n_min"], d["primero"], d["ultimo"], d["rango"],
               d["abs_med"], d["abs_p90"], d["sube_1m"]))
        print("%-12s   (minutos planos: %.1f%% — se excluyen del acierto direccional)"
              % ("", d["cero_1m"]))

    # ---------------- resultados
    for horiz in HORIZONTES:
        res = ev_global.informe(horiz)
        if not res:
            continue
        print("\n" + "=" * 78)
        print("HORIZONTE %d MIN — TODAS LAS FECHAS JUNTAS" % horiz)
        print("=" * 78)
        print("%-26s %5s %6s | %5s %6s %7s | %5s %6s %7s | %6s %6s" %
              ("variable", "n", "base%", "n>0", "ac%", "LIFT", "n<0", "ac%", "LIFT",
               "medio", "rho"))
        print("-" * 106)
        for r in res:
            print("%-26s %5d %6.1f | %5d %6.1f %+7.1f | %5d %6.1f %+7.1f | %+6.1f %6s" %
                  (r["feat"], r["n"], r["base_up"], r["n_up"], r["p_up"], r["lift_up"],
                   r["n_dn"], r["p_dn"], r["lift_dn"], r["lift_medio"],
                   ("%.2f" % r["rho"]) if r["rho"] is not None else "-"))
        print("  (n no solapado del mejor: %d de %d)" % (res[0]["nosol"], res[0]["n"]))

    # ---------------- consistencia entre dias: lo unico que evita el sobreajuste
    print("\n" + "=" * 78)
    print("CONSISTENCIA ENTRE DIAS (lift medio por dia) — horizonte 10 min")
    print("=" * 78)
    porfeat = defaultdict(dict)
    for f in fechas:
        for r in ev_dia[f].informe(10, min_n=20):
            porfeat[r["feat"]][f] = r["lift_medio"]
    filas = []
    for feat, d in porfeat.items():
        if len(d) == len(fechas):
            vals = list(d.values())
            filas.append((min(vals), feat, d))
    filas.sort(reverse=True)
    print("%-26s %s   %s" % ("variable", "  ".join("%10s" % f for f in fechas), "peor dia"))
    for peor, feat, d in filas:
        print("%-26s %s   %+8.1f" %
              (feat, "  ".join("%+10.1f" % d[f] for f in fechas), peor))
    if not filas:
        print("(ninguna variable tiene n suficiente en TODOS los dias)")

    db.close()


if __name__ == "__main__":
    main()
