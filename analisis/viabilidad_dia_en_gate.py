# ¿Se puede evaluar el 2026-08-14 en el gate real-vs-sintetico?
# El backtest exige, por sesion: barras CON premarket (para calentar el ATR del ST-3) y
# al menos 300 minutos RTH. Se comprueba si el 08-14 cumple.
import sqlite3, os
R = r"C:\Users\eulis\proyectos\open-premium-ibkr"

print("=== 1) ¿esta el 08-14 en spy_bars_year.db (la fuente del backtest)? ===")
c = sqlite3.connect("file:%s/spy_bars_year.db?mode=ro" % R.replace("\\", "/"), uri=True)
mx = c.execute("select max(fecha) from bars").fetchone()[0]
n = c.execute("select count(*) from bars where fecha='2026-08-14'").fetchone()[0]
print("   ultimo dia en la BD: %s | barras del 08-14: %d" % (mx, n))
c.close()

print("\n=== 2) ¿que hay en bars_minute del 08-14 (lo que grabo la app)? ===")
c = sqlite3.connect("file:%s/spy_history_20260814.db?mode=ro" % R.replace("\\", "/"), uri=True)
r = c.execute("select count(*),min(hora),max(hora) from bars_minute where fecha='2026-08-14'").fetchone()
print("   %d barras | %s .. %s" % r)
pre = c.execute("select count(*) from bars_minute where fecha='2026-08-14' and hora<'09:30'").fetchone()[0]
print("   barras de PREMARKET (<09:30): %d" % pre)
c.close()

print("\n=== 3) requisitos del backtest ===")
print("   - sesiones() exige len(rth) >= 300 minutos")
print("   - sen_principal calienta el ATR del ST-3 CON premarket (es lo que vale +3.460$)")
print("\n=== VEREDICTO ===")
print("   RTH disponibles: %d de ~390  -> %s" % (r[0], "INSUFICIENTE" if r[0] < 300 else "ok"))
print("   premarket      : %d          -> %s" % (pre, "AUSENTE" if pre == 0 else "ok"))
print("\n   El 08-14 NO es evaluable de forma comparable todavia:")
print("   a) la sesion esta incompleta (la app se cerro a las 13:03 y el mercado cierra a las 16:00)")
print("   b) bars_minute no guarda premarket (self.bars usa useRTH=True), asi que el ATR")
print("      calentaria distinto que en el resto de las 511 sesiones -> no seria comparable")
