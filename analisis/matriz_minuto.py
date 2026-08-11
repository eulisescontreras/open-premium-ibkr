"""
matriz_minuto.py — READ-ONLY

Tabla MINUTO A MINUTO, sin saltarse ninguno:
    fila 1 -> MINUTO   (cada columna es un minuto, la rejilla completa 09:30 -> ultimo dato)
    fila 2 -> CALL k$  premium bruto que entro en ESE minuto en calls
    fila 3 -> PUT  k$  idem en puts
    fila 4 -> C - P    diferencia
    fila 5 -> SPY      precio en ese momento

FUENTE: `premium_minute`, reconstruyendo el flujo del minuto como la diferencia de
`day_prem` de cada strike contra su propia lectura anterior, sumada sobre todos los
strikes de la 0DTE. Se usa esta y no `ta_minute.prem_*_min` porque cubre MAS minutos
(336 de 357 hoy, frente a 321): `ta_minute` no existe hasta que el TA tiene 26 barras.

Precio del SPY: `ta_minute.spy`, y donde no hay, `walls_snapshot.spot`.

QUE SIGNIFICAN LOS HUECOS (no se rellenan; un hueco es un dato):
    ·      no hay NINGUNA fila de premium para ese minuto -> no se midio nada
    *      ese minuto trae ademas el flujo de la BANDA, que solo se lee cada 3 min,
           asi que absorbe 3 minutos de golpe (diente de sierra medido: 5,4x / 8,3x)

⚠️ El premium es BRUTO: NO distingue quien compro de quien vendio. 1 M$ en calls es el
mismo numero lo compre un alcista o lo venda un bajista. Para direccion hace falta el
neto firmado, que solo esta completo en la tabla `tape` (desde hoy 14:36, y solo 4 strikes).

Uso:
    python analisis\matriz_minuto.py
    python analisis\matriz_minuto.py 2026-08-10 --cols 14
"""
import os
import sqlite3
import sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "spy_history.db")
COLS = 12
INICIO = "09:30"


def M(h):
    return int(h[:2]) * 60 + int(h[3:5])


def H(m):
    return "%02d:%02d" % (m // 60, m % 60)


def main():
    argv = sys.argv[1:]
    cols = COLS
    if "--cols" in argv:
        i = argv.index("--cols")
        cols = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    fecha = next((a for a in argv if not a.startswith("--")), None)

    db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    c = db.cursor()
    fechas = [x[0] for x in c.execute(
        "SELECT DISTINCT fecha FROM premium_minute ORDER BY fecha").fetchall()]
    F = fecha or fechas[-1]
    if F not in fechas:
        print("Sin datos para %s. Hay: %s" % (F, ", ".join(fechas)))
        sys.exit(2)
    EXP = F.replace("-", "")

    filas = c.execute(
        "SELECT hora, strike, right, day_prem FROM premium_minute "
        "WHERE fecha=? AND expiry=? AND day_prem IS NOT NULL ORDER BY hora",
        (F, EXP)).fetchall()
    spy = {x[0]: x[1] for x in c.execute(
        "SELECT hora, spy FROM ta_minute WHERE fecha=? AND spy IS NOT NULL",
        (F,)).fetchall()}
    # TA del minuto. NO existe hasta que hay 26 barras (~09:56): esas casillas van vacias,
    # que es la verdad, no un cero.
    TA_COLS = ["rsi", "ta_score", "ta_dir", "macd_hist", "atr_pct", "vwap",
               "obv_trend", "ema8", "ema21", "ema50", "sma20", "sma50", "sma200"]
    ta = {}
    for r in c.execute("SELECT hora,%s FROM ta_minute WHERE fecha=?"
                       % ",".join(TA_COLS), (F,)).fetchall():
        ta[r[0]] = dict(zip(TA_COLS, r[1:]))
    for h, s in c.execute("SELECT hora, spot FROM walls_snapshot WHERE fecha=? "
                          "AND spot IS NOT NULL", (F,)).fetchall():
        spy.setdefault(h, s)          # relleno solo donde ta_minute no llega
    walls = set(x[0] for x in c.execute(
        "SELECT DISTINCT hora FROM walls_snapshot WHERE fecha=?", (F,)).fetchall())
    db.close()

    if not filas:
        print("Sin premium para %s." % F)
        sys.exit(2)

    # flujo del minuto = delta de day_prem de cada strike contra SU lectura anterior
    prev = {}
    call = {}
    put = {}
    con_dato = set()
    resets = 0
    for h, strike, right, dp in filas:
        con_dato.add(h)
        key = (strike, right)
        antes = prev.get(key)
        prev[key] = dp
        if antes is None:
            continue
        d = dp - antes
        if d < 0:                       # reinicio / cambio de referencia: no es flujo
            resets += 1
            continue
        if right == "C":
            call[h] = call.get(h, 0.0) + d
        else:
            put[h] = put.get(h, 0.0) + d

    ini, fin = M(INICIO), max(M(h) for h in con_dato)
    rejilla = [H(m) for m in range(ini, fin + 1)]
    sin_dato = [h for h in rejilla if h not in con_dato]

    print("=" * 100)
    print("PREMIUM POR MINUTO vs PRECIO DEL SPY — %s — expiry 0DTE %s" % (F, EXP))
    print("Rejilla COMPLETA %s -> %s = %d minutos | con dato: %d | sin dato: %d"
          % (INICIO, H(fin), len(rejilla), len(rejilla) - len(sin_dato), len(sin_dato)))
    if sin_dato:
        print("Minutos sin ninguna lectura (se muestran como ·): %s" % ", ".join(sin_dato))
    print("Deltas negativos descartados (reinicios): %d" % resets)
    print("=" * 100)

    W = 9
    for i in range(0, len(rejilla), cols):
        bloque = rejilla[i:i + cols]
        et = [h + ("*" if h in walls else "") for h in bloque]

        def celda(d, h, fmt="%.0f"):
            if h not in con_dato:
                return "·"
            return fmt % (d.get(h, 0.0) / 1000.0)

        print()
        print("%-12s" % "MINUTO" + "".join(("%%%ds" % W) % e for e in et))
        print("%-12s" % "CALL k$" + "".join(("%%%ds" % W) % celda(call, h) for h in bloque))
        print("%-12s" % "PUT  k$" + "".join(("%%%ds" % W) % celda(put, h) for h in bloque))
        print("%-12s" % "C - P" + "".join(
            ("%%%ds" % W) % ("·" if h not in con_dato else
                             "%+.0f" % ((call.get(h, 0.0) - put.get(h, 0.0)) / 1000.0))
            for h in bloque))
        print("%-12s" % "SPY" + "".join(
            ("%%%ds" % W) % (("%.2f" % spy[h]) if h in spy else "·") for h in bloque))

    print()
    print("CALL/PUT k$ = premium BRUTO que entro en ESE minuto, en miles de $.")
    print("   BRUTO no distingue comprador de vendedor: para direccion hace falta el neto.")
    print("·  = sin lectura ese minuto (no se inventa).   * = incluye la banda (3 min de golpe).")

    # ---- ficheros: la salida por pantalla se corta, estos llevan la rejilla ENTERA
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "matriz_minuto_%s" % F)

    # TXT alineado: la rejilla ENTERA, un minuto debajo de otro. Sin separadores:
    # columnas de ancho fijo para poder leerlo en vertical de un vistazo.
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write("PREMIUM POR MINUTO vs PRECIO DEL SPY  —  %s  —  expiry 0DTE %s\n" % (F, EXP))
        f.write("Rejilla completa %s -> %s = %d minutos | con dato %d | sin dato %d\n"
                % (INICIO, H(fin), len(rejilla), len(rejilla) - len(sin_dato), len(sin_dato)))
        f.write("B = ese minuto incluye la banda (3 min de golpe).  "
                "Vacio = sin lectura ese minuto.\n")
        f.write("Importes en DOLARES, premium BRUTO (no distingue comprador de vendedor).\n\n")
        cab = ("MINUTO", "B", "CALL", "PUT", "C - P", "SPY",
               "RSI", "SCORE", "DIR", "MACDh", "ATR%", "VWAP", "OBV",
               "EMA8", "EMA21", "EMA50", "SMA20", "SMA50", "SMA200")
        anchos = (8, 3, 14, 14, 14, 9,
                  6, 6, 7, 8, 6, 8, 8,
                  8, 8, 8, 8, 8, 8)

        def linea(izq, med, der):
            return izq + med.join("─" * (a + 2) for a in anchos) + der + "\n"

        def fila(vals):
            return ("│ " + " │ ".join(
                ("%*s" % (anchos[i], vals[i])) for i in range(len(anchos))) + " │\n")

        def n(v, dec=2):
            """Numero o vacio. Un NULL se muestra VACIO, nunca como 0."""
            return "" if v is None else ("%.*f" % (dec, v))

        f.write(linea("┌", "┬", "┐"))
        f.write(fila(cab))
        f.write(linea("├", "┼", "┤"))
        for h in rejilla:
            hay = h in con_dato
            t = ta.get(h, {})
            f.write(fila((
                h,
                "B" if h in walls else "",
                ("%.0f" % call.get(h, 0.0)) if hay else "",
                ("%.0f" % put.get(h, 0.0)) if hay else "",
                ("%+.0f" % (call.get(h, 0.0) - put.get(h, 0.0))) if hay else "",
                ("%.2f" % spy[h]) if h in spy else "",
                n(t.get("rsi"), 1), n(t.get("ta_score"), 0), t.get("ta_dir") or "",
                n(t.get("macd_hist"), 3), n(t.get("atr_pct"), 2), n(t.get("vwap")),
                (t.get("obv_trend") or "")[:8],
                n(t.get("ema8")), n(t.get("ema21")), n(t.get("ema50")),
                n(t.get("sma20")), n(t.get("sma50")), n(t.get("sma200")))))
        f.write(linea("└", "┴", "┘"))

    print()
    print("ESCRITO — la rejilla ENTERA (%d minutos), matriz alineada, sin separadores:"
          % len(rejilla))
    print("   %s.txt" % base)


if __name__ == "__main__":
    main()
