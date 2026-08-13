# EVALUACION POR COMPONENTE en los DOS dias: entrar / mantener / salir, cada uno aislado.
#
# Para poder juzgar MANTENER y SALIR hay que quitar de en medio la direccion (que no sabemos
# dar): se usa la direccion REAL del tramo (oraculo). Asi, lo que falle es del componente,
# no de la direccion.
#   ENTRAR   -> ¿el filtro de flujo avisa a tiempo del tramo? (¿cuantos minutos tarde?)
#   MANTENER -> ¿aguanta el trailing hasta el final del tramo, o lo corta antes?
#   SALIR    -> ¿sale cerca del pivote, o se pasa y devuelve?
# Lee las BD en SOLO-LECTURA.
import sqlite3
import statistics as st

TXT = "EVALUACION.txt"
UMBRAL_ZZ = 0.75
DIR_MIN = 5


def cargar(dia):
    c = sqlite3.connect("file:spy_history.db?mode=ro", uri=True, timeout=15)
    v = c.execute("select hora,high,low,close from bars_minute where fecha=? order by hora",
                  (dia,)).fetchall()
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
    h = [x[0] for x in v]
    return h, [x[1] for x in v], [x[2] for x in v], [x[3] for x in v], \
        [acc.get(x, 0.0) for x in h]


O = []
def p(s=""):
    O.append(s)


p("EVALUACION POR COMPONENTE  -  los dos dias, cada pieza aislada")
p("=" * 112)
p("La direccion se REGALA (la del tramo real) para poder juzgar mantener y salir por separado.")
p("")

resumen = {}
for dia in ("2026-08-13", "2026-08-12"):
    h, hi, lo, cl, net = cargar(dia)
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

    p(f"--- {dia} ---  {len(tramos)} tramos  mediana flujo {med:,.0f}")
    p(f"{'#':>3} {'desde':>7} {'hasta':>7} {'min':>4} {'recorr':>8} | "
      f"{'ENTRA':>7} {'tarde':>6} | {'SALE':>7} {'dentro?':>8} | {'captura':>8} {'%tramo':>7}")
    tardes, capts, dentro_ = [], [], 0
    for j, (a, b) in enumerate(tramos, 1):
        lado = 1 if cl[b] > cl[a] else -1
        rec = cl[b] - cl[a]
        # ENTRAR: primer minuto del tramo con flujo >= mediana y direccion ya visible
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
            p(f"{j:>3} {h[a]:>7} {h[b]:>7} {b-a:4} {rec:+8.2f} | {'NUNCA':>7} {'-':>6} | "
              f"{'-':>7} {'-':>8} | {0.0:+8.2f} {0:6.0f}%")
            capts.append(0.0)
            continue
        tarde = e - a
        tardes.append(tarde)
        # MANTENER/SALIR: trailing extremo 20
        s = n - 1
        for i in range(e + 1, n):
            fuera = (cl[i] < min(lo[max(e, i - 20):i])) if lado > 0 else \
                    (cl[i] > max(hi[max(e, i - 20):i]))
            if fuera:
                s = i
                break
        g = (cl[s] - cl[e]) * lado
        capts.append(g)
        dd = "si" if s <= b else f"+{s-b}"
        if s <= b:
            dentro_ += 1
        p(f"{j:>3} {h[a]:>7} {h[b]:>7} {b-a:4} {rec:+8.2f} | {h[e]:>7} {tarde:6} | "
          f"{h[s]:>7} {dd:>8} | {g:+8.2f} {100*g/abs(rec) if rec else 0:6.0f}%")
    disp = sum(abs(cl[b] - cl[a]) for a, b in tramos)
    resumen[dia] = (len(tramos), disp, sum(capts),
                    st.mean(tardes) if tardes else None, dentro_, len(tramos))
    p(f"    tramos {len(tramos)} | disponible {disp:.2f} | capturado {sum(capts):+.2f} "
      f"({100*sum(capts)/disp:.0f}%) | retraso medio {st.mean(tardes) if tardes else 0:.1f} min "
      f"| sale dentro del tramo {dentro_}/{len(tramos)}")
    p("")

p("VEREDICTO POR COMPONENTE")
p("-" * 112)
p(f"{'':>12} {'tramos':>8} {'disponible':>11} {'capturado':>11} {'%':>6} "
  f"{'retraso':>9} {'sale a tiempo':>14}")
for dia, (nt, disp, cap, tar, dd, tot) in resumen.items():
    p(f"{dia:>12} {nt:8} {disp:11.2f} {cap:+11.2f} {100*cap/disp:5.0f}% "
      f"{tar if tar else 0:8.1f}m {dd:>7}/{tot}")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
