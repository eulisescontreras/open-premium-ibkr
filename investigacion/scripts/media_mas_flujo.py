# MEDIA + FLUJO: ¿acierta mas la media cuando el tape la respalda?
#
# Direccion  = EMA8 vs EMA21 (la que mejor aguanto en los dos dias: 74-76%)
# Confirmacion = actividad del tape (|neto| y mayor bloque del minuto), SIN filtrar y SIN signo,
#                que es lo unico del tape que ha sobrevivido.
# Verdad     = lado del tramo vigente (ZigZag 1.50).
#
# Se mide el acierto de la media SEGUN el nivel de flujo. Si el flujo confirma, el acierto
# deberia SUBIR con el flujo alto y BAJAR en la calma.
import sqlite3
import statistics as st

TXT = "MEDIA_MAS_FLUJO.txt"
UMBRAL_ZZ = 1.50


def sg(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def cargar(dia):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
    ta = {h: r for h, *r in c.execute(
        "select hora,ema8,ema21 from ta_minute where fecha=?", (dia,))}
    if dia == "2026-08-13":
        t = c.execute("select substr(hora,1,5), last, size from tape where fecha=? "
                      "and grupo='SPY' and last is not null and size is not null "
                      "order by ts,id", (dia,)).fetchall()
        c.close()
    else:
        c.close()
        d = sqlite3.connect("spy_tape_ayer.db")
        t = d.execute("select minuto, price, size from trades_raw "
                      "order by ts_et, rowid").fetchall()
        d.close()
    h = [x[0] for x in v]
    cl = [x[1] for x in v]
    # actividad SIN signo (lo unico robusto) y mayor bloque
    vol, blk = {}, {}
    for m, price, size in t:
        if size is None or size <= 0:
            continue
        vol[m] = vol.get(m, 0) + size
        blk[m] = max(blk.get(m, 0), size)
    return h, cl, ta, [vol.get(x, 0) for x in h], [blk.get(x, 0) for x in h]


O = []
def p(s=""):
    O.append(s)


p("MEDIA + FLUJO: ¿confirma el tape la direccion de la media?")
p("=" * 104)
p("Direccion: EMA8 vs EMA21.  Confirmacion: actividad del tape (sin signo, sin filtrar).")
p("Verdad: lado del tramo vigente (ZigZag $1.50).")
p("")

for dia in ("2026-08-13", "2026-08-12"):
    h, cl, ta, VOL, BLK = cargar(dia)
    n = len(cl)
    piv, d_, hi, lo = [0], 0, 0, 0
    for i in range(1, n):
        if cl[i] > cl[hi]:
            hi = i
        if cl[i] < cl[lo]:
            lo = i
        if d_ >= 0 and cl[hi] - cl[i] >= UMBRAL_ZZ:
            piv.append(hi); d_ = -1; lo = i
        elif d_ <= 0 and cl[i] - cl[lo] >= UMBRAL_ZZ:
            piv.append(lo); d_ = 1; hi = i
    piv.append(n - 1)
    piv = sorted(set(piv))
    verdad = [0] * n
    for k in range(len(piv) - 1):
        a, b = piv[k], piv[k + 1]
        s = 1 if cl[b] > cl[a] else -1
        for i in range(a, b):
            verdad[i] = s

    def dir_media(i):
        t = ta.get(h[i])
        if not t or not t[0] or not t[1]:
            return 0
        return sg(t[0] - t[1])

    p(f"--- {dia} ---")
    for nomf, S in (("volumen del minuto", VOL), ("mayor bloque", BLK)):
        med = st.median([x for x in S if x]) or 1
        p(f"   confirmacion por {nomf}   (mediana {med:,.0f})")
        p(f"   {'nivel de flujo':>22} {'n':>6} {'acierta media':>14} {'vs sin filtro':>14}")
        base = None
        for et, f in (("TODOS", lambda r: True), ("calma <1x", lambda r: r < 1),
                      ("1x-2x", lambda r: 1 <= r < 2), (">=2x", lambda r: r >= 2),
                      (">=3x", lambda r: r >= 3), (">=5x", lambda r: r >= 5)):
            sel = [i for i in range(30, n)
                   if verdad[i] != 0 and dir_media(i) != 0 and f(S[i] / med)]
            if len(sel) < 10:
                continue
            ok = sum(1 for i in sel if dir_media(i) == verdad[i])
            pc = 100 * ok / len(sel)
            if et == "TODOS":
                base = pc
                p(f"   {et:>22} {len(sel):6} {pc:13.1f}% {'(referencia)':>14}")
            else:
                p(f"   {et:>22} {len(sel):6} {pc:13.1f}% {pc-base:+13.1f}")
        p("")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
