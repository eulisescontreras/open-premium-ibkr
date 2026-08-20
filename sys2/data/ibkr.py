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
        """⚠️ CANDIDATO A ELIMINACIÓN (2026-08-17) — YA NO SE USA. Sin callers: `backfill.py`
        deriva el día anterior de `repo.prev_sesion` (max/min de los CIERRES del RTH, que es la
        definición del motor). NO usar esta función: (1) devuelve el high/low de la barra DIARIA,
        un rango más ancho que genera MENOS señales que el backtest; (2) `bars[-2]` es posicional
        y, arrancando en premarket, la serie diaria no incluye hoy -> devolvía ANTEAYER.
        Se conserva sin borrar hasta confirmar que nada externo la invoca (R12).

        Cierre/máx/mín de la sesión RTH previa (para gap_fade / ayer_rev)."""
        bars = self.ib.reqHistoricalData(self._spy, endDateTime="", durationStr="3 D",
                                         barSizeSetting="1 day", whatToShow="TRADES",
                                         useRTH=True, formatDate=1, keepUpToDate=False)
        if len(bars) < 2:
            return None
        b = bars[-2]                 # la penúltima diaria = ayer
        return {"cierre": b.close, "maximo": b.high, "minimo": b.low}

    # ─────────────────────────── cadena de opciones ───────────────────────────
    # ─────────────────────────── tape del subyacente ───────────────────────────
    # AÑADIDO 2026-08-20. La tabla `tape_und` existía en el esquema desde el diseño pero NADIE
    # escribía en ella (0 filas, verificado en sys2.db y en sus 7 copias). `cr_schema` pasaba en
    # verde porque comprueba que la tabla EXISTE, no que tenga datos: seis sesiones de vivo
    # (16-20 ago) sin capturar nada. El sistema ANTERIOR sí lo hacía (spy_history.tape,
    # grupo='SPY'), y de ahí se copia el formato: precio, tamaño, BID/ASK del momento y agresor.
    #
    # Se guarda el bid/ask además del signo para poder RECLASIFICAR después: si solo se guardara
    # el agresor y la regla resultara estar mal, el dato sería irrecuperable.
    #
    # ⚠️ TODO va envuelto en try/except: el tape es un dato secundario y NUNCA debe poder tumbar
    # el sistema de trading. Si falla, se registra y se sigue.
    def tape_suscribir(self):
        """Suscribe el tape del SUBYACENTE: trades (AllLast) + libro (BidAsk). Una sola vez.
        Los ticks se acumulan en memoria; `tape_drenar()` los saca y vacía el buffer."""
        self._tape = []
        self._libro = [None, None]           # (bid, ask) vigentes
        self._tape_seq = 0
        self._tape_err = 0
        try:
            t_ba = self.ib.reqTickByTickData(self._spy, "BidAsk")
            t_al = self.ib.reqTickByTickData(self._spy, "AllLast")

            def _on_libro(tk):
                try:
                    for x in (tk.tickByTicks or []):
                        b, a = getattr(x, "bidPrice", None), getattr(x, "askPrice", None)
                        if b is not None and a is not None and a > 0:
                            self._libro = [b, a]
                except Exception:
                    self._tape_err += 1

            def _on_trade(tk):
                try:
                    for x in (tk.tickByTicks or []):
                        px = getattr(x, "price", None)
                        if px is None:
                            continue
                        b, a = self._libro
                        # regla del quote (Lee-Ready simplificada): agresor por el lado tocado
                        if b is not None and a is not None:
                            sg = "C" if px >= a else ("V" if px <= b else "N")
                        else:
                            sg = None
                        self._tape_seq += 1
                        self._tape.append((x.time, self._tape_seq, float(px),
                                           float(getattr(x, "size", 0) or 0),
                                           getattr(x, "exchange", "") or "", b, a, sg))
                except Exception:
                    self._tape_err += 1

            t_ba.updateEvent += _on_libro
            t_al.updateEvent += _on_trade
            self._tape_tk = (t_ba, t_al)
            L.notificar("TAPE del subyacente SUSCRITO (AllLast + BidAsk)", "IBKR")
            return True
        except Exception as ex:
            L.log("tape_suscribir(): %r — se sigue SIN tape" % ex, "WARN")
            self._tape_tk = None
            return False

    def tape_drenar(self):
        """Saca los ticks acumulados y vacía el buffer. Devuelve [] si no hay suscripción."""
        try:
            t, self._tape = self._tape, []
            return t
        except Exception as ex:
            L.log("tape_drenar(): %r" % ex, "WARN")
            return []

    def _opt(self, expiry, strike, right):
        return Option(C.SYMBOL, expiry, strike, right, "SMART", tradingClass=C.SYMBOL)

    def cadena(self, expiry, spot, n=None):
        """Suscribe, LEE y CANCELA la cadena 0DTE alrededor del spot: dict {(right,strike): datos}
        con bid/ask/mid/last/day_vol/oi + greeks REALES de IBKR (delta/gamma/theta/vega/iv).
        Captura TODOS los strikes ITM+OTM (n por lado, 1$ de paso), calls Y puts, para registrar
        el movimiento de las griegas de toda la cadena.
        ⚠️ CANCELA la suscripción tras leer (si no, las líneas de reqMktData se acumulan minuto a
        minuto y saturan el límite de IBKR (~100) en pocos minutos)."""
        n = n or C.N_STRIKES_LADO
        base = round(spot)
        strikes = [base + i for i in range(-n, n + 1)]
        contratos = []
        for k in strikes:
            for r in ("C", "P"):
                contratos.append(self._opt(expiry, float(k), r))
        self.ib.qualifyContracts(*contratos)
        tickers = [self.ib.reqMktData(c, "", False, False) for c in contratos]
        self.ib.sleep(2.0)           # dejar que lleguen bid/ask/greeks (IBKR calcula los greeks)
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
        for c in contratos:                     # liberar las líneas de datos (evita saturar IBKR)
            try:
                self.ib.cancelMktData(c)
            except Exception:
                pass
        L.log("cadena %s: %d contratos (ITM+OTM C/P) capturados y cancelados (spot %.2f)"
              % (expiry, len(contratos), spot), "DATA")
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

    def abiertas(self, expiry):
        """Posiciones REALES de opciones de ese vencimiento: [(strike, right, cantidad)].
        Fuente de verdad para saber si una posición está cerrada de verdad."""
        out = []
        for p in self.posiciones():
            c = p.contract
            if (getattr(c, "secType", "") == "OPT" and getattr(c, "symbol", "") == C.SYMBOL
                    and getattr(c, "lastTradeDateOrContractMonth", "") == expiry and p.position):
                out.append((float(c.strike), c.right, float(p.position)))
        return out

    def cerrar_todo(self, expiry, right=None, credito=None, qty=1, espera=8, mids=None):
        """CIERRE GARANTIZADO de TODAS las patas abiertas del vencimiento. Devuelve
        (plana: bool, precios: {strike: precio_ejecutado}).

        Cascada (2026-08-18: los tres cierres del día fallaron por no tener esto):
          1) BAG al MID  -> ejecución atómica y mejor precio cuando hay contrapartida.
          2) VERIFICAR contra las posiciones reales. El sistema NO puede dar por cerrado
             lo que no ha comprobado: hoy el BAG a límite no llenó (15:16 y 15:50) y el
             sistema puso pos=None igual, dejando 0DTE vivas creyéndolas cerradas.
          3) FALLBACK pata a pata a MERCADO, **primero las CORTAS**: mientras exista la pata
             corta, IBKR ve la obligación del vencimiento y RECHAZA las órdenes por margen
             (Error 201: "PROJECTED POST EXPIRATION MARGIN DEFICIT"). Recomprando el corto
             primero, la obligación desaparece y el largo se vende sin objeción. Verificado
             en real el 2026-08-18 15:53: llenó a la primera tras rechazar el BAG a mercado.
          4) VERIFICAR de nuevo y devolver si quedó plana.
        """
        precios = {}

        def _fills(trade):
            for f in list(getattr(trade, "fills", []) or []):
                ex, c = getattr(f, "execution", None), getattr(f, "contract", None)
                if ex is None or c is None or getattr(c, "secType", "") == "BAG":
                    continue
                if getattr(ex, "price", None) is not None:
                    precios[float(c.strike)] = ex.price

        abiertas = self.abiertas(expiry)
        if not abiertas:
            return True, precios

        # 1) BAG al mid (solo si hay exactamente un largo y un corto del mismo right)
        largos = [x for x in abiertas if x[2] > 0]
        cortos = [x for x in abiertas if x[2] < 0]
        if credito is not None and len(largos) == 1 and len(cortos) == 1 and largos[0][1] == cortos[0][1]:
            try:
                tr = self.cerrar_vertical(expiry, largos[0][0], cortos[0][0], largos[0][1],
                                          qty, a_mercado=False, credito=credito)
                self.ib.sleep(espera)
                _fills(tr)
            except Exception as ex:
                L.log("cerrar_todo BAG: %r" % ex, "WARN")

        # 2) ¿quedó algo? -> 3) fallback pata a pata, CORTAS PRIMERO, al MID y luego a MERCADO
        for intento, a_mkt in ((1, False), (2, True)):
            resto = self.abiertas(expiry)
            if not resto:
                break
            L.notificar("BAG no cerró (%d pata/s viva/s) — cierre por patas %s"
                        % (len(resto), "a MERCADO (último recurso)" if a_mkt else "al MID"),
                        "RIESGO")
            for k, r, n in sorted(resto, key=lambda x: x[2]):     # negativas (cortas) primero
                try:
                    c = self._opt(expiry, k, r)
                    self.ib.qualifyContracts(c)
                    accion = "BUY" if n < 0 else "SELL"
                    px = (mids or {}).get(k)
                    if a_mkt or px is None:
                        orden = MarketOrder(accion, abs(int(n)))
                        L.notificar("CIERRE MERCADO %s %s %.0f x%d"
                                    % (C.SYMBOL, r, k, abs(int(n))), "ORDEN")
                    else:
                        orden = LimitOrder(accion, abs(int(n)), round(float(px), 2))
                        L.notificar("CIERRE MID %s %s %.0f x%d @%.2f"
                                    % (C.SYMBOL, r, k, abs(int(n)), px), "ORDEN")
                    tr = self.ib.placeOrder(c, orden)
                    self.ib.sleep(espera)
                    _fills(tr)
                except Exception as ex:
                    L.log("cerrar_todo pata %.0f%s: %r" % (k, r, ex), "WARN")

        # 4) verificación final contra IBKR
        queda = self.abiertas(expiry)
        if queda:
            L.notificar("⚠️ NO SE PUDO CERRAR: %s — CERRAR A MANO ANTES DE LAS 16:00 (§12)"
                        % queda, "RIESGO")
        return (not queda), precios

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
