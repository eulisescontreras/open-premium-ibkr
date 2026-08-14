# RE-VERIFICACION INDEPENDIENTE de lo que reporta orb-forense (regla 5: no confiar).
# Tres afirmaciones suyas, cada una comprobada con datos crudos:
#   A) 2025-07-31 esta en las DOS BDs -> 511 unicos pero 512 "sesiones"
#   B) ventana INCLUSIVA <=09:45 da 214 sobre 512 (y 213 sobre 511); la estricta da 183/182
#   C) los dias EXTRA de la inclusiva disparan TODOS a las 09:45
import os, sqlite3
REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"
MIN_AMP = 0.75

def carga(db):
    p = os.path.join(REPO, db)
    d = {}
    con = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    for f, h, hi, lo, cl in con.execute(
            "select fecha,hora,high,low,close from bars where hora>='09:30' and hora<='09:45' "
            "order by fecha,hora"):
        d.setdefault(f, []).append((h, hi, lo, cl))
    con.close()
    return d

y1 = carga("spy_bars_year.db")
y2 = carga("spy_bars_year2.db")

print("=" * 70)
print("A) UNIVERSO: 511 vs 512")
print("=" * 70)
print("  year.db  dias: %d" % len(y1))
print("  year2.db dias: %d" % len(y2))
print("  suma             : %d" % (len(y1) + len(y2)))
comunes = sorted(set(y1) & set(y2))
print("  dias en AMBAS    : %d  -> %s" % (len(comunes), comunes))
print("  union (unicos)   : %d" % len(set(y1) | set(y2)))
for f in comunes:
    print("  %s identico byte a byte: %s" % (f, y1[f] == y2[f]))

def dispara(filas, fin_ventana, inclusivo):
    ran = [x for x in filas if "09:30" <= x[0] <= "09:39"]
    if len(ran) < 10:
        return None
    hi = max(x[1] for x in ran); lo = min(x[2] for x in ran)
    if (hi - lo) < MIN_AMP:
        return "FILTRADO"
    ven = [x for x in filas
           if "09:40" <= x[0] <= fin_ventana] if inclusivo else \
          [x for x in filas if "09:40" <= x[0] < fin_ventana]
    for h, _hi, _lo, cl in ven:
        if cl > hi or cl < lo:
            return h
    return None

print("\n" + "=" * 70)
print("B) CONTEO CON VENTANA ESTRICTA (<09:45) vs INCLUSIVA (<=09:45)")
print("=" * 70)
for etiqueta, universo in (("511 unicos", None), ("512 con el dia repetido", "dup")):
    if universo is None:
        items = list({**y2, **y1}.items())
    else:
        items = list(y1.items()) + list(y2.items())
    for modo, inc in (("estricta <09:45", False), ("inclusiva <=09:45", True)):
        n = sum(1 for _, fl in items
                if (r := dispara(fl, "09:45", inc)) not in (None, "FILTRADO"))
        print("  %-24s %-20s -> %d dias con señal" % (etiqueta, modo, n))

print("\n" + "=" * 70)
print("C) LOS DIAS EXTRA DE LA INCLUSIVA, ¿DISPARAN TODOS A LAS 09:45?")
print("=" * 70)
items = list(y1.items()) + list(y2.items())
extra = []
for f, fl in items:
    e = dispara(fl, "09:45", False)
    i = dispara(fl, "09:45", True)
    if e in (None, "FILTRADO") and i not in (None, "FILTRADO"):
        extra.append((f, i))
print("  dias extra: %d" % len(extra))
horas = {}
for f, h in extra:
    horas[h] = horas.get(h, 0) + 1
print("  horas de disparo de esos extra: %s" % horas)
print("  -> %s" % ("TODOS a las 09:45: incompatible con la linea 'horas 09:40..09:44' de la spec"
                   if set(horas) == {"09:45"} else "NO todos a las 09:45"))

print("\n" + "=" * 70)
print("D) CUADRE: 214 + filtrados + sin_salida = 512 ?")
print("=" * 70)
nf = sum(1 for _, fl in items if dispara(fl, "09:45", True) == "FILTRADO")
ns = sum(1 for _, fl in items if dispara(fl, "09:45", True) is None)
nd = sum(1 for _, fl in items if dispara(fl, "09:45", True) not in (None, "FILTRADO"))
print("  con señal (inclusiva) : %d" % nd)
print("  filtrados por 0.75    : %d" % nf)
print("  sin salir del rango   : %d" % ns)
print("  TOTAL                 : %d" % (nd + nf + ns))
print("  512 - 214 = 298  ->  la linea 'el filtro descarta 298' es el COMPLEMENTO, no los "
      "filtrados (%d)" % nf)
