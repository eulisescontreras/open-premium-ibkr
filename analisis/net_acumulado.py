"""
net_acumulado.py — READ-ONLY

Las dos cifras que muestra el PANEL de la aplicacion, minuto a minuto, con el precio
del SPY al lado. Nada mas.

    NET CALL / NET PUT = `ta_minute.net_call` / `net_put`.

QUE SON EXACTAMENTE (verificado en `_log_minute:3134`, que persiste `self.net_call` y
`self.net_put`, las mismas variables que pinta el panel y que usa `_update_signal`):
  - Premium NETO FIRMADO acumulado DESDE LAS 09:30 (no es el flujo del minuto).
  - Solo de los 2 strikes de SENAL (el call ATM/ITM y el put ATM/ITM), que van
    rotando con el precio. NO son todos los strikes.
  - Los alimenta `_on_ticks`, POR TICK, con el bid/ask del propio momento del trade.
    Es la atribucion buena, la misma que usa el tape — no la de `compute_walls`.

  diff = NET CALL - NET PUT es literalmente lo que decide UP/DOWN cuando supera el
  umbral adaptativo. Esta tabla es, por tanto, la entrada de la señal tal cual.

⚠️ Empieza a las 09:56 y no a las 09:30: `ta_minute` no se escribe hasta que el TA
tiene 26 barras. El arreglo (GAP 21) esta activo desde las 14:36 de hoy, asi que a
partir de manana la serie arrancara en la apertura.

Uso:
    python analisis\net_acumulado.py
    python analisis\net_acumulado.py 2026-08-10
"""
import os
import sqlite3
import sys

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
        "SELECT DISTINCT fecha FROM ta_minute ORDER BY fecha").fetchall()]
    F = argv[0] if argv else fechas[-1]
    if F not in fechas:
        print("Sin datos para %s. Hay: %s" % (F, ", ".join(fechas)))
        sys.exit(2)
    filas = c.execute(
        "SELECT hora, net_call, net_put, spy FROM ta_minute WHERE fecha=? ORDER BY hora",
        (F,)).fetchall()
    # contexto para juzgar los bloques: TA del minuto y GEX (este ultimo cada 3 min,
    # asi que se arrastra el ultimo valor conocido hacia adelante)
    TA = ["rsi", "ta_score", "ta_dir", "atr_pct", "macd_hist", "obv_trend", "vwap"]
    ctx = {}
    for r in c.execute("SELECT hora,%s FROM ta_minute WHERE fecha=?"
                       % ",".join(TA), (F,)).fetchall():
        ctx[r[0]] = dict(zip(TA, r[1:]))
    gex = {}
    for h, g, reg in c.execute(
            "SELECT hora, gex_total, regime FROM walls_snapshot WHERE fecha=? ORDER BY hora",
            (F,)).fetchall():
        gex[h] = (g, reg)
    db.close()

    def gex_en(h):
        """ultimo GEX conocido en o antes de `h` (walls va cada 3 min)."""
        prev = (None, None)
        for k in sorted(gex):
            if k > h:
                break
            prev = gex[k]
        return prev

    # ---- BLOQUES: filas consecutivas con la MISMA senal. Cada bloque se juzga por lo
    # que hizo el SPY entre su primera y su ultima fila. La senal se conoce al EMPEZAR
    # el bloque y el movimiento ocurre despues, asi que la comparacion es honesta —
    # con una salvedad: en vivo no se sabe cuando va a terminar el bloque.
    bloques = []          # (ini, fin, senal, spy_ini, spy_fin, acierto)
    ini = None
    sen_ant = None
    for i, (h, nc, np_, spy) in enumerate(filas):
        s = ("" if (nc is None or np_ is None)
             else ("DOWN" if abs(np_) > abs(nc) else ("UP" if abs(nc) > abs(np_) else "=")))
        if s != sen_ant:
            if ini is not None:
                bloques.append([ini, i - 1, sen_ant])
            ini, sen_ant = i, s
    if ini is not None:
        bloques.append([ini, len(filas) - 1, sen_ant])

    marca = {}
    resumen = []
    for a, b, s in bloques:
        p0 = next((filas[k][3] for k in range(a, b + 1) if filas[k][3] is not None), None)
        p1 = next((filas[k][3] for k in range(b, a - 1, -1) if filas[k][3] is not None), None)
        if s in ("", "=") or p0 is None or p1 is None or p1 == p0:
            ok = None
        else:
            ok = (p1 > p0) if s == "UP" else (p1 < p0)
        for k in range(a, b + 1):
            marca[k] = "✓" if ok else ("✗" if ok is False else "·")
        # CONTEXTO AL EMPEZAR el bloque: es lo unico que se conoceria al decidir.
        h0 = filas[a][0]
        t0 = ctx.get(h0, {})
        g0, reg0 = gex_en(h0)
        nc0, np0 = filas[a][1], filas[a][2]
        resumen.append({
            "ini": h0, "fin": filas[b][0], "n": b - a + 1, "sen": s,
            "p0": p0, "p1": p1, "ok": ok,
            "mov": None if (p0 is None or p1 is None) else p1 - p0,
            "gex": g0, "reg": reg0,
            "ratio": (abs(np0) / abs(nc0)) if (nc0 and np0 is not None) else None,
            "rsi": t0.get("rsi"), "sc": t0.get("ta_score"), "dir": t0.get("ta_dir"),
            "atr": t0.get("atr_pct"), "macd": t0.get("macd_hist"),
            "obv": t0.get("obv_trend"),
            "dvwap": (None if (p0 is None or t0.get("vwap") is None)
                      else p0 - t0["vwap"]),
        })

    # RACHA: cuantas veces SEGUIDAS lleva saliendo esa misma palabra, contando este
    # minuto. Empieza en 1 cada vez que la senal cambia.
    racha = {}
    n_r = 0
    s_ant = None
    for i, (h, nc, np_, spy) in enumerate(filas):
        s = ("" if (nc is None or np_ is None)
             else ("DOWN" if abs(np_) > abs(nc) else ("UP" if abs(nc) > abs(np_) else "=")))
        n_r = n_r + 1 if s == s_ant else 1
        s_ant = s
        racha[i] = n_r

    # CONTADORES ACUMULADOS: cuantos minutos lleva cada palabra desde la apertura.
    # No es la racha (que se reinicia en cada cambio): es el marcador del dia.
    cnt = {}
    cu = cd = 0
    lider_ant = None
    cruces = []          # (hora, tipo, cu, cd) -> EMPATE o ADELANTAMIENTO
    for i, (h, nc, np_, spy) in enumerate(filas):
        s = ("" if (nc is None or np_ is None)
             else ("DOWN" if abs(np_) > abs(nc) else ("UP" if abs(nc) > abs(np_) else "=")))
        if s == "UP":
            cu += 1
        elif s == "DOWN":
            cd += 1
        cnt[i] = (cu, cd)
        lider = "UP" if cu > cd else ("DOWN" if cd > cu else "EMPATE")
        if lider != lider_ant:
            if lider == "EMPATE":
                cruces.append((h, "EMPATE", cu, cd, spy))
            elif lider_ant is not None:
                cruces.append((h, "pasa a mandar %s" % lider, cu, cd, spy))
            lider_ant = lider

    anchos = (8, 15, 15, 15, 10, 7, 5, 5, 5, 4)

    def linea(i, m, d):
        return i + m.join("─" * (a + 2) for a in anchos) + d

    def fila(v):
        return "│ " + " │ ".join("%*s" % (anchos[i], v[i])
                                 for i in range(len(anchos))) + " │"

    out = []
    out.append("NET CALL / NET PUT ACUMULADOS (los del panel) vs PRECIO DEL SPY — %s" % F)
    out.append("Acumulado firmado desde las 09:30, solo los 2 strikes de SENAL.")
    out.append("Atribucion POR TICK (`_on_ticks`), que es la buena.  %d minutos." % len(filas))
    out.append("")
    out.append(linea("┌", "┬", "┐"))
    out.append(fila(("MINUTO", "|CALL|", "|PUT|", "|C| - |P|", "SPY", "SENAL",
                     "RACHA", "#UP", "#DOWN", "OK")))
    out.append(linea("├", "┼", "┤"))
    for _i, (h, nc, np_, spy) in enumerate(filas):
        # SENAL por DOMINANCIA en valor absoluto: manda el lado que mueve mas dinero,
        # sin importar si ese dinero entro comprando o vendiendo.
        # OJO: NO es la señal que usa la app. La app decide con `diff = net_call -
        # net_put` RESPETANDO el signo, y hoy eso dio UP toda la sesion mientras el
        # SPY caia. Esta columna es la lectura alternativa, para poder compararlas.
        if nc is None or np_ is None:
            sen = ""
        elif abs(np_) > abs(nc):
            sen = "DOWN"
        elif abs(nc) > abs(np_):
            sen = "UP"
        else:
            sen = "="
        # |C| - |P|: valor ABSOLUTO de cada lado antes de restar. Mide QUE LADO MUEVE
        # MAS DINERO, sin importar si entro comprando o vendiendo. Positivo = manda el
        # call, negativo = manda el put. Es la magnitud en la que se apoya SENAL.
        dif = "" if (nc is None or np_ is None) else "%+.0f" % (abs(nc) - abs(np_))
        out.append(fila((
            h,
            "" if nc is None else "%.0f" % abs(nc),
            "" if np_ is None else "%.0f" % abs(np_),
            dif,
            "" if spy is None else "%.2f" % spy,
            sen,
            str(racha.get(_i, "")),
            str(cnt.get(_i, ("", ""))[0]),
            str(cnt.get(_i, ("", ""))[1]),
            marca.get(_i, ""))))
    out.append(linea("└", "┴", "┘"))

    # ---- marcador del dia: empates y adelantamientos
    out.append("")
    out.append("MARCADOR DEL DIA: EMPATES Y ADELANTAMIENTOS")
    out.append("Contadores acumulados desde la apertura (no la racha). Se listan los minutos")
    out.append("en que los dos contadores se igualan o en que uno pasa a mandar sobre el otro.")
    out.append("%-8s %-22s %6s %7s %10s" % ("HORA", "QUE PASA", "#UP", "#DOWN", "SPY"))
    out.append("-" * 58)
    for h, tipo, u, d, s in cruces:
        out.append("%-8s %-22s %6d %7d %10s"
                   % (h, tipo, u, d, ("%.2f" % s) if s is not None else ""))
    if not cruces:
        out.append("(ninguno: un solo lado mando toda la sesion)")
    out.append("-" * 58)
    out.append("MARCADOR FINAL:  UP %d  -  DOWN %d   sobre %d minutos" % (cu, cd, len(filas)))

    # ---- resumen por BLOQUE de senal
    out.append("")
    out.append("BLOQUES DE SENAL (filas consecutivas con la misma lectura)")
    out.append("Contexto = valor AL EMPEZAR el bloque (lo unico que se sabria al decidir).")
    cabb = ("%-7s %-7s %5s %6s %8s %7s %8s %7s %6s %5s %7s %7s %7s  %s"
            % ("DESDE", "HASTA", "min", "SENAL", "mov", "ratio", "GEX Bn", "REG",
               "RSI", "SC", "DIR", "ATR%", "dVWAP", "OK"))
    out.append(cabb)
    out.append("-" * len(cabb))
    ok = fallo = 0

    def f(v, d=2):
        return "" if v is None else "%.*f" % (d, v)

    for r in resumen:
        m = "✓" if r["ok"] else ("✗" if r["ok"] is False else "·")
        if r["ok"] is True:
            ok += 1
        elif r["ok"] is False:
            fallo += 1
        out.append("%-7s %-7s %5d %6s %8s %7s %8s %7s %6s %5s %7s %7s %7s  %s"
                   % (r["ini"], r["fin"], r["n"], r["sen"],
                      "" if r["mov"] is None else "%+.2f" % r["mov"],
                      f(r["ratio"]),
                      "" if r["gex"] is None else "%.1f" % (r["gex"] / 1e9),
                      (r["reg"] or "")[:6], f(r["rsi"], 1), f(r["sc"], 0),
                      (r["dir"] or "")[:7], f(r["atr"]),
                      "" if r["dvwap"] is None else "%+.2f" % r["dvwap"], m))
    out.append("-" * len(cabb))
    tot = ok + fallo
    out.append("BLOQUES: %d acertados, %d fallados%s"
               % (ok, fallo, ("  (%.0f%%)" % (100.0 * ok / tot)) if tot else ""))

    # ---- QUE TIENEN EN COMUN los que aciertan frente a los que fallan
    def mediana(vals):
        v = sorted(x for x in vals if x is not None)
        if not v:
            return None
        n2 = len(v)
        return v[n2 // 2] if n2 % 2 else (v[n2 // 2 - 1] + v[n2 // 2]) / 2.0

    aci = [r for r in resumen if r["ok"] is True]
    fal = [r for r in resumen if r["ok"] is False]
    if aci and fal:
        out.append("")
        out.append("QUE DISTINGUE A LOS BLOQUES QUE ACIERTAN (mediana de cada grupo)")
        out.append("%-22s %12s %12s %12s" % ("variable", "ACIERTAN", "FALLAN", "diferencia"))
        out.append("-" * 62)
        for et, k, d in (("duracion (min)", "n", 0), ("|movimiento| SPY", "mov", 2),
                         ("ratio |P|/|C|", "ratio", 2), ("GEX (Bn)", "gex", 2),
                         ("RSI", "rsi", 1), ("ta_score", "sc", 1),
                         ("ATR%", "atr", 3), ("dist a VWAP", "dvwap", 2)):
            va = mediana([abs(r[k]) if k == "mov" and r[k] is not None else r[k]
                          for r in aci])
            vf = mediana([abs(r[k]) if k == "mov" and r[k] is not None else r[k]
                          for r in fal])
            if va is None or vf is None:
                continue
            if k == "gex":
                va, vf = va / 1e9, vf / 1e9
            out.append("%-22s %12.*f %12.*f %12.*f"
                       % (et, d, va, d, vf, d, va - vf))
        out.append("-" * 62)
        out.append("⚠️ %d aciertos y %d fallos. Con esa n, una diferencia de medianas NO es"
                   % (len(aci), len(fal)))
        out.append("   evidencia de nada: es lo que se ve al mirar 15 casos. Sirve para")
        out.append("   decidir QUE medir con mas sesiones, no para concluir.")
    out.append("")
    out.append("⚠️ El bloque se juzga del PRIMER minuto al ULTIMO del propio bloque. La senal")
    out.append("   se conoce al empezar, asi que el movimiento es posterior — pero EN VIVO no")
    out.append("   se sabe cuando va a terminar el bloque. Con %d bloques no se puede concluir"
               % tot)
    out.append("   nada: es una foto, no una tasa de acierto.")

    # ---- QUE HACE EL SPY DESPUES DE CADA CAMBIO DE SENAL
    # Es lo que de verdad se pregunta: la señal se conoce en el minuto del cambio y el
    # movimiento tiene que venir DESPUES. Distinto de juzgar el bloque entero, donde el
    # final se elige a posteriori (en vivo no se sabe cuando termina).
    px = {h: s for h, _a, _b, s in
          [(f[0], f[1], f[2], f[3]) for f in filas] if s is not None}

    def m2(x):
        return int(x[:2]) * 60 + int(x[3:5])

    def h2(m):
        return "%02d:%02d" % (m // 60, m % 60)

    HOR = (5, 10, 15, 30, 60)
    out.append("")
    out.append("QUE HACE EL SPY DESPUES DE CADA CAMBIO DE SENAL")
    out.append("La senal se conoce en el minuto del cambio; el movimiento se mide DESPUES.")
    cab2 = "%-7s %6s %6s %9s" % ("CAMBIO", "SENAL", "VECES", "SPY") + \
           "".join("%12s" % ("+%dmin" % k) for k in HOR)
    out.append(cab2)
    out.append("-" * len(cab2))
    acc = {k: [0, 0] for k in HOR}          # [aciertos, total]
    # el mismo recuento SEPARADO por lado: un agregado puede tapar que un lado
    # funcione y el otro no, y eso es justo lo que se ve en los datos del 08-10.
    porlado = {"UP": {k: [0, 0] for k in HOR}, "DOWN": {k: [0, 0] for k in HOR}}
    for r in resumen:
        if r["sen"] not in ("UP", "DOWN") or r["p0"] is None:
            continue
        base = px.get(r["ini"])
        if base is None:
            continue
        cel = []
        for k in HOR:
            v = px.get(h2(m2(r["ini"]) + k))
            if v is None:
                cel.append("%12s" % "-")
                continue
            d = v - base
            if d != 0:
                acc[k][1] += 1
                porlado[r["sen"]][k][1] += 1
                if (d > 0) == (r["sen"] == "UP"):
                    acc[k][0] += 1
                    porlado[r["sen"]][k][0] += 1
                    cel.append("%12s" % ("%+.2f ✓" % d))
                else:
                    cel.append("%12s" % ("%+.2f ✗" % d))
            else:
                cel.append("%12s" % ("%+.2f ·" % d))
        out.append("%-7s %6s %6d %9.2f"
                   % (r["ini"], r["sen"], r["n"], base) + "".join(cel))
    out.append("-" * len(cab2))
    res = "%-7s %6s %6s %9s" % ("ACIERTO", "", "", "")
    for k in HOR:
        a, t = acc[k]
        res += "%12s" % (("%d/%d" % (a, t)) if t else "-")
    out.append(res)
    res = "%-7s %6s %6s %9s" % ("", "", "", "")
    for k in HOR:
        a, t = acc[k]
        res += "%12s" % (("%.0f%%" % (100.0 * a / t)) if t else "-")
    out.append(res)
    for lado in ("UP", "DOWN"):
        r1 = "%-7s %6s %6s %9s" % ("solo", lado, "", "")
        for k in HOR:
            a, t = porlado[lado][k]
            r1 += "%12s" % (("%d/%d %.0f%%" % (a, t, 100.0 * a / t)) if t else "-")
        out.append(r1)

    txt = "\n".join(out)
    print(txt)
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "investigacion",
                        "net_acumulado_%s.txt" % F)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print()
    print("ESCRITO: %s" % ruta)


if __name__ == "__main__":
    main()
