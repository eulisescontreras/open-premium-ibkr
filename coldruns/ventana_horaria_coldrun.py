# -*- coding: utf-8 -*-
"""COLD RUN de la VENTANA HORARIA (cambio 2026-08-11: recoleccion desde las 09:00).

Ejercita las FUNCIONES REALES `is_market_open()` e `is_rth()` y la logica REAL de
`in_session`/`stop_new`/aplanado que vive dentro de `trade_poll`, inyectando horas reales
mediante el reloj del modulo (`now_et`). No reimplementa nada: parchea la fuente de tiempo
y llama a los metodos de la instancia real.

LO QUE DEBE QUEDAR DEMOSTRADO:
  1. RECOLECCION abierta 09:00-16:15 (antes 09:30) y cerrada fuera.
  2. TRADING sigue empezando a las 09:30: entre 09:00 y 09:29 NO se abre nada.
  3. La vigilancia de barras (GAP 17) solo actua en RTH -> nada de GAP 17 falso en pre-market.
  4. El fin de sesion no cambia: FLATTEN 15:45, STOP_NEW 15:40, CLOSE 16:15.
  5. Fin de semana cerrado en ambas ventanas.
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
import datetime as _dt
import spy_direction as S

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


# --- reloj inyectable: se sustituye la FUENTE de tiempo, no la funcion que se prueba ---
_TZ = None
try:
    _TZ = S.now_et().tzinfo
except Exception:
    pass


def set_et(hhmm, dia=11):
    """11-ago-2026 = martes (habil). 15/16-ago = sabado/domingo."""
    h, m = (int(x) for x in hhmm.split(":"))
    fake = _dt.datetime(2026, 8, dia, h, m, 0, tzinfo=_TZ)
    S.now_et = lambda: fake


_ORIG_NOW = S.now_et
app = S.SpyDirection(demo=True)
app.demo = False          # demo=True cortocircuita trade_poll; aqui se quiere la rama real

# Las expectativas se DERIVAN de las constantes reales del modulo: asi la suite sigue valiendo
# aunque OPEN_HHMM cambie (el 2026-08-11 se probo "09:00" y se revirtio a "09:30" con datos).
OPEN, RTH = S.OPEN_HHMM, S.RTH_OPEN_HHMM
print(f"CONFIG REAL LEIDA DEL MODULO: OPEN_HHMM={OPEN} RTH_OPEN_HHMM={RTH} CLOSE_HHMM={S.CLOSE_HHMM}")
print()


def menos1(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    t = h * 60 + m - 1
    return f"{t // 60:02d}:{t % 60:02d}"


print("=" * 78)
print(f"TEST 1 - RECOLECCION is_market_open(): abre a las {OPEN}")
print("=" * 78)
for hhmm, esperado in [(menos1(OPEN), False), (OPEN, True), ("12:00", True),
                       ("16:14", True), ("16:15", False), ("16:30", False), ("04:00", False)]:
    set_et(hhmm)
    got = app.is_market_open()
    check(got == esperado, f"is_market_open() a las {hhmm} ET -> {got} (esperado {esperado})")

print()
print("=" * 78)
print(f"TEST 2 - RTH is_rth(): {RTH}-{S.CLOSE_HHMM}, independiente de OPEN_HHMM")
print("=" * 78)
for hhmm, esperado in [(menos1(RTH), False), (RTH, True), ("15:59", True),
                       ("16:14", True), ("16:15", False)]:
    set_et(hhmm)
    got = app.is_rth()
    check(got == esperado, f"is_rth() a las {hhmm} ET -> {got} (esperado {esperado})")

print()
print("=" * 78)
print("TEST 3 - INVARIANTE: nunca se OPERA fuera de RTH, recolecte o no")
print("=" * 78)
check(OPEN <= RTH, f"OPEN_HHMM ({OPEN}) <= RTH_OPEN_HHMM ({RTH}): la recoleccion nunca "
                   f"empieza DESPUES de poder operar")
if OPEN < RTH:
    for hhmm in (OPEN, menos1(RTH)):
        set_et(hhmm)
        rec, rth = app.is_market_open(), app.is_rth()
        check(rec and not rth, f"{hhmm} ET -> recoleccion={rec} / RTH={rth}: recolecta sin operar")
else:
    set_et(menos1(RTH))
    check(not app.is_market_open() and not app.is_rth(),
          f"{menos1(RTH)} ET: OPEN==RTH -> ni recoleccion ni trading antes de {RTH}")
set_et(RTH)
check(app.is_market_open() and app.is_rth(), f"{RTH} ET -> recoleccion Y trading activos")

print()
print("=" * 78)
print("TEST 4 - trade_poll REAL: stop_new/aplanado con la instancia de verdad")
print("=" * 78)


class FakeIB:
    def isConnected(self):
        return True

    def openTrades(self):
        return []

    def positions(self):
        return []


def preparar():
    """Deja la app en el punto exacto en que trade_poll evaluaria abrir una posicion."""
    app.ib = FakeIB()
    app.trading = True
    app.reconciled = True
    app.order = None
    app.pos = "FLAT"
    app.pos_qty = 0
    app.buys_pend = 0
    app.target = "CALL"
    app.trade_msg = ""
    app.buy_call = S.Option(S.SYMBOL, "20260811", 773, "C", "SMART", tradingClass=S.SYMBOL)
    app.buy_put = S.Option(S.SYMBOL, "20260811", 772, "P", "SMART", tradingClass=S.SYMBOL)
    app._colocadas = []
    app._place = lambda c, act, tgt=None, qty=None: app._colocadas.append((act, tgt, hhmm_actual))
    app._sync_pos = lambda: None
    app._live_orders = lambda: []
    app.refresh_strikes = lambda: None
    app._mid = lambda c: 0.75
    app._can_afford = lambda px: True


for hhmm_actual in ("09:00", "09:15", "09:29"):
    set_et(hhmm_actual)
    preparar()
    app.trade_poll()
    check(not app._colocadas,
          f"trade_poll() a las {hhmm_actual} ET (pre-market): NO coloca orden "
          f"[colocadas={app._colocadas}] | msg='{app.trade_msg}'")

for hhmm_actual in ("09:30", "10:00", "15:39"):
    set_et(hhmm_actual)
    preparar()
    app.trade_poll()
    check(len(app._colocadas) == 1 and app._colocadas[0][0] == "BUY",
          f"trade_poll() a las {hhmm_actual} ET (RTH): SI compra "
          f"[colocadas={app._colocadas}]")

for hhmm_actual in ("15:40", "15:44"):
    set_et(hhmm_actual)
    preparar()
    app.trade_poll()
    check(not app._colocadas,
          f"trade_poll() a las {hhmm_actual} ET (STOP_NEW): NO abre nuevas "
          f"[colocadas={app._colocadas}]")

set_et("15:45")
preparar()
app.trade_poll()
check(app.target == "FLAT", f"trade_poll() a las 15:45 ET: aplanado -> target={app.target}")

print()
print("=" * 78)
print("TEST 5 - FIN DE SEMANA cerrado en ambas ventanas")
print("=" * 78)
for dia, nombre in ((15, "sabado"), (16, "domingo")):
    set_et("10:00", dia=dia)
    check(not app.is_market_open(), f"{nombre} 10:00 -> is_market_open() False")
    check(not app.is_rth(), f"{nombre} 10:00 -> is_rth() False")

print()
print("=" * 78)
print("TEST 6 - GAP 17: la vigilancia de barras NO se dispara en pre-market")
print("=" * 78)
rows = [{"date": "fija"}]
for hhmm_actual in ("09:00", "09:29"):
    set_et(hhmm_actual)
    app.bars_stale = False
    app._bars_ult_date = "fija"
    app.bars_last_advance = 0.0001          # hace muchisimo que no avanza
    app._chequear_barras(rows)
    check(not app.bars_stale,
          f"{hhmm_actual} ET: barras congeladas pero bars_stale={app.bars_stale} "
          f"(no hay GAP 17 falso ni repeticion del stream)")

set_et("10:00")
app.bars_stale = False
app._bars_ult_date = "fija"
app.bars_last_advance = 0.0001
app._chequear_barras(rows)
check(app.bars_stale, f"10:00 ET (RTH): barras congeladas -> bars_stale={app.bars_stale} "
                      f"(la deteccion del GAP 17 SIGUE viva)")

S.now_et = _ORIG_NOW
print()
print("=" * 78)
print(("TODO VERDE" if not FAILS else f"{len(FAILS)} FALLOS: " + " | ".join(FAILS)))
print("=" * 78)
sys.exit(1 if FAILS else 0)
