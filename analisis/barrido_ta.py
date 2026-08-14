# -*- coding: utf-8 -*-
"""BARRIDO DE INDICADORES TA como señal DIRECCIONAL / de CAMBIO DE DIRECCION.

Usa ta_historico (reconstruido byte-fiel del bot) + su close. Mismo motor/metrica que
barrido_exploracion (EV_op = 85*media_fav - 2.22). Solo EXPLORACION (170 sesiones); la
RESERVA (85) queda intacta salvo que una regla pase las 6 condiciones -> una sola pasada.

Familias:
  G1 RSI reversion (sobreventa->CALL, sobrecompra->PUT)
  G2 MACD histograma: tendencia (hist>0->CALL) y reversion (invertida)
  G3 cruce EMA8/EMA21 (evento de CAMBIO de direccion): tendencia y reversion
  G4 Bollinger: reversion (toca banda->vuelve) y ruptura (rompe banda->sigue)

Uso: python analisis/barrido_ta.py
Salida: investigacion/barrido_ta.txt
"""
import os, sqlite3, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from barrido_exploracion import DELTA, COSTE, N_EXPLORA, RETRASO, mm, agrega, estabilidad_4bloques, control_azar

DB = "historico_spy.db"
GRID_H = [5, 8, 12, 20, 30]
OUT = []
def p(s=""):
    print(s); OUT.append(s)


def carga_ta():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dias = {}
    q = ("select fecha,hora,close,rsi,macd_hist,ema8,ema21,bb_up,bb_low "
         "from ta_historico order by fecha,hora")
    for row in c.execute(q):
        dias.setdefault(row[0], []).append(row[1:])   # (hora,close,rsi,macd_hist,ema8,ema21,bb_up,bb_low)
    c.close()
    orden = sorted(dias)
    return orden[:N_EXPLORA], dias


def ops(barras, H, lado_fn):
    """barras: [(hora,close,rsi,macd_hist,ema8,ema21,bb_up,bb_low)]. lado_fn(prev,cur)->'C'/'P'/None.
    No solapadas, retraso 1 (señal en j=i-1)."""
    horas = [b[0] for b in barras]; mins = [mm(h) for h in horas]; close = [b[1] for b in barras]
    res = []; i = 1; n = len(barras)
    while i < n:
        if horas[i] >= "15:40":
            break
        j = i - RETRASO
        if j < 1:
            i += 1; continue
        lado = lado_fn(barras[j - 1], barras[j])   # prev y cur para detectar cruces
        if lado is None:
            i += 1; continue
        fin = [k for k in range(i, n) if mins[k] >= mins[i] + H]
        if not fin:
            break
        k = fin[0]
        ds = close[k] - close[i]
        res.append(ds if lado == "C" else -ds)
        i = k
    return res


def barre(orden, dias, familia, lado_fn):
    por_sesion = []; todos = []
    for f in orden:
        favs = ops(dias[f], familia["H"], lado_fn)
        por_sesion.append(favs); todos.extend(favs)
    s = agrega(todos); s["por_sesion"] = por_sesion
    return s


# ---- definiciones de lado por familia (idx: 0 hora,1 close,2 rsi,3 macd_hist,4 ema8,5 ema21,6 bb_up,7 bb_low) ----
def make_rsi(lo, hi, modo):
    def f(prev, cur):
        r = cur[2]
        if r is None: return None
        if r <= lo:  return "C" if modo == "rev" else "P"   # sobreventa -> rebote (CALL) en reversion
        if r >= hi:  return "P" if modo == "rev" else "C"
        return None
    return f

def make_macd(modo):
    def f(prev, cur):
        h = cur[3]
        if h is None: return None
        base = "C" if h > 0 else "P"          # hist>0 momentum alcista
        return base if modo == "trend" else ("P" if base == "C" else "C")
    return f

def make_macd_cross(modo):
    """CAMBIO de direccion: el histograma cruza cero."""
    def f(prev, cur):
        if prev[3] is None or cur[3] is None: return None
        if prev[3] <= 0 < cur[3]:  # cruce a alcista
            return "C" if modo == "trend" else "P"
        if prev[3] >= 0 > cur[3]:  # cruce a bajista
            return "P" if modo == "trend" else "C"
        return None
    return f

def make_ema_cross(modo):
    """CAMBIO de direccion: EMA8 cruza EMA21."""
    def f(prev, cur):
        if None in (prev[4], prev[5], cur[4], cur[5]): return None
        pa = prev[4] - prev[5]; ca = cur[4] - cur[5]
        if pa <= 0 < ca:  return "C" if modo == "trend" else "P"
        if pa >= 0 > ca:  return "P" if modo == "trend" else "C"
        return None
    return f

def make_bb(modo):
    def f(prev, cur):
        c, up, lo = cur[1], cur[6], cur[7]
        if None in (up, lo): return None
        if c <= lo:  return "C" if modo == "rev" else "P"   # toca banda baja -> rebota (rev) o rompe (breakout)
        if c >= up:  return "P" if modo == "rev" else "C"
        return None
    return f


def evalua(s):
    """resumen + filtros baratos de congelacion (sin correr azar aun)."""
    estab = estabilidad_4bloques(s["por_sesion"]) if s["n"] else 0
    return estab


def main():
    orden, dias = carga_ta()
    p("=" * 90)
    p(f"BARRIDO TA (indicadores como señal direccional / de cambio) — EXPLORACION {len(orden)} sesiones")
    p(f"  ({orden[0]} a {orden[-1]})   metrica EV_op = 85*media_fav - 2.22 ; equilibrio media_fav>=0.026")
    p("=" * 90)

    celdas = []  # (nombre, H, stats)

    def reg(nombre, H, s):
        celdas.append((nombre, H, s))

    for H in GRID_H:
        # G1 RSI reversion con 3 pares de umbrales
        for lo, hi in ((30, 70), (25, 75), (20, 80)):
            reg(f"G1 RSI rev {lo}/{hi}", H, barre(orden, dias, {"H": H}, make_rsi(lo, hi, "rev")))
        # G2 MACD tendencia y reversion
        reg("G2 MACD trend", H, barre(orden, dias, {"H": H}, make_macd("trend")))
        reg("G2 MACD rev", H, barre(orden, dias, {"H": H}, make_macd("rev")))
        # G2b MACD cruce cero (cambio direccion)
        reg("G2b MACDcross trend", H, barre(orden, dias, {"H": H}, make_macd_cross("trend")))
        reg("G2b MACDcross rev", H, barre(orden, dias, {"H": H}, make_macd_cross("rev")))
        # G3 cruce EMA (cambio direccion)
        reg("G3 EMAcross trend", H, barre(orden, dias, {"H": H}, make_ema_cross("trend")))
        reg("G3 EMAcross rev", H, barre(orden, dias, {"H": H}, make_ema_cross("rev")))
        # G4 Bollinger reversion y ruptura
        reg("G4 BB rev", H, barre(orden, dias, {"H": H}, make_bb("rev")))
        reg("G4 BB breakout", H, barre(orden, dias, {"H": H}, make_bb("breakout")))

    total = len(celdas)
    p(f"\nCELDAS: {total}.  FP esperados al 5% ~ {round(0.05*total)}")

    # ranking por EV
    orden_ev = sorted(celdas, key=lambda x: x[2]["ev"], reverse=True)
    p("\n--- TODAS las celdas por EV (desc) ---")
    p("  familia                   H     n    acc%   media_fav      EV$   estab/4")
    for nombre, H, s in orden_ev:
        estab = evalua(s)
        p(f"  {nombre:24s} {H:3d}  {s['n']:5d}  {100*s['acc']:5.1f}  {s['media_fav']:+.4f}   {s['ev']:+7.2f}    {estab}/4")

    # candidatas: filtros baratos + azar
    p("\n" + "=" * 90)
    p("CANDIDATAS QUE PASAN EL CRITERIO DE CONGELACION (EV>=0.50, media_fav>=0.032, n>=800, estab>=3/4, p_azar<=0.01):")
    hay = False
    for nombre, H, s in orden_ev:
        if s["ev"] < 0.50 or s["media_fav"] < 0.032 or s["n"] < 800:
            continue
        estab = estabilidad_4bloques(s["por_sesion"])
        if estab < 3:
            continue
        pval = control_azar(s["por_sesion"], s["ev"])
        if pval <= 0.01:
            hay = True
            p(f"  *** {nombre} H={H}  EV={s['ev']:+.2f}  media_fav={s['media_fav']:+.4f}  n={s['n']}  estab={estab}/4  p_azar={pval:.4f}")
        else:
            p(f"  (casi) {nombre} H={H}  EV={s['ev']:+.2f} n={s['n']} estab={estab}/4 pero p_azar={pval:.4f} > 0.01")
    if not hay:
        p("  NINGUNA pasa las 6 condiciones.")
    p("=" * 90)

    os.makedirs("investigacion", exist_ok=True)
    with open(os.path.join("investigacion", "barrido_ta.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print(f"\nsalida en: {os.path.abspath(os.path.join('investigacion','barrido_ta.txt'))}")


if __name__ == "__main__":
    main()
