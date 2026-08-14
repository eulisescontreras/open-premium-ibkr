# -*- coding: utf-8 -*-
"""SOPORTES/RESISTENCIAS de PRECIO sobre las 255 sesiones (no solo 2 dias). ¿Misma historia?
Niveles S/R computables del precio: rango de apertura (OR 30min), max/min previos del dia (running),
cierre del dia anterior, numeros redondos ($1). Señal REBOTE (comprar hacia adentro al tocar el nivel)
y RUPTURA (seguir al romper). Acierto direccional + EV modelado (ITM 3pts, cruce).
Usa bars_historico (OHLC 1-min, 255 dias). Read-only.
"""
import sqlite3, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
DB = "historico_spy.db"; H = 8; TOL = 0.06
DELTA = 0.75; FIJO = 0.29*H + 1.72 + 0.071*100   # 3pt ITM, cruce ~11.14
def mm(h): return int(h[:2])*60+int(h[3:5])

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); d = {}
    for f,h,o,hi,lo,cl in c.execute("select fecha,hora,open,high,low,close from bars_historico order by fecha,hora"):
        d.setdefault(f,[]).append((h,o,hi,lo,cl))
    c.close(); o=sorted(d); return o,d

def niveles_dia(b, prev_close):
    """devuelve funcion nivel(i)->(sops, ress) con los niveles ACTIVOS en el minuto i."""
    his=[x[2] for x in b]; los=[x[3] for x in b]; op=b[0][4]
    or_hi = max(his[:30]) if len(b)>=30 else None
    or_lo = min(los[:30]) if len(b)>=30 else None
    def f(i, tipo):
        cl=b[i][4]
        sops=[]; ress=[]
        # rango de apertura (activo tras 30 min)
        if i>=30 and or_hi is not None:
            ress.append(or_hi); sops.append(or_lo)
        # max/min de la sesion hasta i-1 (running)
        if i>5:
            ress.append(max(his[:i])); sops.append(min(los[:i]))
        # cierre previo
        if prev_close:
            (ress if prev_close>cl else sops).append(prev_close)
        # numeros redondos ($1)
        rr=round(cl)
        if rr>cl: ress.append(float(rr))
        else: sops.append(float(rr))
        return sops, ress
    return f

def test(orden, dias, modo):
    favs=[]
    prev_close=None
    for f in orden:
        b=dias[f]; horas=[x[0] for x in b]; cl=[x[4] for x in b]; hi=[x[2] for x in b]; lo=[x[3] for x in b]; mn=[mm(x[0]) for x in b]
        nivel=niveles_dia(b, prev_close)
        i=1; n=len(b)
        while i<n:
            if horas[i]>="15:40": break
            sops,ress=nivel(i,modo)
            lado=None
            # toca soporte (low cerca) / resistencia (high cerca)
            if any(abs(lo[i]-s)<=TOL for s in sops):
                lado = "C" if modo=="rebote" else None    # rebote: sube desde soporte
                if modo=="ruptura" and cl[i] < min(sops)-TOL: lado="P"
            if lado is None and any(abs(hi[i]-r)<=TOL for r in ress):
                lado = "P" if modo=="rebote" else None
                if modo=="ruptura" and cl[i] > max(ress)+TOL: lado="C"
            if lado is None: i+=1; continue
            fin=[k for k in range(i,n) if mn[k]>=mn[i]+H]
            if not fin: break
            k=fin[0]; ds=cl[k]-cl[i]
            favs.append(ds if lado=="C" else -ds); i=k
        prev_close=cl[-1]
    n=len(favs)
    if not n: return "sin ops"
    acc=100*sum(1 for x in favs if x>0)/n
    mf=sum(favs)/n; ev=DELTA*mf*100-FIJO
    return f"n={n:5d}  acierto={acc:5.1f}%  media_fav={mf:+.4f}  EV/op={ev:+.2f}$"

def main():
    orden,dias=carga()
    print("="*90)
    print("S/R de PRECIO sobre 255 sesiones (rango apertura, running max/min, cierre previo, redondos)")
    print("  contrato ITM 3pts modelado. breakeven acierto ~56.7%")
    print("="*90)
    for modo in ("rebote","ruptura"):
        print(f"  {modo.upper():8} | {test(orden,dias,modo)}")
    print("="*90)
    print("LECTURA: si acierto ~50% y EV<0 -> S/R de precio da la MISMA historia en el largo (no solo 2 dias).")

if __name__=="__main__":
    main()
