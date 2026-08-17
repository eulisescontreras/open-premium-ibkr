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


# ─────────────── C-F · aperturas (pm_rev/v1/gap_fade/ayer_rev) — VERBATIM ───────────────
def senales_apertura(bars, prev_hi, prev_lo, prev_cl, modo):
    """Generadores alternativos de apertura (C-F). Devuelve [(hora, 'C'|'P')] (a lo sumo una).
    ⚠️ VERBATIM del motor validado (agente, 2026-08-16) — reemplaza las versiones [DEC] previas.
    CLAVE: las aperturas SOLO miran los primeros 30 min (rth = '09:30' <= h < '10:00'); la
    ruptura se evalua por CIERRE (B[h][2]); pm_hi/pm_lo usan hi/lo del premarket.
      pm_rev  : rompe rango premarket -> REVERSION.   pm_seg: rompe premarket -> SEGUIR.
      ayer_rev: rompe max/min de AYER -> REVERSION (prev_hi/prev_lo).
      gap_fade: si |open - cierre_ayer| >= 0.40 -> dispara en rth[3] (4a barra), fade del gap.
      v1      : rompe rango de la 1a vela de 5 min (>=0.30) desde 09:35 -> REVERSION.
    prev_hi/prev_lo/prev_cl = max_ayer / min_ayer / cierre_ayer."""
    B = {h: (hi, lo, cl) for h, hi, lo, cl in bars}
    hs = sorted(B)
    pm = [h for h in hs if h < '09:30']
    if not pm:
        return []
    pm_hi = max(B[h][0] for h in pm)
    pm_lo = min(B[h][1] for h in pm)
    rth = [h for h in hs if '09:30' <= h < '10:00']
    if len(rth) < 20:
        return []
    op = B[rth[0]][2]
    if modo == 'pm_rev':
        for h in rth:
            if B[h][2] > pm_hi:
                return [(h, 'P')]
            if B[h][2] < pm_lo:
                return [(h, 'C')]
    elif modo == 'pm_seg':
        for h in rth:
            if B[h][2] > pm_hi:
                return [(h, 'C')]
            if B[h][2] < pm_lo:
                return [(h, 'P')]
    elif modo == 'ayer_rev':
        if prev_hi is None:
            return []
        for h in rth:
            if B[h][2] > prev_hi:
                return [(h, 'P')]
            if B[h][2] < prev_lo:
                return [(h, 'C')]
    elif modo == 'gap_fade':
        if prev_cl is None:
            return []
        g = op - prev_cl
        if abs(g) < 0.4:
            return []
        return [(rth[3], 'P' if g > 0 else 'C')]
    elif modo == 'v1':
        p5 = [h for h in rth if h < '09:35']
        if len(p5) < 4:
            return []
        h5 = max(B[h][0] for h in p5)
        l5 = min(B[h][1] for h in p5)
        if h5 - l5 < 0.30:
            return []
        for h in rth:
            if h < '09:35':
                continue
            if B[h][2] > h5:
                return [(h, 'P')]
            if B[h][2] < l5:
                return [(h, 'C')]
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
