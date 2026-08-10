# -*- coding: utf-8 -*-
"""
Cold run HEADLESS de Walls / GEX / Gamma Flip (proyecto SPY Direction).
Ejercita el CODIGO REAL: las funciones puras y el METODO REAL SpyDirection.compute_walls
(con un FakeIB que entrega tickers), sin mercado. Verifica matematica, cableado, persistencia
en BD (walls_snapshot + premium_minute), magneto dinamico != estatico, y deteccion de staleness.

Correr:  python spy_walls_coldrun.py
Exit 0 = todo OK ; Exit 1 = fallo (imprime el detalle).
"""
import math
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import spy_direction as S

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


# ---------------------------------------------------------------- Fakes
class FakeGreeks:
    def __init__(self, gamma):
        self.gamma = gamma


class FakeTicker:
    def __init__(self, oi=None, gamma=None, volume=0.0, last=1.0, bid=0.9, ask=1.1, right="C"):
        # OI se entrega en callOpenInterest/putOpenInterest segun el 'right' del contrato
        self.callOpenInterest = oi if right == "C" else float("nan")
        self.putOpenInterest = oi if right == "P" else float("nan")
        self.modelGreeks = FakeGreeks(gamma) if gamma is not None else None
        self.volume = volume
        self.last = last
        self.bid = bid
        self.ask = ask
        self.time = "2026-08-11 10:00:00"


class FakeContract:
    def __init__(self, strike, right, conId):
        self.strike = strike
        self.right = right
        self.conId = conId
        self.symbol = "SPY"
        self.secType = "OPT"


class FakeIB:
    def __init__(self):
        self._tk = {}   # conId -> FakeTicker
    def isConnected(self):
        return True
    def ticker(self, c):
        return self._tk[c.conId]


# ================================================================ TEST A: funciones puras
print("== TEST A: funciones puras ==")

# A1 walls basicas + max pain (diferencial: max pain no cambia tras refactor)
call_oi = {770: 100, 775: 500, 780: 200}
put_oi = {760: 100, 765: 600, 770: 300}
w = S.compute_walls_from_oi(call_oi, put_oi, 772.0)
check(w["call_wall"] == 775, f"call_wall=775 (mayor call OI) -> {w['call_wall']}")
check(w["put_wall"] == 765, f"put_wall=765 (mayor put OI) -> {w['put_wall']}")
# max pain manual sobre los mismos strikes
strikes = sorted(set(call_oi) | set(put_oi))
def _mp(coi, poi):
    best_k = best = None
    for K in strikes:
        pay = (sum(coi.get(s, 0) * max(0.0, K - s) for s in strikes)
               + sum(poi.get(s, 0) * max(0.0, s - K) for s in strikes))
        if best is None or pay < best:
            best, best_k = pay, K
    return best_k
check(w["max_pain"] == _mp(call_oi, put_oi), f"max_pain == calculo manual ({w['max_pain']})")
check(S._max_pain(call_oi, put_oi) == w["max_pain"], "_max_pain coincide con compute_walls_from_oi")

# A2 vacio
check(S.compute_walls_from_oi({}, {}, 100.0) is None, "walls con OI vacio -> None")
check(S._max_pain({}, {}) is None, "_max_pain vacio -> None")

# A3 GEX signo: dealers +call/-put. Solo calls -> LONG (>0); solo puts -> SHORT (<0)
g_long = S.compute_gex_from_greeks({770: 1000}, {}, {770: 0.05}, {}, 772.0, 1.0, -1.0)
check(g_long["gex_total"] > 0 and g_long["regime"] == "LONG", f"solo calls -> LONG ({g_long['regime']})")
g_short = S.compute_gex_from_greeks({}, {770: 1000}, {}, {770: 0.05}, 772.0, 1.0, -1.0)
check(g_short["gex_total"] < 0 and g_short["regime"] == "SHORT", f"solo puts -> SHORT ({g_short['regime']})")

# A4 gamma flip: calls arriba (+), puts abajo (-) -> la acumulada cruza 0 entre medias
coi = {780: 1000}; poi = {760: 1000}
cg = {780: 0.05}; pg = {760: 0.05}
gf = S.compute_gex_from_greeks(coi, poi, cg, pg, 770.0, 1.0, -1.0)
# acumulada: en 760 (put) negativa, en 780 (call) sube a 0 -> flip entre 760 y 780
check(gf["gamma_flip"] is not None and 760 <= gf["gamma_flip"] <= 780,
      f"gamma_flip en [760,780] -> {S._fmt(gf['gamma_flip'])}")

# A5 gamma NaN / faltante no rompe
gn = S.compute_gex_from_greeks({770: 100}, {770: 100}, {770: float('nan')}, {}, 772.0)
check(gn is not None, "GEX con gamma NaN no crashea")

# A6 centro de peso ponderado por dinero
pc = S.compute_prem_center({760: 100.0, 780: 300.0})
check(abs(pc - (760*100 + 780*300) / 400.0) < 1e-9, f"prem_center centro de masa -> {pc}")
check(S.compute_prem_center({}) is None, "prem_center vacio -> None")

# A7 MAGNETO DINAMICO: el OI compuesto (OI + volumen) SI mueve el max pain (mecanismo real)
mp_base = S._max_pain({100: 10}, {100: 10, 110: 10})          # base: empate -> argmin toma 100
mp_dyn = S._max_pain({100: 10}, {100: 10, 110: 1010})         # +1000 vol en 110P -> dolor empuja a 110
check(mp_base == 100 and mp_dyn == 110 and mp_base != mp_dyn,
      f"magneto dinamico SE MUEVE con OI+volumen: {mp_base} -> {mp_dyn}")


# ================================================================ TEST B: metodo REAL compute_walls
print("== TEST B: SpyDirection.compute_walls (metodo real + FakeIB + BD) ==")
app = S.SpyDirection(demo=True)
app.db.close()
app.db = sqlite3.connect(":memory:")   # BD aislada en memoria (no toca ficheros)
app._init_db()
app.ib = FakeIB()
app.expiry = "20260814"
app.spy_price = 772.0

# banda: 770C/775C/780C y 760P/765P/770P
specs = [(770, "C", 1, 100, 0.05), (775, "C", 2, 500, 0.04), (780, "C", 3, 200, 0.03),
         (760, "P", 4, 100, 0.03), (765, "P", 5, 600, 0.04), (770, "P", 6, 300, 0.05)]
app.band_contracts = [FakeContract(s, r, cid) for (s, r, cid, _oi, _g) in specs]
for (s, r, cid, oi, gm) in specs:
    app.ib._tk[cid] = FakeTicker(oi=oi, gamma=gm, volume=0.0, last=1.0, bid=0.9, ask=1.1, right=r)

# 1a llamada: establece baseline de volumen (prev None -> no acumula), pobla walls/gex
app.compute_walls()
check(app.walls is not None, "1a llamada: self.walls poblado")
check(app.walls["call_wall"] == 775 and app.walls["put_wall"] == 765,
      f"walls: CW=775 PW=765 -> CW={app.walls['call_wall']} PW={app.walls['put_wall']}")
check(app.gex is not None and app.gex["regime"] in ("LONG", "SHORT", "FLAT"),
      f"GEX regime -> {app.gex['regime'] if app.gex else None}")
mp_static_1 = app.walls["max_pain_static"]
check(mp_static_1 is not None, f"max_pain_static -> {mp_static_1}")

# 2a llamada: sube el volumen AGRESOR (last>=ask) en 780C -> net_prem+ y OI_est crece en 780
app.ib._tk[3].volume = 100000.0   # 780C: +100k contratos operados al ask (comprador agresor)
app.ib._tk[3].last = 1.2
app.ib._tk[3].ask = 1.1           # last>=ask -> signed +
app.compute_walls()
key_780c = ("20260814", 780, "C")
check(app.today_vol.get(key_780c, 0) > 0, f"today_vol[780C] acumulo dvol -> {app.today_vol.get(key_780c)}")
check(app.net_prem.get(key_780c, 0) > 0, f"net_prem[780C] positivo (comprador agresor) -> {app.net_prem.get(key_780c)}")
# cableado: max_pain_dyn se calcula desde OI+volumen (oi_est) y es un strike de la banda
band_strikes = {s for (s, r, cid, oi, gm) in specs}
check(app.walls["max_pain_dyn"] in band_strikes,
      f"max_pain_dyn es un strike de la banda -> {app.walls['max_pain_dyn']}")
check(app.walls["prem_center"] is not None, f"prem_center -> {S._fmt(app.walls['prem_center'])}")

# persistencia en BD
n_ws = app.db.execute("SELECT COUNT(*) FROM walls_snapshot").fetchone()[0]
check(n_ws >= 1, f"walls_snapshot tiene filas -> {n_ws}")
row = app.db.execute("SELECT put_wall,call_wall,max_pain_static,max_pain_dyn,gex_total,regime,"
                     "gamma_flip FROM walls_snapshot ORDER BY hora DESC LIMIT 1").fetchone()
check(row is not None and row[0] == 765 and row[1] == 775, f"walls_snapshot persistio PW/CW -> {row}")
n_pm = app.db.execute("SELECT COUNT(*) FROM premium_minute WHERE open_interest IS NOT NULL").fetchone()[0]
check(n_pm >= 1, f"premium_minute con open_interest por strike -> {n_pm}")
oi_row = app.db.execute("SELECT open_interest,gamma,net_prem FROM premium_minute "
                        "WHERE strike=780 AND right='C' ORDER BY hora DESC LIMIT 1").fetchone()
check(oi_row is not None and oi_row[0] == 200, f"premium_minute[780C].open_interest=200 -> {oi_row}")

# staleness: 3a llamada SIN cambiar gammas -> g_changed debe ser 0 (dato estancado detectable)
before = dict(app.prev_gamma)
app.compute_walls()
check(app.prev_gamma == before, "3a llamada: gammas identicos -> prev_gamma sin cambios (staleness detectable)")

# ================================================================ resultado
print()
if FAILS:
    print(f"COLD RUN FALLIDO: {len(FAILS)} checks fallaron")
    for f in FAILS:
        print("   - " + f)
    sys.exit(1)
print("COLD RUN OK: todos los checks pasaron")
sys.exit(0)
