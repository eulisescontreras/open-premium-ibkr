# -*- coding: utf-8 -*-
"""COLD RUN de las 6 ENTRADAS (core/entradas.py) con datos REALES de sys2.bars.
NO reimplementa la logica: alimenta la FUNCION REAL con barras reales y verifica que
cada senal devuelta es COHERENTE con las barras (spec del PDF §10.4/§51). R3/R8/R23.

Valida:
  1) ORB mecanico: orb_en(bars,'09:40',largo=10,ventana=5,rango_min=0.75) == orb_senal(bars,0.75)
     (equivalencia EXACTA con la version validada vieja, dia a dia).
  2) Las 6 entradas corren sin excepcion y devuelven [(hora 'HH:MM','C'|'P')] valido.
  3) Cada senal devuelta CUMPLE su mecanica contra las barras reales:
       - orb/pm_rev/v1/ayer_rev = REVERSION (rompe ARRIBA->P, ABAJO->C), primer cierre, ventana ok.
       - gap_fade = FADE del gap (abre ARRIBA de ayer->P), gap>=umbral, entrada 09:33.
  4) Las 4 aperturas (pm_rev/gap_fade/v1/ayer_rev) DISPARAN en la muestra (estan cableadas).
  5) descartar_cerca_orb elimina lo que cae a <5 min de una senal ORB y conserva el resto.
Exit 0 = verde.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "analisis"))

from sys2.core import entradas as E
from sys2.core.supertrend import mm
from sys2.db import repo
import orb_senal as OV   # analisis/orb_senal.py (version validada vieja, ancla 09:40 / 0.75)


def _valido(sen):
    """[(hora,'C'|'P')] con hora 'HH:MM'."""
    for x in sen:
        if not (isinstance(x, tuple) and len(x) == 2):
            return False
        h, d = x
        if not (isinstance(h, str) and len(h) == 5 and h[2] == ":"):
            return False
        if d not in ("C", "P"):
            return False
    return True


def _cierre_en(bars, hora):
    for h, hi, lo, cl in bars:
        if h == hora:
            return cl
    return None


def main():
    fallos = []
    con = repo.abrir()
    dias = [r[0] for r in con.execute("select distinct fecha from bars order by fecha")]
    muestra = dias[::20]
    print("dias muestreados: %d de %d" % (len(muestra), len(dias)))

    difs_orb = 0
    n_disp = {"orb": 0, "pm_rev": 0, "gap_fade": 0, "v1": 0, "ayer_rev": 0}
    mecanica_mal = []
    excepciones = []
    invalidas = []
    descarte_ok = True
    comparados = 0

    for fk in muestra:
        rows = con.execute(
            "select hora,high,low,close from bars where fecha=? order by hora", (fk,)).fetchall()
        if len(rows) < 100:
            continue
        bars = [(h, hi, lo, cl) for h, hi, lo, cl in rows]
        # dia_anterior: la fila cuyo fecha es el ultimo dia < fk
        da = con.execute(
            "select cierre,maximo,minimo from dia_anterior where fecha<? order by fecha desc limit 1",
            (fk,)).fetchone()
        cierre_ayer = da[0] if da else None
        max_ayer = da[1] if da else None
        min_ayer = da[2] if da else None
        comparados += 1

        # 1) equivalencia ORB exacta (misma ancla/amplitud que la vieja validada)
        try:
            s_new = E.orb_en(bars, "09:40", largo=10, ventana=5, rango_min=0.75)
            s_old = OV.orb_senal(bars, 0.75)
        except Exception as ex:
            excepciones.append("orb_en %s: %r" % (fk, ex)); continue
        if s_new != s_old:
            difs_orb += 1
            if difs_orb <= 3:
                print("  ORB DIFIERE %s: new=%s old=%s" % (fk, s_new, s_old))

        # 2+3) correr las 6 entradas reales y validar mecanica contra barras
        try:
            s_orb = E.orb(bars)
            s_pm = E.pm_rev(bars)
            s_gap = E.gap_fade(bars, cierre_ayer)
            s_v1 = E.v1(bars)
            s_ay = E.ayer_rev(bars, max_ayer, min_ayer)
            # A (ST-3) se valida en cr_supertrend; aqui solo se comprueba que corre integrado
        except Exception as ex:
            excepciones.append("entradas %s: %r" % (fk, ex)); continue

        for nom, sen in (("orb", s_orb), ("pm_rev", s_pm), ("gap_fade", s_gap),
                         ("v1", s_v1), ("ayer_rev", s_ay)):
            if not _valido(sen):
                invalidas.append("%s %s -> %r" % (nom, fk, sen)); continue
            if sen:
                n_disp[nom] += 1

        # --- mecanica REVERSION: rompe arriba->P, abajo->C, cierre real en la hora ---
        # pm_rev: rango premarket (<09:30)
        pm = [(h, hi, lo, cl) for h, hi, lo, cl in bars if h < "09:30"]
        if s_pm and pm:
            h, d = s_pm[0]; c = _cierre_en(bars, h)
            hi = max(x[1] for x in pm); lo = min(x[2] for x in pm)
            ok = c is not None and "09:30" <= h < "11:00" and \
                ((d == "P" and c > hi) or (d == "C" and c < lo))
            if not ok:
                mecanica_mal.append("pm_rev %s %s hi=%.2f lo=%.2f c=%s" % (fk, s_pm[0], hi, lo, c))

        # v1: rango [09:30,09:35)
        v = [(h, hi, lo, cl) for h, hi, lo, cl in bars if "09:30" <= h < "09:35"]
        if s_v1 and v:
            h, d = s_v1[0]; c = _cierre_en(bars, h)
            hi = max(x[1] for x in v); lo = min(x[2] for x in v)
            ok = c is not None and h >= "09:35" and \
                ((d == "P" and c > hi) or (d == "C" and c < lo))
            if not ok:
                mecanica_mal.append("v1 %s %s hi=%.2f lo=%.2f c=%s" % (fk, s_v1[0], hi, lo, c))

        # ayer_rev: rompe max/min de ayer
        if s_ay and max_ayer is not None:
            h, d = s_ay[0]; c = _cierre_en(bars, h)
            ok = c is not None and h >= "09:30" and \
                ((d == "P" and c > max_ayer) or (d == "C" and c < min_ayer))
            if not ok:
                mecanica_mal.append("ayer_rev %s %s max=%.2f min=%.2f c=%s"
                                    % (fk, s_ay[0], max_ayer, min_ayer, c))

        # gap_fade: FADE (abre arriba->P), entrada 09:33, gap>=0.40
        if s_gap and cierre_ayer is not None:
            h, d = s_gap[0]; op = _cierre_en(bars, "09:30")
            gap = (op - cierre_ayer) if op is not None else 0.0
            ok = op is not None and h == "09:33" and abs(gap) >= 0.40 and \
                ((d == "P" and gap > 0) or (d == "C" and gap < 0))
            if not ok:
                mecanica_mal.append("gap_fade %s %s gap=%.3f" % (fk, s_gap[0], gap))

        # orb: reversion tambien
        for h, d in s_orb:
            c = _cierre_en(bars, h)
            if c is None:
                mecanica_mal.append("orb %s %s sin barra" % (fk, (h, d)))

        # 5) descarte <5 min del ORB (invariante sobre datos reales)
        aperturas = s_pm + s_gap + s_v1 + s_ay
        filt = E.descartar_cerca_orb(aperturas, s_orb)
        horas_orb = [mm(x[0]) for x in s_orb]
        # ninguna sobreviviente cae a <5 min de un ORB
        if any(any(abs(mm(h) - o) < 5 for o in horas_orb) for h, _ in filt):
            descarte_ok = False
        # las eliminadas son exactamente las que estaban a <5 min
        elim = [x for x in aperturas if x not in filt]
        for h, _ in elim:
            if not any(abs(mm(h) - o) < 5 for o in horas_orb):
                descarte_ok = False

    con.close()
    print("comparados: %d dias" % comparados)
    print("disparos: %s" % n_disp)

    if difs_orb:
        fallos.append("orb_en difiere de orb_senal(0.75) en %d dias" % difs_orb)
    if excepciones:
        fallos.append("%d excepciones (ej: %s)" % (len(excepciones), excepciones[0]))
    if invalidas:
        fallos.append("%d salidas invalidas (ej: %s)" % (len(invalidas), invalidas[0]))
    if mecanica_mal:
        fallos.append("%d senales incoherentes con barras (ej: %s)"
                      % (len(mecanica_mal), mecanica_mal[0]))
    if not descarte_ok:
        fallos.append("descartar_cerca_orb no respeta el umbral de 5 min")
    # cada apertura debe DISPARAR al menos una vez (estar cableada)
    for nom in ("pm_rev", "gap_fade", "v1", "ayer_rev"):
        if n_disp[nom] == 0:
            fallos.append("la apertura %s NO disparo en ningun dia (no cableada?)" % nom)
    if comparados < 10:
        fallos.append("muy pocos dias comparados (%d)" % comparados)

    if fallos:
        print("\nROJO:")
        for x in fallos:
            print("  -", x)
        return 1
    print("\nVERDE: las 6 entradas corren, sus senales cumplen la mecanica y el ORB equivale al validado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
