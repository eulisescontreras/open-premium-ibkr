# -*- coding: utf-8 -*-
"""BARRIDO DE EXPLORACION DIRECCIONAL DEL SPY  (pre-registrado, ver investigacion/PREREGISTRO_BARRIDO_SPY.md)

Corre SOLO sobre las 170 sesiones de EXPLORACION (primeras por fecha). Las 85 de RESERVA
NO se cargan aqui (intocables hasta congelar una regla).

Metrica unica:  EV_op($) = 85*media(fav_con_signo) - 2.22   ;  equilibrio media(fav) >= 0.026
Familias: F1 reversion, F2 continuacion, F3 reversion x tercil de rango15, F4 acuerdo SMA5&SMA21,
          F5 estructura de sesion (gap, rango primeros 30min, dia de semana).

Uso:
    python analisis/barrido_exploracion.py            # calibracion + barrido exploracion
    python analisis/barrido_exploracion.py calib      # solo la calibracion (255 sesiones)

Salida: investigacion/barrido_exploracion.txt
"""
import os
import random
import sqlite3
import statistics as st
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = "historico_spy.db"
DELTA = 85.0          # $/punto SPY (ITM3, tope 320)
COSTE = 2.22          # comision 1.72 + theta 8min 0.50
EQUILIBRIO = 0.026    # media(fav) para EV=0
N_EXPLORA = 170       # primeras 170 sesiones = exploracion
RETRASO = 1

SALIDA = os.path.join("investigacion", "barrido_exploracion.txt")
OUT = []
def p(s=""):
    print(s); OUT.append(s)

def mm(h):
    return int(h[:2]) * 60 + int(h[3:5])


# ----------------- carga -----------------
def carga(solo_exploracion=True):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dias = {}
    for f, h, o, hi, lo, cl, v in c.execute(
            "select fecha,hora,open,high,low,close,volume from bars_historico order by fecha,hora"):
        dias.setdefault(f, []).append((h, o, hi, lo, cl, v))
    c.close()
    orden = sorted(dias)
    if solo_exploracion:
        orden = orden[:N_EXPLORA]
    return orden, {f: dias[f] for f in orden}


# ----------------- señal base (precio tipico y SMA expansiva, igual que valida_media) -----------------
def serie_media(barras, W):
    """[(hora, close, media, dist, minuto)] con media = SMA(W) expansiva del precio tipico."""
    out = []
    tp = []
    for h, o, hi, lo, cl, v in barras:
        tp.append((hi + lo + cl) / 3.0)
        med = sum(tp[-W:]) / min(W, len(tp))
        out.append((h, cl, med, cl - med, mm(h)))
    return out


def rango15(barras):
    """rango de los ultimos 15 min en cada minuto (max high - min low)."""
    his = [b[2] for b in barras]; los = [b[3] for b in barras]
    r = []
    for i in range(len(barras)):
        a = max(0, i - 14)
        r.append(max(his[a:i + 1]) - min(los[a:i + 1]))
    return r


# ----------------- generador de operaciones (no solapadas, retraso 1) -----------------
def ops_celda(barras, W, umbral, H, familia, cond=None):
    """cond(i) -> bool: filtro extra al minuto de entrada (F3/F4). Devuelve [(minuto, fav)]."""
    serie = serie_media(barras, W)
    horas = [x[0] for x in serie]
    ops = []
    i = 0
    n = len(serie)
    while i < n:
        h = horas[i]
        if h >= "15:40":
            break
        j = i - RETRASO
        if j < 0:
            i += 1; continue
        dd = serie[j][3]
        if abs(dd) < umbral:
            i += 1; continue
        if cond is not None and not cond(i, serie):
            i += 1; continue
        # lado
        if familia == "rev":
            lado = "P" if dd > 0 else "C"      # precio ARRIBA de media -> baja (PUT); ABAJO -> sube (CALL)
        else:  # "cont"
            lado = "C" if dd > 0 else "P"
        fin = [k for k in range(i, n) if serie[k][4] >= serie[i][4] + H]
        if not fin:
            break
        k = fin[0]
        ds = serie[k][1] - serie[i][1]
        fav = ds if lado == "C" else -ds
        ops.append((serie[i][4], fav))
        i = k
    return ops


def agrega(favs):
    n = len(favs)
    if n == 0:
        return {"n": 0, "media_fav": 0.0, "ev": -COSTE, "acc": 0.0}
    mf = sum(favs) / n
    return {"n": n, "media_fav": mf, "ev": DELTA * mf - COSTE,
            "acc": sum(1 for x in favs if x > 0) / n}


# ----------------- barrido de una familia sobre las sesiones -----------------
GRID_W = [3, 5, 8, 13, 21]
GRID_U = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
GRID_H = [3, 5, 8, 12, 20, 30]


def barre_grid(dias_orden, dias, familia, cond_factory=None, etiqueta=""):
    """Devuelve dict {(W,u,H): {favs_por_sesion, stats}}."""
    celdas = {}
    for W in GRID_W:
        for u in GRID_U:
            for H in GRID_H:
                por_sesion = []
                todos = []
                for f in dias_orden:
                    cond = cond_factory(dias[f]) if cond_factory else None
                    o = ops_celda(dias[f], W, u, H, familia, cond)
                    favs = [x[1] for x in o]
                    por_sesion.append(favs)
                    todos.extend(favs)
                celdas[(W, u, H)] = {"por_sesion": por_sesion, **agrega(todos)}
    return celdas


# ----------------- controles -----------------
def estabilidad_4bloques(por_sesion):
    """positiva (EV>0) en cuantos de 4 bloques cronologicos."""
    nb = len(por_sesion) // 4
    if nb == 0:
        return 0
    pos = 0
    for b in range(4):
        seg = por_sesion[b * nb:(b + 1) * nb] if b < 3 else por_sesion[b * nb:]
        favs = [x for s in seg for x in s]
        if favs and (DELTA * (sum(favs) / len(favs)) - COSTE) > 0:
            pos += 1
    return pos


def region_ok(celdas, W, u, H):
    """las 4 vecinas (u+-1 paso, H+-1 paso) con EV>0."""
    iu = GRID_U.index(u); ih = GRID_H.index(H)
    vecinas = []
    for du, dh in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        ju, jh = iu + du, ih + dh
        if 0 <= ju < len(GRID_U) and 0 <= jh < len(GRID_H):
            vecinas.append((W, GRID_U[ju], GRID_H[jh]))
    if not vecinas:
        return False
    return all(celdas[v]["ev"] > 0 for v in vecinas)


def control_azar(por_sesion, ev_obs, seeds=300):
    """misma exposicion, direccion al azar por operacion. p = fraccion de semillas con EV >= observado."""
    favs_abs = [[abs(x) for x in s] for s in por_sesion]
    todos_n = sum(len(s) for s in favs_abs)
    if todos_n == 0:
        return 1.0
    sup = 0
    for sd in range(seeds):
        rnd = random.Random(sd)
        acc = []
        for s in favs_abs:
            for a in s:
                acc.append(a if rnd.random() < 0.5 else -a)
        ev = DELTA * (sum(acc) / len(acc)) - COSTE
        if ev >= ev_obs:
            sup += 1
    return sup / seeds


def t2_top5(por_sesion):
    """EV quitando las 5 mejores sesiones (por suma de fav)."""
    idx = sorted(range(len(por_sesion)), key=lambda i: sum(por_sesion[i]), reverse=True)[:5]
    quitar = set(idx)
    favs = [x for i, s in enumerate(por_sesion) if i not in quitar for x in s]
    if not favs:
        return -COSTE
    return DELTA * (sum(favs) / len(favs)) - COSTE


# ----------------- calibracion (Regla 8: reproducir el resultado conocido de la media) -----------------
def calibracion():
    orden, dias = carga(solo_exploracion=False)   # 255 sesiones
    todos = []
    for f in orden:
        todos.extend(x[1] for x in ops_celda(dias[f], 5, 0.20, 8, "rev"))
    s = agrega(todos)
    p("=" * 90)
    p("CALIBRACION (Regla 8 diferencial) — F1 rev W=5 u=0.20 H=8 sobre 255 sesiones")
    p(f"  esperado (valida_media): n~7664  acc~50.07%  media_fav~+0.0122  EV~-1.18")
    p(f"  obtenido:                n={s['n']}  acc={100*s['acc']:.2f}%  media_fav={s['media_fav']:+.4f}  EV={s['ev']:+.2f}")
    ok = abs(s['media_fav'] - 0.0122) < 0.002 and abs(s['n'] - 7664) <= 60
    p(f"  -> {'MOTOR VALIDADO' if ok else 'DISCREPANCIA: revisar motor antes de confiar en el barrido'}")
    p("=" * 90)
    return ok


# ----------------- main -----------------
def mejores(celdas, familia, k=8):
    top = sorted(celdas.items(), key=lambda kv: kv[1]["ev"], reverse=True)[:k]
    p(f"\n--- {familia}: mejores {k} celdas por EV (de {len(celdas)}) ---")
    p("   W  umbral horiz     n    acc%   media_fav      EV$   estab/4")
    for (W, u, H), s in top:
        estab = estabilidad_4bloques(s["por_sesion"])
        p(f"  {W:2d}  {u:5.2f}  {H:4d}  {s['n']:5d}  {100*s['acc']:5.1f}  {s['media_fav']:+.4f}   {s['ev']:+7.2f}    {estab}/4")


def evalua_congelacion(celdas, familia, resultados):
    """aplica el criterio (c) de 6 condiciones a cada celda; devuelve candidatas."""
    for (W, u, H), s in celdas.items():
        if s["ev"] < 0.50 or s["media_fav"] < 0.032 or s["n"] < 800:
            continue
        if not region_ok(celdas, W, u, H):
            continue
        estab = estabilidad_4bloques(s["por_sesion"])
        if estab < 3:
            continue
        pval = control_azar(s["por_sesion"], s["ev"])
        cumple = pval <= 0.01
        resultados.append({"familia": familia, "W": W, "u": u, "H": H, "ev": s["ev"],
                           "media_fav": s["media_fav"], "n": s["n"], "estab": estab,
                           "p_azar": pval, "congela": cumple})


def main(solo_calib=False):
    ok = calibracion()
    if solo_calib:
        return
    if not ok:
        p("\nABORTADO: la calibracion no cuadra. No se corre el barrido con un motor no validado.")
        _escribe(); return

    orden, dias = carga(solo_exploracion=True)
    p(f"\nEXPLORACION: {len(orden)} sesiones  ({orden[0]} a {orden[-1]})")
    p(f"RESERVA (intocable): sesiones {len(orden)+1}..255")

    # conteo de celdas para multiplicidad
    base = len(GRID_W) * len(GRID_U) * len(GRID_H)   # 180
    total_celdas = base * 2 + base * 3 + (len(GRID_U) * len(GRID_H)) + 4  # F1,F2,F3x3,F4,F5(~4)
    p(f"\nCELDAS TOTALES (pre-registradas): ~{total_celdas}.  FP esperados al 5% ~ {round(0.05*total_celdas)}")

    resultados = []

    # F1 reversion (linea base) + F2 continuacion
    f1 = barre_grid(orden, dias, "rev")
    mejores(f1, "F1 reversion"); evalua_congelacion(f1, "F1 reversion", resultados)
    f2 = barre_grid(orden, dias, "cont")
    mejores(f2, "F2 continuacion"); evalua_congelacion(f2, "F2 continuacion", resultados)

    # F3 reversion condicionada por tercil del rango de 15 min (relativo al dia)
    def cond_factory_tercil(tercil):
        def factory(barras):
            r = rango15(barras)
            rs = sorted(r)
            q1 = rs[len(rs) // 3]; q2 = rs[2 * len(rs) // 3]
            def cond(i, serie):
                v = r[i]
                if tercil == "bajo":  return v <= q1
                if tercil == "medio": return q1 < v <= q2
                return v > q2
            return cond
        return factory
    for terc in ("bajo", "medio", "alto"):
        f3 = barre_grid(orden, dias, "rev", cond_factory_tercil(terc), f"tercil={terc}")
        mejores(f3, f"F3 rev tercil {terc}"); evalua_congelacion(f3, f"F3 rev tercil {terc}", resultados)

    # F4 acuerdo SMA5 & SMA21 (mismo lado). grid = umbral x horizonte (W fijo=5, filtro con SMA21)
    def cond_factory_f4(barras):
        s5 = serie_media(barras, 5); s21 = serie_media(barras, 21)
        def cond(i, serie):
            d5 = s5[i][3]; d21 = s21[i][3]
            return (d5 > 0 and d21 > 0) or (d5 < 0 and d21 < 0)
        return cond
    f4 = {}
    for u in GRID_U:
        for H in GRID_H:
            por_sesion = []; todos = []
            for f in orden:
                o = ops_celda(dias[f], 5, u, H, "rev", cond_factory_f4(dias[f]))
                favs = [x[1] for x in o]; por_sesion.append(favs); todos.extend(favs)
            f4[(5, u, H)] = {"por_sesion": por_sesion, **agrega(todos)}
    mejores(f4, "F4 acuerdo SMA5&SMA21"); evalua_congelacion(f4, "F4 acuerdo SMA5&SMA21", resultados)

    # F5 estructura de sesion
    p("\n--- F5 estructura de sesion ---")
    f5_estructura(orden, dias)

    # ---- veredicto de congelacion ----
    p("\n" + "=" * 90)
    p("CANDIDATAS QUE PASAN EL CRITERIO DE CONGELACION (las 6 condiciones):")
    congeladas = [r for r in resultados if r["congela"]]
    if not congeladas:
        p("  NINGUNA. (Es el resultado mas probable — cierra la via direccional con 170 sesiones.)")
        cerca = sorted(resultados, key=lambda r: r["ev"], reverse=True)[:5] if resultados else []
        if cerca:
            p("  Las que pasaron los filtros baratos pero fallaron azar/otros (diagnostico):")
            for r in cerca:
                p(f"    {r['familia']} W={r['W']} u={r['u']} H={r['H']}  EV={r['ev']:+.2f}  media_fav={r['media_fav']:+.4f}  n={r['n']}  estab={r['estab']}/4  p_azar={r['p_azar']:.4f}")
    else:
        for r in congeladas:
            p(f"  *** {r['familia']} W={r['W']} u={r['u']} H={r['H']}  EV={r['ev']:+.2f}  media_fav={r['media_fav']:+.4f}  n={r['n']}  estab={r['estab']}/4  p_azar={r['p_azar']:.4f}")
        p("  -> CONGELAR por escrito (REGLA_CONGELADA_<fecha>.md) y recien despues correr sobre la RESERVA.")
    p("=" * 90)
    _escribe()


def f5_estructura(orden, dias):
    """gap de apertura, rango primeros 30 min, dia de semana. Medidas + tradables simples."""
    import datetime as _dt
    gaps = []; or30 = []; dow = {}
    prev_close = None
    for f in orden:
        b = dias[f]
        op = b[0][1]; cl_dia = b[-1][4]
        ret_dia = cl_dia - op
        # gap
        if prev_close is not None:
            gap = op - prev_close
            gaps.append((gap, ret_dia))
        prev_close = cl_dia
        # rango primeros 30 min y retorno del resto del dia
        b30 = b[:30]
        rng30 = max(x[2] for x in b30) - min(x[3] for x in b30)
        close30 = b[29][4] if len(b) > 29 else cl_dia
        resto = cl_dia - close30
        or30.append((rng30, resto, close30 - op))
        # dia de semana
        try:
            wd = _dt.date(int(f[:4]), int(f[5:7]), int(f[8:10])).weekday()
        except Exception:
            wd = -1
        dow.setdefault(wd, []).append(ret_dia)

    def corr(xs, ys):
        n = len(xs)
        if n < 3:
            return 0.0
        mx = sum(xs) / n; my = sum(ys) / n
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        dx = (sum((a - mx) ** 2 for a in xs)) ** 0.5; dy = (sum((b - my) ** 2 for b in ys)) ** 0.5
        return num / (dx * dy) if dx and dy else 0.0

    if gaps:
        rho = corr([g[0] for g in gaps], [g[1] for g in gaps])
        p(f"  gap apertura -> retorno del dia: rho={rho:+.3f}  (n={len(gaps)})  [>0=continuacion, <0=reversion]")
    if or30:
        rho = corr([o[0] for o in or30], [abs(o[1]) for o in or30])
        rho_dir = corr([o[2] for o in or30], [o[1] for o in or30])
        p(f"  rango 30min -> |retorno resto|: rho={rho:+.3f}   (rango grande predice movimiento grande?)")
        p(f"  dir 30min -> retorno resto:     rho={rho_dir:+.3f}   [>0=tendencia, <0=reversion]")
    nombres = {0: "Lun", 1: "Mar", 2: "Mie", 3: "Jue", 4: "Vie"}
    p("  retorno medio del dia por dia de semana (puntos SPY):")
    for wd in sorted(k for k in dow if k >= 0):
        v = dow[wd]
        p(f"    {nombres.get(wd, wd)}: media {st.mean(v):+.3f}  (n={len(v)})")
    p("  NOTA: F5 son MEDIDAS exploratorias; ninguna es tradable directa sin pasar los 6 controles.")


def _escribe():
    os.makedirs("investigacion", exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print(f"\nsalida completa en: {os.path.abspath(SALIDA)}")


def reserva():
    """UNA SOLA PASADA sobre las 85 sesiones de reserva (171..255) con la regla CONGELADA:
    F3 reversion, tercil ALTO de rango15, W=5, u=0.40, H=8.
    Criterio: EV>0 con >=400 ops -> real. Negativo -> se descarta y NO se reajusta."""
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dias = {}
    for f, h, o, hi, lo, cl, v in c.execute(
            "select fecha,hora,open,high,low,close,volume from bars_historico order by fecha,hora"):
        dias.setdefault(f, []).append((h, o, hi, lo, cl, v))
    c.close()
    orden = sorted(dias)
    reserva_orden = orden[N_EXPLORA:]      # 171..255 (INTOCADAS hasta ahora)

    def cond_factory_alto(barras):
        r = rango15(barras); rs = sorted(r); q2 = rs[2 * len(rs) // 3]
        def cond(i, serie):
            return r[i] > q2
        return cond

    todos = []
    for f in reserva_orden:
        o = ops_celda(dias[f], 5, 0.40, 8, "rev", cond_factory_alto(dias[f]))
        todos.extend(x[1] for x in o)
    s = agrega(todos)
    p("=" * 90)
    p("PRUEBA DE RESERVA (una sola pasada) — F3 rev tercil ALTO W=5 u=0.40 H=8")
    p(f"  sesiones reserva: {len(reserva_orden)}  ({reserva_orden[0]} a {reserva_orden[-1]})")
    p(f"  n_ops={s['n']}  acc={100*s['acc']:.2f}%  media_fav={s['media_fav']:+.4f}  EV={s['ev']:+.2f}$")
    real = s["ev"] > 0 and s["n"] >= 400
    p(f"  EXPLORACION daba: EV=+2.48 media_fav=+0.0553 n=1560")
    p(f"  -> {'SOBREVIVE (EV>0 y n>=400): candidata REAL' if real else 'NO SOBREVIVE: se descarta, NO se reajusta (era el falso positivo esperado)'}")
    p("=" * 90)
    with open(os.path.join('investigacion', 'reserva_resultado.txt'), 'w', encoding='utf-8') as fh:
        fh.write("\n".join(OUT))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calib":
        main(solo_calib=True)
    elif len(sys.argv) > 1 and sys.argv[1] == "reserva":
        reserva()
    else:
        main()
