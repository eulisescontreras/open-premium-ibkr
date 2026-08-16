# -*- coding: utf-8 -*-
"""Greeks Black-Scholes para el BACKTEST (solo). Invierte el PRECIO REAL de massive
-> IV implicita (preserva la sonrisa/skew real) -> delta/gamma/theta/vega. NUNCA fija
precios: el P&L del backtest usa el precio REAL de massive; estos greeks solo alimentan
las decisiones (rodado delta 0.35, skew, ratio_otm, iv_atm).

FUNDAMENTO (PDF §57 + H3):
  - BS con IV PLANA da 60% de error de P&L -> PROHIBIDO usar BS para precio. Aqui la IV
    se OBTIENE del precio real (por contrato/minuto), asi que la sonrisa queda dentro.
  - H3 (pag 70): el sistema es INSENSIBLE a +-0.10 de delta (0 decisiones cambian en
    25.034 obs). Rango real de delta comprada: p5 0.544 | mediana 0.704 | p95 0.893.
    Por eso una delta BS-invertida es aceptable para las reglas.

FRONTERA (decision usuario 2026-08-16): esto vive en sys2/backtest/, corre sobre massive.
EN VIVO los greeks los da IBKR (captura.py), NUNCA este modulo. R7/R9/R13.
OBLIGATORIO: antes de modificar, leer el plan aprobado, ESTADO.md y correr cr_greeks_bs.py.
"""
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
MS_ANIO = 365.0 * 24 * 3600 * 1000.0
_T_MIN = 60_000.0 / MS_ANIO            # suelo: 1 minuto en anios (evita T=0)
_OCC = re.compile(r"^O:([A-Z]+)(\d{6})([CP])(\d{8})$")


# ─────────────────────────────── parseo OCC ───────────────────────────────
def parse_occ(ticker):
    """'O:SPY240815C00547000' -> ('2024-08-15', 'C', 547.0). None si no matchea."""
    m = _OCC.match(ticker)
    if not m:
        return None
    _sub, ymd, right, strike8 = m.groups()
    expiry = "20%s-%s-%s" % (ymd[0:2], ymd[2:4], ymd[4:6])
    strike = int(strike8) / 1000.0
    return expiry, right, strike


def t_years(ts_ms, expiry_ymd, cierre_hhmm="16:00"):
    """Tiempo a vencimiento en anios (calendario) desde el instante ts_ms (epoch UTC ms)
    hasta el cierre (16:00 ET por defecto) del dia de expiry. Usa zoneinfo (NO offset
    fijo — trampa §2.3). expiry_ymd: 'YYYY-MM-DD'. Suelo 1 minuto."""
    y, mo, d = (int(x) for x in expiry_ymd.split("-"))
    hh, mm = int(cierre_hhmm[:2]), int(cierre_hhmm[3:5])
    venc = datetime(y, mo, d, hh, mm, tzinfo=_ET)
    venc_ms = venc.timestamp() * 1000.0
    return max(_T_MIN, (venc_ms - ts_ms) / MS_ANIO)


# ─────────────────────────────── Black-Scholes ───────────────────────────────
def _cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1d2(S, K, T, r, q, sigma):
    v = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / v
    return d1, d1 - v


def bs_price(S, K, T, r, q, sigma, right):
    """Precio Black-Scholes-Merton (con dividendo continuo q). right 'C'|'P'."""
    if T <= 0 or sigma <= 0:
        # limite: valor intrinseco descontado
        fwd = S * math.exp(-q * T) - K * math.exp(-r * T)
        return max(fwd, 0.0) if right == "C" else max(-fwd, 0.0)
    d1, d2 = _d1d2(S, K, T, r, q, sigma)
    disc_S = S * math.exp(-q * T)
    disc_K = K * math.exp(-r * T)
    if right == "C":
        return disc_S * _cdf(d1) - disc_K * _cdf(d2)
    return disc_K * _cdf(-d2) - disc_S * _cdf(-d1)


def _intrinseco(S, K, r, q, T, right):
    """Suelo intrinseco (trampa §2.3: extrinseco negativo -> suelo intrinseco)."""
    if right == "C":
        return max(S - K, 0.0)
    return max(K - S, 0.0)


def implied_vol(precio, S, K, T, r, q, right, lo=1e-4, hi=5.0, tol=1e-6, it=100):
    """IV implicita por biseccion (robusta cerca de expiry, no falla como Newton).
    Devuelve None si el precio esta por debajo del intrinseco (§2.3) o fuera de rango.
    Preserva la sonrisa: cada contrato/minuto tiene su propia IV del precio REAL."""
    if precio is None or precio <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None
    intr = _intrinseco(S, K, r, q, T, right)
    if precio < intr - 1e-6:           # extrinseco negativo -> no invertible
        return None
    plo = bs_price(S, K, T, r, q, lo, right)
    phi = bs_price(S, K, T, r, q, hi, right)
    if not (plo <= precio <= phi):     # fuera del rango [lo,hi] de vol
        return None
    a, b = lo, hi
    for _ in range(it):
        m = 0.5 * (a + b)
        pm = bs_price(S, K, T, r, q, m, right)
        if abs(pm - precio) < tol:
            return m
        if pm < precio:
            a = m
        else:
            b = m
    return 0.5 * (a + b)


def greeks(S, K, T, r, q, sigma, right):
    """delta/gamma/theta/vega analiticos (BSM). theta por dia, vega por 1% de vol.
    Devuelve dict. sigma debe venir de implied_vol (IV del precio real)."""
    if sigma is None or sigma <= 0 or T <= 0:
        return None
    d1, d2 = _d1d2(S, K, T, r, q, sigma)
    disc_S = math.exp(-q * T)
    disc_K = math.exp(-r * T)
    pdf1 = _pdf(d1)
    gamma = disc_S * pdf1 / (S * sigma * math.sqrt(T))
    vega = S * disc_S * pdf1 * math.sqrt(T) / 100.0          # por 1% de vol
    if right == "C":
        delta = disc_S * _cdf(d1)
        theta = (-S * disc_S * pdf1 * sigma / (2 * math.sqrt(T))
                 - r * K * disc_K * _cdf(d2) + q * S * disc_S * _cdf(d1)) / 365.0
    else:
        delta = -disc_S * _cdf(-d1)
        theta = (-S * disc_S * pdf1 * sigma / (2 * math.sqrt(T))
                 + r * K * disc_K * _cdf(-d2) - q * S * disc_S * _cdf(-d1)) / 365.0
    return {"iv": sigma, "delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def desde_precio(precio, S, K, T, r, q, right):
    """Atajo del backtest: precio REAL -> IV -> greeks. dict con iv/delta/... o None."""
    iv = implied_vol(precio, S, K, T, r, q, right)
    if iv is None:
        return None
    return greeks(S, K, T, r, q, iv, right)
