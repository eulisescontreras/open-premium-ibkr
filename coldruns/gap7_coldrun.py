# -*- coding: utf-8 -*-
"""
COLD RUN GAP 7 — _log_minute borraba open_interest/gamma/net_prem escritos por _persist_walls.
Reproduce el escenario REAL observado hoy (09:55-09:57: 772C y 773P perdieron OI y gamma)
ejercitando los metodos REALES _persist_walls y _log_minute sobre una BD :memory:.

Antes del arreglo: (500.0, 0.05, 7000.0) -> (None, None, None)
Despues:           los tres valores deben SOBREVIVIR, y cum_prem/day_prem deben ACTUALIZARSE.
"""
import datetime as _dt
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"C:\Users\eulis\proyectos\open-premium-ibkr")
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


def nueva():
    a = S.SpyDirection(demo=True)
    a.db.close()
    a.db = sqlite3.connect(":memory:")
    a._init_db()
    a.demo = False
    return a


VALS = {"close": 773.2, "rsi": 55.0, "ema8": 773.0, "ema21": 772.5, "ema50": 772.0,
        "macd_line": 0.1, "macd_signal": 0.05, "macd_hist": 0.05, "bb_up": 775.0,
        "bb_mid": 773.0, "bb_low": 771.0, "atr": 1.2, "atr_pct": 0.15, "vwap": 773.1,
        "obv_trend": "bullish", "score": 3, "dir": "BULL"}

print("=" * 74)
print("COLD RUN GAP 7 - _log_minute ya NO debe borrar OI/gamma/net_prem")
print("=" * 74)

# ---------------------------------------------------------------- T1: el caso real
print("\n== T1: escenario real (772C de la expiry cercana, escrita por AMBOS) ==")
a = nueva()
a.expiry = "20260810"
a.spy_price = 773.4
k = ("20260810", 772, "C")
a.accum = {k: 50000.0}
a.today_prem = {k: 12000.0}
a.net_prem = {k: 7000.0}
a.walls = {"put_wall": 765.0, "call_wall": 780.0, "max_pain_static": 773.0,
           "max_pain_dyn": 773.0, "prem_center": 773.2, "spot": 773.4}
a.gex = {"gex_total": 1.8e11, "regime": "LONG", "gamma_flip": 773.36}

a._persist_walls({772: 7386.0}, {}, {772: 0.11}, {})          # metodo REAL (10 columnas)
antes = a.db.execute("SELECT open_interest,gamma,net_prem,cum_prem,day_prem FROM premium_minute "
                     "WHERE strike=772 AND right='C'").fetchone()
print("     tras _persist_walls : OI=%s gamma=%s net=%s cum=%s day=%s" % antes)

# _log_minute con un bar_dt que cae en la MISMA fecha/hora "%Y-%m-%d %H:%M"
ahora = _dt.datetime.now()
a.accum[k] = 51111.0                                          # valores nuevos que SI debe pisar
a.today_prem[k] = 13222.0
a._log_minute(VALS, ahora.strftime("%Y-%m-%d %H:%M:00"))      # metodo REAL (7 columnas)
desp = a.db.execute("SELECT open_interest,gamma,net_prem,cum_prem,day_prem FROM premium_minute "
                    "WHERE strike=772 AND right='C'").fetchone()
print("     tras _log_minute    : OI=%s gamma=%s net=%s cum=%s day=%s" % desp)

check(desp[0] == 7386.0 and desp[1] == 0.11 and desp[2] == 7000.0,
      "OI/gamma/net_prem SOBREVIVEN (antes quedaban en None): %s" % (desp[:3],))
check(desp[3] == 51111.0 and desp[4] == 13222.0,
      "cum_prem/day_prem SI se actualizan con los valores nuevos: cum=%s day=%s"
      % (desp[3], desp[4]))

# ---------------------------------------------------------------- T2: orden inverso
print("\n== T2: orden inverso (_log_minute primero, luego _persist_walls) ==")
b = nueva()
b.expiry = "20260810"
b.spy_price = 773.4
b.accum = {k: 1000.0}
b.today_prem = {k: 2000.0}
b.net_prem = {k: 3000.0}
b.walls = dict(a.walls)
b.gex = dict(a.gex)
b._log_minute(VALS, ahora.strftime("%Y-%m-%d %H:%M:00"))
b._persist_walls({772: 5555.0}, {}, {772: 0.22}, {})
r2 = b.db.execute("SELECT open_interest,gamma,net_prem,cum_prem,day_prem FROM premium_minute "
                  "WHERE strike=772 AND right='C'").fetchone()
check(r2[0] == 5555.0 and r2[1] == 0.22,
      "el orden inverso tambien deja OI/gamma correctos: OI=%s gamma=%s" % (r2[0], r2[1]))

# ---------------------------------------------------------------- T3: expiraciones futuras
print("\n== T3: expiraciones FUTURAS (solo las escribe _log_minute) ==")
c = nueva()
c.expiry = "20260810"
kf1 = ("20260811", 773, "P")
kf2 = ("20260812", 770, "C")
c.accum = {kf1: 456707.0, kf2: 4995.0}
c.today_prem = {kf1: 82867.0, kf2: 1200.0}
c._log_minute(VALS, ahora.strftime("%Y-%m-%d %H:%M:00"))
n_fut = c.db.execute("SELECT COUNT(*) FROM premium_minute WHERE expiry > '20260810'").fetchone()[0]
f1 = c.db.execute("SELECT cum_prem,day_prem,open_interest FROM premium_minute "
                  "WHERE expiry='20260811' AND strike=773 AND right='P'").fetchone()
check(n_fut == 2, "se crean las filas de expiraciones futuras: %d (esperado 2)" % n_fut)
check(f1[0] == 456707.0 and f1[1] == 82867.0 and f1[2] is None,
      "linea base OK: cum=%s day=%s OI=%s (None es correcto, la banda no las cubre)" % f1)

# ---------------------------------------------------------------- T4: idempotencia
print("\n== T4: llamadas repetidas en el mismo minuto no destruyen nada ==")
e = nueva()
e.expiry = "20260810"
e.spy_price = 773.4
e.accum = {k: 100.0}
e.today_prem = {k: 200.0}
e.net_prem = {k: 300.0}
e.walls = dict(a.walls)
e.gex = dict(a.gex)
e._persist_walls({772: 9999.0}, {}, {772: 0.33}, {})
for i in range(5):
    e.accum[k] = 100.0 + i
    e._log_minute(VALS, ahora.strftime("%Y-%m-%d %H:%M:00"))
r4 = e.db.execute("SELECT open_interest,gamma,cum_prem FROM premium_minute "
                  "WHERE strike=772 AND right='C'").fetchone()
n4 = e.db.execute("SELECT COUNT(*) FROM premium_minute WHERE strike=772 AND right='C'").fetchone()[0]
check(r4[0] == 9999.0 and r4[1] == 0.33 and n4 == 1,
      "tras 5 _log_minute: OI=%s gamma=%s cum=%s, y sigue habiendo 1 sola fila (%d)"
      % (r4[0], r4[1], r4[2], n4))

print()
if FAILS:
    print("GAP 7 NO CERRADO: %d checks fallaron" % len(FAILS))
    for x in FAILS:
        print("   - " + x)
    sys.exit(1)
print("GAP 7 CERRADO: todos los checks pasaron")
sys.exit(0)
