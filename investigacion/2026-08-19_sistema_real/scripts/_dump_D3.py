# Hijo que corre el motor REAL sobre los ULTIMOS DIAS capturados EN VIVO (tabla `premium` de
# sys2.db), no sobre massive. Ventaja: la captura viva tiene 82 contratos/minuto CON BID/ASK
# reales (massive solo trae el close de ~13). Permite comparar el sistema mejorado contra lo
# que REALMENTE hizo el sistema esos dias.
#
# RL_PRECIO: mid (lo que asume el backtest) | ask (peor caso al comprar) | bid (peor al vender)
import json, os, sys, sqlite3
RAIZ = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, RAIZ)
from sys2.backtest import motor

DIAS = (os.environ.get("RL_DIAS") or "2026-08-17,2026-08-18,2026-08-19").split(",")
PREC = os.environ.get("RL_PRECIO", "mid")

con = sqlite3.connect(os.path.join(RAIZ, "sys2.db"))
SES, PREM, ETFB = [], {}, {"DIA": {}, "TLT": {}}

for fk in DIAS:
    rows = con.execute("select hora,open,high,low,close from bars where fecha=? order by hora",
                       (fk,)).fetchall()
    if not rows:
        continue
    bars = [(h, hi, lo, cl) for h, op, hi, lo, cl in rows]
    rth = [(h, cl, hi, lo, cl) for h, op, hi, lo, cl in rows if "09:30" <= h <= "16:00"]
    SES.append((fk, bars, rth))
    dd = {}
    for hora, strike, right, bid, ask, mid in con.execute(
            "select hora,strike,right,bid,ask,mid from premium where fecha=? and expiry=?",
            (fk, fk.replace("-", ""))):
        p = {"mid": mid, "ask": ask, "bid": bid}.get(PREC, mid)
        if p is None:
            p = mid if mid is not None else (ask if ask is not None else bid)
        if p is None or p <= 0:
            continue
        dd.setdefault(hora, {})[(right, float(strike))] = (float(p), 0.0)
    if dd:
        PREM[fk] = dd

for tk in ("DIA", "TLT"):
    for fk, h, cl in con.execute(
            "select fecha,hora,close from bars_etf where ticker=? and fecha in (%s) order by fecha,hora"
            % ",".join("?" * len(DIAS)), [tk] + DIAS):
        ETFB[tk].setdefault(fk, []).append((h, cl, cl, cl))
con.close()

print("dias con cadena viva: %s (precio=%s)" % (sorted(PREM), PREC))
D = motor.SIS70(SES, PREM, ETFB)
json.dump({k: float(v) for k, v in D.items()}, open(sys.argv[1], "w"))
print("RESULTADO: " + "  ".join("%s %+.2f" % (k, v) for k, v in sorted(D.items()))
      + "   TOTAL %+.2f" % sum(D.values()))
