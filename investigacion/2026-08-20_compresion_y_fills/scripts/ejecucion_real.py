# -*- coding: utf-8 -*-
# SUPERFICIE EMPÍRICA DE EJECUCIÓN — el equivalente de `envolvente.py` pero para el LIBRO.
#
# `envolvente.py` construyó una superficie de PRECIOS (percentiles del extrínseco) para preguntar
# "¿y si las opciones hubieran estado más caras?". Aquí se construye la superficie de EJECUCIÓN
# a partir de las 587 órdenes REALES lanzadas contra IBKR el 2026-08-20, para preguntar algo que
# el backtest nunca ha respondido: "¿y si solo contamos lo que de verdad se puede ejecutar?".
#
# EL BACKTEST HOY ASUME TRES COSAS FALSAS (verificado):
#   1. que toda orden se acepta        -> IBKR rechaza el ITM por la tarde (hasta el 100%)
#   2. que toda orden llena            -> el fill real va del 14% al 84% según moneyness
#   3. que se compra y vende al precio -> usa el `close` del minuto (motor.cargar: select close)
#
# QUÉ SE MODELA Y QUÉ NO:
#   SÍ  P(rechazo por margen | hora, moneyness)   — 587 pruebas
#   SÍ  P(fill | moneyness), solo débitos >=20$   — los que el sistema compraría de verdad
#   SÍ  slippage de SALIDA por tramo de débito    — 132 operaciones completas
#   NO  el coste de ENTRADA: el motor ya aplica *1.01 y el slippage de compra medido es +0,80%.
#       Añadir el medio spread sería CONTARLO DOS VECES.
#   NO  fills parciales (el sondeo fue siempre de 1 contrato).
#   NO  la variación HORARIA del fill: el n por celda (hora x mny) no da para estimarla.
#
# ⚠️ LIMITACIÓN QUE NO SE PUEDE ARREGLAR CON ESTOS DATOS: es UN SOLO DÍA. La ESTRUCTURA
# (que el ITM se rechaza por la tarde, que el fill cae con el spread) es microestructura y
# probablemente estable; el NIVEL depende de la volatilidad de la sesión. Extrapolar a 485
# sesiones es una HIPÓTESIS, no una medición. Se declara en el JSON y en el informe.
import sqlite3, json, os, collections

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
BD = os.path.join(RAIZ, "investigacion", "2026-08-19_sistema_real", "resultados", "fills_reales.db")
SAL = os.path.join(RAIZ, "investigacion", "2026-08-20_compresion_y_fills", "resultados",
                   "ejecucion_real.json")
FECHA = "2026-08-20"
DEB_MIN = 20.0          # el sistema exige 20$ de débito: por debajo no compra nada

c = sqlite3.connect(BD)
c.row_factory = sqlite3.Row
filas = [dict(r) for r in c.execute(
    "select hora,mny_obj,mny_real,mid,spread_pct,compra_estado,compra_motivo,slip_venta_pct,"
    "forzado from barrido where fecha=? and mid is not null", (FECHA,))]
c.close()
print("pruebas cargadas: %d" % len(filas))

MNYS = sorted({int(f['mny_obj']) for f in filas})
HORAS = ["09", "10", "11", "12", "13", "14", "15"]

# ── 1. RECHAZO POR MARGEN: P(rechazo | hora, moneyness) ────────────────────────────
# Celdas con n<3 se dejan vacías y el consumidor cae al agregado de la HORA (el patrón
# dominante es horario: antes de las 12:00 no se rechaza NADA, 130 pruebas, 0 rechazos).
rech = {}
rech_hora = {}
for hh in HORAS:
    sub_h = [f for f in filas if f['hora'][:2] == hh]
    if not sub_h:
        continue
    rech_hora[hh] = sum(1 for f in sub_h if f['compra_motivo'] == 'MARGEN') / float(len(sub_h))
    for m in MNYS:
        s = [f for f in sub_h if int(f['mny_obj']) == m]
        if len(s) >= 3:
            rech["%s|%d" % (hh, m)] = sum(1 for f in s if f['compra_motivo'] == 'MARGEN') / float(len(s))

# ── 2. FILL: P(fill | moneyness) sobre las NO rechazadas y con débito >= 20$ ────────
fill = {}
for m in MNYS:
    s = [f for f in filas if int(f['mny_obj']) == m and f['compra_motivo'] != 'MARGEN'
         and f['mid'] * 100 >= DEB_MIN]
    if len(s) >= 5:
        fill[str(m)] = sum(1 for f in s if f['compra_estado'] == 'Filled') / float(len(s))

# ── 3. SLIPPAGE DE SALIDA por tramo de débito (132 operaciones completas) ───────────
TRAMOS = [(20, 80), (80, 150), (150, 250), (250, 10000)]
slipv = {}
for lo, hi in TRAMOS:
    s = [f['slip_venta_pct'] for f in filas if f['slip_venta_pct'] is not None
         and lo <= f['mid'] * 100 < hi]
    if len(s) >= 4:
        s2 = sorted(s)
        slipv["%d-%d" % (lo, hi)] = {"n": len(s), "media": sum(s) / len(s),
                                     "mediana": s2[len(s2) // 2]}

# ── 4. SPREAD por moneyness (informativo: NO se aplica, el motor ya cobra 1% a la entrada) ──
spread = {}
for m in MNYS:
    s = [f['spread_pct'] for f in filas if int(f['mny_obj']) == m and f['spread_pct'] is not None
         and f['mid'] * 100 >= DEB_MIN]
    if len(s) >= 5:
        spread[str(m)] = sum(s) / len(s)

forz = [f for f in filas if f['forzado'] is not None]
E = {"fecha": FECHA, "n_pruebas": len(filas), "deb_min": DEB_MIN,
     "rechazo": rech, "rechazo_hora": rech_hora, "fill": fill, "slip_venta": slipv,
     "spread": spread,
     "ventas_forzadas": {"n": len(forz), "forzadas": sum(1 for f in forz if f['forzado'])},
     "AVISO": ("UN SOLO DÍA (2026-08-20). La ESTRUCTURA es microestructura y probablemente "
               "estable; el NIVEL depende de la volatilidad de la sesión. Aplicarlo a 485 "
               "sesiones es HIPÓTESIS, no medición. El coste de ENTRADA no está aquí a "
               "propósito: el motor ya aplica *1.01 y el slippage de compra medido es +0,80%.")}
json.dump(E, open(SAL, "w"), indent=1)

print("\n=== RECHAZO POR MARGEN (celdas con n>=3) ===")
print("%-6s" % "hora", end="")
for m in MNYS:
    print("%8s" % ("%+d" % m), end="")
print("%9s" % "TODA h")
for hh in HORAS:
    if hh not in rech_hora:
        continue
    print("%-6s" % (hh + ":xx"), end="")
    for m in MNYS:
        k = "%s|%d" % (hh, m)
        print("%8s" % (("%.0f%%" % (100 * rech[k])) if k in rech else "-"), end="")
    print("%8.0f%%" % (100 * rech_hora[hh]))

print("\n=== FILL (débito >= 20$, no rechazadas) ===")
for m in MNYS:
    if str(m) in fill:
        print("   mny %+d : %.0f%%   (spread medio %.1f%%)"
              % (m, 100 * fill[str(m)], spread.get(str(m), 0)))

print("\n=== SLIPPAGE DE SALIDA por débito ===")
for k, v in sorted(slipv.items(), key=lambda x: int(x[0].split("-")[0])):
    print("   %-12s n=%-3d media %+.2f%%  mediana %+.2f%%" % (k + "$", v["n"], v["media"], v["mediana"]))

print("\nventas forzadas a mercado: %d de %d" % (E["ventas_forzadas"]["forzadas"],
                                                 E["ventas_forzadas"]["n"]))
print("\nguardado en %s" % SAL)
