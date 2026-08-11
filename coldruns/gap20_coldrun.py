# -*- coding: utf-8 -*-
"""COLD RUN del GAP 20 y de la rotacion tolerante del log (2026-08-11).

GAP 20 - REAL, observado en vivo hoy: la orden 2134 se reporto `Cancelled` con filled=0 y se
llenó igual (09:35:12). `_sync_pos` corrigio la posicion (bien), pero NADIE abria la fila en
`trades`, asi que el PUT 773 comprado a 1.1104 y vendido a 1.12 (+0.96) no dejo rastro ni en
`trades` ni en `posicion_minuto`. Es el simetrico del cierre "externa" que ya existia.

ROTACION - REAL, observado hoy: el monitor tenia abierto spy_activity.log y en Windows no se
puede renombrar un fichero abierto por otro proceso -> doRollover() reventaba y el logging se
quedaba MUDO en silencio (32 min de traza perdidos).

Se ejercitan las FUNCIONES REALES (_sync_pos, _trade_abrir, _pos_snapshot, doRollover).
"""
import os
import sqlite3
import sys
import tempfile

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


# ---------------------------------------------------------------- utilidades
class FakePos:
    """Lo que devuelve ib.positions(): contrato + cantidad + coste medio."""
    def __init__(self, contract, position, avgCost):
        self.contract = contract
        self.position = position
        self.avgCost = avgCost


class FakeIB:
    def __init__(self, posiciones=None):
        self._pos = posiciones or []

    def positions(self):
        return self._pos

    def isConnected(self):
        return True

    def openTrades(self):
        return []

    def reqMktData(self, *a, **k):
        return None

    def ticker(self, c):
        return None


def nueva_app():
    a = S.SpyDirection(demo=True)
    a.demo = False
    a.db = sqlite3.connect(":memory:")
    a._crear_tablas() if hasattr(a, "_crear_tablas") else None
    return a


# ============================================================ GAP 20
print("=" * 78)
print("GAP 20 - posicion ADOPTADA de IBKR debe abrir fila en trades")
print("=" * 78)

app = S.SpyDirection(demo=True)
app.demo = False
# BD en memoria con el esquema REAL: se usa _init_db(), el mismo metodo que corre en produccion
app.db.close()
app.db = sqlite3.connect(":memory:")
app._init_db()
tiene = bool(app.db.execute(
    "SELECT name FROM sqlite_master WHERE name='trades'").fetchone())
check(tiene, "esquema 'trades' creado con _init_db() REAL de la app")
if not tiene:
    print("  (sin esquema no se puede seguir)")
    sys.exit(1)

put = S.Option(S.SYMBOL, "20260811", 773, "P", "SMART", tradingClass=S.SYMBOL)
put.conId = 999001
pos = FakePos(put, 1.0, 111.04)          # avgCost REAL del episodio de hoy
app.ib = FakeIB([pos])
app.spy_price = 773.33
app.pos, app.pos_qty = "FLAT", 0.0       # la app cree que esta FLAT (el bug de hoy)
app.trade_id = None
app.entry_price = None
app.buy_put = None
app._ensure_mkt = lambda c: None
app._greeks_de = lambda c: {"delta": -0.5, "gamma": 0.12, "theta": -1.2,
                            "vega": 0.1, "iv": 0.15, "und_price": 773.33}
app._live_orders = lambda: []

n_antes = app.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
app._sync_pos()                           # <-- FUNCION REAL
n_desp = app.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

check(app.pos == "PUT" and app.pos_qty == 1.0,
      f"la posicion real de IBKR manda -> pos={app.pos} qty={app.pos_qty}")
check(app.entry_price and abs(app.entry_price - 1.1104) < 1e-6,
      f"entry_price recuperado del avgCost 111.04 -> {app.entry_price}")
check(n_desp == n_antes + 1,
      f"SE ABRE la fila en trades ({n_antes} -> {n_desp})   <-- ESTO ES EL GAP 20")
check(app.trade_id is not None, f"trade_id asignado -> {app.trade_id}")

if n_desp > n_antes:
    r = app.db.execute("SELECT strike,right,entry_price,qty,hora_entrada,delta_entrada,"
                       "gamma_entrada,spy_entrada FROM trades ORDER BY trade_id DESC "
                       "LIMIT 1").fetchone()
    check(r[0] == 773 and r[1] == "P", f"contrato correcto en la fila: {r[0]:g}{r[1]}")
    check(abs(r[2] - 1.1104) < 1e-6, f"entry_price guardado = avgCost real: {r[2]}")
    check(r[3] == 1.0, f"qty = {r[3]}")
    check(r[5] is not None and r[6] is not None, f"griegas rellenas: delta={r[5]} gamma={r[6]}")
    check(r[7] == 773.33, f"spy_entrada = {r[7]}")
    nsnap = app.db.execute("SELECT COUNT(*) FROM posicion_minuto WHERE tipo='entrada'").fetchone()[0]
    check(nsnap == 1, f"posicion_minuto tiene su fila 'entrada' -> {nsnap}")

# --- no debe duplicar si ya hay un trade abierto ---
n1 = app.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
app._sync_pos()
n2 = app.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
check(n1 == n2, f"segunda llamada con trade ya abierto: NO duplica ({n1} -> {n2})")

# --- sin precio (ni avgCost ni MID) NO se inventa nada ---
app2 = S.SpyDirection(demo=True)
app2.demo = False
app2.db = app.db
call = S.Option(S.SYMBOL, "20260811", 775, "C", "SMART", tradingClass=S.SYMBOL)
call.conId = 999002
app2.ib = FakeIB([FakePos(call, 1.0, 0)])      # avgCost 0 -> sin dato
app2.pos, app2.pos_qty, app2.trade_id, app2.entry_price = "FLAT", 0.0, None, None
app2.buy_call = None
app2._ensure_mkt = lambda c: None
app2._mid = lambda c: None                      # tampoco hay MID
app2._live_orders = lambda: []
n3 = app.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
app2._sync_pos()
n4 = app.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
check(n3 == n4, f"sin avgCost ni MID: NO se abre fila y NO se inventa precio ({n3} -> {n4})")
check(app2.pos == "CALL", f"...pero la posicion SI se corrige igualmente -> {app2.pos}")

# --- el cierre "externa" sigue funcionando (no se rompio lo que ya habia) ---
app.ib = FakeIB([])                              # la posicion desaparece de IBKR
tid = app.trade_id
app._sync_pos()
cerrado = app.db.execute("SELECT hora_salida,razon_salida FROM trades WHERE trade_id=?",
                         (tid,)).fetchone()
check(app.pos == "FLAT", "posicion desaparecida -> pos=FLAT")
check(cerrado and cerrado[1] == "externa",
      f"el cierre 'externa' SIGUE funcionando -> razon={cerrado[1] if cerrado else None}")

# ============================================================ ROTACION
print()
print("=" * 78)
print("ROTACION TOLERANTE - el log NO debe quedarse mudo si falla el rollover")
print("=" * 78)

tmp = tempfile.mkdtemp()
ruta = os.path.join(tmp, "prueba.log")
h = S._RotacionTolerante(ruta, when="midnight", backupCount=3, encoding="utf-8")
h.setFormatter(_lg.Formatter("%(message)s"))
lg = _lg.getLogger("prueba_rotacion")
lg.handlers = []
lg.setLevel(_lg.INFO)
lg.propagate = False
lg.addHandler(h)

lg.info("linea ANTES de la rotacion")
h.flush()
check(os.path.exists(ruta), "el fichero de log se creo")

# forzar que la rotacion FALLE, igual que en Windows con el fichero abierto por otro proceso
import logging.handlers as _lh
orig = _lh.TimedRotatingFileHandler.doRollover


def revienta(self):
    raise PermissionError(13, "El proceso no tiene acceso al archivo porque esta siendo "
                              "utilizado por otro proceso")


_lh.TimedRotatingFileHandler.doRollover = revienta
try:
    h.doRollover()                     # <-- FUNCION REAL de la subclase
    ok_no_lanza = True
except Exception as e:
    ok_no_lanza = False
    print("    (excepcion propagada:", type(e).__name__, e, ")")
finally:
    _lh.TimedRotatingFileHandler.doRollover = orig

check(ok_no_lanza, "doRollover() con PermissionError NO propaga la excepcion")
check(h.stream is not None and not h.stream.closed,
      "el stream sigue ABIERTO tras el fallo (antes quedaba cerrado = log mudo)")

lg.info("linea DESPUES de la rotacion fallida")
h.flush()
with open(ruta, "r", encoding="utf-8") as f:
    contenido = f.read()
check("linea ANTES de la rotacion" in contenido, "se conserva lo escrito antes")
check("linea DESPUES de la rotacion fallida" in contenido,
      "SE SIGUE ESCRIBIENDO tras el fallo   <-- esto es lo que hoy no pasaba")
check("ROTACION DEL LOG FALLIDA" in contenido,
      "queda constancia del fallo EN EL PROPIO LOG (no falla en silencio)")
h.close()

print()
print("=" * 78)
print(("TODO VERDE" if not FAILS else f"{len(FAILS)} FALLOS: " + " | ".join(FAILS)))
print("=" * 78)
sys.exit(1 if FAILS else 0)
