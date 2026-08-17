# -*- coding: utf-8 -*-
"""PANEL compacto del sistema SPY 0DTE (Tkinter, sin dependencias). Muestra qué está haciendo
el sistema, leyendo sys2/vivo/estado.json cada segundo. Chico y sencillo.
Ejecutar: `python -m sys2.vivo.panel`  (o doble-clic en panel.sh).
"""
import tkinter as tk

from sys2.vivo import estado as E

# paleta
BG = "#0a0c0a"; CARD = "#141714"; LINE = "#242824"
VERDE = "#4ade4a"; GRIS = "#7f857f"; BLANCO = "#e8e8e8"; ROJO = "#ff5a5a"
FASES = ["ESPERA", "SEÑAL", "ORDEN", "GESTIÓN", "CIERRE"]


def _col(v):
    """verde si >=0, rojo si <0 (para P&L)."""
    try:
        return VERDE if float(v) >= 0 else ROJO
    except Exception:
        return BLANCO


def _money(v, pct=None):
    try:
        s = "%+.2f$" % float(v)
    except Exception:
        return "—"
    if pct is not None:
        try:
            s += "  (%+.2f%%)" % float(pct)
        except Exception:
            pass
    return s


class Panel:
    def __init__(self, root):
        self.root = root
        root.title("SPY 0DTE")
        root.configure(bg=BG)
        root.geometry("580x420")
        root.minsize(540, 400)
        self.w = {}       # labels dinámicos
        self.fase_lbl = {}
        self._build()
        self._tick()

    # ── helpers de layout ──
    def _card(self, parent):
        return tk.Frame(parent, bg=CARD)

    def _lab(self, parent, txt, fg, font, **kw):
        return tk.Label(parent, text=txt, bg=kw.pop("bg", CARD), fg=fg, font=font, **kw)

    def _build(self):
        F = ("Segoe UI", 9); Fb = ("Segoe UI", 15, "bold"); Fs = ("Segoe UI", 8)
        Fm = ("Segoe UI", 11, "bold")

        # 1) barra de fases
        top = tk.Frame(self.root, bg=BG); top.pack(fill="x", padx=6, pady=(6, 3))
        for i, f in enumerate(FASES):
            c = tk.Frame(top, bg=CARD, highlightbackground=LINE, highlightthickness=1)
            c.grid(row=0, column=i, sticky="nsew", padx=2)
            top.grid_columnconfigure(i, weight=1)
            l = self._lab(c, f, GRIS, ("Segoe UI", 10, "bold"), pady=6)
            l.pack(fill="both", expand=True)
            self.fase_lbl[f] = (c, l)

        # 2) CAPITAL | P&L HOY | P&L MES
        row2 = tk.Frame(self.root, bg=BG); row2.pack(fill="x", padx=6, pady=3)
        for i, (k, tit) in enumerate([("capital", "CAPITAL"), ("pnl_hoy", "P&L HOY"), ("pnl_mes", "P&L MES")]):
            c = self._card(row2); c.grid(row=0, column=i, sticky="nsew", padx=2); row2.grid_columnconfigure(i, weight=1)
            self._lab(c, tit, GRIS, Fs).pack(pady=(6, 0))
            self.w[k] = self._lab(c, "—", BLANCO, Fb); self.w[k].pack(pady=(0, 6))

        # 3) CONTRATO
        c3 = self._card(self.root); c3.pack(fill="x", padx=6, pady=3)
        self._lab(c3, "CONTRATO", GRIS, Fs).grid(row=0, column=0, sticky="w", padx=8, pady=(5, 0))
        self.w["contrato"] = self._lab(c3, "—", BLANCO, Fm); self.w["contrato"].grid(row=1, column=0, sticky="w", padx=8, pady=(0, 6))
        self.w["flecha"] = self._lab(c3, "", GRIS, Fm); self.w["flecha"].grid(row=1, column=1, padx=4)
        self.w["contrato_act"] = self._lab(c3, "", VERDE, Fm); self.w["contrato_act"].grid(row=1, column=2, sticky="e", padx=8)
        self.w["debito"] = self._lab(c3, "", GRIS, Fs); self.w["debito"].grid(row=2, column=0, sticky="w", padx=8, pady=(0, 6))
        self.w["mid"] = self._lab(c3, "", VERDE, Fs); self.w["mid"].grid(row=2, column=2, sticky="e", padx=8, pady=(0, 6))
        c3.grid_columnconfigure(1, weight=1)

        # 4) info row
        row4 = tk.Frame(self.root, bg=BG); row4.pack(fill="x", padx=6, pady=3)
        campos = [("reloj", "⏱"), ("entrada", "ENTRADA"), ("duracion", "DURACIÓN"), ("unidades", "UNIDADES"), ("ops", "OPS HOY")]
        for i, (k, tit) in enumerate(campos):
            c = self._card(row4); c.grid(row=0, column=i, sticky="nsew", padx=2); row4.grid_columnconfigure(i, weight=1)
            self._lab(c, tit, GRIS, Fs).pack(pady=(5, 0))
            self.w[k] = self._lab(c, "—", VERDE, Fm); self.w[k].pack(pady=(0, 5))

        # 5) nivel
        c5 = self._card(self.root); c5.pack(fill="x", padx=6, pady=3)
        self.w["nivel"] = self._lab(c5, "NIVEL —", VERDE, Fm); self.w["nivel"].pack(side="left", padx=8, pady=5)
        self.w["nivel_extra"] = self._lab(c5, "", GRIS, F); self.w["nivel_extra"].pack(side="left", padx=8)
        self.w["meta"] = self._lab(c5, "", VERDE, F); self.w["meta"].pack(side="right", padx=8)

        # 6) status
        c6 = tk.Frame(self.root, bg=BG); c6.pack(fill="x", padx=6, pady=(3, 6))
        self.w["conx"] = self._lab(c6, "● SIN DATOS", GRIS, Fs, bg=BG); self.w["conx"].pack(side="left")
        self.w["status"] = self._lab(c6, "", GRIS, Fs, bg=BG); self.w["status"].pack(side="right")

    # ── refresco ──
    def _tick(self):
        d = E.leer()
        if d:
            self._pintar(d)
        else:
            self.w["conx"].config(text="● SIN DATOS (¿sistema apagado?)", fg=GRIS)
        self.root.after(1000, self._tick)

    def _pintar(self, d):
        # fases
        fase = (d.get("fase") or "").upper()
        for f, (c, l) in self.fase_lbl.items():
            act = (f == fase)
            l.config(fg=BG if act else GRIS, bg=(VERDE if act else CARD))
            c.config(bg=(VERDE if act else CARD))
        # capital / pnl
        cap = d.get("capital")
        self.w["capital"].config(text=("${:,.0f}".format(cap)) if cap is not None else "—", fg=VERDE)
        self.w["pnl_hoy"].config(text=_money(d.get("pnl_hoy"), d.get("pnl_hoy_pct")), fg=_col(d.get("pnl_hoy", 0)))
        self.w["pnl_mes"].config(text=_money(d.get("pnl_mes"), d.get("pnl_mes_pct")), fg=_col(d.get("pnl_mes", 0)))
        # contrato
        con = d.get("contrato")
        self.w["contrato"].config(text=con or "sin posición", fg=(BLANCO if con else GRIS))
        self.w["flecha"].config(text="→" if d.get("contrato_act") else "")
        self.w["contrato_act"].config(text=d.get("contrato_act") or "")
        self.w["debito"].config(text=("DÉBITO: $%s" % d["debito"]) if d.get("debito") is not None else "")
        mid = d.get("mid")
        self.w["mid"].config(text=("MID: $%s (%+.1f%%)" % (mid, d.get("mid_pct", 0))) if mid is not None else "",
                             fg=_col(d.get("mid_pct", 0)))
        # info
        self.w["reloj"].config(text=d.get("reloj") or "—")
        self.w["entrada"].config(text=d.get("entrada") or "—")
        self.w["duracion"].config(text=d.get("duracion") or "—")
        self.w["unidades"].config(text=str(d.get("unidades") or "—"))
        self.w["ops"].config(text=d.get("ops") or "—")
        # nivel
        self.w["nivel"].config(text="NIVEL %s" % (d.get("nivel") if d.get("nivel") is not None else "—"))
        self.w["nivel_extra"].config(text="%s · TOPE: $%s · %s UD"
                                     % (d.get("version") or "—", d.get("tope") if d.get("tope") is not None else "—",
                                        d.get("unidades") or "—"))
        self.w["meta"].config(text=("META: +$%s/MES" % d["meta"]) if d.get("meta") is not None else "")
        # status
        conx = d.get("conectado")
        self.w["conx"].config(text="● CONECTADO: IBKR" if conx else "● DESCONECTADO",
                              fg=(VERDE if conx else ROJO))
        self.w["status"].config(text="DATOS: %s   ÚLT: %s" % (d.get("datos") or "1m", d.get("ultima_act") or "—"))


def main():
    root = tk.Tk()
    Panel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
