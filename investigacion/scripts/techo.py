# TECHO ABSOLUTO: se entra en el PUNTO EXACTO del giro, con la direccion correcta.
# Mantener = no hacer nada (o exigir magnitud). Salir = trailing.
# Es un ORACULO PERFECTO de entrada: NO operable. Marca el maximo que el resto del sistema
# podria aspirar a capturar si la entrada fuera perfecta.
import sqlite3
import statistics as st

TXT = "TECHO.txt"
UMBRAL_ZZ = 1.50
CAPITAL, FRAC = 400.0, 0.80
TOPE = CAPITAL * FRAC


def cargar(dia):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
    ta = {hh: r for hh, *r in c.execute(
        "select hora,ema8,ema21 from ta_minute where fecha=?", (dia,))}
    pm = c.execute("select hora,strike,right,bid,ask,mid from premium_minute where fecha=? "
                   "and expiry=?", (dia, dia.replace("-", ""))).fetchall()
    if dia == "2026-08-13":
        t = c.execute("select substr(hora,1,5), size from tape where fecha=? and grupo='SPY' "
                      "and size is not null order by ts,id", (dia,)).fetchall()
        c.close()
    else:
        c.close()
        d = sqlite3.connect("spy_tape_ayer.db")
        t = d.execute("select minuto, size from trades_raw").fetchall()
        d.close()
    PR = {}
    for hora, k, r, b, a, m in pm:
        PR.setdefault(hora, {})[(k, r)] = (b, a, m)
    h = [x[0] for x in v]
    vol = {}
    for m, s in t:
        if s and s > 0:
            vol[m] = vol.get(m, 0) + s
    return h, [x[1] for x in v], [x[2] for x in v], [x[3] for x in v], PR, \
        [vol.get(x, 0) for x in h], ta


O = []
def p(s=""):
    O.append(s)


p("TECHO ABSOLUTO: entrada en el PUNTO EXACTO del giro")
p("=" * 104)
p(f"capital {CAPITAL:.0f}$ | tope {TOPE:.0f}$ | contrato ITM que quepa | precios ASK/BID")
p("⚠️ ORACULO: la entrada es perfecta en tiempo Y direccion. NO es operable.")
p("")

TOTALES = {}
for dia in ("2026-08-13", "2026-08-12"):
    h, hi, lo, cl, PR, VOL, ta = cargar(dia)
    n = len(cl)
    med = st.median([x for x in VOL if x]) or 1.0

    def dir_ema(i):
        t = ta.get(h[i])
        if not t or not t[0] or not t[1]:
            return 0
        return 1 if t[0] > t[1] else (-1 if t[0] < t[1] else 0)

    piv, d_, hii, loi = [0], 0, 0, 0
    for i in range(1, n):
        if cl[i] > cl[hii]:
            hii = i
        if cl[i] < cl[loi]:
            loi = i
        if d_ >= 0 and cl[hii] - cl[i] >= UMBRAL_ZZ:
            piv.append(hii); d_ = -1; loi = i
        elif d_ <= 0 and cl[i] - cl[loi] >= UMBRAL_ZZ:
            piv.append(loi); d_ = 1; hii = i
    piv.append(n - 1)
    piv = sorted(set(piv))
    tramos = [(piv[k], piv[k + 1]) for k in range(len(piv) - 1) if piv[k + 1] - piv[k] >= 3]

    def elegir(i, right):
        d = PR.get(h[i], {})
        px = cl[i]
        ks = sorted([k for (k, r) in d if r == right and
                     (k < px if right == "C" else k > px)], reverse=(right == "P"))
        for k in ks:
            b, a, m = d[(k, right)]
            c_ = a or m
            if c_ and c_ > 0 and c_ * 100 <= TOPE:
                return k
        cs = [k for (k, r) in d if r == right]
        return min(cs, key=lambda k: abs(k - px)) if cs else None

    def salir(e, lado, K, exige_mag, mag_min, mag_n):
        flojo = 0
        for i in range(e + 1, n):
            if exige_mag:
                flojo = flojo + 1 if VOL[i] < mag_min * med else 0
                if flojo >= mag_n:
                    return i
            if (cl[i] < min(lo[max(e, i - K):i])) if lado > 0 else \
               (cl[i] > max(hi[max(e, i - K):i])):
                return i
        return n - 1

    p(f"--- {dia} ---  {len(tramos)} giros")
    for nom, K, exige, mm, mn, fuente in (
            ("[dir REAL] solo trail 20m", 20, False, 0, 0, "real"),
            ("[dir EMA]  solo trail 20m", 20, False, 0, 0, "ema"),
            ("[dir EMA]  solo trail 30m", 30, False, 0, 0, "ema"),
            ("[dir EMA]  trail20 + mag<0.5x 5m", 20, True, 0.5, 5, "ema"),
            ("[dir EMA]  trail20 + mag<1x 5m", 20, True, 1.0, 5, "ema")):
        usd, gan, ops, sinp = 0.0, 0, 0, 0
        det = []
        for a, b in tramos:
            e = a                       # ENTRADA EN EL PUNTO EXACTO (oraculo de TIMING)
            # la DIRECCION: real (oraculo total) o la que diga la EMA en ese minuto
            lado = (1 if cl[b] > cl[a] else -1) if fuente == "real" else dir_ema(e)
            if lado == 0:
                sinp += 1
                continue
            s = salir(e, lado, K, exige, mm, mn)
            right = "C" if lado > 0 else "P"
            k = elegir(e, right)
            de = PR.get(h[e], {}).get((k, right)) if k else None
            ds = PR.get(h[s], {}).get((k, right)) if k else None
            if not de or not ds:
                sinp += 1
                continue
            pa, pb = (de[1] or de[2]), (ds[0] or ds[2])
            nc = int(TOPE // (pa * 100)) if pa else 0
            if nc < 1 or not pb:
                sinp += 1
                continue
            g = (pb - pa) * 100 * nc
            usd += g
            ops += 1
            gan += 1 if g > 0 else 0
            det.append((h[e], h[s], right, s - e, g))
        TOTALES[(nom, dia)] = usd
        p(f"  {nom:>34}  {ops} ops, {gan} ganan, {usd:+8.2f}$ ({sinp} sin precio)")
        if nom.startswith("[dir EMA]  solo trail 20m"):
            for e, s_, r, dur, g in det:
                p(f"       {e} -> {s_}  {r}  {dur:3} min  {g:+8.2f}$")
    p("")

p("TOTAL DE LOS DOS DIAS")
p("-" * 104)
for nom in ("[dir REAL] solo trail 20m", "[dir EMA]  solo trail 20m",
            "[dir EMA]  solo trail 30m", "[dir EMA]  trail20 + mag<0.5x 5m",
            "[dir EMA]  trail20 + mag<1x 5m"):
    s = sum(TOTALES.get((nom, d), 0) for d in ("2026-08-13", "2026-08-12"))
    p(f"  {nom:>32}  {s:+10.2f}$   ({100*s/CAPITAL:+.0f}% del capital)")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
