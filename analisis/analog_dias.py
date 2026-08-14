# -*- coding: utf-8 -*-
"""PRONOSTICO POR ANALOGIA (k-NN sobre la FORMA del inicio del dia).

Hipotesis del usuario: dias que EMPIEZAN con una forma parecida terminan parecido.
Test honesto y FUERA DE MUESTRA:
  - Forma del inicio = camino de los primeros M minutos, normalizado (z-score) -> compara FIGURA, no tamano.
  - Para cada dia: k vecinos mas cercanos (euclidea) entre OTROS dias; se predice el signo del
    'resto del dia' (de minuto M al cierre) = signo del retorno medio del resto-del-dia de los vecinos.
  - EXPLORACION: leave-one-out dentro de las 170 (el dia nunca es su propio vecino).
  - RESERVA: se predice cada dia de reserva con vecinos SOLO de exploracion (out-of-sample puro).
  - Baseline: deriva del SPY (siempre CALL) — hay que BATIRLA, no solo pasar de 50%.
  - Version filtrada por CONFIANZA: operar solo cuando los vecinos concuerdan (>=umbral).

Uso: python analisis/analog_dias.py
Salida: investigacion/analog_dias.txt
"""
import os, sqlite3, sys, math
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = "historico_spy.db"
N_EXPLORA = 170
OUT = []
def p(s=""):
    print(s); OUT.append(s)


def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dias = {}
    for f, h, o, hi, lo, cl, v in c.execute(
            "select fecha,hora,open,high,low,close,volume from bars_historico order by fecha,hora"):
        dias.setdefault(f, []).append(cl)
    c.close()
    orden = [f for f in sorted(dias) if len(dias[f]) >= 300]   # dias completos
    return orden, {f: dias[f] for f in orden}


def forma_inicio(closes, M):
    """vector z-scoreado del camino de los primeros M minutos (retornos vs primer close)."""
    op = closes[0]
    path = [(closes[t] - op) for t in range(1, M + 1)]
    mu = sum(path) / len(path)
    sd = (sum((x - mu) ** 2 for x in path) / len(path)) ** 0.5 or 1e-9
    return [(x - mu) / sd for x in path]


def resto_dia(closes, M):
    """retorno del resto del dia: de minuto M al cierre (puntos SPY)."""
    return closes[-1] - closes[M]


def dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def evalua(orden_pred, feats, resto, orden_vecinos, k, conf=None):
    """Predice cada dia de orden_pred usando vecinos de orden_vecinos.
    Devuelve (acc, n, acc_conf, n_conf, media_fav_conf)."""
    aciertos = 0; n = 0
    aciertos_c = 0; n_c = 0; fav_c = []
    for d in orden_pred:
        cand = [(dist(feats[d], feats[e]), e) for e in orden_vecinos if e != d]
        cand.sort()
        vec = cand[:k]
        signos = [1 if resto[e] > 0 else -1 for _, e in vec]
        up = sum(1 for s in signos if s > 0)
        pred = 1 if up >= (k - up) else -1
        real = 1 if resto[d] > 0 else -1
        n += 1
        if pred == real:
            aciertos += 1
        # version filtrada por confianza
        acuerdo = max(up, k - up) / k
        if conf is not None and acuerdo >= conf:
            n_c += 1
            if pred == real:
                aciertos_c += 1
            fav_c.append(resto[d] if pred == real else -abs(resto[d]) if False else (resto[d] if pred > 0 else -resto[d]))
    acc = 100 * aciertos / n if n else 0
    acc_c = 100 * aciertos_c / n_c if n_c else 0
    mf = (sum(fav_c) / len(fav_c)) if fav_c else 0.0
    return acc, n, acc_c, n_c, mf


def main():
    orden, dias = carga()
    expl = orden[:N_EXPLORA]
    resv = orden[N_EXPLORA:]
    p("=" * 92)
    p(f"ANALOGIA k-NN sobre forma del inicio — expl={len(expl)} dias, reserva={len(resv)} dias")
    p("=" * 92)

    # baseline de deriva: fraccion de dias que suben (resto del dia > 0)
    for etq, oo in (("exploracion", expl), ("reserva", resv)):
        up = sum(1 for d in oo if (dias[d][-1] - dias[d][len(dias[d]) // 2]) > 0)
        p(f"  baseline deriva ({etq}): dias que suben en la 2a mitad = {100*up/len(oo):.1f}%")

    p("\n  M=min de inicio | k=vecinos | acc=acierto direccion del resto del dia")
    p("  (acc_conf = solo dias con acuerdo de vecinos >= 70%)")
    p("  " + "-" * 84)
    for M in (15, 30, 60):
        feats_all = {d: forma_inicio(dias[d], M) for d in orden}
        resto_all = {d: resto_dia(dias[d], M) for d in orden}
        for k in (10, 20, 40):
            # EXPLORACION: leave-one-out dentro de expl
            acc, n, accc, nc, mfc = evalua(expl, feats_all, resto_all, expl, k, conf=0.70)
            # RESERVA: vecinos solo de exploracion (out-of-sample)
            accr, nr, accrc, nrc, mfr = evalua(resv, feats_all, resto_all, expl, k, conf=0.70)
            p(f"  M={M:3d} k={k:3d} | EXPL acc={acc:5.1f}% (n={n})  conf70 acc={accc:5.1f}% (n={nc}) "
              f"| RESERVA acc={accr:5.1f}% (n={nr})  conf70 acc={accrc:5.1f}% (n={nrc})")

    p("\n" + "=" * 92)
    p("COMO LEERLO:")
    p("  - Si la RESERVA no bate claramente al baseline de deriva, la analogia no aporta.")
    p("  - Para opciones 0DTE el liston sigue siendo ~56.7% de acierto direccional.")
    p("  - acc de exploracion ALTA + reserva ~50% = sobreajuste (encontro parecidos por azar).")
    p("=" * 92)

    os.makedirs("investigacion", exist_ok=True)
    with open(os.path.join("investigacion", "analog_dias.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print(f"\nsalida en: {os.path.abspath(os.path.join('investigacion','analog_dias.txt'))}")


if __name__ == "__main__":
    main()
