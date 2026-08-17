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
from sys2.core.supertrend import mm
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
        da = self.con.execute("select maximo,minimo,cierre from dia_anterior where fecha=?",
                              (self.fecha,)).fetchone()
        if da:
            self.prev = (da[0], da[1], da[2])
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
        Sen, L_, ks, ik, sp = pipeline.construir_sen(bars, cl_, PM, ph, pl, pc)
        dia = [(h, hi, lo, cl) for h, hi, lo, cl in self.con.execute(
            "select hora,close,close,close from bars_etf where ticker='DIA' and fecha=?", (self.fecha,))]
        tlt = [(h, hi, lo, cl) for h, hi, lo, cl in self.con.execute(
            "select hora,close,close,close from bars_etf where ticker='TLT' and fecha=?", (self.fecha,))]
        self.nq = self.unidades_base * (2 if (C.DIABUENO and R.dia_bueno(cl_, dia, tlt)) else 1)
        self.nq = min(self.nq, autocalibra.TOPE_UNIDADES)

        # 3) valorar posición desde la cadena viva
        if self.pos:
            self._valorar(spot, pm_h)

        # 4) gestión: salida (flip/aplanar/mercado) + rodar/piramidar
        if self.pos:
            self._gestionar(hora, spot, Sen, pm_h)

        # 5) apertura
        if self.pos is None and hora in Sen and SAL.puede_abrir(hora, self.hechas):
            self._abrir(hora, spot, Sen[hora], pm_h)

        # 6) verificación de posición plana al final
        if SAL.debe_verificar_plana(hora) and self.pos is not None:
            L.notificar("⚠️ POSICIÓN ABIERTA a las %s — forzando cierre a MERCADO (asignación §12)" % hora, "RIESGO")
            self._cerrar(hora, spot, "cierre", a_mercado=True)

        # 7) volcar estado para el PANEL (desde la BD; el panel NO consulta IBKR)
        fase = "ORDEN" if self.pos else ("SEÑAL" if hora in Sen else "ESPERA")
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
            d = {
                "fase": fase, "capital": capital,
                "pnl_hoy": pnl_hoy, "pnl_hoy_pct": (100 * pnl_hoy / base_hoy) if base_hoy else 0,
                "pnl_mes": pnl_mes, "pnl_mes_pct": (100 * pnl_mes / base_mes) if base_mes else 0,
                "reloj": hora, "conectado": self.ib.conectado(), "datos": "1m",
                "ops": "%d/%d" % (self.hechas, C.MAX_TRADES),
                "unidades": (self.pos.get("nq") if self.pos else self.nq),
                "nivel": self.cfg["nivel"], "version": self.cfg["version"],
                "tope": int(self.cfg["tope"]), "meta": self.cfg["meta"],
                "contrato": None,
            }
            if self.pos:
                p = self.pos
                if p.get("vert"):
                    d["contrato"] = "%s %.0f%s/%.0f%s" % (self.expiry, p["k"], p["rt"], p["ks"], p["rt"])
                    d["debito"] = round(p["ask"] * 100 / 1.01)     # débito inicial $ (ask=(débito)*1.01)
                else:
                    d["contrato"] = "%s %.0f%s" % (self.expiry, p["k"], p["rt"])
                    d["debito"] = round(p["ask"] * 100 / 1.01)
                d["mid"] = round(p["mid"] * 100)
                ent = p.get("h0")
                d["entrada"] = ent
                d["duracion"] = "%dm" % max(0, mm(hora) - mm(ent)) if ent else "—"
                d["mid_pct"] = (100 * (p["mid"] - p["ask"]) / p["ask"]) if p["ask"] else 0
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

    def _gestionar(self, hora, spot, Sen, pm_h):
        p = self.pos
        razon = SAL.decidir_salida(p, Sen.get(hora), hora)
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
                self.ib.comprar_single(self.expiry, e[0], p['rt'], e[1][0], self.nq)
                p['extra'] = {'k': e[0], 'ask': e[1][0] * 1.01, 'mid': e[1][0]}
                L.notificar("PIRAMIDAR: +1 single %s %.0f" % (p['rt'], e[0]), "GESTION")
        # rodar
        elif (not p['extra'] and p['rod'] < C.ROD_MAX and hora < C.ROD_HASTA
              and dl is not None and dl < C.ROD_DELTA):
            L.notificar("RODAR: delta %.2f<%.2f (rod %d)" % (dl, C.ROD_DELTA, p['rod'] + 1), "GESTION")
            self._cerrar(hora, spot, "rodar", a_mercado=False, rodando=True)

    def _abrir(self, hora, spot, rt, pm_h):
        # ratio call/put OTM (veto)
        if C.RUMB:
            rr = R.ratio_otm(pm_h, spot)
            if rr is not None and ((rt == 'C' and rr < C.RUMB) or (rt == 'P' and rr > 1.0 / C.RUMB)):
                L.log("apertura %s %s VETADA por ratio_otm=%.2f" % (hora, rt, rr), "SENAL")
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
                self.ib.comprar_vertical(self.expiry, kl, ksh, rt, pl_ - psh, self.nq)
                self.pos = {'k': kl, 'ks': ksh, 'rt': rt, 'ask': (pl_ - psh) * 1.01, 'mid': pl_ - psh,
                            'rod': 0, 'extra': None, 'h0': hora, 'd0': d0, 'vert': True, 'nq': self.nq}
                self._persistir_operacion(hora, spot, "vertical", rt, kl, ksh, pl_ - psh, d0)
            # con ANCHO activo, si NO hay vertical disponible se DESCARTA la señal (espeja el motor:
            # no cae al single). Solo se opera single cuando ANCHO es None.
            return
        e = I.elegir(cd, spot, hora, rt, "presupuesto", C.TOPE)
        if e:
            s_ = _iv(e[1][0], spot, e[0], hora, rt == 'C')
            if s_:
                d0 = _delta(spot, e[0], hora, s_, rt == 'C')
            self.ib.comprar_single(self.expiry, e[0], rt, e[1][0], self.nq)
            self.pos = {'k': e[0], 'rt': rt, 'ask': e[1][0] * 1.01, 'mid': e[1][0], 'rod': 0,
                        'extra': None, 'h0': hora, 'd0': d0, 'nq': self.nq}
            self._persistir_operacion(hora, spot, "single", rt, e[0], None, e[1][0], d0)

    def _cerrar(self, hora, spot, razon, a_mercado=False, rodando=False):
        p = self.pos
        if p.get('vert'):
            self.ib.cerrar_vertical(self.expiry, p['k'], p['ks'], p['rt'], p.get('nq', 1),
                                    a_mercado=a_mercado, credito=p['mid'])
        else:
            self.ib.cerrar_single(self.expiry, p['k'], p['rt'], p.get('nq', 1),
                                  a_mercado=a_mercado, precio=p['mid'])
        pnl = (p['mid'] - p['ask']) * 100 - C.COMISION
        if p['extra']:
            self.ib.cerrar_single(self.expiry, p['extra']['k'], p['rt'], p.get('nq', 1),
                                  a_mercado=a_mercado, precio=p['extra']['mid'])
            pnl += (p['extra']['mid'] - p['extra']['ask']) * 100 - C.COMISION
        L.notificar("CIERRE (%s) %s -> P&L≈%+.0f$ x%d" % (razon, p['rt'], pnl, p.get('nq', 1)), "CIERRE")
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
    def _persistir_operacion(self, hora, spot, tipo, rt, kl, ks, debito, d0):
        repo.insertar(self.con, "operaciones", [{
            "fecha": self.fecha, "n_op_dia": self.hechas + 1, "tipo": tipo, "right": rt,
            "strike_largo": kl, "strike_corto": ks, "ancho": C.ANCHO, "qty": self.nq,
            "nivel": self.cfg["nivel"], "modo": self.cfg["modo"], "tope": C.TOPE, "unidades": self.nq,
            "hora_entrada": hora, "spy_entrada": spot, "debito_neto": debito,
            "delta_entrada": d0, "moneyness": (spot - kl) if rt == 'C' else (kl - spot),
        }])
        self.con.commit()
        L.log("operación abierta persistida: %s %s L=%s S=%s débito=%.2f" % (tipo, rt, kl, ks, debito), "POS")

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
        """Trae la última barra 1-min del SPY y la guarda (fuente='live')."""
        try:
            bars = self.ib.backfill_spy(dur="120 S", bar="1 min")
            if bars:
                b = bars[-1]
                h = ahora.strftime("%H:%M")
                CAP.guardar_barra_spy(self.con, self.fecha, h, b.open, b.high, b.low, b.close,
                                      b.volume, getattr(b, "average", None))
        except Exception as ex:
            L.log("sincronizar barra: %r" % ex, "WARN")


def main():
    SistemaVivo().correr()


if __name__ == "__main__":
    main()
