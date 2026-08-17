# -*- coding: utf-8 -*-
"""Capa IBKR (ib_insync) del sistema VIVO — conexión, datos y órdenes. TODO se obtiene de IBKR
(frontera de datos: en vivo NADA de massive). clientId propio (17), puerto 4002 paper.

Capacidad NUEVA vs el bot viejo: órdenes COMBINADAS (BAG/ComboLeg) para el vertical de débito.
⚠️ NO VALIDADO offline (requiere IB Gateway paper). Se prueba en paper (cr en vivo). Logs exhaustivos.
OBLIGATORIO: antes de modificar, leer el plan/ESTADO. clientId NO 7/24/25 (otros procesos).
"""
from ib_insync import IB, Stock, Option, Contract, ComboLeg, LimitOrder, MarketOrder

from sys2 import config as C
from sys2.vivo import log as L


class IBKR:
    def __init__(self):
        self.ib = IB()
        self._spy = None
        self._conid = {}          # (expiry,strike,right) -> conId (cache de qualify)

    # ─────────────────────────── conexión ───────────────────────────
    def conectar(self):
        L.log("IBKR conectando a %s:%d clientId=%d" % (C.IBKR_HOST, C.IBKR_PORT, C.IBKR_CLIENT_ID), "DATA")
        self.ib.connect(C.IBKR_HOST, C.IBKR_PORT, clientId=C.IBKR_CLIENT_ID, timeout=15)
        L.notificar("IBKR conectado (paper %d)" % C.IBKR_PORT, "IBKR")
        self._spy = Stock(C.SYMBOL, "SMART", "USD")
        self.ib.qualifyContracts(self._spy)
        return self

    def conectado(self):
        return self.ib.isConnected()

    def desconectar(self):
        try:
            self.ib.disconnect()
            L.log("IBKR desconectado", "DATA")
        except Exception as ex:
            L.log("error al desconectar: %r" % ex, "WARN")

    # ─────────────────────────── cuenta ───────────────────────────
    def saldo(self):
        """NetLiquidation de la cuenta (para autocalibra)."""
        try:
            for v in self.ib.accountSummary():
                if v.tag == "NetLiquidation":
                    return float(v.value)
        except Exception as ex:
            L.log("saldo(): %r" % ex, "WARN")
        return None

    def posiciones(self):
        try:
            return list(self.ib.positions())
        except Exception:
            return []

    # ─────────────────────────── barras ───────────────────────────
    def backfill_spy(self, dur=None, bar="1 min"):
        """reqHistoricalData useRTH=False -> premarket 04:00→ahora. Devuelve [(hora,o,h,l,c,vol)]."""
        dur = dur or C.BACKFILL_DUR
        L.log("backfill SPY %s %s useRTH=False" % (dur, bar), "DATA")
        bars = self.ib.reqHistoricalData(self._spy, endDateTime="", durationStr=dur,
                                         barSizeSetting=bar, whatToShow="TRADES",
                                         useRTH=False, formatDate=1, keepUpToDate=False)
        return bars

    def barras_live_spy(self, bar="1 min"):
        """reqHistoricalData keepUpToDate=True -> se actualiza sola minuto a minuto."""
        L.log("suscribiendo barras live SPY (keepUpToDate)", "DATA")
        return self.ib.reqHistoricalData(self._spy, endDateTime="", durationStr="1 D",
                                         barSizeSetting=bar, whatToShow="TRADES",
                                         useRTH=False, formatDate=1, keepUpToDate=True)

    def backfill_etf(self, ticker, dur="1 D", bar="1 min"):
        c = Stock(ticker, "SMART", "USD")
        self.ib.qualifyContracts(c)
        return self.ib.reqHistoricalData(c, endDateTime="", durationStr=dur, barSizeSetting=bar,
                                         whatToShow="TRADES", useRTH=True, formatDate=1, keepUpToDate=False)

    def dia_anterior_spy(self):
        """Cierre/máx/mín de la sesión RTH previa (para gap_fade / ayer_rev)."""
        bars = self.ib.reqHistoricalData(self._spy, endDateTime="", durationStr="3 D",
                                         barSizeSetting="1 day", whatToShow="TRADES",
                                         useRTH=True, formatDate=1, keepUpToDate=False)
        if len(bars) < 2:
            return None
        b = bars[-2]                 # la penúltima diaria = ayer
        return {"cierre": b.close, "maximo": b.high, "minimo": b.low}

    # ─────────────────────────── cadena de opciones ───────────────────────────
    def _opt(self, expiry, strike, right):
        return Option(C.SYMBOL, expiry, strike, right, "SMART", tradingClass=C.SYMBOL)

    def cadena(self, expiry, spot, n=None):
        """Suscribe y devuelve la cadena 0DTE alrededor del spot: dict {(right,strike): datos}
        con bid/ask/mid/last/day_vol/oi + greeks REALES de IBKR (delta/gamma/theta/vega/iv).
        n strikes por lado (1$ de paso en SPY)."""
        n = n or C.N_STRIKES_LADO
        base = round(spot)
        strikes = [base + i for i in range(-n, n + 1)]
        contratos = []
        for k in strikes:
            for r in ("C", "P"):
                contratos.append(self._opt(expiry, float(k), r))
        self.ib.qualifyContracts(*contratos)
        tickers = [self.ib.reqMktData(c, "", False, False) for c in contratos]
        self.ib.sleep(1.5)           # dejar que lleguen bid/ask/greeks
        out = {}
        for c, t in zip(contratos, tickers):
            g = t.modelGreeks
            bid = t.bid if t.bid and t.bid > 0 else None
            ask = t.ask if t.ask and t.ask > 0 else None
            mid = (bid + ask) / 2 if (bid and ask) else (t.last if t.last and t.last > 0 else None)
            out[(c.right, float(c.strike))] = {
                "bid": bid, "ask": ask, "mid": mid,
                "last": t.last if t.last and t.last > 0 else None,
                "day_vol": (t.volume * 100) if t.volume and t.volume > 0 else 0.0,
                "oi": None,
                "iv": g.impliedVol if g else None, "delta": g.delta if g else None,
                "gamma": g.gamma if g else None, "theta": g.theta if g else None,
                "vega": g.vega if g else None,
            }
        L.log("cadena %s: %d contratos suscritos (spot %.2f)" % (expiry, len(contratos), spot), "DATA")
        return out

    # ─────────────────────────── órdenes ───────────────────────────
    def comprar_vertical(self, expiry, k_long, k_short, right, debito, qty=1):
        """Orden COMBINADA (BAG): compra la pata larga, vende la corta. Débito límite = debito*1.01.
        Devuelve el Trade de ib_insync (para seguir fills por pata)."""
        cl = self._opt(expiry, float(k_long), right)
        cs = self._opt(expiry, float(k_short), right)
        self.ib.qualifyContracts(cl, cs)
        bag = Contract(symbol=C.SYMBOL, secType="BAG", exchange="SMART", currency="USD",
                       comboLegs=[
                           ComboLeg(conId=cl.conId, ratio=1, action="BUY", exchange="SMART"),
                           ComboLeg(conId=cs.conId, ratio=1, action="SELL", exchange="SMART"),
                       ])
        lim = round(debito * 1.01, 2)
        orden = LimitOrder("BUY", qty, lim)
        L.notificar("COMPRA VERTICAL %s %s L=%.0f/S=%.0f x%d débito<=%.2f"
                    % (C.SYMBOL, right, k_long, k_short, qty, lim), "ORDEN")
        return self.ib.placeOrder(bag, orden)

    def comprar_single(self, expiry, k, right, precio, qty=1):
        c = self._opt(expiry, float(k), right)
        self.ib.qualifyContracts(c)
        lim = round(precio * 1.01, 2)
        orden = LimitOrder("BUY", qty, lim)
        L.notificar("COMPRA SINGLE %s %s %.0f x%d <=%.2f" % (C.SYMBOL, right, k, qty, lim), "ORDEN")
        return self.ib.placeOrder(c, orden)

    def cerrar_single(self, expiry, k, right, qty=1, a_mercado=False, precio=None):
        c = self._opt(expiry, float(k), right)
        self.ib.qualifyContracts(c)
        orden = MarketOrder("SELL", qty) if a_mercado else LimitOrder("SELL", qty, round((precio or 0), 2))
        L.notificar("CIERRE %s %s %.0f x%d %s" % (C.SYMBOL, right, k, qty,
                    "MERCADO" if a_mercado else "límite %.2f" % (precio or 0)), "ORDEN")
        return self.ib.placeOrder(c, orden)

    def cerrar_vertical(self, expiry, k_long, k_short, right, qty=1, a_mercado=False, credito=None):
        cl = self._opt(expiry, float(k_long), right)
        cs = self._opt(expiry, float(k_short), right)
        self.ib.qualifyContracts(cl, cs)
        bag = Contract(symbol=C.SYMBOL, secType="BAG", exchange="SMART", currency="USD",
                       comboLegs=[
                           ComboLeg(conId=cl.conId, ratio=1, action="SELL", exchange="SMART"),
                           ComboLeg(conId=cs.conId, ratio=1, action="BUY", exchange="SMART"),
                       ])
        orden = MarketOrder("SELL", qty) if a_mercado else LimitOrder("SELL", qty, round((credito or 0), 2))
        L.notificar("CIERRE VERTICAL %s %s L=%.0f/S=%.0f x%d %s"
                    % (C.SYMBOL, right, k_long, k_short, qty,
                       "MERCADO" if a_mercado else "crédito %.2f" % (credito or 0)), "ORDEN")
        return self.ib.placeOrder(bag, orden)
