# -*- coding: utf-8 -*-
"""COLD RUN de la señal Supertrend-3min en vivo (spy_direction._st3_dir).
   Espejo del cambio de 2026-08-14 (USAR_ST3): valida que la señal en vivo es EJECUTABLE
   (anti look-ahead) y REPLICA el Supertrend del backtest, sin conectarse a IBKR.

   El vivo usa self.bars_st3 = barras 1-min CON premarket (useRTH=False), reset diario. Aca se
   simula ese stream: se alimenta obj.bars_st3 con las barras (premarket+RTH) de un dia real y
   se hace crecer minuto a minuto (la ultima barra = EN FORMACION). Dos validaciones:
     (1) ANTI LOOK-AHEAD: en cada paso _st3_dir() == referencia independiente (ST del ultimo
         bucket de 3-min CERRADO antes de la barra en formacion). 100% de los pasos.
     (2) REPLICA DEL BACKTEST: la SECUENCIA de direcciones de los flips que emite el vivo ==
         la secuencia de flips de sen_Nmin(bars,3) del backtest (analisis/exp_st_flip), que es
         la funcion de señal validada en 2 años. (El vivo actua en label+3 = confirmacion.)
   PASA si ambas se cumplen.
"""
import os, sys, sqlite3
from datetime import datetime
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "analisis"))
try:
    import logging as _lg
    import spy_direction as _S
    from spy_direction import _supertrend_dir, SpyDirection, ST3_TF_MIN, ST3_PER
    from exp_st_flip import sen_Nmin
except Exception as e:
    print("FALLO import:", e); sys.exit(1)

# 2026-08-14: desde que _st3_dir LOGUEA, este cold run escribia sus 720 pasos en el
# spy_activity.log de PRODUCCION y ensuciaba la sesion real. Mismo silenciado que m1m2_coldrun.
for _l in (_S.ACT, _S.LOG):
    _l.handlers = []
    _l.addHandler(_lg.NullHandler())

DB = os.path.join(REPO, "spy_bars_year.db")
DIA = "2026-03-10"

class _Bar:
    __slots__ = ("high", "low", "close", "date")
    def __init__(self, h, l, c, d): self.high=h; self.low=l; self.close=c; self.date=d

def _bkey(dt, N):
    return dt.replace(minute=(dt.minute // N)*N, second=0, microsecond=0)

def ref_dir(bars_hasta, N):
    """ST del ultimo bucket cerrado ANTES de la barra en formacion. Reset diario."""
    forming = bars_hasta[-1].date; cur = forming.date(); fk = _bkey(forming, N)
    buck = {}
    for b in bars_hasta:
        if b.date.date() != cur: continue
        k = _bkey(b.date, N)
        if k >= fk: continue
        a = buck.get(k)
        if a is None: buck[k] = [b.high, b.low, b.close]
        else: a[0]=max(a[0],b.high); a[1]=min(a[1],b.low); a[2]=b.close
    if len(buck) <= ST3_PER: return None
    order = sorted(buck)
    HI=[buck[k][0] for k in order]; LO=[buck[k][1] for k in order]; CL=[buck[k][2] for k in order]
    D=_supertrend_dir(HI,LO,CL); d = D[-1] if D else 0
    return d if d in (1,-1) else None

def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    # premarket + RTH del dia (como useRTH=False). Afterhours (>16:00) fuera: en el dia real aun
    # no ocurrio cuando el sistema opera.
    filas = con.execute("select hora,high,low,close from bars where fecha=? and hora<='16:00' order by hora",(DIA,)).fetchall()
    con.close()
    if len(filas) < 100:
        print(f"FALLO: dia {DIA} sin barras suficientes ({len(filas)})"); return 1
    y,m,dd = map(int, DIA.split("-"))
    bars = [_Bar(h_, l_, c_, datetime(y,m,dd,int(ho[:2]),int(ho[3:5]))) for ho,h_,l_,c_ in filas]
    prem = sum(1 for b in bars if b.date.strftime("%H:%M") < "09:30")
    print(f"COLD RUN ST-3 · dia {DIA} · TF={ST3_TF_MIN}min per={ST3_PER} · {len(bars)} barras ({prem} premarket)")

    # --- validacion 1: anti look-ahead vs referencia, sobre bars_st3 (ruta real del vivo) ---
    obj = SpyDirection.__new__(SpyDirection); obj.bars = None
    N = ST3_TF_MIN; pasos=0; ok=0; flips_vivo=[]; prev=None
    for i in range(2, len(bars)+1):
        obj.bars_st3 = bars[:i]
        try:
            d = SpyDirection._st3_dir(obj)
        except Exception as e:
            print(f"FALLO: excepcion en _st3_dir paso {i}: {e}"); return 1
        r = ref_dir(bars[:i], N); pasos += 1
        if d == r: ok += 1
        else:
            print(f"FALLO look-ahead en paso {i} ({bars[i-1].date.strftime('%H:%M')}): _st3_dir={d} ref={r}"); return 1
        if d in (1,-1):
            hh = bars[i-1].date.strftime("%H:%M")
            if prev is not None and d != prev and "09:30" <= hh <= "16:00":
                flips_vivo.append("C" if d==1 else "P")
            prev = d

    # --- validacion 2: la secuencia de flips del vivo == la de sen_Nmin (backtest validado) ---
    sen = sen_Nmin([(b.date.strftime("%H:%M"), b.high, b.low, b.close) for b in bars], ST3_TF_MIN)
    flips_bt = [lado for _h,lado in sen]
    print(f"  anti look-ahead: {ok}/{pasos} coinciden con la referencia")
    print(f"  flips vivo    (dir): {flips_vivo}")
    print(f"  flips backtest(dir): {flips_bt}")
    if ok != pasos:
        print("FALLO: divergencia anti look-ahead."); return 1
    if flips_vivo != flips_bt:
        print("FALLO: la secuencia de flips del vivo NO replica el backtest."); return 1
    print("PASS: señal ST-3 ejecutable (anti look-ahead) y replica EXACTA la señal del backtest.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
