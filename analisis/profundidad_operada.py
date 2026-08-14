# SOLO LECTURA. Profundidad ITM de las operaciones REALES ya ejecutadas: sirve para saber en
# que tramo del modelo sintetico cae de verdad el sistema (compra "el ITM mas profundo que
# quepa en el tope"), y por tanto que fila de la auditoria es la que importa.
import os, sqlite3
REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"

print("%-12s %-6s %-8s %8s %8s %9s %10s" %
      ("fecha", "right", "strike", "spy_ent", "prof_ITM", "entry", "profit"))
print("-" * 74)
prof = []
for db in ("spy_history_20260811.db", "spy_history_20260812.db", "spy_history_20260813.db",
           "spy_history_20260814.db"):
    p = os.path.join(REPO, db)
    if not os.path.exists(p):
        continue
    c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    try:
        rows = c.execute(
            "select fecha,right,strike,spy_entrada,entry_price,profit from trades "
            "where spy_entrada is not null order by fecha,hora_entrada").fetchall()
    except Exception as e:
        rows = []
    c.close()
    for f, r, K, s, px, pr in rows:
        d = (s - K) if r == "C" else (K - s)
        prof.append((d, px))
        print("%-12s %-6s %-8g %8.2f %8.2f %9s %10s"
              % (f, r, K, s, d, ("%.2f" % px) if px else "-",
                 ("%+.2f" % pr) if pr is not None else "abierta"))
    # dedup: la BD de hoy trae tambien filas de dias anteriores
print("-" * 74)
if prof:
    ds = sorted(set(round(d, 2) for d, _ in prof))
    import statistics as st
    print("operaciones: %d | profundidad ITM  min %.2f  mediana %.2f  max %.2f"
          % (len(prof), min(x[0] for x in prof), st.median([x[0] for x in prof]),
             max(x[0] for x in prof)))
    pxs = [x[1] for x in prof if x[1]]
    if pxs:
        print("precio de entrada: min %.2f  mediana %.2f  max %.2f  (tope 400$ = 4.00 por contrato)"
              % (min(pxs), st.median(pxs), max(pxs)))
else:
    print("sin operaciones con spy_entrada registrado")
