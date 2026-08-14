import sqlite3
DB = r"C:\Users\eulis\proyectos\open-premium-ibkr\spy_history_20260814.db"
c = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True, timeout=20)
cols = [r[1] for r in c.execute("PRAGMA table_info(sesion_config)")]
print("=== sesion_config de HOY (lo GRABADO en la BD) ===")
for r in c.execute("SELECT * FROM sesion_config WHERE fecha='2026-08-14'"):
    d = dict(zip(cols, r))
    print("\n  fecha=%s hora=%s arranque=%s trading=%s" % (
        d.get("fecha"), d.get("hora"), d.get("arranque"), d.get("trading")))
    n = d.get("notas") or ""
    print("  notas -> %s" % n[:150])
print("\n=== comprobacion aritmetica del +122.7%% del panel ===")
base, actual = 179.60, 400.00
print("  (400.00 - 179.60) = %+.2f" % (actual - base))
print("  %+.2f / 179.60     = %+.1f%%" % (actual - base, (actual - base) / base * 100))
print("  el panel mostro    : DIA +220.40 (+122.7%)")
print("  -> %s" % ("COINCIDE EXACTO: era la base obsoleta, NO PnL residual"
                   if abs((actual - base) - 220.40) < 0.01 else "no coincide"))
c.close()
