# -*- coding: utf-8 -*-
"""Verificacion EN VIVO (solo lectura) de que cada pieza del plan se esta llenando de verdad."""
import sqlite3

c = sqlite3.connect(
    "file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro", uri=True)


def q(sql, *a):
    try:
        return c.execute(sql, a).fetchall()
    except Exception as e:
        return [("ERROR", str(e))]


print("=== TABLAS ===")
print([r[0] for r in q("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])

print("\n=== A) trades ===")
print("filas:", q("SELECT COUNT(*) FROM trades")[0][0])
for r in q("SELECT trade_id,hora_entrada,strike,right,entry_price,delta_entrada,gamma_entrada,"
           "iv_entrada,mfe,hora_salida,razon_salida FROM trades ORDER BY trade_id DESC LIMIT 5"):
    print("  ", r)

print("\n=== A) posicion_minuto (recorrido) ===")
print("filas:", q("SELECT COUNT(*) FROM posicion_minuto")[0][0])
print("por tipo:", q("SELECT tipo,COUNT(*) FROM posicion_minuto GROUP BY tipo"))
for r in q("SELECT trade_id,hora,tipo,bid,ask,mid,pnl,delta,gamma,theta,iv "
           "FROM posicion_minuto ORDER BY rowid DESC LIMIT 6"):
    print("  ", r)

print("\n=== B) cum_net / day_net ===")
print("strike_accum con cum_net no nulo:",
      q("SELECT COUNT(*) FROM strike_accum WHERE cum_net IS NOT NULL")[0][0],
      "de", q("SELECT COUNT(*) FROM strike_accum")[0][0])
for r in q("SELECT expiry,strike,right,cum_prem,cum_net FROM strike_accum "
           "WHERE cum_net IS NOT NULL ORDER BY ABS(cum_net) DESC LIMIT 6"):
    print("   %s %7.0f%s  bruto=%14.0f  NETO=%+14.0f" % r)
print("strike_daily con day_net:",
      q("SELECT COUNT(*) FROM strike_daily WHERE day_net IS NOT NULL")[0][0])

print("\n=== C) instrumentacion de la senal ===")
print("ta_minute con diff:", q("SELECT COUNT(*) FROM ta_minute WHERE diff IS NOT NULL")[0][0],
      "de", q("SELECT COUNT(*) FROM ta_minute")[0][0])
for r in q("SELECT hora,diff,thr,momentum,net_call_1m,net_put_1m,net_call_5m,net_put_5m,"
           "net_call_15m,net_put_15m FROM ta_minute WHERE diff IS NOT NULL "
           "ORDER BY hora DESC LIMIT 5"):
    print("  ", r)

print("\n=== D) GAP 17: spot y spot_stale ===")
for r in q("SELECT hora,spot,spot_stale FROM walls_snapshot ORDER BY rowid DESC LIMIT 8"):
    print("   %s  spot=%.2f  stale=%s" % r)

print("\n=== salud general ===")
print("ta_minute ultima:", q("SELECT MAX(hora) FROM ta_minute")[0][0])
print("walls ultima:", q("SELECT MAX(hora) FROM walls_snapshot")[0][0])
print("premium_minute:", q("SELECT COUNT(*) FROM premium_minute")[0][0])
print("transitions:", q("SELECT COUNT(*) FROM transitions")[0][0])
print("integrity:", q("PRAGMA integrity_check")[0][0])
