# -*- coding: utf-8 -*-
"""SIMULADOR DE CONTRATOS (READ-ONLY) — el motor con el que se encontro la señal de la media.

No toca `spy_history.db` (se abre con ?mode=ro). No toca produccion.

POR QUE EXISTE: ningun script anterior leia `premium_minute.bid/ask/mid`, asi que no habia
forma de responder "cuanto habria dado esta regla EN DINERO". Sin eso, cualquier teoria es
indemostrable. Reproduce los numeros publicados en investigacion/INVESTIGACION_MEDIA_CORTA.md.

CONVENCIONES DE EJECUCION (declaradas, no implicitas):
  - capital 400$ al empezar CADA dia (el usuario reinicia la cuenta paper; no se arrastra)
  - tope por contrato = 400 * 0.80 = 320$   (CAPITAL_FRAC_MAX)
  - contrato: el ITM mas profundo que quepa (mismo criterio que `_strike_ejecucion`)
  - precios al MID (es lo que los LIMIT del sistema consiguen: sus fills reales fueron al mid)
  - comision 1.72$ por operacion ida+vuelta (medida en `trades.comision`)
  - FLATTEN 15:45, no se abre despues de STOP_NEW 15:40
  - NO se obliga a estar en mercado: sin señal se esta FUERA. En 0DTE estar siempre comprado
    paga theta las 6 horas y es letal (medido: siempre-CALL -360$, siempre-PUT -3$).
  - RETRASO = 1 minuto por defecto: el TA de la vela X se conoce en X+1. Con retraso 0 el
    resultado sube un 29% pero es look-ahead y NO es alcanzable.

Uso:
    python analisis/simulador_media.py
"""
import random
import sqlite3
import statistics as st
import sys

# La consola de Windows es cp1252 y revienta con cualquier caracter fuera de ese mapa
# (mismo `reconfigure` que usan todas las cold runs del proyecto).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = 'file:C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db?mode=ro'
CAP0, TOPE, COM = 400.0, 320.0, 1.72
FLATTEN, STOP_NEW = '15:45', '15:40'
DIAS = ('2026-08-11', '2026-08-12')


class Dia:
    """Todos los datos de un dia, cargados una vez."""

    def __init__(self, f):
        c = sqlite3.connect(DB, uri=True)
        self.fecha = f
        self.b = list(c.execute(
            "select hora,open,high,low,close,volume from bars_minute where fecha=? order by hora",
            (f,)))
        self.horas = [x[0] for x in self.b]
        self.close = {x[0]: x[4] for x in self.b}
        self.P = {}
        for stk, rt, h, mid in c.execute(
                """select strike,right,hora,mid from premium_minute
                   where fecha=? and expiry=? and mid is not null and mid>0""",
                (f, f.replace('-', ''))):
            self.P[(stk, rt, h)] = mid
        self.media = {h: (s, v) for h, s, v in c.execute(
            "select hora,spy,vwap from ta_minute where fecha=? and vwap is not null", (f,))}
        c.close()

    def elegir(self, rt, h, tope=TOPE):
        """El ITM mas profundo que quepa = el mas CARO dentro del tope (criterio de produccion)."""
        cand = [(s, m) for (s, r, hh), m in self.P.items()
                if r == rt and hh == h and m * 100 <= tope]
        return max(cand, key=lambda x: x[1]) if cand else None


def correr(d, decidir, minutos):
    """decidir(i, h) -> 'C' | 'P' | None. Ejecucion identica para todo candidato."""
    cap, pos, ops = CAP0, None, []
    for i, h in enumerate(d.horas):
        if pos:
            m = d.P.get((pos['strike'], pos['right'], h))
            if m is not None:
                pos['mid'] = m
            if ((i - pos['i0']) >= minutos or h >= FLATTEN) and pos['mid'] is not None:
                g = (pos['mid'] - pos['mid0']) * 100 - COM
                cap += g
                ops.append((d.horas[pos['i0']], h, pos['right'], pos['strike'], g))
                pos = None
        if h >= FLATTEN:
            break
        if pos is None and h < STOP_NEW:
            rt = decidir(i, h)
            if rt:
                el = d.elegir(rt, h)
                if el:
                    pos = {'right': rt, 'strike': el[0], 'mid0': el[1], 'i0': i, 'mid': el[1]}
    return cap - CAP0, ops


def señal_media(d, umbral, retraso=1):
    """LA SEÑAL. Se compra HACIA la media (contraintuitivo). `retraso` = minutos que tarda en
    conocerse el dato de la vela cerrada; 1 es lo realista, 0 seria look-ahead."""
    def g(i, h):
        j = i - retraso
        if j < 0:
            return None
        t = d.media.get(d.horas[j])
        if not t:
            return None
        dd = t[0] - t[1]
        if abs(dd) < umbral:
            return None
        return 'P' if dd > 0 else 'C'      # ARRIBA -> PUT ; ABAJO -> CALL
    return g


def azar(semilla, p):
    rnd = random.Random(semilla)
    return lambda i, h: (rnd.choice('CP') if rnd.random() < p else None)


if __name__ == "__main__":
    D = {f: Dia(f) for f in DIAS}
    for f in DIAS:
        print("cargado %s: %d barras, %d precios de contrato, %d minutos con media"
              % (f, len(D[f].b), len(D[f].P), len(D[f].media)))

    print("\n" + "=" * 84)
    print("LA SEÑAL — barrido de umbral x minutos en posicion (suma de los 2 dias)")
    print("=" * 84)
    print("   %-8s" % "umb\\sal" + "".join("%9s" % ("t%d" % N) for N in (6, 8, 10, 12, 15)))
    cel = []
    for umb in (0.12, 0.16, 0.20, 0.24, 0.28):
        fila = "   %-8.2f" % umb
        for N in (6, 8, 10, 12, 15):
            s = sum(correr(D[f], señal_media(D[f], umb), N)[0] for f in DIAS)
            cel.append(s)
            fila += "%9.0f" % s
        print(fila)
    print("   positivas %d/%d | mediana %.0f | min %.0f | max %.0f"
          % (sum(1 for x in cel if x > 0), len(cel), st.median(cel), min(cel), max(cel)))
    print("   ⚠️ leer la REGION, no la celda maxima: solo la columna t8 es positiva en los")
    print("      5 umbrales con ejecucion realista.")

    print("\n" + "=" * 84)
    print("DETALLE de la configuracion vigente (umbral 0.20, salida 8 min)")
    print("=" * 84)
    tot, nops = 0.0, 0
    for f in DIAS:
        g, ops = correr(D[f], señal_media(D[f], 0.20), 8)
        gan = sorted([o[4] for o in ops], reverse=True)
        tot += g
        nops += len(ops)
        print("   %s  %+8.2f$ en %2d ops | ganadoras %d (%.0f%%) | sin la mejor %+8.2f | "
              "sin 3 mejores %+8.2f"
              % (f, g, len(ops), sum(1 for x in gan if x > 0),
                 100.0 * sum(1 for x in gan if x > 0) / len(gan) if gan else 0,
                 g - gan[0] if gan else 0, g - sum(gan[:3])))
    print("   TOTAL 2 dias: %+.2f$ en %d operaciones" % (tot, nops))

    print("\n" + "=" * 84)
    print("CONTROL DE AZAR — misma exposicion al mercado, 300 semillas")
    print("=" * 84)
    tot_min = sum(len(D[f].horas) for f in DIAS)
    p = nops * 8.0 / tot_min
    az = sorted(sum(correr(D[f], azar(sd * 7 + i, p), 8)[0] for i, f in enumerate(DIAS))
                for sd in range(300))
    sup = sum(1 for x in az if x >= tot)
    print("   SEÑAL: %+.2f$   |   AZAR: mediana %+.1f | p90 %+.1f | max %+.1f | %%>0 %.0f%%"
          % (tot, st.median(az), az[270], az[-1], 100.0 * sum(1 for x in az if x > 0) / len(az)))
    print("   semillas que la igualan o superan: %d de 300  ->  p = %.4f  %s"
          % (sup, sup / 300.0, "LA SEÑAL APORTA" if sup <= 15 else "NO SE DISTINGUE DEL AZAR"))

    print("\n" + "=" * 84)
    print("CONTROL DIRECCIONAL — ¿gana una direccion fija? (si ganara, la señal sobraria)")
    print("=" * 84)
    for rt in ('C', 'P'):
        s = sum(correr(D[f], (lambda i, h, r=rt: r if i % 8 == 0 else None), 8)[0] for f in DIAS)
        print("   siempre %s cada 8 min: %+9.2f$" % (rt, s))
    sys.exit(0)
