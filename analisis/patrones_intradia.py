# -*- coding: utf-8 -*-
"""PATRON DE FIGURA intradia (k-NN sobre features de FORMA) -> predecir el proximo movimiento.

Captura 'figuras' (banderas/canales/impulsos) describiendo cada ventana de M velas por su FORMA:
  retorno total, subida max, bajada max, rango, posicion del maximo, posicion del minimo,
  pendiente lineal, curvatura. k-NN en ese espacio (normalizado) -> predice el signo del
  movimiento en los proximos H minutos. Miles de muestras -> potencia estadistica real.

FUERA DE MUESTRA:
  - EXPLORACION: vecinos de exploracion EXCLUYENDO el mismo dia del query (evita fuga temporal).
  - RESERVA: vecinos SOLO de exploracion (out-of-sample puro).
Metrica: acierto direccional + EV_op = 85*media_fav - 2.22 (fiel a H=8).
Baseline: siempre CALL (deriva).

Uso: python analisis/patrones_intradia.py
Salida: investigacion/patrones_intradia.txt
"""
import os, sqlite3, sys
import numpy as np
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = "historico_spy.db"; N_EXPLORA = 170
DELTA = 85.0; COSTE = 2.22
def mm(h): return int(h[:2]) * 60 + int(h[3:5])
OUT = []
def p(s=""):
    print(s); OUT.append(s)


def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dias = {}
    for f, h, o, hi, lo, cl in c.execute(
            "select fecha,hora,open,high,low,close from bars_historico order by fecha,hora"):
        dias.setdefault(f, []).append((mm(h), o, hi, lo, cl))
    c.close()
    orden = [f for f in sorted(dias) if len(dias[f]) >= 300]
    return orden, dias


def features_ventana(b, i, M):
    """forma de las velas [i-M+1 .. i]. Devuelve vector de 8 features de FORMA (escala-libre)."""
    seg = b[i - M + 1:i + 1]
    close = np.array([x[4] for x in seg], float)
    hi = np.array([x[2] for x in seg], float); lo = np.array([x[3] for x in seg], float)
    base = close[0]
    r = (close - base)                      # camino vs inicio de ventana
    rng = (hi.max() - lo.min()) or 1e-9
    ret_total = (close[-1] - base) / rng
    max_up = (hi.max() - base) / rng
    max_dn = (base - lo.min()) / rng
    pos_max = float(np.argmax(hi)) / (M - 1)
    pos_min = float(np.argmin(lo)) / (M - 1)
    x = np.arange(M, dtype=float)
    slope = np.polyfit(x, r, 1)[0] / rng * M
    curv = np.polyfit(x, r, 2)[0] / rng * M * M
    amp = rng / (base if base else 1e-9)    # amplitud relativa (unico feature de tamano)
    return [ret_total, max_up, max_dn, pos_max, pos_min, slope, curv, amp]


def construir(orden, dias, M, H):
    """matriz de features X, target signo del mov a H, y el mov en puntos; + dia por fila."""
    X = []; sig = []; mov = []; dia = []
    for f in orden:
        b = dias[f]; n = len(b)
        for i in range(M - 1, n):
            fin = [k for k in range(i, n) if b[k][0] >= b[i][0] + H]
            if not fin:
                break
            if b[i][0] >= mm("15:40"):
                break
            k = fin[0]
            X.append(features_ventana(b, i, M))
            m = b[k][4] - b[i][4]
            mov.append(m); sig.append(1 if m > 0 else -1); dia.append(f)
    return np.array(X, float), np.array(sig), np.array(mov, float), np.array(dia)


def knn_eval(Xq, diaq, movq, Xref, diaref, sigref, movref, k, muestra=3000, seed=0):
    """predice signo por mayoria de k vecinos (excluyendo mismo dia). VECTORIZADO por lotes.
    dist^2 = ||q||^2 + ||r||^2 - 2 q.r  ; el mismo dia se pone a +inf. Devuelve acc, ev, n, mfav."""
    rng = np.random.default_rng(seed)
    idx = np.arange(len(Xq))
    if len(idx) > muestra:
        idx = rng.choice(idx, muestra, replace=False)
    mu = Xref.mean(0); sd = Xref.std(0); sd[sd == 0] = 1e-9
    Rn = (Xref - mu) / sd                          # (R,8)
    Qn = (Xq[idx] - mu) / sd                        # (Q,8)
    r2 = (Rn ** 2).sum(1)                            # (R,)
    # codigo entero de dia para comparar rapido
    uni = {d: i for i, d in enumerate(np.unique(np.concatenate([diaref, diaq])))}
    cref = np.array([uni[d] for d in diaref])
    cq = np.array([uni[d] for d in diaq[idx]])
    sigpos = (sigref > 0)
    aciertos = 0; favs = np.empty(len(idx))
    CH = 400
    for a in range(0, len(idx), CH):
        b = min(a + CH, len(idx))
        Qb = Qn[a:b]                                 # (q,8)
        d2 = r2[None, :] - 2.0 * (Qb @ Rn.T)         # (q,R)  (se omite ||q||^2: constante por fila)
        same = (cref[None, :] == cq[a:b, None])
        d2[same] = np.inf
        nn = np.argpartition(d2, k, axis=1)[:, :k]   # (q,k)
        up = sigpos[nn].sum(1)                        # (q,)
        pred = np.where(up >= (k - up), 1, -1)
        mv = movq[idx[a:b]]
        real = np.where(mv > 0, 1, -1)
        aciertos += int((pred == real).sum())
        favs[a:b] = np.where(pred > 0, mv, -mv)
    n = len(idx)
    acc = 100 * aciertos / n
    mfav = float(favs.mean())
    ev = DELTA * mfav - COSTE
    return acc, ev, n, mfav


def main():
    orden, dias = carga()
    expl = orden[:N_EXPLORA]; resv = orden[N_EXPLORA:]
    p("=" * 96)
    p(f"PATRON DE FIGURA k-NN — expl={len(expl)} dias, reserva={len(resv)} dias")
    p("  features de forma: ret_total, max_up, max_dn, pos_max, pos_min, slope, curv, amplitud")
    p("  metrica EV fiel a H=8; baseline = siempre CALL (deriva)")
    p("=" * 96)
    p(f"{'M':>4}{'H':>4}{'k':>5} | {'EXPL acc%':>9}{'EXPL EV$':>9}{'EXPL mfav':>10} | {'RES acc%':>9}{'RES EV$':>9}{'RES mfav':>10}   n_ref")
    for M in (10, 20, 30):
        for H in (8, 15, 30):
            Xe, sige, move, diae = construir(expl, dias, M, H)
            Xr, sigr, movr, diar = construir(resv, dias, M, H)
            for k in (25, 50, 100):
                ae, eve, ne, mfe = knn_eval(Xe, diae, move, Xe, diae, sige, move, k)
                ar, evr, nr, mfr = knn_eval(Xr, diar, movr, Xe, diae, sige, move, k)  # reserva: ref=exploracion
                p(f"{M:>4}{H:>4}{k:>5} | {ae:>9.1f}{eve:>+9.2f}{mfe:>+10.4f} | {ar:>9.1f}{evr:>+9.2f}{mfr:>+10.4f}   {len(Xe)}")
    p("\n" + "=" * 96)
    p("COMO LEERLO: la RESERVA (out-of-sample) manda. acc alta en EXPL y ~50% en RESERVA = sobreajuste.")
    p("  Para 0DTE 8min el liston es ~56.7% (o 54.4% con capital 800). EV>0 y estable en reserva = candidata.")
    p("=" * 96)
    os.makedirs("investigacion", exist_ok=True)
    with open(os.path.join("investigacion", "patrones_intradia.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print("\nsalida en:", os.path.abspath(os.path.join('investigacion', 'patrones_intradia.txt')))


if __name__ == "__main__":
    main()
