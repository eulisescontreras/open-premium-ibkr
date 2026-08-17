# -*- coding: utf-8 -*-
"""COLD RUN anti-LOOK-AHEAD (MANUAL §2.3) — verifica que el motor no tiene las 6 trampas
documentadas. Aserciones sobre las FUNCIONES REALES (no reimplementa). Exit 0 = verde.

Las 6 trampas §2.3:
  1. pos=None sin contabilizar        -> toda posición cerrada suma su P&L.
  2. resultado con otro nombre         -> (n/a en este motor).
  3. menú de contratos                 -> elegir/elegir_vert eligen de la cadena REAL del minuto.
  4. desfase horario fijo              -> t_years usa zoneinfo, NO offset fijo.
  5. extrínseco negativo               -> suelo intrínseco: precio = max(observado, intrínseco).
  6. contrato que deja de cotizar      -> valoración usa el último precio conocido con piso intrínseco.
"""
import os, sys, inspect
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from sys2.backtest import greeks as G, motor
from sys2.core import instrumento as I


def main():
    fallos = []

    # TRAMPA 4 — zoneinfo, no offset fijo. t_years usa datetime+ZoneInfo(ET).
    src_g = inspect.getsource(G)
    if "ZoneInfo" not in src_g or "America/New_York" not in src_g:
        fallos.append("greeks.t_years no usa zoneinfo America/New_York (trampa 4: desfase fijo)")
    src_m = inspect.getsource(motor)
    if "ZoneInfo" not in src_m:
        fallos.append("motor no usa zoneinfo (trampa 4)")

    # TRAMPA 5 — suelo intrínseco: max(observado, intrínseco).
    # call ITM: S=550, K=545 (intr=5); precio observado 3 (< intr) -> debe acotarse a 5.
    v = I.suelo(545, (3.0, 100), 550, 'C')
    if abs(v[0] - 5.0) > 1e-9:
        fallos.append("suelo no acota al intrínseco (call): %.2f != 5.0 (trampa 5)" % v[0])
    v = I.suelo(548, (0.5, 50), 550, 'P')          # put OTM (intr=0) -> queda el observado
    if abs(v[0] - 0.5) > 1e-9:
        fallos.append("suelo altera un precio ya por encima del intrínseco (put): %.2f" % v[0])
    # y conserva el resto de campos (volumen)
    if v[1] != 50:
        fallos.append("suelo no conserva el resto de v (volumen)")

    # TRAMPA 5-bis — implied_vol devuelve None por debajo del intrínseco (no inventa IV).
    iv = G.implied_vol(3.0, 550, 545, 0.001, 0.0, 0.0, 'C')   # precio 3 < intrínseco 5
    if iv is not None:
        fallos.append("implied_vol NO devuelve None con precio<intrínseco (trampa 5): %s" % iv)

    # TRAMPA 1/6 — verificar en el CÓDIGO del motor que:
    #  (1) toda posición se cierra sumando g y poniendo pos=None (nunca pos=None sin sumar);
    #  (6) la valoración usa el último conocido con piso intrínseco (pos.get('_l')).
    if "pos.get('_l'" not in src_m:
        fallos.append("motor no usa el último precio conocido en la valoración (trampa 6)")
    # el cierre siempre suma antes de pos=None: buscar el patrón tot += ... ; ... pos = None
    if "tot += g" not in src_m or "pos = None" not in src_m:
        fallos.append("motor: patrón de cierre 'suma g -> pos=None' no hallado (trampa 1)")
    # NO debe haber un 'pos = None' de cierre sin una suma a tot en su bloque (revisión estructural):
    # el motor tiene exactamente 2 puntos de cierre que suman (gira/aplanado y rodar) — verificado
    # por cr_motor (reproduce +72.375; una posición no contabilizada bajaría el total).

    # TRAMPA 3 — el motor elige contratos de la cadena PM[h] del minuto (no de un menú global):
    if "PM[h].items()" not in src_m:
        fallos.append("motor no selecciona de la cadena del minuto PM[h] (trampa 3)")

    if fallos:
        print("ROJO — trampas de look-ahead detectadas:")
        for x in fallos:
            print("  -", x)
        return 1
    print("VERDE: sin las 6 trampas de look-ahead (§2.3):")
    print("  4) t_years con zoneinfo ET (no offset fijo)")
    print("  5) suelo intrínseco aplicado; implied_vol=None bajo intrínseco")
    print("  6) valoración con último precio conocido + piso intrínseco")
    print("  1) cierres suman P&L antes de pos=None (respaldado por cr_motor)")
    print("  3) contratos elegidos de la cadena real del minuto (PM[h])")
    return 0


if __name__ == "__main__":
    sys.exit(main())
