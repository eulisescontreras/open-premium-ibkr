# SOLO LECTURA. Reconstruye los buckets de 3 min alrededor de las 10:10 tal como los ve
# _st3_dir(), para mostrar que ve el sistema y que NO ve.
import sqlite3, os
DB = r"C:\Users\eulis\proyectos\open-premium-ibkr\spy_history_20260814.db"
c = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True, timeout=20)

print("=== BARRAS 1-MIN REALES DE HOY (09:57 -> 10:15) ===")
filas = c.execute(
    "SELECT hora,open,high,low,close FROM bars_minute WHERE fecha='2026-08-14' "
    "AND hora>='09:57' AND hora<='10:15' ORDER BY hora").fetchall()
for h, o, hi, lo, cl in filas:
    m = int(h[3:5])
    marca = "  <-- inicio bucket 3min" if m % 3 == 0 else ""
    print("  %s  O=%.2f H=%.2f L=%.2f C=%.2f%s" % (h, o, hi, lo, cl, marca))

print("\n=== AGRUPADO EN BUCKETS DE 3 MIN (lo que evalua el Supertrend) ===")
buck = {}
for h, o, hi, lo, cl in filas:
    hh, mm = int(h[:2]), int(h[3:5])
    k = "%02d:%02d" % (hh, (mm // 3) * 3)
    a = buck.get(k)
    if a is None:
        buck[k] = [hi, lo, cl, 1]
    else:
        a[0] = max(a[0], hi); a[1] = min(a[1], lo); a[2] = cl; a[3] += 1
ult = max(buck)
for k in sorted(buck):
    hi, lo, cl, n = buck[k]
    estado = "EN FORMACION -> el sistema lo DESCARTA" if k == ult else "CERRADO -> el sistema SI lo usa"
    print("  bucket %s  H=%.2f L=%.2f C=%.2f  (%d min)  %s" % (k, hi, lo, cl, n, estado))

print("\n=== RECORRIDO DENTRO DEL BUCKET 10:09 (el que te llamo la atencion) ===")
sub = [f for f in filas if f[0] >= "10:09" and f[0] <= "10:11"]
if sub:
    print("  minuto   close     movimiento intra-bucket")
    base = sub[0][1]
    for h, o, hi, lo, cl in sub:
        print("    %s   %.2f    %+.2f desde la apertura del bucket" % (h, cl, cl - base))
    print("  -> rango del bucket: L=%.2f  H=%.2f  (recorrido %.2f)" % (
        min(x[3] for x in sub), max(x[2] for x in sub),
        max(x[2] for x in sub) - min(x[3] for x in sub)))
c.close()
