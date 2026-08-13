# ¿QUE CONTRATO CONVIENE segun el movimiento esperado? Se simulan las 5 operaciones REALES
# del sistema de hoy comprando CADA strike disponible, con el tope de capital del usuario.
#
# Capital: 400 $ | tope por contrato: 320 $ (80%), como en el sistema actual.
# Precio de ejecucion: `mid` de premium_minute (0DTE). NO incluye spread ni comision: es una
# cota SUPERIOR optimista, y se dice explicitamente. Lee la BD en SOLO-LECTURA.
import sqlite3

SRC = "spy_history.db"
TXT = "MEJOR_CONTRATO_HOY.txt"
DIA = "2026-08-13"
CAPITAL, TOPE = 400.0, 320.0

# operaciones reales del sistema (de SALIDAS_HOY / DIAGNOSTICO_HOY)
OPS = [("09:35", "10:43", +1), ("10:44", "12:05", -1), ("12:20", "13:32", +1),
       ("14:05", "14:06", +1), ("14:07", "15:09", +1)]

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)
cl = {h: c for h, c in src.execute(
    "select hora,close from bars_minute where fecha=?", (DIA,))}
pm = src.execute("select hora,strike,right,mid from premium_minute where fecha=? "
                 "and expiry='20260813' and mid is not null and mid>0", (DIA,)).fetchall()
src.close()
P = {}
for hora, strike, right, mid in pm:
    P.setdefault(hora, {})[(strike, right)] = mid

O = []
def p(s=""):
    O.append(s)


p(f"¿QUE CONTRATO CONVIENE?  -  {DIA}")
p("=" * 104)
p(f"capital {CAPITAL:.0f} $ | tope por contrato {TOPE:.0f} $ | precio = mid de premium_minute")
p("OJO: el mid NO incluye spread ni comision. Los numeros son una COTA OPTIMISTA.")
p("     Hoy la primera orden costo 4 intentos y 96 segundos: la ejecucion real resta.")
p("")

tot = {}
for e, s, lado in OPS:
    right = "C" if lado > 0 else "P"
    de, ds = P.get(e, {}), P.get(s, {})
    spy_e, spy_s = cl.get(e), cl.get(s)
    if not de or not ds or spy_e is None:
        continue
    p(f"OPERACION {e} -> {s}   {'CALL' if lado>0 else 'PUT':>4}   "
      f"SPY {spy_e:.2f} -> {spy_s:.2f}  ({spy_s-spy_e:+.2f})")
    p(f"{'strike':>8} {'moneyness':>11} {'entrada':>8} {'salida':>8} {'contr':>6} "
      f"{'coste':>8} {'valor':>8} {'P&L':>9} {'%':>8}")
    filas = []
    for (k, r), mid_e in sorted(de.items()):
        if r != right:
            continue
        mid_s = ds.get((k, r))
        if mid_s is None:
            continue
        nc = int(TOPE // (mid_e * 100))
        if nc < 1:
            continue
        coste = nc * mid_e * 100
        valor = nc * mid_s * 100
        pl = valor - coste
        # moneyness respecto al SPY en la entrada
        dist = (spy_e - k) if right == "C" else (k - spy_e)
        mon = "ITM" if dist > 0 else ("ATM" if abs(dist) < 0.5 else "OTM")
        filas.append((pl, k, mon, mid_e, mid_s, nc, coste, valor))
        tot.setdefault((mon, r), []).append(pl)
    for pl, k, mon, me, ms, nc, co, va in sorted(filas, key=lambda x: -x[0])[:14]:
        p(f"{k:8.0f} {mon:>11} {me:8.2f} {ms:8.2f} {nc:6} {co:8.2f} {va:8.2f} "
          f"{pl:+9.2f} {100*pl/co:+7.1f}%")
    p("")

p("RESUMEN POR TIPO DE CONTRATO (suma de las 5 operaciones)")
p("-" * 104)
p(f"{'tipo':>12} {'n':>5} {'P&L total':>12} {'P&L medio':>12}")
for key in sorted(tot):
    v = tot[key]
    p(f"{key[0] + ' ' + key[1]:>12} {len(v):5} {sum(v):+12.2f} {sum(v)/len(v):+12.2f}")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT} ({len(O)} lineas)")
