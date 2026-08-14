import sqlite3
DB = r"C:\Users\eulis\proyectos\open-premium-ibkr\spy_history_20260814.db"
c = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True, timeout=20)
F = "2026-08-14"
n = c.execute("SELECT COUNT(*) FROM trades WHERE fecha=?", (F,)).fetchone()[0]
ab = c.execute("SELECT COUNT(*) FROM trades WHERE fecha=? AND hora_salida IS NULL",
               (F,)).fetchone()[0]
print("trades de hoy: %d   |   SIN cerrar (posicion viva): %d" % (n, ab))
r = c.execute("SELECT hora,estado,pnl_realizado,n_trades FROM estado_intradia WHERE fecha=?",
              (F,)).fetchone()
print("estado_intradia:", r)
for t in ("tape", "premium_minute", "bars_minute", "ta_minute"):
    print("  %-16s %d filas hoy" % (t, c.execute(
        "SELECT COUNT(*) FROM %s WHERE fecha=?" % t, (F,)).fetchone()[0]))
c.close()
print("\nSEGURO CERRAR" if ab == 0 else "\n*** OJO: HAY POSICION ABIERTA ***")
