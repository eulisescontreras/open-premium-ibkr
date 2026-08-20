# -*- coding: utf-8 -*-
"""COLD RUN: capturador de TAPE del subyacente. Corre las FUNCIONES REALES de ibkr.IBKR y
captura.guardar_tape con DATOS REALES (los 31.349 ticks del 2026-08-13 del sistema anterior).
NO requiere IB Gateway: lo único que no se puede probar sin mercado es que IBKR entregue el
stream. Todo lo demás — clasificación del signo, persistencia, aviso del primer tick, contadores
y la caída a RTVolume — sí. Exit 0 = verde, 1 = rojo.
"""
import os, sys, sqlite3, datetime, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.data.ibkr import IBKR
from sys2.data import captura as CAP
from sys2.db import repo

FUENTE = os.path.join(RAIZ, "spy_history.db")
fallos = []


def _ticks_reales(n=None):
    """Ticks REALES del 2026-08-13 (spy_history.tape, grupo='SPY': el único día con bid/ask)."""
    c = sqlite3.connect("file:%s?mode=ro" % FUENTE.replace("\\", "/"), uri=True)
    q = "select hora,last,size,bid,ask,agresor from tape where grupo='SPY' order by hora"
    if n:
        q += " limit %d" % n
    filas = list(c.execute(q))
    c.close()
    return filas


# ── 1. LA REGLA DEL SIGNO contra el agresor REAL del sistema anterior ────────────────
k = IBKR()                                  # sin conectar: solo se usa la lógica pura
filas = _ticks_reales()
if not filas:
    fallos.append("sin ticks reales en %s" % FUENTE)
else:
    M = {"COMPRA": "C", "VENTA": "V", "MID": "N"}
    ok = 0
    for px, b, a, agr in [(f[1], f[3], f[4], f[5]) for f in filas]:
        if b is None or a is None:
            continue
        k._libro = [b, a]
        if k._tape_signo(px) == M.get(agr):
            ok += 1
    pct = 100.0 * ok / len(filas)
    print("1. signo: %d/%d = %.1f%% de coincidencia con el agresor REAL" % (ok, len(filas), pct))
    if pct < 99.9:
        fallos.append("la regla del signo no reproduce el agresor real (%.1f%%)" % pct)

# ── 2. PERSISTENCIA por la función REAL, sin pérdida ─────────────────────────────────
ticks = []
for i, (hora, px, sz, b, a, agr) in enumerate(filas[:5000], 1):
    hh, mm, resto = hora.split(":")
    seg, _, ms = resto.partition(".")
    t = datetime.datetime(2026, 8, 13, int(hh), int(mm), int(seg),
                          int((ms or "0").ljust(3, "0")) * 1000)
    k._libro = [b, a]
    ticks.append((t, i, float(px), float(sz or 0), "TEST", b, a, k._tape_signo(px)))
tmp = os.path.join(tempfile.mkdtemp(), "t.db")
con = repo.abrir(tmp)
n = CAP.guardar_tape(con, "2026-08-13", ticks)
leidas = con.execute("select count(*) from tape_und").fetchone()[0]
sin_libro = con.execute("select count(*) from tape_und where bid is null").fetchone()[0]
con.close()
print("2. persistencia: %d entrada -> %d guardados, %d sin bid/ask" % (len(ticks), leidas, sin_libro))
if leidas != len(ticks):
    fallos.append("pérdida de ticks al persistir: %d de %d" % (len(ticks) - leidas, len(ticks)))

# ── 3. DRENAJE: aviso del primer tick y contadores ───────────────────────────────────
k.tape_suscribir.__wrapped__ if False else None
k._tape = list(ticks[:10])
k._libro = [ticks[0][5], ticks[0][6]]
k._tape_seq, k._tape_err, k._tape_vacios, k._tape_visto, k._tape_n = 10, 0, 0, False, 0
k._tape_modo, k._tape_tk = "tickbytick", None
salida = k.tape_drenar()
est = k.tape_estado()
print("3. drenaje: %d ticks devueltos | estado=%s" % (len(salida), est))
if len(salida) != 10 or est["ticks"] != 10 or not k._tape_visto:
    fallos.append("tape_drenar no devuelve/contabiliza bien (%d, %s)" % (len(salida), est))
if k.tape_drenar():
    fallos.append("el buffer no se vació tras drenar")

# ── 4. CAÍDA A RTVOLUME tras N minutos sin ticks (sin IBKR debe fallar LIMPIO) ────────
k._tape_modo, k._tape_vacios, k._tape_visto = "tickbytick", 0, True
for _ in range(C.TAPE_FALLBACK_MIN):
    k.tape_drenar()                       # buffer vacío -> debe intentar el fallback
print("4. tras %d min sin ticks -> modo=%s (sin IBKR debe quedar en None, no reventar)"
      % (C.TAPE_FALLBACK_MIN, k._tape_modo))
if k._tape_modo == "tickbytick":
    fallos.append("no intentó el fallback tras %d min sin ticks" % C.TAPE_FALLBACK_MIN)

print()
if fallos:
    print("ROJO: " + " | ".join(fallos))
    sys.exit(1)
print("VERDE: capturador de tape OK (signo, persistencia, drenaje y fallback)")
print("  ⚠️ NO cubierto sin mercado: que IBKR ENTREGUE el stream. Se comprueba en la apertura.")
sys.exit(0)
