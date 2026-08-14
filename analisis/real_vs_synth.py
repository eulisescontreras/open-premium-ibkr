# -*- coding: utf-8 -*-
"""EL GATE: mismo sistema, mismas señales, PRECIOS REALES vs PRECIOS SINTETICOS.

Corre `simular()` DOS veces por sesion con señales IDENTICAS, cambiando solo la fuente de
precios de las opciones:
    A) db_velas = BD sintetica que genera build_tmp (lo que usa el backtest de 2 años)
    B) db_velas = spy_history_YYYYMMDD.db, con el premium REAL (bid/ask de IBKR)

Si el sistema gana con precios sinteticos y pierde con reales, el backtest esta inflado y
ninguna cifra de la spec se sostiene. Es el paso 3 (PRIORITARIO) del documento congelado.

Ambas corridas usan mid=False, o sea COMPRA AL ASK y VENDE AL BID.

⚠️ CORRECCION 2026-08-14 (error de una version anterior de este comentario): el sintetico SI
   PAGA SPREAD. Hay DOS generadores de premium sintetico y es facil confundirlos:
       synth_premium.genera_synth_db  -> bid = ask = mid   (SIN spread)
       exp_trail_2min.build_tmp       -> bid = mid*0.99, ask = mid*1.01  (2% de spread)
   `backtest_st3_orb.py` importa build_tmp (linea 45), y este script usa B.build_tmp, o sea
   el que SI aplica el 2%. Ademas el spread real medido en los datos es 2,2-2,3%, asi que ese
   2% esta bien calibrado.
   CONSECUENCIA: la diferencia real-vs-sintetico NO se explica por spread ausente. Es sesgo
   del MODELO DE EXTRINSECO casi puro, lo que la hace MAS grave, no menos.

⚠️ Los dias 08-11, 08-12 y 08-13 son los MISMOS con los que se calibra el modelo. Para esos
   la comparacion es IN-SAMPLE y favorece al sintetico. Se marca en la salida.

Uso:  python analisis/real_vs_synth.py
"""
import os
import sqlite3
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "analisis"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import backtest_st3_orb as B
from synth_premium import calibra
from simulador_st import simular, CAPITAL_0


def db_real(fk):
    return os.path.join(RAIZ, "spy_history_%s.db" % fk.replace("-", ""))


def tiene_premium(fk):
    p = db_real(fk)
    if not os.path.exists(p):
        return 0
    c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
    try:
        n = c.execute("select count(*) from premium_minute where fecha=? and expiry=? "
                      "and bid is not null and ask is not null", (fk, fk.replace("-", ""))
                      ).fetchone()[0]
    except Exception:
        n = 0
    c.close()
    return n


def corrida(fk, bars, rth, modelo, fuente):
    """fuente: 'synth' o 'real'. Devuelve (pnl, ops)."""
    dk = fk.replace("-", "")
    if fuente == "synth":
        B.build_tmp(modelo, fk, dk, rth)
        dbv = B.TMP
    else:
        dbv = db_real(fk)
    p = B.sen_principal(bars)
    s = B.orb_senal(bars)
    sen = sorted(s + p)
    if not sen:
        return 0.0, [], sen
    ops, cap = simular(fk, senales=sen, trail=99.0, db_velas=dbv, db_tape=None,
                       expiry=dk, mid=False, mag_umbral=None,
                       size_cap=B.SIZE_CAP, salir_en_flip=True, max_trades=B.MAX_TRADES)
    return cap - CAPITAL_0, ops, sen


def main():
    print("=" * 88)
    print("GATE: PRECIOS REALES vs SINTETICOS, mismas señales")
    print("=" * 88)

    # dias con premium real utilizable
    cand = ["2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]
    dias = []
    for fk in cand:
        n = tiene_premium(fk)
        marca = "CALIBRACION (in-sample)" if fk in B.DIAS_CALIBRACION else "fuera de muestra"
        print("  %s  premium real: %6d filas   %s" % (fk, n, marca if n else "SIN DATOS"))
        if n > 500:
            dias.append(fk)
    if not dias:
        print("\nno hay dias con premium real suficiente")
        return 1

    modelo = calibra(B.DIAS_CALIBRACION)
    print("\n  modelo sintetico calibrado con %s (%d buckets)"
          % (", ".join(B.DIAS_CALIBRACION), len(modelo)))

    # barras de cada sesion, del mismo sitio que usa el backtest
    ses = {fk: (bars, rth) for fk, bars, rth in B.sesiones()}

    print("\n" + "=" * 88)
    print("  %-12s %4s %12s %12s %12s   %s" %
          ("fecha", "ops", "SINTETICO", "REAL", "diferencia", "señales"))
    print("=" * 88)
    tot_s = tot_r = 0.0
    filas = []
    for fk in dias:
        if fk not in ses:
            print("  %-12s  sin barras en spy_bars_year (no evaluable)" % fk)
            continue
        bars, rth = ses[fk]
        ps, ops_s, sen = corrida(fk, bars, rth, modelo, "synth")
        pr, ops_r, _ = corrida(fk, bars, rth, modelo, "real")
        tot_s += ps
        tot_r += pr
        filas.append((fk, len(ops_s), ps, pr))
        print("  %-12s %4d %+11.2f$ %+11.2f$ %+11.2f$   %s"
              % (fk, len(ops_s), ps, pr, pr - ps,
                 " ".join("%s%s" % (h, r) for h, r in sen[:6])))
    print("=" * 88)
    print("  %-12s      %+11.2f$ %+11.2f$ %+11.2f$" % ("TOTAL", tot_s, tot_r, tot_r - tot_s))

    if os.path.exists(B.TMP):
        os.remove(B.TMP)

    print("\n" + "=" * 88)
    print("LECTURA")
    print("=" * 88)
    if tot_s != 0:
        print("  el premium real da un %+.1f%% respecto al sintetico" % (100.0 * (tot_r - tot_s) / abs(tot_s)))
    print("  diferencia por operacion: %+.2f$" % ((tot_r - tot_s) / max(1, sum(f[1] for f in filas))))
    n_ops = sum(f[1] for f in filas)
    n_cal = sum(1 for f in filas if f[0] in B.DIAS_CALIBRACION)
    print("  ⚠️ MUESTRA MINUSCULA: %d sesiones y %d operaciones. No decide nada por si sola,"
          % (len(filas), n_ops))
    print("     pero es la UNICA medicion con precios reales frente a 511 sesiones sinteticas.")
    print("  ⚠️ %d de esas %d sesiones son las de CALIBRACION del modelo: ahi el sintetico"
          % (n_cal, len(filas)))
    print("     juega en casa, y aun asi conviene mirar si pierde.")
    print("  ⚠️ El sintetico SI paga spread: build_tmp genera bid=mid*0.99 / ask=mid*1.01 (2%),")
    print("     y el spread real medido es 2,2-2,3%. Asi que la diferencia NO es spread")
    print("     ausente: es sesgo del MODELO DE EXTRINSECO casi puro. Mas grave, no menos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
