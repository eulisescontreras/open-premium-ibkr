# SOLO LECTURA. Que datos REALES de premium hay disponibles para auditar el modelo sintetico.
import os, sqlite3
REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"

print("=== BD auxiliar que usa synth_premium (spy_bars_pm.db) ===")
p = os.path.join(REPO, "spy_bars_pm.db")
print("  existe: %s" % os.path.exists(p))
if os.path.exists(p):
    c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    for t, in c.execute("select name from sqlite_master where type='table'"):
        n = c.execute("select count(*) from %s" % t).fetchone()[0]
        f = c.execute("select min(fecha),max(fecha),count(distinct fecha) from %s" % t).fetchone()
        print("  tabla %-10s %6d filas | %s .. %s (%d dias)" % (t, n, f[0], f[1], f[2]))
    c.close()

print("\n=== PREMIUM REAL por dia (bid/ask no nulos) ===")
for db in ("spy_history_20260810.db", "spy_history_20260811.db", "spy_history_20260812.db",
           "spy_history_20260813.db", "spy_history_20260814.db"):
    p = os.path.join(REPO, db)
    if not os.path.exists(p):
        print("  %-28s NO EXISTE" % db)
        continue
    c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(premium_minute)")]
        tiene = "bid" in cols and "ask" in cols
        if not tiene:
            print("  %-28s premium_minute SIN bid/ask" % db)
            c.close(); continue
        n = c.execute("select count(*) from premium_minute where bid is not null "
                      "and ask is not null").fetchone()[0]
        d = c.execute("select min(fecha),max(fecha) from premium_minute").fetchone()
        ex = c.execute("select count(distinct expiry) from premium_minute").fetchone()[0]
        k = c.execute("select count(distinct strike) from premium_minute where bid is not null").fetchone()[0]
        print("  %-28s %7d filas con bid/ask | %s | %d expiries | %d strikes"
              % (db, n, d[0], ex, k))
    except Exception as e:
        print("  %-28s ERROR %s" % (db, e))
    c.close()

print("\n=== ¿hay barras 1-min del SPY por dia (para el precio subyacente)? ===")
for db in ("spy_history_20260811.db", "spy_history_20260812.db", "spy_history_20260813.db",
           "spy_history_20260814.db"):
    p = os.path.join(REPO, db)
    if not os.path.exists(p):
        continue
    c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    n = c.execute("select count(*) from bars_minute").fetchone()[0]
    f = c.execute("select fecha,count(*) from bars_minute group by fecha").fetchall()
    print("  %-28s bars_minute %d filas -> %s" % (db, n, f))
    c.close()
