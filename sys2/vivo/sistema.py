# -*- coding: utf-8 -*-
"""ORQUESTADOR VIVO — arranque → backfill → captura minuto a minuto → señales (núcleo compartido)
→ reglas → ejecución IBKR → persistencia. TODO ACTIVO (6 entradas + 5 reglas + rodar/piramidar +
vertical). Logs exhaustivos + notificaciones. Sin dashboard.

Reutiliza el NÚCLEO validado (R9): core/pipeline (Sen), core/reglas (ratio/skew/día bueno),
core/instrumento (vertical/single), core/salida (salida operable), core/autocalibra, backtest/greeks.
La lógica de gestión/apertura ESPEJA backtest/motor.SIS70 (mismos umbrales de config) pero con
datos y órdenes REALES de IBKR (frontera de datos del usuario: en vivo todo de IBKR).

⚠️ Integración NO validada offline — se prueba mañana en paper. Cada acción se loguea y notifica,
y se persiste en sys2.db (bars/premium/senales/operaciones/fills). Punto de entrada: `python -m sys2.vivo.sistema`.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from sys2 import config as C
from sys2.core.supertrend import mm, hhmm
from sys2.core import pipeline, reglas as R, instrumento as I, salida as SAL, autocalibra
from sys2.backtest import greeks as G
from sys2.data.ibkr import IBKR
from sys2.data import backfill as BF, captura as CAP
from sys2.db import repo
from sys2.vivo import log as L
from sys2.vivo import estado as ST

_ET = ZoneInfo("America/New_York")


def _T(h):
    return max(1e-6, (960 - mm(h)) / (60 * 24 * 252))


def _iv(precio, S, K, h, esC):
    return G.implied_vol(precio, S, K, _T(h), C.GREEKS_R, C.GREEKS_Q, "C" if esC else "P")


def _delta(S, K, h, s_, esC):
    g = G.greeks(S, K, _T(h), C.GREEKS_R, C.GREEKS_Q, s_, "C" if esC else "P")
    return abs(g["delta"]) if g else None


class SistemaVivo:
    def __init__(self):
        self.ib = IBKR()
        self.con = repo.abrir()
        self.pos = None            # posición abierta (mismo dict que el motor)
        self.hechas = 0
        self.cfg = None            # autocalibración de la sesión
        self._saldo = 0.0          # cache del saldo (el panel usa la BD, no IBKR)
        self._etf_hecho = False    # reintento del backfill ETF (una sola vez por sesión)
        self._origen = {}          # {hora: origen de la señal} (ST-3/ORB/pm_rev/... para el panel)
        self.nq = 1                # unidades (día bueno dobla)
        self.fecha = None
        self.expiry = None         # 0DTE 'YYYYMMDD'
        self.prev = (None, None, None)   # (max_ayer, min_ayer, cierre_ayer)
        self._ultimo_min = None

    # ─────────────────────────── arranque ───────────────────────────
    def arrancar(self):
        ahora = datetime.now(_ET)
        self.fecha = ahora.strftime("%Y-%m-%d")
        self.expiry = ahora.strftime("%Y%m%d")     # 0DTE = hoy
        L.notificar("ARRANQUE del sistema vivo — %s (0DTE %s)" % (self.fecha, self.expiry), "ARRANQUE")
        self.ib.conectar()

        # autocalibración por saldo real
        saldo = self.ib.saldo()
        self._saldo = saldo or 0.0            # cache: el panel usa la BD, NO consulta IBKR
        self.cfg = autocalibra.configuracion(saldo)
        if self.cfg is None:
            L.notificar("saldo insuficiente (%s) — NO se opera" % saldo, "ARRANQUE")
            return False
        # aplicar la config de la sesión (ancho/tope/unidades)
        C.ANCHO = self.cfg["ancho"]
        C.TOPE = self.cfg["tope"]
        self.unidades_base = self.cfg["unidades"]
        L.notificar("Autocalibra: saldo=%.0f nivel=%d ancho=%.0f tope=%.0f unidades=%d"
                    % (saldo, self.cfg["nivel"], self.cfg["ancho"], self.cfg["tope"],
                       self.cfg["unidades"]), "ARRANQUE")

        # backfill (premarket SPY + ETF + día anterior)
        BF.backfill(self.ib, self.con, self.fecha)
        # prev = max/min de los CIERRES del RTH de la sesión anterior + su último cierre.
        # MISMA definición que el motor de backtest (motor.py:255-256). NO son el high/low de
        # la barra diaria: ese rango es más ancho y generaría MENOS señales que lo validado.
        self.prev = repo.prev_sesion(self.con, self.fecha)
        L.log("día anterior (cierres RTH): max=%s min=%s cierre=%s" % self.prev, "DATA")
        if self.prev[0] is None:
            L.notificar("SIN datos de la sesión anterior — ayer_rev y gap_fade quedan inactivas",
                        "DATA")
        # Reinicio a media sesión: si ya hay posición 0DTE abierta en IBKR hay que adoptarla,
        # o queda sin gestión de salida (flip ST-3 / aplanado 15:50 §12).
        self._recuperar_posicion()
        return True

    # ─────────────────────────── datos del minuto ───────────────────────────
    def _spot(self):
        r = self.con.execute("select close from bars where fecha=? order by hora desc limit 1",
                             (self.fecha,)).fetchone()
        return r[0] if r else None

    def _PM_all(self):
        """{hora: {(right,strike): (mid, day_vol)}} de todo el día (para el skew del pipeline)."""
        PM = {}
        for h, r, k, mid, dv in self.con.execute(
                "select hora,right,strike,mid,day_vol from premium where fecha=? and expiry=?",
                (self.fecha, self.expiry)):
            if mid is not None:
                PM.setdefault(h, {})[(r, k)] = (mid, dv or 0.0)
        return PM

    # ─────────────────────────── paso por minuto ───────────────────────────
    def _recuperar_posicion(self):
        """Reconstruye self.pos si el proceso arranca con una posición YA abierta en IBKR.
        Sin esto, un reinicio a media sesión deja la posición HUÉRFANA: nadie la valora, nadie
        aplica el flip del ST-3 y —lo grave con 0DTE— nadie ejecuta el aplanado de las 15:50
        (riesgo de asignación §12). Caso real 2026-08-18: vertical 767/769 + pirámide abiertos.
        Fuente de verdad = IBKR (posiciones reales); la BD aporta hora de entrada, delta y origen.
        El coste de entrada se toma del avgCost REAL de IBKR (incluye comisión), no del teórico.
        Si IBKR tiene posición y la BD no tiene operación abierta, NO inventa: avisa y deja
        self.pos=None para no operar a ciegas encima de una posición que no entiende."""
        try:
            abiertas = [p for p in self.ib.posiciones()
                        if getattr(p.contract, "secType", "") == "OPT"
                        and getattr(p.contract, "lastTradeDateOrContractMonth", "") == self.expiry
                        and p.position != 0]
        except Exception as ex:
            L.log("recuperar posición: %r" % ex, "WARN")
            return
        if not abiertas:
            return
        fila = self.con.execute(
            "select right, strike_largo, strike_corto, qty, hora_entrada, delta_entrada, id "
            "from operaciones where fecha=? and hora_salida is null order by id desc limit 1",
            (self.fecha,)).fetchone()
        if fila is None:
            L.notificar("⚠️ %d pata(s) 0DTE abiertas en IBKR SIN operación abierta en la BD — "
                        "no se reconstruye; revisar y cerrar a mano" % len(abiertas), "RIESGO")
            return
        rt, kl, ks, qty, h0, d0, op_id = fila
        coste = {float(p.contract.strike): abs(p.avgCost) / 100.0 for p in abiertas}
        largos = sorted(float(p.contract.strike) for p in abiertas if p.position > 0)
        es_vert = ks is not None and float(ks) in coste
        ask = coste.get(float(kl), 0.0) - (coste.get(float(ks), 0.0) if es_vert else 0.0)
        self.pos = {'k': float(kl), 'ks': float(ks) if es_vert else None, 'rt': rt,
                    'ask': ask, 'mid': ask, 'rod': 0, 'extra': None,
                    'h0': h0 or "09:30", 'd0': d0, 'vert': bool(es_vert),
                    'nq': int(qty or 1), 'origen': "recuperada", 'op_id': op_id}
        # pirámide: un largo extra que no es la pata larga del vertical (no se persiste en la BD,
        # solo existía en memoria -> se detecta por diferencia contra las posiciones reales).
        extra = [k for k in largos if k != float(kl)]
        if extra:
            self.pos['extra'] = {'k': extra[0], 'ask': coste[extra[0]], 'mid': coste[extra[0]]}
        L.notificar("POSICIÓN RECUPERADA de IBKR: %s %s L=%.0f%s coste=%.2f%s (entrada %s)"
                    % ("vertical" if es_vert else "single", rt, float(kl),
                       "/S=%.0f" % float(ks) if es_vert else "", ask,
                       " +pirámide %.0f" % extra[0] if extra else "", h0), "ARRANQUE")

    def _sincronizar(self, hora):
        """RED DE SEGURIDAD: la posición REAL de IBKR manda sobre self.pos, que es solo memoria
        y PUEDE DIVERGIR. El 2026-08-18 divergió tres veces en una sola sesión: dos cierres que
        no se llenaron (15:16 y 15:50) dejaron 0DTE vivas con el sistema creyéndose plano, sin
        aplanado ni verificación posterior (§12). El sistema ANTERIOR ya tenía esto
        (`spy_direction.py:3982 _sync_pos`) y sys2 no lo heredó.

        Dos direcciones:
          IBKR tiene y el sistema NO  -> ADOPTAR (reusa _recuperar_posicion).
          el sistema tiene e IBKR NO  -> SOLTAR, pero solo tras 2 confirmaciones seguidas: un
                                          fallo puntual de la API no puede hacernos abandonar
                                          una posición viva. La fila de la BD se cierra con
                                          razón 'externa' y pnl NULL: NO se inventa un precio
                                          de salida que nadie ejecutó (regla 13)."""
        try:
            reales = self.ib.abiertas(self.expiry)
        except Exception as ex:
            L.log("sync: %r" % ex, "WARN")
            return
        if self.pos is None and reales:
            L.notificar("SYNC %s: IBKR tiene %d pata(s) 0DTE y el sistema se creía PLANO — "
                        "adoptando" % (hora, len(reales)), "RIESGO")
            self._sync_falta = 0
            self._recuperar_posicion()
        elif self.pos is not None and not reales:
            self._sync_falta = getattr(self, "_sync_falta", 0) + 1
            if self._sync_falta >= 2:
                L.notificar("SYNC %s: el sistema creía tener posición e IBKR está PLANA "
                            "(2 confirmaciones) — se suelta y se cierra la fila como 'externa'"
                            % hora, "RIESGO")
                self.con.execute(
                    "update operaciones set hora_salida=?, razon_salida='externa' "
                    "where fecha=? and hora_salida is null", (hora, self.fecha))
                self.con.commit()
                self.pos = None
                self._sync_falta = 0
        else:
            self._sync_falta = 0

    def _recalibrar(self, hora):
        """Relee el saldo REAL de IBKR y reajusta tope/unidades. Antes esto ocurría SOLO en
        arrancar(), así que un reset de la cuenta (o el P&L del día) no movía el tope hasta
        reiniciar el proceso (caso real 2026-08-18: cuenta pasada de 200$ a 600$ en caliente).
        C.ANCHO queda CONGELADO al del arranque: cambiarlo a media sesión mezclaría dos
        estrategias distintas (§13.1 pasa de 2 a 3 puntos en el nivel 800) en el mismo día.
        Si IBKR no responde o el saldo cae bajo el mínimo de la tabla, se MANTIENE la última
        configuración válida: nunca se interrumpe el bucle ni se deja el sistema sin tope.
        NO toca self._saldo a propósito: _volcar_estado() calcula capital = _saldo + pnl_hoy y
        NetLiquidation ya incluye el P&L realizado -> se contaría dos veces en el panel."""
        saldo = self.ib.saldo()
        cfg = autocalibra.configuracion(saldo) if saldo is not None else None
        if cfg is None:
            L.log("recalibra %s: saldo=%s sin configuración válida — se mantiene tope %.0f"
                  % (hora, saldo, C.TOPE), "WARN")
            return
        if self.cfg is None or cfg["nivel"] != self.cfg["nivel"]:
            L.notificar("RECALIBRA %s: saldo=%.0f nivel %s->%d tope %.0f->%.0f unidades %s->%d "
                        "(ancho FIJO %.0f)"
                        % (hora, saldo, self.cfg["nivel"] if self.cfg else "?", cfg["nivel"],
                           C.TOPE, cfg["tope"], self.unidades_base, cfg["unidades"], C.ANCHO),
                        "ARRANQUE")
        self.cfg = cfg
        C.TOPE = cfg["tope"]
        self.unidades_base = cfg["unidades"]

    def paso(self, hora):
        """Un minuto de mercado (09:30-16:00). Captura, decide y ejecuta. Espeja motor.SIS70."""
        spot = self._spot()
        if spot is None:
            L.log("paso %s sin spot; salto" % hora, "WARN")
            return
        # 1) capturar + persistir la cadena 0DTE con greeks reales
        try:
            cad = self.ib.cadena(self.expiry, spot)
            CAP.guardar_cadena(self.con, self.fecha, hora, self.expiry, cad)
        except Exception as ex:
            L.log("captura cadena %s: %r" % (hora, ex), "WARN")

        bars = CAP.bars_de_bd(self.con, self.fecha)
        cl_ = {h: cl for h, _, _, cl in bars if "09:30" <= h <= "16:00"}
        PM = self._PM_all()
        pm_h = PM.get(hora, {})           # cadena de ESTE minuto {(r,k):(mid,vol)}

        # 2) señales (pipeline compartido) + día bueno
        ph, pl, pc = self.prev
        Sen, L_, ks, ik, sp, origen = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc)
        self._origen = origen
        # ── MINUTO DE DECISIÓN (h_dec) = la última barra CERRADA, o sea `hora` - 1 min ──────────
        # Las señales se evalúan SOLO sobre barras cerradas; la cadena y el precio de ejecución son
        # del minuto ACTUAL. Es la latencia física inevitable: no se puede actuar sobre el cierre
        # de un minuto antes de que ese minuto termine. Antes se consultaba `Sen[hora]`, cuando la
        # barra de `hora` aún no existía (y encima venía mal fechada, ver _sincronizar_barra),
        # así que se decidía sobre una barra en formación.
        h_dec = hhmm(mm(hora) - 1)
        sen_dec = Sen.get(h_dec)
        # Reintento del backfill ETF: si el sistema arrancó ANTES de las 10:05, la ventana
        # 09:25-10:05 que pide backfill.etf_dia aún no existía y bars_etf quedó vacío toda la
        # sesión -> dia_bueno() devuelve False siempre (caso real 2026-08-18, arranque 09:25).
        # Se reintenta UNA vez, ya cerrada la ventana. insertar() es OR REPLACE: no duplica.
        if not self._etf_hecho and hora >= "10:06":
            self._etf_hecho = True
            if not self.con.execute("select 1 from bars_etf where fecha=? limit 1",
                                    (self.fecha,)).fetchone():
                L.notificar("bars_etf vacío — reintentando backfill ETF (%d barras)"
                            % BF.etf_dia(self.ib, self.con, self.fecha), "DATA")
        dia = [(h, hi, lo, cl) for h, hi, lo, cl in self.con.execute(
            "select hora,close,close,close from bars_etf where ticker='DIA' and fecha=?", (self.fecha,))]
        tlt = [(h, hi, lo, cl) for h, hi, lo, cl in self.con.execute(
            "select hora,close,close,close from bars_etf where ticker='TLT' and fecha=?", (self.fecha,))]
        self._sincronizar(hora)         # IBKR manda sobre self.pos (red de seguridad)
        self._recalibrar(hora)          # tope/unidades al saldo real de AHORA (ancho fijo)
        self.nq = self.unidades_base * (2 if (C.DIABUENO and R.dia_bueno(cl_, dia, tlt)) else 1)
        self.nq = min(self.nq, autocalibra.TOPE_UNIDADES)

        # 3) valorar posición desde la cadena viva
        if self.pos:
            self._valorar(spot, pm_h)

        # 4) gestión: salida (flip/aplanar/mercado) + rodar/piramidar
        # El flip se evalúa con la señal del minuto CERRADO (h_dec); los tiempos de aplanado y
        # mercado siguen usando `hora` (son horas de reloj, no dependen de la barra).
        if self.pos:
            self._gestionar(hora, spot, sen_dec, pm_h)

        # 5) apertura — TODA señal se registra en `senales`, se opere o no (schema.sql:39).
        # Es el registro que hace VISIBLE por qué un día no operó: sin él, 3 señales descartadas
        # y 0 errores en el log son indistinguibles de "no hubo señales" (caso real 2026-08-17).
        # La señal se registra con SU hora (h_dec); la ejecución ocurre en `hora` (1 min después).
        if sen_dec is not None:
            if self.pos is not None:
                self._persistir_senal(h_dec, sen_dec, spot, pm_h, "pos_abierta")
            elif not SAL.puede_abrir(h_dec, self.hechas):
                self._persistir_senal(h_dec, sen_dec, spot, pm_h, "limite_ops")
            else:
                self._abrir(hora, spot, sen_dec, pm_h, h_dec)

        # 6) verificación de posición plana al final
        if SAL.debe_verificar_plana(hora) and self.pos is not None:
            L.notificar("⚠️ POSICIÓN ABIERTA a las %s — forzando cierre a MERCADO (asignación §12)" % hora, "RIESGO")
            self._cerrar(hora, spot, "cierre", a_mercado=True)

        # 7) volcar estado para el PANEL (desde la BD; el panel NO consulta IBKR)
        fase = "ORDEN" if self.pos else ("SEÑAL" if sen_dec is not None else "ESPERA")
        self._volcar_estado(hora, spot, fase)

    def _volcar_estado(self, hora, spot, fase):
        """Escribe estado.json para el panel. P&L calculado desde la BD (operaciones), NO de IBKR."""
        try:
            hoy = self.fecha
            mes = self.fecha[:7]
            r = self.con.execute("select coalesce(sum(pnl),0) from operaciones where fecha=?", (hoy,)).fetchone()
            pnl_hoy = r[0] if r else 0.0
            r = self.con.execute("select coalesce(sum(pnl),0) from operaciones where substr(fecha,1,7)=?", (mes,)).fetchone()
            pnl_mes = r[0] if r else 0.0
            capital = (self._saldo or 0.0) + pnl_hoy
            base_hoy = capital - pnl_hoy
            base_mes = capital - pnl_mes
            # estrategia/entrada aplicada en este momento (para el label del panel)
            if self.pos:
                est = self.pos.get("origen") or "—"
                if self.pos.get("rod", 0) > 0:
                    est += " · RODADO x%d" % self.pos["rod"]
                if self.pos.get("extra"):
                    est += " · PIRAMIDA"
            elif fase == "SEÑAL":
                est = self._origen.get(hora) or "señal"
            else:
                est = "en espera"
            d = {
                "fase": fase, "estrategia": est, "capital": capital,
                "pnl_hoy": pnl_hoy, "pnl_hoy_pct": (100 * pnl_hoy / base_hoy) if base_hoy else 0,
                "pnl_mes": pnl_mes, "pnl_mes_pct": (100 * pnl_mes / base_mes) if base_mes else 0,
                "reloj": hora, "conectado": self.ib.conectado(), "datos": "1m",
                "ops": "%d/%d" % (self.hechas, C.MAX_TRADES),
                "unidades": (self.pos.get("nq") if self.pos else self.nq),
                "nivel": self.cfg["nivel"], "version": self.cfg["version"],
                "tope": int(self.cfg["tope"]), "meta": self.cfg["meta"],
                "contrato": None,
                # última notificación (compra/venta/arranque/riesgo) para que el panel la
                # muestre: el print de notificar() se pierde con nohup y nadie lo ve.
                "evento": L.ultima(),
            }
            if self.pos:
                p = self.pos
                if p.get("vert"):
                    d["contrato"] = "%s %.0f%s/%.0f%s" % (self.expiry, p["k"], p["rt"], p["ks"], p["rt"])
                    d["debito"] = round(p["ask"] * 100 / 1.01)     # débito inicial $ (ask=(débito)*1.01)
                else:
                    d["contrato"] = "%s %.0f%s" % (self.expiry, p["k"], p["rt"])
                    d["debito"] = round(p["ask"] * 100 / 1.01)
                # TODAS las patas abiertas a la vista: la pirámide es un contrato más que se
                # compró de verdad y no aparecía (solo la etiqueta "+extra"). `xN` = unidades.
                if p.get("extra"):
                    d["contrato"] += " +%.0f%s" % (p["extra"]["k"], p["rt"])
                if p.get("nq", 1) > 1:
                    d["contrato"] += " x%d" % p["nq"]
                # La PIRÁMIDE se suma: es dinero de la MISMA posición. Antes el panel mostraba
                # solo el vertical y ocultaba la mitad del P&L (2026-08-18: mostraba +28$ cuando
                # la posición real ganaba +47$; el usuario lo detectó porque 600+17 no daba 653).
                # _cerrar ya liquida las dos partes por separado: aquí se replica esa suma.
                x = p.get("extra")
                mid_t = p["mid"] + (x["mid"] if x else 0.0)
                ask_t = p["ask"] + (x["ask"] if x else 0.0)
                if x:
                    d["debito"] = round(ask_t * 100 / 1.01)   # débito TOTAL (vertical + pirámide)
                d["mid"] = round(mid_t * 100)
                ent = p.get("h0")
                d["entrada"] = ent
                d["duracion"] = "%dm" % max(0, mm(hora) - mm(ent)) if ent else "—"
                d["mid_pct"] = (100 * (mid_t - ask_t) / ask_t) if ask_t else 0
                # cambio en DÓLARES de la posición (misma fórmula que el P&L de _cerrar, sin
                # comisión): lo que se ganaría/perdería cerrando ahora al mid.
                d["mid_usd"] = round((mid_t - ask_t) * 100)
                if p.get("rod", 0) > 0 or p.get("extra"):
                    d["contrato_act"] = "rodado x%d" % p.get("rod", 0) if p.get("rod") else "+extra"
            ST.escribir(d)
        except Exception as ex:
            L.log("volcar estado: %r" % ex, "WARN")

    def _valorar(self, spot, pm_h):
        p = self.pos
        intr = max(0.0, (spot - p['k']) if p['rt'] == 'C' else (p['k'] - spot))
        q = pm_h.get((p['rt'], p['k']))
        _long = max(q[0], intr) if q else max(p.get('_l', intr), intr)
        p['_l'] = _long
        if p.get('vert'):
            iss = max(0.0, (spot - p['ks']) if p['rt'] == 'C' else (p['ks'] - spot))
            q2 = pm_h.get((p['rt'], p['ks']))
            sh = max(q2[0], iss) if q2 else max(p.get('_s', iss), iss)
            p['_s'] = sh
            p['mid'] = _long - sh
        else:
            p['mid'] = _long
        # La PIRÁMIDE también hay que revaluarla: sin esto extra['mid'] se queda CONGELADO en
        # el precio de compra y su P&L sale siempre 0. El motor sí lo hace (motor.py:181-184);
        # el vivo no lo hacía -> divergencia con lo validado. Caso real 2026-08-18: el panel
        # mostraba -14$ cuando la posición perdía -82$, y el cierre por flip de las 15:16
        # registró -27$ contando SOLO el vertical.
        x = p.get('extra')
        if x:
            i2 = max(0.0, (spot - x['k']) if p['rt'] == 'C' else (x['k'] - spot))
            q3 = pm_h.get((p['rt'], x['k']))
            x['mid'] = max(q3[0], i2) if q3 else max(x.get('mid', i2), i2)

    def _gestionar(self, hora, spot, sen_dir, pm_h):
        """`sen_dir` = dirección de la señal del minuto CERRADO ('C'/'P'/None), no el dict Sen:
        el flip debe evaluarse sobre una barra cerrada. `hora` sigue siendo el reloj (aplanar/mercado)."""
        p = self.pos
        razon = SAL.decidir_salida(p, sen_dir, hora)
        if razon:
            self._cerrar(hora, spot, razon, a_mercado=(razon == "mercado"))
            return
        # delta (mismo filtro binario que el motor: invertir el débito)
        dl = None
        s_ = _iv(p['mid'], spot, p['k'], hora, p['rt'] == 'C')
        if s_:
            dl = _delta(spot, p['k'], hora, s_, p['rt'] == 'C')
        # piramidar
        if (C.PIR and not p['extra'] and hora < C.PIR_HASTA
                and mm(hora) - mm(p['h0']) >= C.PIR_ESPERA_MIN
                and dl is not None and p['d0'] is not None and dl - p['d0'] > C.PIR_DELTA):
            cd = [(k, v) for (r, k), v in pm_h.items() if r == p['rt']]
            e = I.elegir(cd, spot, hora, p['rt'], "presupuesto", C.TOPE)
            if e:
                tr = self.ib.comprar_single(self.expiry, e[0], p['rt'], e[1][0], self.nq)
                p['extra'] = {'k': e[0], 'ask': e[1][0] * 1.01, 'mid': e[1][0]}
                # La pirámide NO se registraba en NINGUNA tabla: solo existía en p['extra'], en
                # memoria (2026-08-18: se compró un C768 por 94$ que no figuraba en la BD y solo
                # se detectó comparando con las posiciones reales de IBKR). Se cuelga de la MISMA
                # operación —no abre fila nueva: es la misma posición, con una pata más.
                self._persistir_fills(tr, p.get('op_id'), hora, "piramide", [(e[0], p['rt'], "BUY")])
                L.notificar("PIRAMIDAR: +1 single %s %.0f" % (p['rt'], e[0]), "GESTION")
        # rodar
        elif (not p['extra'] and p['rod'] < C.ROD_MAX and hora < C.ROD_HASTA
              and dl is not None and dl < C.ROD_DELTA):
            L.notificar("RODAR: delta %.2f<%.2f (rod %d)" % (dl, C.ROD_DELTA, p['rod'] + 1), "GESTION")
            self._cerrar(hora, spot, "rodar", a_mercado=False, rodando=True)

    def _abrir(self, hora, spot, rt, pm_h, h_sen=None):
        """`hora` = minuto de EJECUCIÓN (precios de la cadena de ahora).
        `h_sen` = minuto de la SEÑAL (la barra cerrada que la generó); si es None, se asume `hora`.
        Se separan porque la señal se detecta al cerrar su minuto y la orden se manda al siguiente:
        la operación y los greeks se fechan con la ejecución, el registro en `senales` con la señal.
        """
        h_sen = h_sen or hora
        # ratio call/put OTM (veto)
        if C.RUMB:
            rr = R.ratio_otm(pm_h, spot)
            if rr is not None and ((rt == 'C' and rr < C.RUMB) or (rt == 'P' and rr > 1.0 / C.RUMB)):
                L.log("apertura %s %s VETADA por ratio_otm=%.2f" % (hora, rt, rr), "SENAL")
                self._persistir_senal(h_sen, rt, spot, pm_h, "RATIO")
                return
        cd = [(k, v) for (r, k), v in pm_h.items() if r == rt]
        d0 = None
        if C.ANCHO:
            cd2 = [(k, I.suelo(k, v, spot, rt)) for k, v in cd]
            ev = I.elegir_vert(cd2, spot, hora, rt, C.TOPE, C.ANCHO)
            if ev:
                kl, pl_, ksh, psh = ev
                s_ = _iv(pl_, spot, kl, hora, rt == 'C')
                if s_:
                    d0 = _delta(spot, kl, hora, s_, rt == 'C')
                trade = self.ib.comprar_vertical(self.expiry, kl, ksh, rt, pl_ - psh, self.nq)
                self.pos = {'k': kl, 'ks': ksh, 'rt': rt, 'ask': (pl_ - psh) * 1.01, 'mid': pl_ - psh,
                            'rod': 0, 'extra': None, 'h0': hora, 'd0': d0, 'vert': True, 'nq': self.nq,
                            'origen': self._origen.get(h_sen)}
                op_id = self._persistir_operacion(hora, spot, "vertical", rt, kl, ksh,
                                                  pl_ - psh, d0, s_)
                self.pos['op_id'] = op_id          # para colgar la pirámide de ESTA operación
                self._persistir_fills(trade, op_id, hora, "vertical", [(kl, rt, "BUY"), (ksh, rt, "SELL")])
                self._enlazar_senal(op_id, self._persistir_senal(h_sen, rt, spot, pm_h, None))
            else:
                # NO hay vertical dentro del tope: la señal se pierde. Es el caso mas frecuente
                # con capital bajo (2026-08-17: tope 110$ y el mas barato costaba 113$).
                self._persistir_senal(h_sen, rt, spot, pm_h, "sin_contrato")
            # con ANCHO activo, si NO hay vertical disponible se DESCARTA la señal (espeja el motor:
            # no cae al single). Solo se opera single cuando ANCHO es None.
            return
        e = I.elegir(cd, spot, hora, rt, "presupuesto", C.TOPE)
        if e:
            s_ = _iv(e[1][0], spot, e[0], hora, rt == 'C')
            if s_:
                d0 = _delta(spot, e[0], hora, s_, rt == 'C')
            trade = self.ib.comprar_single(self.expiry, e[0], rt, e[1][0], self.nq)
            self.pos = {'k': e[0], 'rt': rt, 'ask': e[1][0] * 1.01, 'mid': e[1][0], 'rod': 0,
                        'extra': None, 'h0': hora, 'd0': d0, 'nq': self.nq,
                        'origen': self._origen.get(h_sen)}
            op_id = self._persistir_operacion(hora, spot, "single", rt, e[0], None, e[1][0], d0, s_)
            self.pos['op_id'] = op_id
            self._persistir_fills(trade, op_id, hora, "single", [(e[0], rt, "BUY")])
            self._enlazar_senal(op_id, self._persistir_senal(hora, rt, spot, pm_h, None))
        else:
            self._persistir_senal(h_sen, rt, spot, pm_h, "sin_contrato")

    def _cerrar(self, hora, spot, razon, a_mercado=False, rodando=False):
        p = self.pos
        # CIERRE GARANTIZADO de TODAS las patas (vertical + pirámide) en una sola llamada:
        # BAG al mid -> patas al mid -> patas a mercado, VERIFICANDO contra IBKR en cada paso.
        # Antes se mandaban 2 órdenes a límite y se daba el cierre por hecho sin comprobar: el
        # 2026-08-18 eso dejó 0DTE vivas dos veces (15:16 y 15:50, cierre PARCIAL) con el
        # sistema creyéndose plano, sin aplanado ni verificación posterior (§12 asignación).
        mids = {p['k']: p['mid']}
        if p.get('ks') is not None:
            mids[p['ks']] = 0.0                      # la corta se recompra: mid propio abajo
        if p.get('extra'):
            mids[p['extra']['k']] = p['extra']['mid']
        plana, px = self.ib.cerrar_todo(self.expiry, right=p['rt'],
                                        credito=(p['mid'] if p.get('vert') else None),
                                        qty=p.get('nq', 1), mids=mids)
        # P&L con los precios REALMENTE ejecutados; el mid de la cadena queda de respaldo.
        def _real(k, teorico):
            return px[k] if k in px else teorico
        if p.get('vert'):
            cred = _real(p['k'], p['_l'] if '_l' in p else p['mid']) - _real(p['ks'], p.get('_s', 0.0))
        else:
            cred = _real(p['k'], p['mid'])
        pnl = (cred - p['ask']) * 100 - C.COMISION
        if p['extra']:
            pnl += (_real(p['extra']['k'], p['extra']['mid']) - p['extra']['ask']) * 100 - C.COMISION
        L.notificar("CIERRE (%s) %s -> P&L %s %+.0f$ x%d%s"
                    % (razon, p['rt'], "REAL" if px else "estimado (sin fills)", pnl,
                       p.get('nq', 1), "" if plana else "  ⚠️ NO PLANA"), "CIERRE")
        if not plana:
            # NO se suelta la posición: IBKR dice que sigue viva. Mantenerla en self.pos es lo
            # que permite reintentar el cierre en el minuto siguiente y que el aplanado 15:50 /
            # mercado 15:55 / verificación 15:59 sigan actuando sobre ella (todos exigen
            # pos is not None). Poner pos=None a ciegas fue el fallo del 2026-08-18.
            L.notificar("CIERRE NO CONFIRMADO (%s): la posición SIGUE ABIERTA en IBKR — se "
                        "mantiene y se reintenta el próximo minuto" % razon, "RIESGO")
            return
        self._persistir_cierre(hora, spot, razon, pnl)
        rt, r2, h0 = p['rt'], p['rod'] + 1, p['h0']
        self.pos = None
        if not rodando:
            self.hechas += 1
        else:                          # rodar: reabrir single del mismo lado (pierde 'vert' y 'nq')
            pm_h = self._PM_all().get(hora, {})
            cd = [(k, v) for (r, k), v in pm_h.items() if r == rt]
            e = I.elegir(cd, spot, hora, rt, "presupuesto", C.TOPE)
            if e:
                s_ = _iv(e[1][0], spot, e[0], hora, rt == 'C')
                d0 = _delta(spot, e[0], hora, s_, rt == 'C') if s_ else None
                self.ib.comprar_single(self.expiry, e[0], rt, e[1][0], 1)
                self.pos = {'k': e[0], 'rt': rt, 'ask': e[1][0] * 1.01, 'mid': e[1][0],
                            'rod': r2, 'extra': None, 'h0': h0, 'd0': d0}

    # ─────────────────────────── persistencia ───────────────────────────
    def _persistir_senal(self, hora, rt, spot, pm_h, descartada_por):
        """Registra la señal en `senales` (schema.sql:39), se opere o no.
        `descartada_por`: None si se operó | 'RATIO' | 'sin_contrato' | 'pos_abierta' | 'limite_ops'.

        `origen` viene del pipeline ('ORB'|'pm_rev'|'v1'|'gap_fade'|'ayer_rev'|'ST-3 NORMAL'|
        'ST-3 RETRASA'|'ST-3 INVIERTE'|'ST-3 SKEW'); de ahí se deriva `grupo` para los flips del
        ST-3. NO se toca pipeline.py (núcleo compartido con el backtest): solo se persiste lo que
        ya devuelve. Las columnas que exigirían cambiarlo (hora_efectiva, dist_linea, iv_atm,
        giros_st1_5m, flip_falso) quedan NULL — documentado en PENDIENTES.md.
        Idempotente: no duplica si ya hay fila para (fecha, hora, origen).
        """
        try:
            org = self._origen.get(hora)
            grupo = None
            if org and org.startswith("ST-3 "):
                grupo = org.split(" ", 1)[1]          # NORMAL | RETRASA | INVIERTE | SKEW
            ya = self.con.execute(
                "select id from senales where fecha=? and hora=? and ifnull(origen,'')=?",
                (self.fecha, hora, org or "")).fetchone()
            if ya:
                return ya[0]        # id de la señal ya registrada (para enlazar operaciones.senal_id)
            rr = None
            try:
                rr = R.ratio_otm(pm_h, spot) if pm_h else None
            except Exception:
                pass
            repo.insertar(self.con, "senales", [{
                "fecha": self.fecha, "hora": hora, "origen": org,
                "direccion": rt, "grupo": grupo, "direccion_final": rt,
                "descartada_por": descartada_por, "spy": spot, "ratio_otm": rr,
            }])
            self.con.commit()
            L.log("señal %s %s (%s) -> %s" % (hora, rt, org or "?",
                  descartada_por or "OPERADA"), "SENAL")
            return self.con.execute("select last_insert_rowid()").fetchone()[0]
        except Exception as ex:
            L.log("persistir señal %s: %r" % (hora, ex), "WARN")
        return None

    def _persistir_operacion(self, hora, spot, tipo, rt, kl, ks, debito, d0, iv=None):
        repo.insertar(self.con, "operaciones", [{
            "fecha": self.fecha, "n_op_dia": self.hechas + 1, "tipo": tipo, "right": rt,
            "strike_largo": kl, "strike_corto": ks, "ancho": C.ANCHO, "qty": self.nq,
            "nivel": self.cfg["nivel"], "modo": self.cfg["modo"], "tope": C.TOPE, "unidades": self.nq,
            "hora_entrada": hora, "spy_entrada": spot, "debito_neto": debito,
            "delta_entrada": d0, "iv_entrada": iv,      # la IV que YA se calcula para la delta
            "moneyness": (spot - kl) if rt == 'C' else (kl - spot),
        }])
        self.con.commit()
        op_id = self.con.execute("select last_insert_rowid()").fetchone()[0]
        L.log("operación #%s abierta: %s %s L=%s S=%s débito=%.2f" % (op_id, tipo, rt, kl, ks, debito), "POS")
        return op_id

    def _persistir_fills(self, trade, op_id, hora, tipo, esperadas):
        """Guarda los fills POR PATA del spread (tabla `fills`). Detecta parciales (crítico: si el
        vertical no llena ambas patas). `esperadas` = [(strike, right, accion)]. Espera al fill.
        ⚠️ Requiere IBKR real; con FakeIB (smoke) trade=None -> no persiste."""
        if trade is None:
            return
        try:
            self.ib.ib.sleep(3)              # dar tiempo a que lleguen los fills
            fills = list(getattr(trade, "fills", []) or [])
            filas = []
            llenas = set()
            for f in fills:
                ex = getattr(f, "execution", None)
                c = getattr(f, "contract", None)
                if ex is None or c is None:
                    continue
                if getattr(c, "secType", "") == "BAG":
                    continue          # ib_insync incluye el fill AGREGADO del combo (secType='BAG',
                    #                    strike=0) ademas de las patas -> se salta (solo patas reales)
                k = float(getattr(c, "strike", 0) or 0)
                r = getattr(c, "right", "") or ""
                accion = "BUY" if getattr(ex, "side", "") == "BOT" else "SELL"
                llenas.add((k, r))
                filas.append({"operacion_id": op_id, "fecha": self.fecha, "hora": hora,
                              "strike": k, "right": r, "accion": accion,
                              "precio_ordenado": None, "precio_lleno": getattr(ex, "price", None),
                              "segundos_hasta_fill": None, "lleno": 1, "parcial": 0})
            # parcial: patas esperadas que NO se llenaron (crítico en el vertical)
            faltan = [e for e in esperadas if (e[0], e[1]) not in llenas]
            for k, r, accion in faltan:
                filas.append({"operacion_id": op_id, "fecha": self.fecha, "hora": hora,
                              "strike": k, "right": r, "accion": accion,
                              "precio_ordenado": None, "precio_lleno": None,
                              "segundos_hasta_fill": None, "lleno": 0, "parcial": 1})
            if filas:
                repo.insertar(self.con, "fills", filas)
                self.con.commit()
                if tipo != "piramide":
                    # la pirámide es una compra ADICIONAL sobre la misma operación: si se dejara
                    # pasar, su precio sobrescribiría el precio_largo_pagado de la pata original.
                    self._completar_entrada(op_id, hora, filas)
            if faltan and tipo == "vertical":
                L.notificar("⚠️ FILL PARCIAL del vertical (op #%s): faltó %s — vigilar regla >5%%→single"
                            % (op_id, faltan), "FILL")
            else:
                L.log("fills op #%s: %d pata(s) llena(s)" % (op_id, len(llenas)), "POS")
        except Exception as ex:
            L.log("persistir fills op #%s: %r" % (op_id, ex), "WARN")

    def _enlazar_senal(self, op_id, sen_id):
        """Enlaza operaciones.senal_id con la señal que la originó. Sin esto no se puede
        reconstruir a posteriori QUÉ señal produjo cada operación (quedaba siempre NULL)."""
        if not op_id or not sen_id:
            return
        try:
            self.con.execute("update operaciones set senal_id=? where id=?", (sen_id, op_id))
            self.con.commit()
        except Exception as ex:
            L.log("enlazar señal op #%s: %r" % (op_id, ex), "WARN")

    def _completar_entrada(self, op_id, hora, filas):
        """Copia a `operaciones` los precios REALMENTE pagados/cobrados por pata (que hasta
        ahora solo vivían en `fills`) y el bid/ask del momento desde `premium`. Sin esto la
        fila de la operación queda con precio_largo_pagado / precio_corto_cobrado / bid / ask
        en NULL y es imposible auditar a posteriori a qué precio se entró de verdad."""
        try:
            d = {}
            for f in filas:
                if f.get("precio_lleno") is None:
                    continue
                col = "precio_largo_pagado" if f["accion"] == "BUY" else "precio_corto_cobrado"
                d[col] = f["precio_lleno"]
                lado = "largo" if f["accion"] == "BUY" else "corto"
                q = self.con.execute(
                    "select bid,ask from premium where fecha=? and hora=? and strike=? and right=?",
                    (self.fecha, hora, f["strike"], f["right"])).fetchone()
                if q:
                    d["bid_%s" % lado], d["ask_%s" % lado] = q
            if not d:
                return
            self.con.execute("update operaciones set %s where id=?"
                             % ",".join("%s=?" % k for k in d),
                             list(d.values()) + [op_id])
            self.con.commit()
            L.log("op #%s: entrada completada (%s)" % (op_id, ", ".join(sorted(d))), "POS")
        except Exception as ex:
            L.log("completar entrada op #%s: %r" % (op_id, ex), "WARN")

    def _credito_real(self, trade):
        """Crédito NETO por contrato realmente ejecutado en una orden de cierre, leyendo
        execution.price de ib_insync (SELL suma, BUY resta). Devuelve None si no llegó ningún
        fill -> el caller cae a la estimación teórica. Se separa del P&L teórico porque
        `(mid - ask)` usa precios de la CADENA: sirve para decidir, no para contabilizar.
        Salta el fill agregado del combo (secType='BAG'), igual que _persistir_fills."""
        if trade is None:
            return None
        try:
            self.ib.ib.sleep(3)
            neto, hubo = 0.0, False
            for f in list(getattr(trade, "fills", []) or []):
                ex = getattr(f, "execution", None)
                c = getattr(f, "contract", None)
                if ex is None or c is None or getattr(c, "secType", "") == "BAG":
                    continue
                px = getattr(ex, "price", None)
                if px is None:
                    continue
                hubo = True
                neto += px if getattr(ex, "side", "") == "SLD" else -px
            return neto if hubo else None
        except Exception as ex:
            L.log("crédito real: %r" % ex, "WARN")
            return None

    def _persistir_cierre(self, hora, spot, razon, pnl):
        self.con.execute(
            "update operaciones set hora_salida=?, spy_salida=?, razon_salida=?, pnl=? "
            "where fecha=? and hora_salida is null", (hora, spot, razon, pnl, self.fecha))
        self.con.commit()

    # ─────────────────────────── loop principal ───────────────────────────
    def correr(self):
        if not self.arrancar():
            self.ib.desconectar()
            return
        L.notificar("Sistema EN MARCHA — esperando barras (todo activo)", "ARRANQUE")
        try:
            while True:
                ahora = datetime.now(_ET)
                hora = ahora.strftime("%H:%M")
                if hora >= "16:00":
                    L.notificar("Cierre de mercado — fin de sesión", "FIN")
                    break
                if "09:30" <= hora <= "16:00" and hora != self._ultimo_min:
                    self._ultimo_min = hora
                    try:
                        self._sincronizar_barra(ahora)   # trae y guarda la última barra SPY
                        self.paso(hora)
                    except Exception as ex:
                        L.error("paso %s falló" % hora, ex)
                self.ib.ib.sleep(5)
        except KeyboardInterrupt:
            L.notificar("Detenido por el usuario", "FIN")
        finally:
            if self.pos is not None:
                L.notificar("⚠️ quedaba posición abierta al terminar — revisar manualmente", "RIESGO")
            self.ib.desconectar()
            self.con.close()

    def _sincronizar_barra(self, ahora):
        """Trae las últimas barras 1-min del SPY y las guarda CON SU PROPIA HORA (fuente='live').

        ⚠️ BUG CORREGIDO 2026-08-17 (era GRAVE): antes hacía `b = bars[-1]` y la etiquetaba con
        `h = ahora.strftime("%H:%M")`, o sea con la hora ACTUAL en vez de la de la barra. Como
        reqHistoricalData devuelve la última barra CERRADA (la del minuto anterior), el sistema
        archivaba el precio de las 11:03 como si fuera de las 11:04: un DESPLAZAMIENTO
        SISTEMÁTICO de 1 minuto en toda la serie.
        MEDIDO sobre la sesión del 2026-08-17 (391 minutos): solo 19 coincidían con el valor real
        (4,9%), error mediano 0,06 pts y hasta 0,54. Con esos precios mal fechados se calculaban
        el Supertrend, el ORB y todas las rupturas. Coste concreto de ese día: el ORB de las 11:04
        no disparó (veía 775,44 en vez de 775,50 contra un techo de 775,48) y era una operación
        de +125$ sobre una cuenta de 600$.
        Se descarta la barra del minuto EN CURSO (todavía no ha cerrado).
        """
        try:
            bars = self.ib.backfill_spy(dur="120 S", bar="1 min")
            h_actual = ahora.strftime("%H:%M")
            n = 0
            for b in (bars or []):
                d = b.date
                h = d.strftime("%H:%M") if hasattr(d, "strftime") else str(d)[11:16]
                fk = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                if fk != self.fecha or h >= h_actual:
                    continue          # otra sesión, o barra aún en formación (no cerrada)
                CAP.guardar_barra_spy(self.con, self.fecha, h, b.open, b.high, b.low, b.close,
                                      b.volume, getattr(b, "average", None))
                n += 1
            if n == 0:
                L.log("sincronizar barra: sin barras cerradas nuevas (actual %s)" % h_actual, "WARN")
        except Exception as ex:
            L.log("sincronizar barra: %r" % ex, "WARN")


def main():
    SistemaVivo().correr()


if __name__ == "__main__":
    main()
