# -*- coding: utf-8 -*-
"""
COLD RUN GAP 3 (por fin) + WALLS PONDERADAS POR GAMMA.

A) refresh_strikes(): senal, ejecucion y banda de walls deben SEGUIR AL PRECIO.
   Antes setup_contracts corria 1 sola vez y todo quedaba congelado al precio de apertura.
   La ejecucion pasa a ATM REAL (strike mas cercano) por decision del usuario 2026-08-10.
   SEGURIDAD: los contratos de ejecucion NO se mueven con posicion abierta ni orden viva.

B) compute_walls_from_oi con gamma: el OI de IBKR es EOD (congelado); el gamma es vivo.
   Con datos reales de hoy: OI puro -> CW=780 ; gamma*OI -> CW=775 (lo que marca MarketSnack).

Funciones REALES, BD :memory:.
"""
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
import spy_direction as S

# 2026-08-12: esta suite ejercita el disparador ANTERIOR (M1 / diff-thr) o el flujo generico de
# compra. Desde hoy el default es USAR_MEDIA=True, que exige `ta_vals["vwap"]`, y las apps
# minimas de las cold runs no lo tienen -> `_senal_media()` devuelve None, el target se queda
# en FLAT y NADA compra. Sin esta linea fallan 7 suites por una sola causa.
# Un test A/B tiene que FIJAR la variable que prueba, no heredarla del default (misma leccion
# que ENTRADA_RETROCESO en gap14 el mismo dia).
S.USAR_MEDIA = False

S.ENABLE_TOAST = False
import logging as _lg
for _l in (S.ACT, S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


STRIKES = [float(x) for x in range(760, 801)]


class FakeIB:
    def __init__(self):
        self.subs = []          # (conId, genericTicks)
        self.cancels = []
        self._n = 1000
    def isConnected(self):
        return True
    def sleep(self, s):
        pass
    def qualifyContracts(self, *cs):
        for c in cs:
            if not getattr(c, "conId", None):
                self._n += 1
                c.conId = self._n
        return list(cs)
    def reqMktData(self, c, gen, snap, reg):
        self.subs.append((c.conId, gen))
    def cancelMktData(self, c):
        self.cancels.append(getattr(c, "conId", None))
    def positions(self):
        return []
    def openTrades(self):
        return []
    def ticker(self, c):
        return None


def nueva(px):
    a = S.SpyDirection(demo=True)
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.demo = False
    a.ib = FakeIB()
    a.expiry = "20260810"
    a.strikes = list(STRIKES)
    a.spy_price = px
    return a


print("=" * 78)
print("COLD RUN GAP 3 - todo sigue al precio  +  WALLS por exposicion gamma")
print("=" * 78)

# ---------------------------------------------------------------- A1
print("\n== A1: primera pasada fija senal y ejecucion al precio actual ==")
a = nueva(774.45)
a.refresh_strikes()                                   # metodo REAL
check(a.call is not None and a.call.strike == 774 and a.put is not None and a.put.strike == 775,
      "SENAL ATM/ITM: call=%gC (<=precio) put=%gP (>=precio)" % (a.call.strike, a.put.strike))
check(a.buy_call.strike == 774 and a.buy_put.strike == 774,
      "EJECUCION ATM REAL: ambos en %g (el strike mas cercano a 774.45)" % a.buy_call.strike)

# ---------------------------------------------------------------- A2
print("\n== A2: el precio sube 4 dolares -> TODO se re-centra ==")
a.spy_price = 778.30
a.refresh_strikes()
check(a.call.strike == 778 and a.put.strike == 779,
      "SENAL re-centrada: %gC / %gP (antes 774/775)" % (a.call.strike, a.put.strike))
check(a.buy_call.strike == 778 and a.buy_put.strike == 778,
      "EJECUCION re-centrada al ATM real %g (antes 774)" % a.buy_call.strike)
check(len(a.ib.cancels) >= 4,
      "se liberaron las suscripciones viejas (%d cancelMktData) - no se acumulan lineas"
      % len(a.ib.cancels))

# ---------------------------------------------------------------- A3
print("\n== A3: GUARDA - con posicion abierta la EJECUCION no se mueve ==")
b = nueva(774.45)
b.refresh_strikes()
b.pos = "CALL"                                        # hay posicion
strike_antes = b.buy_call.strike
b.spy_price = 780.10
b.refresh_strikes()
check(b.buy_call.strike == strike_antes,
      "con pos=CALL el contrato de ejecucion NO cambia (%g) -> no se vende lo que no se tiene"
      % b.buy_call.strike)
check(b.call.strike == 780,
      "pero la SENAL si se re-centra (%gC): solo lee flujo, no opera" % b.call.strike)

print("\n== A4: GUARDA - con orden viva tampoco se mueve la ejecucion ==")
c = nueva(774.45)
c.refresh_strikes()
c.order = object()                                    # orden en vuelo
sc = c.buy_call.strike
c.spy_price = 779.0
c.refresh_strikes()
check(c.buy_call.strike == sc, "con orden viva el contrato de ejecucion sigue en %g" % sc)

# ---------------------------------------------------------------- A5
print("\n== A5: la BANDA de walls se re-centra solo si el precio deriva >3 strikes ==")
e = nueva(774.0)
e.band_contracts = []
for s in [float(x) for x in range(764, 784)]:
    for r in ("C", "P"):
        o = S.Option(S.SYMBOL, "20260810", s, r, "SMART", tradingClass=S.SYMBOL)
        e.ib.qualifyContracts(o)
        e.band_contracts.append(o)
n_antes = len(e.ib.subs)
e.spy_price = 775.0                                   # deriva pequena
e.refresh_strikes()
banda1 = sorted({x.strike for x in e.band_contracts})
check(banda1[0] == 764 and banda1[-1] == 783,
      "deriva de 1 strike -> banda INTACTA %g-%g (no gasta 40 suscripciones)"
      % (banda1[0], banda1[-1]))
e.spy_price = 782.0                                   # deriva grande
e.refresh_strikes()
banda2 = sorted({x.strike for x in e.band_contracts})
check(banda2[0] != banda1[0] and 782 in banda2,
      "deriva de 8 strikes -> banda RE-CENTRADA %g-%g (contiene el precio)"
      % (banda2[0], banda2[-1]))
check(len(e.ib.cancels) >= 40, "se soltaron las 40 viejas (%d cancels)" % len(e.ib.cancels))

# ---------------------------------------------------------------- B
print("\n== B: WALLS por OI puro vs por exposicion gamma (datos REALES de hoy 10:43) ==")
call_oi = {772: 7386, 773: 10190, 774: 5784, 775: 10945, 779: 9535, 780: 13144}
put_oi = {765: 14055, 768: 7669, 770: 8829, 771: 6196, 772: 6420, 773: 4665}
call_g = {772: 0.0965, 773: 0.1307, 774: 0.1641, 775: 0.1726, 779: 0.0391, 780: 0.0250}
put_g = {765: 0.0093, 768: 0.0209, 770: 0.0441, 771: 0.0632, 772: 0.0965, 773: 0.1307}

w_oi = S.compute_walls_from_oi(call_oi, put_oi, 774.57)                    # sin gamma
w_gx = S.compute_walls_from_oi(call_oi, put_oi, 774.57, call_g, put_g)     # con gamma
check(w_oi["call_wall"] == 780 and w_oi["put_wall"] == 765,
      "sin gamma (compatibilidad): CW=%g PW=%g" % (w_oi["call_wall"], w_oi["put_wall"]))
check(w_gx["call_wall"] == 775,
      "con gamma: CW=%g  <-- EXACTAMENTE lo que muestra MarketSnack" % w_gx["call_wall"])
check(w_gx["put_wall"] == 772,
      "con gamma: PW=%g (el OI puro daba 765, lejisimos del precio)" % w_gx["put_wall"])
check(w_oi["max_pain"] == w_gx["max_pain"],
      "el max_pain NO cambia (%s): sigue siendo por OI, como debe ser" % w_gx["max_pain"])

print("\n== B2: gamma incompleto -> cae a OI puro, no mezcla criterios ==")
w_mix = S.compute_walls_from_oi(call_oi, put_oi, 774.57, {772: 0.09}, put_g)
check(w_mix["call_wall"] == 780,
      "con gamma parcial la call wall vuelve a OI puro (%g)" % w_mix["call_wall"])
_g_nan = dict(call_g)
_g_nan[775] = float("nan")      # dict(**{775:...}) no vale: ** exige claves de texto
w_nan = S.compute_walls_from_oi(call_oi, put_oi, 774.57, _g_nan, put_g)
check(w_nan["call_wall"] == 780, "con un gamma NaN tambien cae a OI puro (%g)" % w_nan["call_wall"])

# ---------------------------------------------------------------- C
print("\n== C: tras CERRAR una posicion, la recompra debe ser el ATM DE AHORA ==")
print("   Caso real 10:51:54: se vendio la 772P, _sync_pos vio FLAT y recompro la MISMA")
print("   772P porque _reconcile habia dejado buy_put apuntando al contrato vendido.")


class Tk:
    def __init__(self, bid, ask):
        self.bid = bid; self.ask = ask; self.last = bid
        self.volume = 0.0; self.modelGreeks = None; self.time = None
        self.callOpenInterest = float("nan"); self.putOpenInterest = float("nan")


class IBOrdenes(FakeIB):
    def __init__(self):
        FakeIB.__init__(self)
        self.placed = []
        self._pos = []
        self._tk = {}
    def positions(self):
        return list(self._pos)
    def ticker(self, c):
        return self._tk.get(getattr(c, "conId", None), Tk(float("nan"), float("nan")))
    def reqMktData(self, c, gen, snap, reg):
        FakeIB.reqMktData(self, c, gen, snap, reg)
        self._tk.setdefault(c.conId, Tk(0.60, 0.64))     # cualquier contrato nuevo cotiza
        return self._tk[c.conId]
    def reqContractDetails(self, c):
        return []
    def accountSummary(self):
        return []
    def placeOrder(self, c, o):
        class _St:
            status = "Submitted"; filled = 0.0; avgFillPrice = 0.0
        class _T:
            pass
        t = _T(); t.contract = c; t.order = o; t.orderStatus = _St()
        self.placed.append(t)
        return t


class _ET11:
    def weekday(self):
        return 0
    def strftime(self, f):
        return "11:00"


_orig_now = S.now_et
S.now_et = lambda: _ET11()

f = nueva(774.92)
f.ib = IBOrdenes()
f.trading = True
f.reconciled = True
f.refresh_strikes()                       # deja buy_put en el ATM 775
# simular lo que hace _reconcile con una posicion abierta: apuntar al contrato POSEIDO
viejo = f._nuevo_opt(772, "P")
f.buy_put = viejo
f.ib._tk[viejo.conId] = Tk(0.21, 0.23)
f.pos = "PUT"; f.pos_qty = 1.0
f.target = "PUT"
strike_viejo = f.buy_put.strike
# ahora la posicion se CIERRA por fuera (como hice yo a mano): IBKR ya no la tiene
f.ib._pos = []
f.last_sync = 0.0
f.trade_poll()                            # metodo REAL
compras = [t for t in f.ib.placed if t.order.action == "BUY"]
check(len(compras) == 1, "se coloco 1 compra (%d)" % len(compras))
if compras:
    comprado = compras[0].contract.strike
    check(comprado == 775,
          "compro el ATM DE AHORA: %gP (el contrato vendido era %gP) - antes recompraba el viejo"
          % (comprado, strike_viejo))

S.now_et = _orig_now

# ---------------------------------------------------------------- B: LINEA BASE
print("\n== B: LINEA BASE (expiraciones posteriores) tambien sigue al precio ==")
print("   Antes solo se fijaba en setup_contracts -> se acumulaba premium de strikes")
print("   que ya eran OTM conforme el subyacente se movia.")

bl = nueva(774.45)
bl.base_expiries = ["20260811", "20260812", "20260813"]
bl.refresh_strikes()                                  # metodo REAL
n1 = len(bl.info_base)
strikes1 = sorted({v[1] for v in bl.info_base.values()})
calls1 = sorted({v[1] for v in bl.info_base.values() if v[2] == "C"})
puts1 = sorted({v[1] for v in bl.info_base.values() if v[2] == "P"})
check(n1 == 24, "B1 se siguen %d contratos (3 expiraciones x 8 = 24)" % n1)
check(all(s <= 774.45 for s in calls1) and all(s >= 774.45 for s in puts1),
      "B1 calls<=precio %s | puts>=precio %s (ATM/ITM, nunca OTM)" % (calls1, puts1))
check(set(bl.info_base) == set(bl._base_ct),
      "B4 info_base y _base_ct sincronizados (%d/%d)" % (len(bl.info_base), len(bl._base_ct)))

print("\n   -- el precio sube 3 dolares --")
subs_antes = len(bl.ib.subs); canc_antes = len(bl.ib.cancels)
# simular acumulado y volumen previo en un strike que va a quedar fuera de rango
fuera = [cid for cid, v in bl.info_base.items() if v[1] == min(calls1)][0]
k_fuera = bl.info_base[fuera]
bl.accum[k_fuera] = 123456.0
bl.prev_vol[fuera] = 999.0
bl.spy_price = 777.50
bl.refresh_strikes()                                  # metodo REAL
n2 = len(bl.info_base)
calls2 = sorted({v[1] for v in bl.info_base.values() if v[2] == "C"})
puts2 = sorted({v[1] for v in bl.info_base.values() if v[2] == "P"})
check(n2 == 24, "B2 sigue siguiendo 24 contratos (%d) - presupuesto de lineas constante" % n2)
check(calls2 != calls1 and all(s <= 777.50 for s in calls2),
      "B2 re-centrado: calls %s -> %s" % (calls1, calls2))
check(all(s >= 777.50 for s in puts2), "B2 puts re-centradas -> %s" % puts2)
check(len(bl.ib.subs) > subs_antes and len(bl.ib.cancels) > canc_antes,
      "B2 hubo altas (%d) y bajas (%d) de market data"
      % (len(bl.ib.subs) - subs_antes, len(bl.ib.cancels) - canc_antes))
check(fuera not in bl.prev_vol,
      "B3 prev_vol LIMPIADO del contrato soltado -> sin premium fantasma si vuelve")
check(bl.accum.get(k_fuera) == 123456.0,
      "B6 lo acumulado del strike soltado SOBREVIVE (%.0f) - no se pierde histórico"
      % bl.accum.get(k_fuera, -1))
check(set(bl.info_base) == set(bl._base_ct),
      "B4 siguen sincronizados tras el re-centrado (%d/%d)"
      % (len(bl.info_base), len(bl._base_ct)))

print("\n   -- precio ESTABLE: no debe tocar nada (idempotencia) --")
s3, c3 = len(bl.ib.subs), len(bl.ib.cancels)
bl.refresh_strikes()
bl.refresh_strikes()
check(len(bl.ib.subs) == s3 and len(bl.ib.cancels) == c3,
      "B5 dos llamadas con precio estable -> 0 altas y 0 bajas (subs=%d cancels=%d)"
      % (len(bl.ib.subs) - s3, len(bl.ib.cancels) - c3))

print()
if FAILS:
    print("NO CERRADO: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("GAP 3 + WALLS GAMMA CERRADOS: todos los checks pasaron")
sys.exit(0)
