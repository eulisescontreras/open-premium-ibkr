# -*- coding: utf-8 -*-
"""COLD RUN de core/salida — verifica la lógica de salida operable (flip / aplanar 15:50 /
mercado 15:55 / verificación plana <16:00) y las guardas de apertura. Exit 0 = verde."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from sys2.core import salida as S
from sys2 import config as C

pC = {"rt": "C"}


def main():
    f = []
    # flip: señal contraria antes del aplanado
    if S.decidir_salida(pC, "P", "11:00") != "flip":
        f.append("no detecta flip (señal contraria)")
    # sin señal / misma dirección -> mantener
    if S.decidir_salida(pC, None, "11:00") is not None:
        f.append("mantiene mal (sin señal)")
    if S.decidir_salida(pC, "C", "11:00") is not None:
        f.append("cierra con señal MISMA dirección (no debería)")
    # aplanar a las 15:50
    if S.decidir_salida(pC, None, "15:50") != "aplanar":
        f.append("no aplana a las 15:50")
    if S.decidir_salida(pC, None, "15:49") is not None:
        f.append("aplana antes de tiempo (15:49)")
    # mercado a las 15:55 (prioridad sobre aplanar/flip)
    if S.decidir_salida(pC, None, "15:55") != "mercado":
        f.append("no fuerza mercado a las 15:55")
    if S.decidir_salida(pC, "P", "15:56") != "mercado":
        f.append("mercado no tiene prioridad sobre flip a las 15:56")
    # sin posición -> None
    if S.decidir_salida(None, "P", "15:55") is not None:
        f.append("devuelve algo sin posición")
    # verificación plana: entre VERIF_PLANA y 16:00
    if not S.debe_verificar_plana(C.VERIF_PLANA) or not S.debe_verificar_plana("15:59"):
        f.append("no marca verificar plana a las 15:59")
    if S.debe_verificar_plana("16:00") or S.debe_verificar_plana("15:40"):
        f.append("marca verificar plana fuera de ventana")
    # apertura: no después de 15:40 ni con 4 trades
    if S.puede_abrir("15:40", 0) or S.puede_abrir("15:41", 0):
        f.append("permite abrir >= 15:40")
    if S.puede_abrir("11:00", C.MAX_TRADES):
        f.append("permite abrir con MAX_TRADES alcanzado")
    if not S.puede_abrir("11:00", 0):
        f.append("no permite abrir en horario válido")

    if f:
        print("ROJO:")
        for x in f:
            print("  -", x)
        return 1
    print("VERDE: salida operable correcta (flip/aplanar 15:50/mercado 15:55/verif plana <16:00)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
