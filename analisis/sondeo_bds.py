import sqlite3, os, glob

BASE = r"C:\Users\eulis\proyectos\open-premium-ibkr"

def sondeo(path):
    if not os.path.exists(path):
        print(f"  [NO EXISTE] {os.path.basename(path)}")
        return
    mb = os.path.getsize(path) / 1024 / 1024
    print(f"\n=== {os.path.basename(path)}  ({mb:.1f} MB) ===")
    try:
        c = sqlite3.connect(f"file:{path.replace(chr(92),'/')}?mode=ro", uri=True, timeout=15)
    except Exception as e:
        print(f"  ERROR abriendo: {e}")
        return
    tablas = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"  tablas ({len(tablas)}): {', '.join(tablas)}")
    for t in ("strike_accum", "strike_daily"):
        if t in tablas:
            n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            extra = ""
            if t == "strike_daily" and n:
                fechas = c.execute(
                    "SELECT MIN(fecha), MAX(fecha), COUNT(DISTINCT fecha) FROM strike_daily"
                ).fetchone()
                extra = f"  fechas: {fechas[0]} .. {fechas[1]} ({fechas[2]} dias)"
            print(f"  {t}: {n} filas{extra}")
        else:
            print(f"  {t}: TABLA AUSENTE")
    # dias presentes en ta_minute (referencia de contenido)
    if "ta_minute" in tablas:
        f = c.execute("SELECT MIN(fecha), MAX(fecha), COUNT(DISTINCT fecha) FROM ta_minute").fetchone()
        print(f"  ta_minute: fechas {f[0]} .. {f[1]} ({f[2]} dias)")
    c.close()

print("########## BD ACUMULADA (produccion actual) ##########")
sondeo(os.path.join(BASE, "spy_history.db"))

print("\n########## BDs PARTIDAS POR DIA (partir_bd.py) ##########")
for p in sorted(glob.glob(os.path.join(BASE, "spy_history_2*.db"))):
    sondeo(p)

print("\n########## COLISION DE NOMBRE PARA HOY ##########")
hoy = os.path.join(BASE, "spy_history_20260814.db")
print(f"  spy_history_20260814.db existe: {os.path.exists(hoy)}")
