"""RELLENA las tablas de metodos y entrada_minute para el 08-10 y el 08-11.

POR QUE SE PUEDE: todo lo que calculan M1/M2/CLASICO/CONFIRMACION sale de DOS numeros por
minuto (net_call, net_put) que `ta_minute` guarda desde el primer dia. El metodo esta
VALIDADO: reconstruir el 08-12 reproduce `m1_minute` al 100% (282/282 en senal_min y en los
contadores). Aqui se aplica a los dias que no tienen tabla porque se creo despues.

LO QUE SE MARCA Y POR QUE (regla 13): las filas insertadas llevan `origen='reconstruido'`.
Sin esa marca, un analisis futuro tomaria dato calculado por dato medido. Las filas vivas
quedan con origen NULL (que es lo que ya hay) y NO se tocan: se usa INSERT OR IGNORE y se
filtra por fecha, asi que el dia en curso es intocable.

LIMITE DECLARADO: `ta_minute` de esos dias empieza a las 09:55, no a las 09:30. Los contadores
ACUMULADOS (n_up, n_down, marcador, usd_up, usd_down, M1, M2) arrancan por tanto en 09:55 y NO
son identicos a los que produccion habria tenido. La senal del minuto (`senal_min`) SI es
exacta, y con ella todas las reglas no acumuladas. Queda en `origen` para que se sepa.

Uso:  python backfill.py            -> solo INFORMA de lo que haria (no escribe)
      python backfill.py --escribir -> escribe. Requiere la app PARADA.
"""
import sqlite3
import sys

PROD = 'C:/Users/eulis/proyectos/open-premium-ibkr/spy_history.db'
DIAS = ("2026-08-10", "2026-08-11")
ESCRIBIR = "--escribir" in sys.argv
ER_VENTANA, IMPULSO_VENTANA, ER_UMBRAL = 30, 5, 0.30
RETARDO, CONFIRMACION_MIN = 20, 5


def mins(h):
    return int(h[:2]) * 60 + int(h[3:5])


def hm(m):
    return f'{m // 60:02d}:{m % 60:02d}'


con = sqlite3.connect(PROD if ESCRIBIR else f'file:{PROD}?mode=ro', uri=not ESCRIBIR)
con.execute("PRAGMA busy_timeout=8000")

# --- columna `origen` en las 5 tablas (aditiva, patron ya usado en el proyecto) ---
TABLAS = ("m1_minute", "m2_minute", "clasico_minute", "confirmacion_minute", "entrada_minute")
if ESCRIBIR:
    for t in TABLAS:
        try:
            con.execute(f"ALTER TABLE {t} ADD COLUMN origen TEXT")
            print(f"  columna `origen` anadida a {t}")
        except Exception:
            pass

total = {}
for F in DIAS:
    ta = list(con.execute(
        "select hora,spy,net_call,net_put from ta_minute where fecha=? and net_call is not null "
        "and net_put is not null and spy is not null order by hora", (F,)))
    if not ta:
        print(f"{F}: sin datos en ta_minute")
        continue

    spy = {h: s for h, s, _a, _b in ta}
    # DOS listas separadas por metodo: la HISTORIA (hora, estado) que alimenta el retardo, y
    # las FILAS que se insertan. Mezclarlas rompia `efec`, que espera tuplas de 2.
    m1_hist, m2_hist, cl_hist, cf_hist = [], [], [], []
    m1h, m2h, clh, cfh, enh = [], [], [], [], []
    up = dn = 0
    u_up = u_dn = 0.0
    m1_est = m2_est = cl_est = sen_est = conf = None
    m1_r = m2_r = cl_r = sen_r = 0

    for h, s, nc, np_ in ta:
        ac, ap = abs(nc), abs(np_)
        dif = ac - ap
        sen = "UP" if dif > 0 else "DOWN"
        if dif > 0:
            up += 1
            u_up += dif
        else:
            dn += 1
            u_dn += -dif
        m1 = "UP" if up > dn else ("DOWN" if dn > up else "NEUTRAL")
        m2 = "UP" if u_up > u_dn else ("DOWN" if u_dn > u_up else "NEUTRAL")
        m1_r = m1_r + 1 if m1 == m1_est else 1
        m2_r = m2_r + 1 if m2 == m2_est else 1
        m1_est, m2_est = m1, m2
        # CLASICO: mismo criterio que produccion (diff vs umbral adaptativo)
        diff = nc - np_
        thr = max(5000.0, 0.15 * (ac + ap))
        cl = "UP" if diff > thr else ("DOWN" if diff < -thr else "NEUTRAL")
        cl_r = cl_r + 1 if cl == cl_est else 1
        cl_est = cl
        # CONFIRMACION
        sen_r = sen_r + 1 if sen == sen_est else 1
        sen_est = sen
        if sen_r >= CONFIRMACION_MIN:
            conf = sen

        def efec(hist):
            lim = mins(h) - RETARDO
            r = None
            for hh, vv in hist:
                if mins(hh) <= lim:
                    r = vv
                else:
                    break
            return r

        # el EFECTIVO se calcula ANTES de meter el minuto actual: el retardo mira hacia atras
        e1, e2, ec, ef = (efec(m1_hist), efec(m2_hist), efec(cl_hist), efec(cf_hist))
        m1_hist.append((h, m1)); m2_hist.append((h, m2))
        cl_hist.append((h, cl)); cf_hist.append((h, conf))
        # ER e impulso desde la serie de SPY
        v = [spy[hm(mins(h) - i)] for i in range(ER_VENTANA, -1, -1)
             if hm(mins(h) - i) in spy]
        er = None
        if len(v) >= ER_VENTANA // 2:
            br = sum(abs(v[i] - v[i - 1]) for i in range(1, len(v)))
            er = (abs(v[-1] - v[0]) / br) if br > 0 else None
        h0 = hm(mins(h) - IMPULSO_VENTANA)
        imp = (s - spy[h0]) if h0 in spy else None
        reg = "-" if er is None else ("REVERSION" if er < ER_UMBRAL else "TENDENCIA")
        enh.append((F, h, s, er, reg, imp, None, 0, None, None, None, 0,
                    ER_UMBRAL, 0.50, 10, "reconstruido"))

        m1h.append((F, h, s, nc, np_, ac, ap, dif, sen, up, dn, up - dn, m1, m1_r,
                    e1, RETARDO, 0, "reconstruido"))
        m2h.append((F, h, s, nc, np_, ac, ap, dif, sen, u_up, u_dn, u_up - u_dn, m2, m2_r,
                    e2, RETARDO, 0, "reconstruido"))
        clh.append((F, h, s, nc, np_, diff, thr, thr * 0.6, 0.0, 0.0, cl, None, None, cl_r,
                    ec, RETARDO, 0, "reconstruido"))
        cfh.append((F, h, s, nc, np_, ac, ap, dif, sen, sen_r, conf, ef,
                    CONFIRMACION_MIN, RETARDO, 0, "reconstruido"))

    total[F] = len(ta)
    print(f"{F}: {len(ta)} minutos reconstruidos  ({ta[0][0]} -> {ta[-1][0]})")
    print(f"    senal UP={sum(1 for x in m1h if x[8] == 'UP')} "
          f"DOWN={sum(1 for x in m1h if x[8] == 'DOWN')} | "
          f"M1 final={m1h[-1][12]} marcador={m1h[-1][11]:+d} | M2 final={m2h[-1][12]} | "
          f"cambios de senal={sum(1 for i in range(1, len(m1h)) if m1h[i][8] != m1h[i-1][8])}")

    if ESCRIBIR:
        con.executemany(
            "INSERT OR IGNORE INTO m1_minute(fecha,hora,spy,net_call,net_put,abs_call,abs_put,"
            "dif,senal_min,n_up,n_down,marcador,m1,racha,m1_efectivo,retardo_min,recentrado,"
            "origen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", m1h)
        con.executemany(
            "INSERT OR IGNORE INTO m2_minute(fecha,hora,spy,net_call,net_put,abs_call,abs_put,"
            "dif,senal_min,usd_up,usd_down,acumulado,m2,racha,m2_efectivo,retardo_min,"
            "recentrado,origen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", m2h)
        con.executemany(
            "INSERT OR IGNORE INTO clasico_minute(fecha,hora,spy,net_call,net_put,diff,thr,"
            "banda,momentum,mom_min,clasico,estado_real,warn_side,racha,clasico_efectivo,"
            "retardo_min,recentrado,origen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", clh)
        con.executemany(
            "INSERT OR IGNORE INTO confirmacion_minute(fecha,hora,spy,net_call,net_put,"
            "abs_call,abs_put,dif,senal_min,racha,confirmado,confirmado_efectivo,"
            "confirmacion_min,retardo_min,recentrado,origen) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", cfh)
        con.executemany(
            "INSERT OR IGNORE INTO entrada_minute(fecha,hora,spy,er,regimen,impulso,objetivo,"
            "esperando,min_esperando,target,pos,activo,er_umbral,retro_frac,retro_max_min,"
            "origen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", enh)
        con.commit()

if ESCRIBIR:
    print()
    print("ESCRITO. Comprobacion:")
    for t in TABLAS:
        for F in DIAS + ("2026-08-12",):
            n = con.execute(f"select count(1) from {t} where fecha=?", (F,)).fetchone()[0]
            r = con.execute(f"select count(1) from {t} where fecha=? and origen='reconstruido'",
                            (F,)).fetchone()[0]
            print(f"  {t:22s} {F}: {n:4d} filas ({r} reconstruidas)")
else:
    print()
    print("MODO INFORME: no se ha escrito nada. Para escribir: --escribir (con la app PARADA)")
