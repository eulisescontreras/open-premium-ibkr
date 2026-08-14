# CORRIDA EN FRIO REAL de "una BD por dia".
# Ejecuta la FUNCION REAL: instancia SpyDirection() (no un mock, no una reimplementacion) y
# recorre el grafo aguas abajo hasta el consumidor real (_load_accum).
# Diferencial: la BD fuente spy_history.db se mide ANTES y DESPUES; debe quedar IDENTICA.
import os, sys, sqlite3, hashlib

BASE = r"C:\Users\eulis\proyectos\open-premium-ibkr"
os.chdir(BASE)
sys.path.insert(0, BASE)

FUENTE = os.path.join(BASE, "spy_history.db")
HOY = None  # se toma de now_et() del modulo real

def huella(path):
    """Tamano + hash del contenido: detecta cualquier escritura."""
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return (os.path.getsize(path), h.hexdigest()[:16])

def conteos(path):
    if not os.path.exists(path):
        return {}
    c = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True, timeout=15)
    out = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND "
                          "name NOT LIKE 'sqlite_%' ORDER BY name"):
        out[t] = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    c.close()
    return out

print("=" * 78)
print("BASELINE: huella de la BD fuente ANTES de tocar nada")
print("=" * 78)
h_antes = huella(FUENTE)
n_antes = conteos(FUENTE)
print("  spy_history.db -> %d bytes  sha=%s" % h_antes)
print("  strike_accum=%d  strike_daily=%d" % (n_antes["strike_accum"], n_antes["strike_daily"]))

print("\n" + "=" * 78)
print("PASO 1: instanciar la CLASE REAL SpyDirection()  (sin conectar a IB)")
print("=" * 78)
import spy_direction as SD
HOY = SD.now_et().strftime("%Y%m%d")
NUEVA = os.path.join(BASE, "spy_history_%s.db" % HOY)
print("  fecha ET del modulo real: %s" % HOY)
print("  BD esperada             : %s" % os.path.basename(NUEVA))
print("  existia antes           : %s" % os.path.exists(NUEVA))

app = SD.SpyDirection()
print("  -> app.db_fecha  = %r" % app.db_fecha)
print("  -> ruta abierta  = %s" % os.path.basename(
    app.db.execute("PRAGMA database_list").fetchall()[0][2]))

print("\n" + "=" * 78)
print("PASO 2: contenido de la BD NUEVA (esquema + siembra)")
print("=" * 78)
app.db.commit()
n_nueva = conteos(NUEVA)
print("  tablas creadas: %d" % len(n_nueva))
sembradas = ("strike_accum", "strike_daily")
ok = True
for t in sorted(n_nueva):
    marca = "SEMBRADA" if t in sembradas else ("vacia" if n_nueva[t] == 0 else "*** CON DATOS ***")
    print("    %-22s %8d   %s" % (t, n_nueva[t], marca))
    if t not in sembradas and n_nueva[t] != 0:
        ok = False
print("\n  strike_accum : %d (fuente %d)  %s" % (
    n_nueva.get("strike_accum", -1), n_antes["strike_accum"],
    "OK" if n_nueva.get("strike_accum") == n_antes["strike_accum"] else "MISMATCH"))
print("  strike_daily : %d (fuente %d)  %s" % (
    n_nueva.get("strike_daily", -1), n_antes["strike_daily"],
    "OK" if n_nueva.get("strike_daily") == n_antes["strike_daily"] else "MISMATCH"))
print("  resto de tablas vacias: %s" % ("OK" if ok else "NO -- hay intradia heredado"))

print("\n" + "=" * 78)
print("PASO 3: CONSUMIDOR REAL aguas abajo -> app._load_accum()")
print("=" * 78)
app.accum = {}; app.accum_net = {}; app.base_prev = {}
app._load_accum()
print("  app.accum     : %d claves" % len(app.accum))
print("  app.accum_net : %d claves" % len(app.accum_net))
print("  app.base_prev : %d claves (premium del DIA PREVIO)" % len(app.base_prev))
if app.base_prev:
    k = list(app.base_prev)[:2]
    for kk in k:
        print("      ej: %s -> %.2f" % (kk, app.base_prev[kk]))
print("  -> el consumidor %s" % ("LEE datos (siembra efectiva)" if app.accum and app.base_prev
                                 else "*** NO LEE: siembra INUTIL ***"))

print("\n" + "=" * 78)
print("PASO 4: IDEMPOTENCIA - segunda instancia el MISMO dia (no debe resembrar/duplicar)")
print("=" * 78)
app.db.commit(); app.db.close()
app2 = SD.SpyDirection()
n_2 = conteos(NUEVA)
print("  strike_accum: %d -> %d  %s" % (n_nueva.get("strike_accum"), n_2.get("strike_accum"),
      "OK (sin duplicar)" if n_2.get("strike_accum") == n_nueva.get("strike_accum") else "DUPLICO"))
print("  strike_daily: %d -> %d  %s" % (n_nueva.get("strike_daily"), n_2.get("strike_daily"),
      "OK (sin duplicar)" if n_2.get("strike_daily") == n_nueva.get("strike_daily") else "DUPLICO"))

print("\n" + "=" * 78)
print("PASO 5: ROTACION EN CALIENTE - _rotar_db() real cruzando medianoche")
print("=" * 78)
print("  a) idempotente si NO cambio el dia:")
antes_f = app2.db_fecha
app2._rotar_db()
print("     db_fecha %s -> %s  %s" % (antes_f, app2.db_fecha,
      "OK (no rota)" if app2.db_fecha == antes_f else "ROTO SIN CAMBIO DE DIA"))
print("  b) simulando que la app venia de AYER (db_fecha=20260813):")
app2.db_fecha = "20260813"
app2._rotar_db()
ruta_post = app2.db.execute("PRAGMA database_list").fetchall()[0][2]
print("     db_fecha -> %s" % app2.db_fecha)
print("     archivo  -> %s  %s" % (os.path.basename(ruta_post),
      "OK" if os.path.basename(ruta_post) == os.path.basename(NUEVA) else "RUTA MAL"))
n_3 = conteos(NUEVA)
print("     strike_accum tras rotar: %d  %s" % (n_3.get("strike_accum"),
      "OK (no resembro)" if n_3.get("strike_accum") == n_nueva.get("strike_accum") else "RESEMBRO"))
app2.db.commit(); app2.db.close()

print("\n" + "=" * 78)
print("PASO 6: DIFERENCIAL - la BD fuente NO se pudo tocar")
print("=" * 78)
h_desp = huella(FUENTE)
print("  antes  : %d bytes  sha=%s" % h_antes)
print("  despues: %d bytes  sha=%s" % h_desp)
print("  -> %s" % ("IDENTICA (solo-lectura respetada)" if h_antes == h_desp
                   else "*** MODIFICADA - REGRESION ***"))
for aux in ("-wal", "-shm", "-journal"):
    p = FUENTE + aux
    if os.path.exists(p):
        print("  AVISO: quedo %s" % os.path.basename(p))
print("\nFIN")
