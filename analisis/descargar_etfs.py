# -*- coding: utf-8 -*-
"""Orquesta la descarga de 2 años de velas 1-min (con premarket) de QQQ / IWM / DIA.
REUTILIZA analisis/bajar_bars_year.py (R9: no se duplica el descargador), llamandolo una vez
por tramo y SECUENCIALMENTE: dos descargas a la vez multiplicarian las peticiones por minuto
y IBKR limita el historico a ~60 cada 10 min.
Mismo formato que spy_bars_year.db: tabla `bars` (fecha,hora,open,high,low,close,volume,wap),
US/Eastern, TRADES, useRTH=False -> comparable 1:1 con el SPY.
"""
import subprocess, sys, os, time, sqlite3

PY = r"C:\Users\eulis\AppData\Local\Programs\Python\Python311\python.exe"
REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"
SCRIPT = os.path.join(REPO, "analisis", "bajar_bars_year.py")
PAUSA = "8.0"          # segundos entre peticiones (limite IBKR ~60/10min)

# (simbolo, FIN, INICIO, db, clientId) -- mismos tramos que se usaron para el SPY
TRAMOS = [
    ("QQQ", "20260813", "20250801", "qqq_bars_year.db",  "31"),
    ("QQQ", "20250801", "20240731", "qqq_bars_year2.db", "31"),
    ("IWM", "20260813", "20250801", "iwm_bars_year.db",  "32"),
    ("IWM", "20250801", "20240731", "iwm_bars_year2.db", "32"),
    ("DIA", "20260813", "20250801", "dia_bars_year.db",  "33"),
    ("DIA", "20250801", "20240731", "dia_bars_year2.db", "33"),
]

t0 = time.time()
print("=" * 74, flush=True)
print("DESCARGA QQQ / IWM / DIA  ·  2 años de velas 1-min con premarket", flush=True)
print("pausa entre peticiones: %ss   |   %d tramos SECUENCIALES" % (PAUSA, len(TRAMOS)), flush=True)
print("=" * 74, flush=True)

for i, (sim, fin, ini, db, cid) in enumerate(TRAMOS, 1):
    print("\n" + "-" * 74, flush=True)
    print("[%d/%d] %s  %s -> %s   ->  %s" % (i, len(TRAMOS), sim, ini, fin, db), flush=True)
    print("-" * 74, flush=True)
    cmd = [PY, SCRIPT, fin, ini, db, cid, sim, PAUSA]
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=7200)
        out = (r.stdout or "").strip().splitlines()
        for l in out[-6:]:
            print("   " + l, flush=True)
        if r.returncode != 0:
            print("   *** returncode=%d ***" % r.returncode, flush=True)
            err = (r.stderr or "").strip().splitlines()
            for l in err[-5:]:
                print("   ERR " + l, flush=True)
    except subprocess.TimeoutExpired:
        print("   *** TIMEOUT en este tramo, sigo con el siguiente ***", flush=True)
    except Exception as e:
        print("   *** ERROR %s ***" % e, flush=True)
    # respiro entre tramos para no encadenar peticiones
    if i < len(TRAMOS):
        time.sleep(20)

print("\n" + "=" * 74, flush=True)
print("RESUMEN FINAL  (%.1f min)" % ((time.time() - t0) / 60.0), flush=True)
print("=" * 74, flush=True)
for sim, _, _, db, _ in TRAMOS:
    p = os.path.join(REPO, db)
    if not os.path.exists(p):
        print("  %-22s NO SE CREO" % db, flush=True)
        continue
    try:
        c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
        n = c.execute("select count(*) from bars").fetchone()[0]
        d = c.execute("select count(distinct fecha) from bars").fetchone()[0]
        mn, mx = c.execute("select min(fecha), max(fecha) from bars").fetchone()
        c.close()
        print("  %-22s %7d barras | %3d dias | %s .. %s | %.1f MB"
              % (db, n, d, mn, mx, os.path.getsize(p) / 1024 / 1024), flush=True)
    except Exception as e:
        print("  %-22s ERROR %s" % (db, e), flush=True)
print("\nFIN", flush=True)
