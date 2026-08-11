"""
neto_por_strike.py — READ-ONLY

Lo que pidio el usuario: el premium NETO por strike y por minuto.

    "si uno compra 50.000 en calls y otro vende 20.000, ese strike tiene +30.000
     en ese minuto"

    neto(strike, minuto) = SUMA(premium de las COMPRAS) - SUMA(premium de las VENTAS)

Solo se puede desde `tape`, que es la unica tabla con el agresor de cada operacion.

⚠️ QUE ES EXACTAMENTE "COMPRA" Y "VENTA" (importa, y no es un tecnicismo)
En toda opcion negociada hay un comprador Y un vendedor: siempre. Lo que se clasifica
aqui es quien CRUZO EL SPREAD, o sea el lado AGRESIVO, que es el que tiene prisa:
    last >= ask  -> COMPRA   (el agresor pago el ask)
    last <= bid  -> VENTA    (el agresor solto contra el bid)
    en medio     -> MID      NO ATRIBUIBLE, no cuenta ni a un lado ni a otro
Es una INFERENCIA a partir del bid/ask del instante, no un dato que de IBKR. La columna
MID k$ dice cuanto dinero quedo sin clasificar: es la medida de lo que NO sabemos.

⚠️ COBERTURA: `_on_ticks:1817` solo procesa SENAL y BASELINE, asi que del vencimiento
0DTE el tape ve los 2 strikes de señal (que van rotando con el precio), no los 40 de la
banda. Y el tape existe desde las 14:36 del 2026-08-11.

Uso:
    python analisis\neto_por_strike.py
    python analisis\neto_por_strike.py 2026-08-11
"""
import os
import sqlite3
import sys

# la consola de Windows va en cp1252 y revienta con los bordes de caja
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "spy_history.db")


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    c = db.cursor()
    fechas = [x[0] for x in c.execute(
        "SELECT DISTINCT fecha FROM tape ORDER BY fecha").fetchall()]
    if not fechas:
        print("La tabla `tape` esta vacia.")
        sys.exit(2)
    F = argv[0] if argv else fechas[-1]
    EXP = F.replace("-", "")

    filas = c.execute(
        "SELECT substr(hora,1,5), strike, right, agresor, premium_dvol "
        "FROM tape WHERE fecha=? AND expiry=? ORDER BY hora", (F, EXP)).fetchall()
    spy = {x[0]: x[1] for x in c.execute(
        "SELECT hora, spy FROM ta_minute WHERE fecha=? AND spy IS NOT NULL",
        (F,)).fetchall()}
    db.close()
    if not filas:
        print("Sin tape para %s." % F)
        sys.exit(2)

    neto = {}       # (minuto, k) -> neto
    mid = {}        # minuto -> dinero sin clasificar
    claves = set()
    minutos = []
    for m, strike, right, agr, prem in filas:
        k = "%g%s" % (strike, right)
        claves.add(k)
        if m not in mid:
            mid[m] = 0.0
            minutos.append(m)
        p = prem or 0.0
        if agr == "COMPRA":
            neto[(m, k)] = neto.get((m, k), 0.0) + p
        elif agr == "VENTA":
            neto[(m, k)] = neto.get((m, k), 0.0) - p
        else:
            mid[m] += p
            neto.setdefault((m, k), 0.0)

    orden = sorted(claves, key=lambda k: (k[-1], float(k[:-1])))
    anchos = [8] + [11] * len(orden) + [11, 11, 11, 10, 9]
    cab = (["MINUTO"] + orden +
           ["TOT CALL", "TOT PUT", "C - P", "MID k$", "SPY"])

    def linea(i, m, d):
        return i + m.join("─" * (a + 2) for a in anchos) + d

    def fila(v):
        return "│ " + " │ ".join("%*s" % (anchos[i], v[i]) for i in range(len(v))) + " │"

    salida = []
    salida.append("PREMIUM NETO POR STRIKE Y POR MINUTO — %s — expiry 0DTE %s" % (F, EXP))
    salida.append("neto = COMPRAS - VENTAS (por agresor, quien cruzo el spread), en MILES de $")
    salida.append("Positivo = entro dinero comprando ese strike. Negativo = se vendio.")
    salida.append("MID k$ = dinero que se cruzo dentro del spread y NO se puede atribuir.")
    salida.append("Cobertura: %d strikes (los de SENAL, que rotan con el precio). "
                  "La banda NO entra." % len(orden))
    salida.append("")
    salida.append(linea("┌", "┬", "┐"))
    salida.append(fila(cab))
    salida.append(linea("├", "┼", "┤"))
    tot = {k: 0.0 for k in orden}
    for m in minutos:
        vals = [m]
        sc = sp = 0.0
        for k in orden:
            v = neto.get((m, k))
            if v is None:
                vals.append("")
            else:
                vals.append("%+.0f" % (v / 1000.0))
                tot[k] += v
                if k.endswith("C"):
                    sc += v
                else:
                    sp += v
        # suma de TODOS los strikes de cada lado en ESE minuto
        vals.append("%+.0f" % (sc / 1000.0))
        vals.append("%+.0f" % (sp / 1000.0))
        vals.append("%+.0f" % ((sc - sp) / 1000.0))
        vals.append("%.0f" % (mid[m] / 1000.0))
        vals.append(("%.2f" % spy[m]) if m in spy else "")
        salida.append(fila(vals))
    salida.append(linea("├", "┼", "┤"))
    tc = sum(v for k, v in tot.items() if k.endswith("C"))
    tp = sum(v for k, v in tot.items() if k.endswith("P"))
    salida.append(fila(["TOTAL"] + ["%+.0f" % (tot[k] / 1000.0) for k in orden]
                       + ["%+.0f" % (tc / 1000.0), "%+.0f" % (tp / 1000.0),
                          "%+.0f" % ((tc - tp) / 1000.0),
                          "%.0f" % (sum(mid.values()) / 1000.0), ""]))
    salida.append(linea("└", "┴", "┘"))

    txt = "\n".join(salida)
    print(txt)
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "neto_por_strike_%s.txt" % F)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print()
    print("ESCRITO: %s" % ruta)


if __name__ == "__main__":
    main()
