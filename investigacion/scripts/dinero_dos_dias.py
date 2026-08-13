# CUANTO SE SACARIA POR DIA con los parametros de entrada/mantener/salida ya definidos,
# ASUMIENDO que la direccion se conoce (oraculo). En dinero, con el contrato real.
#
# Contrato: ITM mas profundo que quepa en 320$ (80% de 400$), MISMO criterio que
# _strike_ejecucion del sistema. Precios reales -> el theta esta dentro.
# Se dan MID (referencia) y ASK/BID (realista, con spread).
# Lee las BD en SOLO-LECTURA.
import sqlite3
import statistics as st

TXT = "DINERO_DOS_DIAS.txt"
# UMBRAL_ZZ 1.50 y no 0.75: con 0.75 el ZigZag troceaba el 08-12 en 9 "tramos" que en realidad
# eran retrocesos dentro de 3 movimientos largos. Con 1.50 salen los 3 tramos reales en AMBOS
# dias, y en el 08-13 la estructura es la misma de 1.00 a 2.50 -> no depende de afinar el numero.
UMBRAL_ZZ, DIR_MIN = 1.50, 5
CAPITAL, FRAC = 400.0, 0.80
TOPE = CAPITAL * FRAC


def cargar(dia):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
    pm = c.execute("select hora,strike,right,bid,ask,mid from premium_minute where fecha=? "
                   "and expiry=?", (dia, dia.replace("-", ""))).fetchall()
    if dia == "2026-08-13":
        t = c.execute("select substr(hora,1,5), last, size from tape where fecha=? "
                      "and grupo='SPY' and last is not null order by ts,id", (dia,)).fetchall()
        c.close()
    else:
        c.close()
        d = sqlite3.connect("spy_tape_ayer.db")
        t = d.execute("select minuto, price, size from trades_raw "
                      "order by ts_et, rowid").fetchall()
        d.close()
    acc, pp, ps = {}, None, None
    for m, last, mag in t:
        if last is None or mag is None or mag <= 0:
            continue
        ag = None if pp is None else (1 if last > pp else (-1 if last < pp else ps))
        if ag:
            ps = ag
        pp = last
        if ag:
            acc[m] = acc.get(m, 0.0) + ag * last * mag
    PR = {}
    for hora, k, r, b, a, m in pm:
        PR.setdefault(hora, {})[(k, r)] = (b, a, m)
    h = [x[0] for x in v]
    return h, [x[1] for x in v], [x[2] for x in v], [x[3] for x in v], \
        [acc.get(x, 0.0) for x in h], PR


O = []
def p(s=""):
    O.append(s)


p("CUANTO SE SACARIA POR DIA  (entrada+mantener+salida ya definidas, DIRECCION REGALADA)")
p("=" * 112)
p(f"capital {CAPITAL:.0f}$ | tope {TOPE:.0f}$ | contrato: ITM mas profundo que quepa")
p("⚠️ La direccion se REGALA. NO es un resultado operable: es el TECHO si se resolviera.")
p("")

for dia in ("2026-08-13", "2026-08-12"):
    h, hi, lo, cl, net, PR = cargar(dia)
    n = len(cl)
    med = st.median([abs(x) for x in net if x]) or 1.0

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

    p(f"--- {dia} ---  {len(tramos)} tramos")
    p(f"{'#':>3} {'entra':>7} {'sale':>7} {'lado':>5} {'pts':>7} | {'strike':>7} "
      f"{'ent':>6} {'sal':>6} {'x':>3} {'MID $':>9} | {'ent':>6} {'sal':>6} {'REAL $':>9}")
    tot_mid = tot_real = 0.0
    ops = ganan = 0
    for j, (a, b) in enumerate(tramos, 1):
        lado = 1 if cl[b] > cl[a] else -1
        e = None
        for i in range(a + 1, b + 1):
            if i < DIR_MIN:
                continue
            f = sum(net[max(0, i - 4):i + 1]) / 5
            dd = cl[i] - cl[i - DIR_MIN]
            if abs(f) >= med and dd != 0 and (1 if dd > 0 else -1) == lado:
                e = i
                break
        if e is None:
            continue
        s = n - 1
        for i in range(e + 1, n):
            if (cl[i] < min(lo[max(e, i - 20):i])) if lado > 0 else \
               (cl[i] > max(hi[max(e, i - 20):i])):
                s = i
                break
        right = "C" if lado > 0 else "P"
        k = elegir(e, right)
        de = PR.get(h[e], {}).get((k, right)) if k else None
        ds = PR.get(h[s], {}).get((k, right)) if k else None
        if not de or not ds:
            p(f"{j:>3} {h[e]:>7} {h[s]:>7} {right:>5} {(cl[s]-cl[e])*lado:+7.2f} | "
              f"{'sin precio del contrato':>60}")
            continue
        ops += 1
        pm_, ps_ = de[2], ds[2]
        pa, pb = (de[1] or de[2]), (ds[0] or ds[2])
        nc_m = int(TOPE // (pm_ * 100)) if pm_ else 0
        nc_r = int(TOPE // (pa * 100)) if pa else 0
        gm = (ps_ - pm_) * 100 * nc_m if nc_m else 0.0
        gr = (pb - pa) * 100 * nc_r if nc_r else 0.0
        tot_mid += gm
        tot_real += gr
        ganan += 1 if gr > 0 else 0
        p(f"{j:>3} {h[e]:>7} {h[s]:>7} {right:>5} {(cl[s]-cl[e])*lado:+7.2f} | "
          f"{k:7.0f} {pm_:6.2f} {ps_:6.2f} {nc_m:3} {gm:+9.2f} | "
          f"{pa:6.2f} {pb:6.2f} {gr:+9.2f}")
    p(f"    {ops} operaciones, {ganan} ganadoras  |  MID {tot_mid:+.2f}$  |  "
      f"REAL {tot_real:+.2f}$  ({100*tot_real/CAPITAL:+.0f}% del capital)")
    p("")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
