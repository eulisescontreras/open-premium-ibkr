# -*- coding: utf-8 -*-
# ¿LA COMPRESIÓN ES UN MECANISMO O UNA PROPIEDAD DEL SPY DE ESTOS 2 AÑOS?
#
# EL TEST (propuesto por el agente del motor original, y lo único que tumbó un candidato suyo
# equivalente): la compresión es GEOMETRÍA PURA del Supertrend — no necesita premium ni opciones.
# Si funciona en SPY pero falla en QQQ/IWM/DIA/GLD, es una propiedad del período, no del mecanismo.
#
# LA REGLA MEDIDA: cuando la línea del ST-3 lleva >= N buckets SIN MOVERSE (congelada en el mismo
# valor), el movimiento posterior del precio es distinto. Solo usa buckets ya cerrados.
#
# Y AQUÍ SE RESPONDE TAMBIÉN la pregunta clave del otro agente: ¿es MECANISMO o COBERTURA?
# Se normaliza el efecto POR BUCKET TOCADO, no solo el agregado: si el máximo se mantiene en 6-8
# tras normalizar, hay mecanismo; si se aplana, era simplemente que 8 toca más días que 20.
import sqlite3, sys, os, statistics as stt

RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2 import config as C
from sys2.core.rebote import st_lin_p
from sys2.core.supertrend import mm, hhmm

FUENTES = [("SPY", ["sys2.db"]),
           ("QQQ", ["qqq_bars_year2.db", "qqq_bars_year.db"]),
           ("IWM", ["iwm_bars_year2.db", "iwm_bars_year.db"]),
           ("DIA", ["dia_bars_year2.db", "dia_bars_year.db"]),
           ("GLD", ["gld_bars_year.db"])]


def analiza(tk, ficheros):
    D = []
    for fich in ficheros:
        ruta = os.path.join(RAIZ, fich)
        if not os.path.exists(ruta):
            continue
        con = sqlite3.connect(ruta)
        try:
            fechas = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
        except Exception:
            con.close()
            continue
        for f in fechas:
            bars = con.execute("select hora,high,low,close from bars where fecha=? order by hora",
                               (f,)).fetchall()
            if len(bars) < 100:
                continue
            try:
                L, ks, Dd = st_lin_p(bars, C.ST_PER, C.ST_MULT)
            except Exception:
                continue
            for i in range(12, len(ks) - 13):
                h = hhmm(ks[i])
                if not ("09:45" <= h <= "15:30"):
                    continue
                atr = sum(L[ks[j]]['hi'] - L[ks[j]]['lo'] for j in range(i - 10, i + 1)) / 11.0
                if atr <= 0:
                    continue
                plana = 0
                for j in range(i, max(0, i - 60), -1):
                    if abs(L[ks[j]]['linea'] - L[ks[j - 1]]['linea']) < 1e-9:
                        plana += 1
                    else:
                        break
                lado = 1 if L[ks[i]]['d'] > 0 else -1
                cls = [L[ks[j]]['cl'] for j in range(i, i + 13)]
                # a FAVOR de la dirección del ST (que es lo que opera el sistema)
                favor = max((y - cls[0]) * lado for y in cls) / atr
                contra = min((y - cls[0]) * lado for y in cls) / atr
                neto = (cls[-1] - cls[0]) * lado / atr
                camino = sum(abs(cls[j] - cls[j - 1]) for j in range(1, len(cls))) / atr
                D.append(dict(f=f, plana=plana, favor=favor, contra=contra, neto=neto,
                              efic=abs(neto) / camino if camino > 0 else 0,
                              bueno=1 if favor >= 1.0 else 0))
        con.close()
    return D


print("%-5s %8s %7s %8s %8s %8s %8s %8s"
      % ("ETF", "buckets", "grupo", "n", "%bueno", "favor", "neto", "efic"))
RES = {}
for tk, fichs in FUENTES:
    D = analiza(tk, fichs)
    if len(D) < 2000:
        print("%-5s  (sin datos suficientes: %d)" % (tk, len(D)))
        continue
    base_b = 100.0 * sum(x['bueno'] for x in D) / len(D)
    base_f = stt.mean(x['favor'] for x in D)
    base_n = stt.mean(x['neto'] for x in D)
    print("%-5s %8d %7s %8d %7.1f%% %8.3f %8.3f %8.3f"
          % (tk, len(D), "BASE", len(D), base_b, base_f, base_n, stt.mean(x['efic'] for x in D)))
    RES[tk] = {}
    for lo, hi, et in ((6, 11, "6-10"), (11, 16, "11-15"), (16, 999, "16+")):
        sub = [x for x in D if lo <= x['plana'] < hi]
        if len(sub) < 200:
            continue
        b = 100.0 * sum(x['bueno'] for x in sub) / len(sub)
        fv = stt.mean(x['favor'] for x in sub)
        nt = stt.mean(x['neto'] for x in sub)
        RES[tk][et] = (b - base_b, fv - base_f, nt - base_n)
        print("%-5s %8s %7s %8d %7.1f%% %8.3f %8.3f %8.3f"
              % ("", "", et, len(sub), b, fv, nt, stt.mean(x['efic'] for x in sub)))
    # el grupo que usa la regla del motor: plana >= 8
    sub = [x for x in D if x['plana'] >= 8]
    no = [x for x in D if x['plana'] < 8]
    if len(sub) >= 200:
        b1 = 100.0 * sum(x['bueno'] for x in sub) / len(sub)
        b0 = 100.0 * sum(x['bueno'] for x in no) / len(no)
        n1, n0 = stt.mean(x['neto'] for x in sub), stt.mean(x['neto'] for x in no)
        RES[tk][">=8"] = (b1 - b0, 0, n1 - n0)
        print("%-5s %8s %7s %8d  %+.1f pts vs resto   neto %+.3f  (%d%% de los buckets)"
              % ("", "", ">=8", len(sub), b1 - b0, n1 - n0, 100 * len(sub) / len(D)))
    print()

print("=== VEREDICTO: ¿replica fuera del SPY? ===")
print("%-6s %12s %12s %12s" % ("ETF", "plana>=8 %bueno", "neto", "¿mismo signo?"))
ref = RES.get("SPY", {}).get(">=8")
for tk in ("SPY", "QQQ", "IWM", "DIA", "GLD"):
    v = RES.get(tk, {}).get(">=8")
    if not v:
        continue
    ok = "-" if tk == "SPY" else ("SÍ" if (v[0] > 0) == (ref[0] > 0) else "NO")
    print("%-6s %+11.1f pts %+11.3f %12s" % (tk, v[0], v[2], ok))
