"""
direccion_foco.py — READ-ONLY

Zoom sobre las POCAS variables que sobrevivieron el barrido de `direccion_premium.py`.
Reutiliza sus funciones (no las reimplementa): misma carga, mismas features, mismo
criterio de lift. Aqui solo se mira con lupa: por horizonte Y por dia, con n total,
n no solapado y el reparto de aciertos.

Uso:
    python analisis\direccion_foco.py
    python analisis\direccion_foco.py atm_ratio vol_C_menos_P
"""
import sys
import os
import sqlite3
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from direccion_premium import (DB, HORIZONTES, hhmm_a_min, cargar_precio,
                               cargar_premium, features_de_snapshot, spearman)

FOCO = ["atm_ratio", "atm_C_menos_P", "cerca_menos_lejos_norm",
        "vol_C_menos_P", "z_sup0a1_ratio", "bruto_ratio_CP", "neto_C_menos_P"]


def recoger(c, fecha, spot_ref="actual"):
    """
    [(minuto, feats)] + precio, para una fecha.

    `spot_ref` decide QUE precio se usa para clasificar cada strike en
    ITM/ATM/OTM. Importa: el flujo del intervalo ocurrio ENTRE dos lecturas,
    y el SPY se movio mientras tanto. Un strike que ahora es OTM pudo ser
    ATM cuando se negocio.
        actual  -> spot al CIERRE del intervalo (lo que hace el codigo en vivo)
        previo  -> spot al INICIO del intervalo
        medio   -> media de ambos
    """
    precio = cargar_precio(c, fecha)
    snaps = cargar_premium(c, fecha, fecha.replace("-", ""))
    out = []
    previo = None
    previo_neto = None          # ultimo snapshot que traia net_prem (filas de walls)
    for h in sorted(snaps.keys()):
        m = hhmm_a_min(h)
        tiene_neto = any(d["net_prem"] is not None for d in snaps[h].values())
        if m not in precio:
            previo = h
            if tiene_neto:
                previo_neto = h
            continue
        mp = hhmm_a_min(previo) if previo else None
        if spot_ref == "previo" and mp is not None and mp in precio:
            spot = precio[mp]
        elif spot_ref == "medio" and mp is not None and mp in precio:
            spot = (precio[mp] + precio[m]) / 2.0
        else:
            spot = precio[m]
        feats = features_de_snapshot(snaps[h], snaps.get(previo, {}) if previo else {},
                                     spot,
                                     snaps.get(previo_neto, {}) if previo_neto else None)
        previo = h
        if tiene_neto:
            previo_neto = h
        if feats.get("_n_strikes", 0):
            out.append((m, feats))
    return out, precio


def evalua(muestras, precio, feat, horiz):
    pares = []
    for m, f in muestras:
        v = f.get(feat)
        if v is None or v == 0 or (m + horiz) not in precio or m not in precio:
            continue
        ret = precio[m + horiz] - precio[m]
        if ret == 0:
            continue
        pares.append((v, ret, m))
    if len(pares) < 15:
        return None
    n = len(pares)
    base_up = sum(1 for _, r, _ in pares if r > 0) / n
    up = [p for p in pares if p[0] > 0]
    dn = [p for p in pares if p[0] < 0]
    if len(up) < 5 or len(dn) < 5:
        return None
    p_up = sum(1 for _, r, _ in up if r > 0) / len(up)
    p_dn = sum(1 for _, r, _ in dn if r < 0) / len(dn)

    def nosolap(sub):
        k, ult = 0, -10 ** 9
        for _, _, m in sorted(sub, key=lambda t: t[2]):
            if m - ult >= horiz:
                k += 1
                ult = m
        return k

    return {
        "n": n, "base_up": base_up * 100,
        "n_up": len(up), "p_up": p_up * 100, "lift_up": (p_up - base_up) * 100,
        "n_dn": len(dn), "p_dn": p_dn * 100, "lift_dn": (p_dn - (1 - base_up)) * 100,
        "nosol": nosolap(up) + nosolap(dn),
        "rho": spearman([p[0] for p in pares], [p[1] for p in pares]),
    }


def main():
    feats = sys.argv[1:] or FOCO
    db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    c = db.cursor()
    fechas = [f for (f,) in c.execute(
        "SELECT DISTINCT fecha FROM premium_minute ORDER BY fecha")]

    datos = {}
    for f in fechas:
        datos[f] = recoger(c, f)

    for feat in feats:
        print("\n" + "=" * 92)
        print("VARIABLE:", feat)
        print("=" * 92)
        print("%-12s %5s | %5s %6s | %5s %6s %7s | %5s %6s %7s | %5s %6s" %
              ("fecha", "horiz", "n", "base%", "n>0", "ac%", "LIFT",
               "n<0", "ac%", "LIFT", "nosol", "rho"))
        print("-" * 92)
        for fecha in fechas:
            muestras, precio = datos[fecha]
            for h in HORIZONTES:
                r = evalua(muestras, precio, feat, h)
                if not r:
                    continue
                print("%-12s %5d | %5d %6.1f | %5d %6.1f %+7.1f | %5d %6.1f %+7.1f | %5d %6s" %
                      (fecha, h, r["n"], r["base_up"], r["n_up"], r["p_up"], r["lift_up"],
                       r["n_dn"], r["p_dn"], r["lift_dn"], r["nosol"],
                       ("%.2f" % r["rho"]) if r["rho"] is not None else "-"))
            print("-" * 92)
    db.close()


if __name__ == "__main__":
    main()
