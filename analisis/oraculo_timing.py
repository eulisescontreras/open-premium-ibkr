# -*- coding: utf-8 -*-
"""PASO 2 (GATE DECISIVO) — TA-timing bajo direccion ORACULO.

Pregunta: DADA la direccion PERFECTA del dia (oraculo, ex-post = cota superior), ¿puede el TA
cronometrar entradas 0DTE de 8 min con EV>0? Si NI ASI aporta, el hibrido M1/M2+TA esta muerto.

Direccion oraculo del dia = signo(close_cierre - close_t) en cada minuto t (se conoce el futuro:
es la MEJOR direccion posible). Solo se permiten operaciones EN ESA direccion.
- CALL permitido si el dia termina ARRIBA respecto a t ; PUT si termina ABAJO.
Metrica: EV_op = 85*media_fav - 2.22 ; horizonte 8 min, no solapado, retraso 1. Split 170/85.

Compara:
  (i)   siempre-en-direccion-oraculo, SIN filtro TA (entra cada minuto en la direccion del dia)
  (ii)  TA-timing SIN direccion (reversion a la media, lo ya probado) -> baseline conocido
  (iii) TA-timing + direccion oraculo (entra solo cuando el TA dispara Y coincide con el oraculo)

Reusa el motor de barrido_exploracion (serie_media). Read-only. Uso: python analisis/oraculo_timing.py
Salida: investigacion/oraculo_timing.txt
"""
import os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from barrido_exploracion import serie_media, DELTA, COSTE, N_EXPLORA, RETRASO, mm

DB = "historico_spy.db"
OUT = []
def p(s=""):
    print(s); OUT.append(s)

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dias = {}
    for f, h, o, hi, lo, cl in c.execute(
            "select fecha,hora,open,high,low,close from bars_historico order by fecha,hora"):
        dias.setdefault(f, []).append((h, o, hi, lo, cl, 0.0))   # v dummy (serie_media espera 6)
    c.close()
    orden = [f for f in sorted(dias) if len(dias[f]) >= 100]
    return orden, dias

def agrega(favs):
    n = len(favs)
    if n == 0:
        return (0, 0.0, -COSTE, 0.0)
    mf = sum(favs) / n
    return (n, 100 * sum(1 for x in favs if x > 0) / n, DELTA * mf - COSTE, mf)

def ops_modo(barras, W, umbral, H, modo):
    """modo:
      'oraculo'      -> entra CADA minuto en la direccion del dia (signo close_fin - close_i)
      'ta'           -> reversion a la media (sin direccion): lado hacia la media si |dist|>=umbral
      'ta_oraculo'   -> dispara el TA (|dist|>=umbral) PERO solo si el lado coincide con el oraculo
    Devuelve lista de fav (puntos con signo a favor). No solapado, retraso 1, horizonte H."""
    serie = serie_media(barras, W)              # (hora, close, media, dist, minuto)
    n = len(serie)
    close_fin = serie[-1][1]
    res = []; i = 0
    while i < n:
        h = serie[i][0]
        if h >= "15:40":
            break
        fin = [k for k in range(i, n) if serie[k][4] >= serie[i][4] + H]
        if not fin:
            break
        k = fin[0]
        ci = serie[i][1]
        ora = "C" if (close_fin - ci) > 0 else "P"    # direccion perfecta del resto del dia
        if modo == "oraculo":
            lado = ora
        else:
            j = i - RETRASO
            if j < 0:
                i += 1; continue
            dd = serie[j][3]
            if abs(dd) < umbral:
                i += 1; continue
            lado_ta = "P" if dd > 0 else "C"           # reversion a la media
            if modo == "ta":
                lado = lado_ta
            else:  # ta_oraculo: el TA marca el timing, el oraculo filtra la direccion
                if lado_ta != ora:
                    i += 1; continue
                lado = lado_ta
        ds = serie[k][1] - ci
        res.append(ds if lado == "C" else -ds)
        i = k
    return res

def corre(orden, dias, modo, W=5, umbral=0.20, H=8):
    favs = []
    for f in orden:
        favs.extend(ops_modo(dias[f], W, umbral, H, modo))
    return agrega(favs)

def main():
    orden, dias = carga()
    expl = orden[:N_EXPLORA]; resv = orden[N_EXPLORA:]
    p("=" * 92)
    p("PASO 2 (GATE) — TA-timing bajo direccion ORACULO. Liston 0DTE 56.7% (320)/54.4% (800).")
    p(f"  exploracion {len(expl)} dias | reserva {len(resv)} dias | W=5 umbral=0.20 H=8")
    p("=" * 92)
    p(f"{'modo':>26} | {'EXPL n':>7}{'acc%':>7}{'EV$':>8}{'mfav':>9} | {'RES n':>7}{'acc%':>7}{'EV$':>8}{'mfav':>9}")
    for modo, etq in (("oraculo", "(i) oraculo puro s/TA"),
                      ("ta", "(ii) TA sin direccion"),
                      ("ta_oraculo", "(iii) TA + direccion oraculo")):
        ne, ae, eve, mfe = corre(expl, dias, modo)
        nr, ar, evr, mfr = corre(resv, dias, modo)
        p(f"{etq:>26} | {ne:>7}{ae:>7.1f}{eve:>+8.2f}{mfe:>+9.4f} | {nr:>7}{ar:>7.1f}{evr:>+8.2f}{mfr:>+9.4f}")
    p("\n  barrido de umbral en (iii) TA+oraculo (reserva), por si el timing ayuda a algun nivel:")
    p("   umbral |   n   acc%     EV$     mfav")
    for u in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
        nr, ar, evr, mfr = corre(resv, dias, "ta_oraculo", umbral=u)
        p(f"   {u:>6.2f} | {nr:>4} {ar:>5.1f} {evr:>+7.2f}  {mfr:>+7.4f}")
    p("\n" + "=" * 92)
    p("LECTURA:")
    p("  (i) mide cuanto rinde la direccion perfecta sola (cota superior del sesgo direccional).")
    p("  (iii) vs (i): si el TA-timing NO sube el EV sobre (i), el TA no aporta timing.")
    p("  Si (iii) NO da EV>0 en reserva -> el hibrido esta MUERTO aunque M1/M2 fuera perfecto.")
    p("=" * 92)
    os.makedirs("investigacion", exist_ok=True)
    with open(os.path.join("investigacion", "oraculo_timing.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print("\nsalida:", os.path.abspath(os.path.join("investigacion", "oraculo_timing.txt")))

if __name__ == "__main__":
    main()
