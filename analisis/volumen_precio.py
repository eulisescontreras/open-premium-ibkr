# -*- coding: utf-8 -*-
"""VOLUMEN + PRECIO del SPY sobre 255 sesiones. Ultima dimension del historico largo sin probar.
Señales (todas con retraso 1, no solapadas, 8 min, contrato ITM 3pts modelado):
  A) pico de volumen + vela de rechazo -> REVERSION (giro con volumen)
  B) pico de volumen + vela direccional -> CONTINUACION (breakout con volumen)
  C) volumen alto + precio bajo la media -> CALL (capitulacion/rebote)
  D) climax: volumen en tercil ALTO del dia + |cambio de precio| grande -> fade (reversion)
Pico = volumen del minuto vs media movil de volumen de los ultimos 20 min (ratio).
Reporta acierto direccional + EV/op. bars_historico (OHLCV 255 dias). Read-only.
"""
import sqlite3, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
DB = "historico_spy.db"; H = 8
DELTA = 0.75; FIJO = 0.29*H + 1.72 + 0.071*100   # 3pt ITM cruce ~11.14
def mm(h): return int(h[:2])*60+int(h[3:5])

def carga():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); d = {}
    for f,h,o,hi,lo,cl,v in c.execute("select fecha,hora,open,high,low,close,volume from bars_historico order by fecha,hora"):
        d.setdefault(f,[]).append((h,o,hi,lo,cl,v))
    c.close(); return sorted(d), d

def run(orden, dias, senal, ratio_min):
    favs=[]
    for f in orden:
        b=dias[f]; horas=[x[0] for x in b]; op=[x[1] for x in b]; hi=[x[2] for x in b]; lo=[x[3] for x in b]
        cl=[x[4] for x in b]; vol=[x[5] for x in b]; mn=[mm(x[0]) for x in b]
        tp=[(hi[t]+lo[t]+cl[t])/3 for t in range(len(b))]
        med=[sum(tp[max(0,t-4):t+1])/min(5,t+1) for t in range(len(b))]
        volavg=[sum(vol[max(0,t-19):t+1])/min(20,t+1) for t in range(len(b))]
        i=1; n=len(b)
        while i<n:
            if horas[i]>="15:40": break
            j=i-1
            if j<20: i+=1; continue
            ratio = vol[j]/volavg[j] if volavg[j] else 0
            lado=None
            if ratio>=ratio_min:
                cuerpo = cl[j]-op[j]            # vela j: verde si >0
                if senal=="rev_rechazo":
                    # rechazo: vela con mecha larga contraria -> revierte
                    lado = "P" if cuerpo>0 else "C"     # volumen alto en vela verde -> agotamiento -> baja
                elif senal=="cont":
                    lado = "C" if cuerpo>0 else "P"     # volumen alto confirma la direccion
                elif senal=="capitulacion":
                    d=cl[j]-med[j]
                    lado = "C" if d<0 else "P"          # volumen alto + lejos de media -> vuelve a la media
            if lado is None: i+=1; continue
            fin=[k for k in range(i,n) if mn[k]>=mn[i]+H]
            if not fin: break
            k=fin[0]; ds=cl[k]-cl[i]
            favs.append(ds if lado=="C" else -ds); i=k
    n=len(favs)
    if not n: return "sin ops"
    acc=100*sum(1 for x in favs if x>0)/n; mf=sum(favs)/n; ev=DELTA*mf*100-FIJO
    return f"n={n:5d}  acierto={acc:5.1f}%  media_fav={mf:+.4f}  EV/op={ev:+.2f}$"

def main():
    orden,dias=carga()
    print("="*92)
    print("VOLUMEN + PRECIO del SPY, 255 sesiones. contrato ITM 3pts. breakeven acierto ~56.7%")
    print("="*92)
    for senal,etq in (("rev_rechazo","pico vol -> REVERSION (agotamiento)"),
                      ("cont","pico vol -> CONTINUACION (confirma direccion)"),
                      ("capitulacion","pico vol + lejos de media -> vuelve a la media")):
        for rm in (1.5, 2.0, 3.0):
            print(f"  [{etq:42}] ratio>={rm}: {run(orden,dias,senal,rm)}")
        print()
    print("="*92)
    print("LECTURA: acierto ~50% y EV<0 -> el volumen del SPY (aun con el precio) no da direccion.")

if __name__=="__main__":
    main()
