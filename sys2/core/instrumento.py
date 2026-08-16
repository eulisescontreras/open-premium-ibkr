# -*- coding: utf-8 -*-
"""INSTRUMENTO — selección del contrato: vertical de débito 4pts (larga ITM profundo, corta
+ANCHO OTM, débito 20-320$) con fallback a SINGLE (ITM más profundo que quepa en el tope).
Transcripción VERBATIM del motor validado (agente, 2026-08-16), salvo `elegir` (ver nota).

Interfaz cadena: cands = [(k, v)] con v[0]=mid/precio, v[1:]=resto (vol, oi, ...).
`suelo` aplica el piso intrínseco (corrección §20 B_suelo, la que da +70.769$ vs +40.638$).
OBLIGATORIO: antes de modificar, leer el plan/ESTADO y correr el motor (cr_motor).
"""


def suelo(k, v, S, rt):
    """Piso intrínseco: acota el precio por abajo al valor intrínseco (§20). VERBATIM."""
    intr = max(0.0, (S - k) if rt == 'C' else (k - S))
    return (max(v[0], intr),) + tuple(v[1:])


def elegir_vert(cands, S, h, rt, tope, ancho):
    """Vertical de débito: larga = ITM más profundo; corta = +ancho OTM exacto; débito
    20<=deb<=tope. Devuelve (k_larga, precio_larga, k_corta, precio_corta) o None. VERBATIM."""
    cs = sorted(cands, key=lambda x: -((S - x[0]) if rt == 'C' else (x[0] - S)))
    for kl, vl in cs:
        mny = (S - kl) if rt == 'C' else (kl - S)
        if mny < 0.5:
            continue
        ks_obj = kl + ancho if rt == 'C' else kl - ancho
        cand_s = [(k, v) for k, v in cands if abs(k - ks_obj) < 0.01]
        if not cand_s:
            continue
        ksh, vsh = cand_s[0]
        deb = (vl[0] - vsh[0]) * 100
        if 20 <= deb <= tope:
            return (kl, vl[0], ksh, vsh[0])
    return None


def elegir(cands, S, h, rt, modo, tope):
    """SINGLE (modo presupuesto): el ITM más profundo cuyo débito quepa en el tope.
    ⚠️ RECONSTRUIDO de la nota del agente ('filtra v[0]*100<=tope y devuelve
    max(c, key=lambda x: x[1][0])'), no verbatim literal — validar con cr_motor; si el P&L
    no cuadra, pedir el verbatim exacto de `elegir` (y el valor de `modo`)."""
    c = [(k, v) for k, v in cands if v[0] * 100 <= tope]
    if not c:
        return None
    return max(c, key=lambda x: x[1][0])
