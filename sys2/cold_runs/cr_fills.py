# -*- coding: utf-8 -*-
"""COLD RUN: persistencia de FILLS por pata (hipotesis critica: se llenan las DOS patas del
vertical?). Ejercita el CHAIN REAL del vivo: SistemaVivo._abrir -> ib.comprar_vertical/single
-> _persistir_operacion -> _persistir_fills, con un FakeIBKR que devuelve Trades de ib_insync
simulados (fills por pata). NO reimplementa la logica: usa los metodos REALES.

Cubre: (A) vertical LLENO (2 patas), (B) vertical PARCIAL (solo la larga -> alerta + parcial=1),
(C) single LLENO, (D) trade=None (smoke/FakeIB) -> no persiste, no crash.
Corre contra una BD temporal (no toca sys2.db). Exit 0 = verde, 1 = rojo.
"""
import os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sys2 import config as C
from sys2.db import repo
from sys2.vivo import log as L
from sys2.vivo.sistema import SistemaVivo


# ── Trade de ib_insync SIMULADO (misma forma que lee _persistir_fills: fills[].execution/.contract) ──
class FakeExec:
    def __init__(self, side, price):
        self.side = side          # 'BOT' | 'SLD'
        self.price = price


class FakeContract:
    def __init__(self, strike, right, secType="OPT"):
        self.strike = strike
        self.right = right
        self.secType = secType


class FakeFill:
    def __init__(self, strike, right, side, price, secType="OPT"):
        self.contract = FakeContract(strike, right, secType)
        self.execution = FakeExec(side, price)


class FakeTrade:
    def __init__(self, fills):
        self.fills = fills


class FakeIBnucleo:
    def sleep(self, s):           # _persistir_fills hace self.ib.ib.sleep(3)
        return None


class FakeIBKR:
    """Devuelve el Trade preconfigurado en `self._trade` al colocar cualquier orden."""
    def __init__(self):
        self.ib = FakeIBnucleo()
        self._trade = None

    def comprar_vertical(self, *a, **k):
        return self._trade

    def comprar_single(self, *a, **k):
        return self._trade


# ── cadena del minuto {(right,strike): (mid, day_vol)} — calls alrededor de spot=500 ──
def _pm_calls():
    return {
        ("C", 494.0): (7.0, 100.0),
        ("C", 496.0): (5.5, 90.0),
        ("C", 498.0): (4.5, 80.0),
        ("C", 500.0): (3.0, 120.0),
        ("C", 502.0): (2.0, 110.0),
    }


def _nuevo_sistema(con, fake):
    """SistemaVivo sin __init__ (evita abrir sys2.db real y crear IB). Solo lo que usa el chain."""
    s = SistemaVivo.__new__(SistemaVivo)
    s.con = con
    s.ib = fake
    s.pos = None
    s.hechas = 0
    s.nq = 1
    s.unidades_base = 1
    s.fecha = "2025-04-09"
    s.expiry = "20250409"
    s._origen = {"09:45": "cr_fills"}
    s.cfg = {"nivel": 1, "modo": "test", "version": "t", "tope": 320, "meta": 0}
    return s


def _fills_de(con, op_id):
    return list(con.execute(
        "select strike,right,accion,lleno,parcial from fills where operacion_id=? order by strike",
        (op_id,)))


def _ultima_op(con):
    return con.execute("select max(id) from operaciones").fetchone()[0]


def main():
    fallos = []
    notis = []       # capturamos notificaciones para asertar la alerta de parcial
    d = tempfile.mkdtemp()
    con = repo.abrir(os.path.join(d, "t.db"))

    # aislar logs/notificaciones (no contaminar los logs reales; capturar la alerta)
    L.log = lambda *a, **k: None
    L.notificar = lambda msg, cat="": notis.append((cat, msg))
    C.RUMB = None                # saltar el veto direccional (no es lo que se testea aqui)

    fake = FakeIBKR()

    # ───────────────────── A) VERTICAL LLENO (2 patas) ─────────────────────
    C.ANCHO = 4.0
    s = _nuevo_sistema(con, fake)
    # ib_insync incluye el fill AGREGADO del combo (secType='BAG', strike=0) junto a las 2 patas:
    # el sistema debe SALTARLO y persistir SOLO las patas reales (validado contra la doc de ib_insync).
    fake._trade = FakeTrade([FakeFill(0.0, "", "BOT", 2.5, secType="BAG"),   # <- agregado del combo
                             FakeFill(494.0, "C", "BOT", 7.0),               # larga comprada
                             FakeFill(498.0, "C", "SLD", 4.5)])              # corta vendida
    notis.clear()
    s._abrir("09:45", 500.0, "C", _pm_calls())
    op = _ultima_op(con)
    rows = _fills_de(con, op)
    llenas = [r for r in rows if r[3] == 1]
    parciales = [r for r in rows if r[4] == 1]
    alerta = any("PARCIAL" in m for _, m in notis)
    bag = [r for r in rows if r[0] == 0.0]      # NO debe persistirse el fill del BAG
    print("A) vertical lleno: op#%s filas=%d llenas=%d parciales=%d alerta=%s bag_filas=%d"
          % (op, len(rows), len(llenas), len(parciales), alerta, len(bag)))
    if len(rows) != 2 or len(llenas) != 2 or parciales or alerta:
        fallos.append("A: esperado 2 filas / 2 llenas / 0 parciales / sin alerta; got "
                      "%d/%d/%d/%s" % (len(rows), len(llenas), len(parciales), alerta))
    if bag:
        fallos.append("A: el fill del BAG (strike=0) NO debe persistirse: %s" % bag)
    if {(r[0], r[2]) for r in rows} != {(494.0, "BUY"), (498.0, "SELL")}:
        fallos.append("A: patas/acciones incorrectas: %s" % rows)

    # ───────────────────── B) VERTICAL PARCIAL (solo la larga) ─────────────────────
    s = _nuevo_sistema(con, fake)
    fake._trade = FakeTrade([FakeFill(494.0, "C", "BOT", 7.0)])     # SOLO la larga se lleno
    notis.clear()
    s._abrir("09:45", 500.0, "C", _pm_calls())
    op = _ultima_op(con)
    rows = _fills_de(con, op)
    llenas = [r for r in rows if r[3] == 1]
    parciales = [r for r in rows if r[4] == 1]
    alerta = any("PARCIAL" in m for _, m in notis)
    print("B) vertical parcial: op#%s filas=%d llenas=%d parciales=%d alerta=%s"
          % (op, len(rows), len(llenas), len(parciales), alerta))
    # 494 llena (lleno=1), 498 faltante (parcial=1, lleno=0) + alerta disparada
    corta = [r for r in rows if r[0] == 498.0]
    larga = [r for r in rows if r[0] == 494.0]
    if len(rows) != 2 or len(llenas) != 1 or len(parciales) != 1 or not alerta:
        fallos.append("B: esperado 2 filas / 1 llena / 1 parcial / alerta; got "
                      "%d/%d/%d/%s" % (len(rows), len(llenas), len(parciales), alerta))
    if not (larga and larga[0][3] == 1 and larga[0][4] == 0):
        fallos.append("B: la larga 494 deberia estar llena (lleno=1,parcial=0): %s" % larga)
    if not (corta and corta[0][3] == 0 and corta[0][4] == 1):
        fallos.append("B: la corta 498 deberia faltar (lleno=0,parcial=1): %s" % corta)

    # ───────────────────── C) SINGLE LLENO ─────────────────────
    C.ANCHO = None               # fuerza el camino single en _abrir
    s = _nuevo_sistema(con, fake)
    fake._trade = FakeTrade([FakeFill(500.0, "C", "BOT", 3.0)])
    notis.clear()
    s._abrir("09:45", 500.0, "C", _pm_calls())
    op = _ultima_op(con)
    rows = _fills_de(con, op)
    print("C) single lleno: op#%s filas=%d" % (op, len(rows)))
    if len(rows) != 1 or rows[0][2] != "BUY" or rows[0][3] != 1:
        fallos.append("C: esperado 1 fila BUY llena; got %s" % rows)
    if any("PARCIAL" in m for _, m in notis):
        fallos.append("C: single no debe disparar alerta de PARCIAL de vertical")

    # ───────────────────── D) trade=None (smoke/FakeIB) -> no persiste, no crash ─────────────────────
    antes = repo.contar(con, "fills")
    s = _nuevo_sistema(con, fake)
    s._persistir_fills(None, 999999, "09:45", "vertical", [(1.0, "C", "BUY")])
    despues = repo.contar(con, "fills")
    print("D) trade=None: fills antes=%d despues=%d (sin cambio)" % (antes, despues))
    if despues != antes:
        fallos.append("D: trade=None NO debe insertar filas (antes=%d despues=%d)" % (antes, despues))

    con.close()
    if fallos:
        print("\nROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("\nVERDE: persistencia de fills por pata OK (lleno / parcial+alerta / single / trade=None)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
