"""
atribucion.py — READ-ONLY

Por que el premium BRUTO no puede decir la direccion, medido sobre la BD real.

El premium bruto de un strike no sabe si alguien COMPRO calls (alcista) o los
VENDIO (bajista): es el mismo dinero. La direccion vive UNICAMENTE en el signo
(el agresor). Este script mide que fraccion del flujo llega con signo.
"""
import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "spy_history.db")
db = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
c = db.cursor()

print("=" * 78)
print("CUANTO DEL FLUJO LLEGA CON DIRECCION (signo) — por dia y expiry 0DTE")
print("=" * 78)
print("VERIFICADO en spy_direction.py:1450 y :1458 — `day_prem` y `net_prem` son")
print("AMBOS acumulados del dia sobre la misma base. Se toma, por strike, el ULTIMO")
print("valor del dia, y se compara |neto| contra bruto.")
print()
print("%-12s %8s %16s %16s %10s" %
      ("fecha", "strikes", "bruto del dia", "|neto| del dia", "atribuido"))
print("-" * 78)
# fetchall ANTES del bucle: reusar el mismo cursor dentro reinicia la iteracion
# y solo se procesaria la primera fecha (me acaba de pasar).
_fechas = [x[0] for x in c.execute(
    "SELECT DISTINCT fecha FROM premium_minute ORDER BY fecha").fetchall()]
for f in _fechas:
    exp = f.replace("-", "")
    filas = c.execute(
        "SELECT hora, strike, right, day_prem, net_prem FROM premium_minute "
        "WHERE fecha=? AND expiry=? AND net_prem IS NOT NULL AND day_prem IS NOT NULL "
        "ORDER BY hora", (f, exp)).fetchall()
    ultimo = {}
    for h, k, r, dp, npr in filas:
        ultimo[(k, r)] = (dp, npr)          # ordenado por hora -> queda el ultimo
    bruto = sum(v[0] for v in ultimo.values())
    neto = sum(abs(v[1]) for v in ultimo.values())
    pct = (neto / bruto * 100) if bruto else 0
    print("%-12s %8d %16.0f %16.0f %9.1f%%" % (f, len(ultimo), bruto, neto, pct))

print("\n" + "=" * 78)
print("EL PUNTO DE FONDO")
print("=" * 78)
print("""El premium BRUTO es direccionalmente CIEGO por construccion: 1 M$ en calls
es identico lo compre un alcista o lo venda un bajista. Todas las variables
'bruto_*' del barrido miden VOLUMEN DE DINERO, no intencion.

La direccion solo existe en el NETO (agresor: quien cruza el spread). Y el neto
es justo la parte que hoy se descarta: `_on_ticks` solo firma cuando
last >= ask o last <= bid, comparando el precio del ULTIMO trade contra el
bid/ask del momento de la LECTURA — casi nunca coinciden.

=> No es que el premium no diga la direccion. Es que la parte del premium que
   LLEVA la direccion es la que no estamos capturando bien todavia.""")
db.close()
