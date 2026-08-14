# -*- coding: utf-8 -*-
"""Corre un dia COMPLETO 'todo IBKR' con premium mezclado:
   premium REAL donde existe + SINTETICO (contratos ITM calibrados) donde falta.
   Uso: python analisis/run_dia_completo.py 20260811
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from simulador_st import simular, CAPITAL_0
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth_premium import calibra, extr, spy_min, ttc, DIAS  # reusar (R9)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def R(p): return os.path.join(RAIZ, p)

DK = sys.argv[1] if len(sys.argv) > 1 else "20260811"
FK = f"{DK[:4]}-{DK[4:6]}-{DK[6:]}"

# 1) modelo calibrado con los OTROS dias reales (leave-this-day-out)
cal = [d for d in DIAS if d != FK]
modelo = calibra(cal)
print(f"modelo calibrado con {cal} ({len(modelo)} buckets)")

# 2) tape denso del dia
con = sqlite3.connect(f"file:{R('spy_tape.db')}?mode=ro", uri=True)
listo = con.execute("select count(*) from dias_listos where fecha=?", (FK,)).fetchone()[0]
con.close()
if not listo:
    if DK == "20260812" and os.path.exists(R("spy_tape_ayer.db")):
        denso = R("spy_tape_ayer.db")   # tape live 380k (respaldo mientras baja el IBKR)
        print("tape 08-12: usando spy_tape_ayer.db (live) - IBKR aun en cola")
    else:
        print(f"tape {FK} no listo aun -> abortar"); raise SystemExit(1)
else:
    denso = R(f"spy_tape_{DK}_denso.db")
    if not os.path.exists(denso):
        src = sqlite3.connect(f"file:{R('spy_tape.db')}?mode=ro", uri=True)
        filas = src.execute("select substr(ts,12,8),substr(ts,12,5),price,size from trades "
                            "where fecha=? and price is not null and size is not null and size>0 order by ts", (FK,)).fetchall()
        src.close()
        d = sqlite3.connect(denso)
        d.execute("CREATE TABLE trades_raw (ts_et TEXT,minuto TEXT,price REAL,size REAL,exchange TEXT,cond TEXT)")
        d.executemany("insert into trades_raw values (?,?,?,?,NULL,NULL)", filas); d.commit(); d.close()

# 3) premium mezclado: real donde hay + sintetico donde falta
S = spy_min(FK)
real = {}
con = sqlite3.connect(f"file:{R('spy_history_'+DK+'.db')}?mode=ro", uri=True)
for h, K, r, b, a in con.execute("select hora,strike,right,bid,ask from premium_minute "
                                 "where fecha=? and expiry=? and bid is not null and ask is not null", (FK, DK)):
    real[(h, K, r)] = (b, a)
con.close()
horas_real = set(h for (h, K, r) in real)
mezcla = R(f"spy_prem_mix_{DK}.db")
if os.path.exists(mezcla): os.remove(mezcla)
dm = sqlite3.connect(mezcla)
dm.execute("CREATE TABLE premium_minute (fecha TEXT,hora TEXT,expiry TEXT,strike REAL,right TEXT,bid REAL,ask REAL)")
# reales
for (h, K, r), (b, a) in real.items():
    dm.execute("insert into premium_minute values (?,?,?,?,?,?,?)", (FK, h, DK, K, r, b, a))
# sinteticos SOLO en minutos sin real
nsyn = 0
for h, s in S.items():
    if h in horas_real:
        continue
    k0 = round(s)
    for K in range(k0 - 12, k0 + 13):
        for r in ("C", "P"):
            intr = max(s - K, 0.0) if r == "C" else max(K - s, 0.0)
            dep = (s - K) if r == "C" else (K - s)
            mid = max(intr + extr(modelo, dep, ttc(h)), 0.01)
            dm.execute("insert into premium_minute values (?,?,?,?,?,?,?)", (FK, h, DK, float(K), r, mid, mid))
            nsyn += 1
dm.commit(); dm.close()
print(f"premium mezclado: {len(real)} reales + {nsyn} sinteticos (minutos sin real: {len(S)-len(horas_real)})")

# 4) senales ST premarket
def senales_pm(fk):
    con = sqlite3.connect(f"file:{R('spy_bars_pm.db')}?mode=ro", uri=True)
    b = con.execute("select hora,high,low,close from bars_pm where fecha=? order by hora", (fk,)).fetchall()
    con.close()
    hi=[x[1] for x in b]; lo=[x[2] for x in b]; cl=[x[3] for x in b]; ho=[x[0] for x in b]
    n=len(cl); tr=[0.0]*n
    for i in range(1,n): tr[i]=max(hi[i]-lo[i],abs(hi[i]-cl[i-1]),abs(lo[i]-cl[i-1]))
    atr=[None]*n
    if n>7:
        atr[7]=sum(tr[1:8])/7
        for i in range(8,n): atr[i]=(atr[i-1]*6+tr[i])/7
    tend=[0]*n; fu=fl=None; d=1
    for i in range(n):
        if atr[i] is None: continue
        med=(hi[i]+lo[i])/2; bu=med+3.0*atr[i]; bl=med-3.0*atr[i]
        fu=bu if (fu is None or bu<fu or cl[i-1]>fu) else fu
        fl=bl if (fl is None or bl>fl or cl[i-1]<fl) else fl
        if d==1 and cl[i]<fl: d=-1
        elif d==-1 and cl[i]>fu: d=1
        tend[i]=d
    out=[]; prev=None
    for i in range(n):
        if ho[i]<"09:30" or ho[i]>"16:00": continue
        if tend[i]==0: continue
        if prev is None or tend[i]!=prev: out.append((ho[i],"C" if tend[i]>0 else "P"))
        prev=tend[i]
    return out

sen = senales_pm(FK)
print(f"ST premarket: {len(sen)} sen -> " + "  ".join(f"{h}{r}" for h,r in sen))

# 5) correr (mid)
print("\n" + "="*70)
ops, cap = simular(FK, senales=sen, db_velas=mezcla, db_tape=denso, expiry=DK, mid=True, verbose=True)
print(f"  {FK}: {len(ops)} ops   {cap-CAPITAL_0:+.2f}$ (mid, desde $400)")
