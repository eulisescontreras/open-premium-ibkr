# -*- coding: utf-8 -*-
"""Las 6 entradas del sistema (MANUAL §3.2, PDF §51/§10.4). Compartido backtest+vivo.
bars = [(hora 'HH:MM', high, low, close)] de 1 min, DESDE LAS 04:00 (premarket incluido).
Devuelven [(hora, 'C'|'P')] (reversion salvo gap_fade). Cada senal se persiste en `senales`.

FUENTES:
  A) ST-3       -> core/supertrend.flips_st3 (equivalencia verificada, cr_supertrend)
  B) ORB        -> orb_en, CODIGO EXACTO del PDF §10.4 (rango_min=0.40, anclas 09:40 y 11:00).
                   OJO: analisis/orb_senal.py es la version VIEJA (premium sintetico, 0.75, 1 ancla);
                   el sistema validado (premium real) usa 0.40 y 2 anclas. cr_entradas valida la
                   MECANICA (orb_en con 0.75 y ancla 09:40 == orb_senal con 0.75).
  C-F) pm_rev/gap_fade/v1/ayer_rev -> NUEVAS. El doc las describe (PDF §51) pero NO da codigo.
       Las decisiones de implementacion marcadas [DEC] las juzga el motor de backtest por su
       APORTE esperado (v1 +8293, gap_fade +7621, pm_rev +7288, ayer_rev +5619). Si no lo
       reproduce, ajustar aqui (flujo cold-run -> fix, R8).
OBLIGATORIO: antes de modificar, leer el plan aprobado y correr cr_entradas.py + el motor.
"""
from sys2.core.supertrend import mm


# ─────────────────────────────── B · ORB (PDF §10.4) ───────────────────────────────
def orb_en(bars, ancla, largo=10, ventana=5, rango_min=0.40):
    """Un ORB para una ancla ('09:40' o '11:00'). Rango = high/low de los `largo` min
    previos al ancla (solo RTH); disparo por CIERRE fuera del rango en [ancla, ancla+ventana);
    REVERSION (rompe arriba->PUT, abajo->CALL). Codigo exacto del PDF §10.4."""
    a = mm(ancla)
    ini = [(h, hi, lo, cl) for h, hi, lo, cl in bars if a - largo <= mm(h) < a]
    if len(ini) < largo - 2:
        return []
    hi = max(x[1] for x in ini)
    lo = min(x[2] for x in ini)
    if (hi - lo) < rango_min:
        return []
    for h, H, L, C in bars:
        if not (a <= mm(h) < a + ventana):
            continue
        if C > hi:
            return [(h, "P")]           # rompe ARRIBA -> PUT (reversion)
        if C < lo:
            return [(h, "C")]           # rompe ABAJO  -> CALL (reversion)
    return []


def orb(bars, anclas=("09:40", "11:00"), rango_min=0.40):
    """ORB del sistema: aplica orb_en a las dos anclas. Devuelve todas las senales."""
    out = []
    for a in anclas:
        out += orb_en(bars, a, rango_min=rango_min)
    return out


# ─────────────────────────── C · pm_rev (rompe premarket) ──────────────────────────
def pm_rev(bars, fin_pm="09:30", disparo_hasta="11:00"):
    """Rompe el rango del PREMARKET (04:00-09:29) -> REVERSION.
    [DEC] rango = high/low de barras con hora < fin_pm (04:00-09:29).
    [DEC] disparo = primer CIERRE fuera del rango en [09:30, disparo_hasta). Una sola senal."""
    pm = [(h, hi, lo, cl) for h, hi, lo, cl in bars if h < fin_pm]
    if not pm:
        return []
    hi = max(x[1] for x in pm)
    lo = min(x[2] for x in pm)
    for h, H, L, C in bars:
        if h < fin_pm or h >= disparo_hasta:
            continue
        if C > hi:
            return [(h, "P")]
        if C < lo:
            return [(h, "C")]
    return []


# ─────────────────────────── D · gap_fade (cerrar el gap) ──────────────────────────
def gap_fade(bars, cierre_ayer, gap_min=0.40, entrada="09:33"):
    """Gap de apertura >= gap_min -> operar A FAVOR de cerrarlo (abre ARRIBA de ayer -> PUT,
    abajo -> CALL). NO es reversion pura: opera hacia el cierre de ayer.
    [DEC] gap = open(09:30) - cierre_ayer. [DEC] entrada FIJA al 4o minuto (09:33)."""
    if cierre_ayer is None:
        return []
    ap = next((cl for h, hi, lo, cl in bars if h == "09:30"
               for cl in [_open_de(bars, "09:30")]), None)
    op = _open_de(bars, "09:30")
    if op is None:
        return []
    gap = op - cierre_ayer
    if abs(gap) < gap_min:
        return []
    # abre por ENCIMA de ayer (gap>0) -> esperar que BAJE a cerrarlo -> PUT
    lado = "P" if gap > 0 else "C"
    return [(entrada, lado)] if _hay_barra(bars, entrada) else []


# ──────────────────────── E · v1 (rompe 1a vela de 5 min) ──────────────────────────
def v1(bars, ini="09:30", fin="09:35", rango_min=0.30, disparo_hasta="11:00"):
    """Rompe el rango de la 1a vela de 5 min (09:30-09:34) -> REVERSION.
    [DEC] rango = high/low de [09:30, 09:35). [DEC] disparo por CIERRE desde 09:35."""
    v = [(h, hi, lo, cl) for h, hi, lo, cl in bars if ini <= h < fin]
    if not v:
        return []
    hi = max(x[1] for x in v)
    lo = min(x[2] for x in v)
    if (hi - lo) < rango_min:
        return []
    for h, H, L, C in bars:
        if h < fin or h >= disparo_hasta:
            continue
        if C > hi:
            return [(h, "P")]
        if C < lo:
            return [(h, "C")]
    return []


# ───────────────────────── F · ayer_rev (rompe max/min ayer) ───────────────────────
def ayer_rev(bars, max_ayer, min_ayer, ini="09:30", disparo_hasta="15:40"):
    """Rompe el maximo/minimo de AYER -> REVERSION.
    [DEC] disparo = primer CIERRE fuera de [min_ayer, max_ayer] desde 09:30."""
    if max_ayer is None or min_ayer is None:
        return []
    for h, H, L, C in bars:
        if h < ini or h >= disparo_hasta:
            continue
        if C > max_ayer:
            return [(h, "P")]
        if C < min_ayer:
            return [(h, "C")]
    return []


# ─────────────────────────────── fusion + descarte ─────────────────────────────────
def descartar_cerca_orb(senales_apertura, senales_orb, min_dist=5):
    """C-F se descartan si caen a < min_dist minutos de una senal del ORB (MANUAL §3.2)."""
    horas_orb = [mm(h) for h, _ in senales_orb]
    out = []
    for h, d in senales_apertura:
        if any(abs(mm(h) - o) < min_dist for o in horas_orb):
            continue
        out.append((h, d))
    return out


# ─────────────────────────────────── helpers ───────────────────────────────────────
def _open_de(bars, hora):
    """close de la barra 'hora' (proxy del precio de apertura de RTH; en 1-min el
    close de 09:30 es el nivel de apertura efectivo tras el primer minuto)."""
    for h, hi, lo, cl in bars:
        if h == hora:
            return cl
    return None


def _hay_barra(bars, hora):
    return any(h == hora for h, _, _, _ in bars)
