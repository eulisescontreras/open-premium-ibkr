# Tape de HOY agregado por minuto, junto al movimiento del precio.
# net_call/net_put = premium de opciones agredido a COMPRA menos el agredido a VENTA.
# net_spy          = lo mismo con el tape del SUBYACENTE.
# Abre la BD viva en solo-lectura y la cierra en cuanto tiene los datos.
import sqlite3

SRC = "spy_history.db"
TXT = "TAPE_HOY.txt"
DIA = "2026-08-13"

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=15)

# --- tape de opciones agregado por minuto (grupo != SPY) ---
opc = src.execute("""
    select substr(hora,1,5) m, right,
           sum(case when agresor='COMPRA' then premium else 0 end),
           sum(case when agresor='VENTA'  then premium else 0 end),
           count(*)
    from tape where fecha=? and grupo<>'SPY' and right is not null
    group by m, right""", (DIA,)).fetchall()

# --- tape del SPY (subyacente) agregado por minuto ---
spy = src.execute("""
    select substr(hora,1,5) m,
           sum(case when agresor='COMPRA' then premium else 0 end),
           sum(case when agresor='VENTA'  then premium else 0 end),
           count(*)
    from tape where fecha=? and grupo='SPY'
    group by m""", (DIA,)).fetchall()

velas = src.execute("select hora,open,close from bars_minute where fecha=? order by hora",
                    (DIA,)).fetchall()
src.close()
print(f"tape opciones {len(opc)} grupos-minuto | tape SPY {len(spy)} minutos | "
      f"velas {len(velas)}. BD viva CERRADA.")

C = {m: (c, v, n) for m, r, c, v, n in opc if r == "C"}
P = {m: (c, v, n) for m, r, c, v, n in opc if r == "P"}
S = {m: (c, v, n) for m, c, v, n in spy}

O = []
O.append(f"TAPE DE {DIA} POR MINUTO + PRECIO")
O.append("=" * 110)
O.append("acum_call = suma corrida del neto de CALLS (COMPRA - VENTA), los negativos restan")
O.append("acum_put  = lo mismo en PUTS")
O.append("acum_spy  = lo mismo con el tape del SUBYACENTE (sin el x100 del contrato)")
O.append("digitos   = cuantas cifras tiene acum_spy (sin contar el signo)")
O.append("acum/tick = acum_spy dividido entre los ticks_spy de ESE minuto")
O.append("ticks_spy = operaciones del tape del SPY en ese minuto")
O.append("")
O.append(f"{'hora':>7} {'spy':>9} {'cuerpo':>7} "
         f"{'acum_call':>14} {'acum_put':>14} {'acum_spy':>15} "
         f"{'digitos':>8} {'acum/tick':>14} {'ticks_spy':>10}")

acum = ac_call = ac_put = 0.0
for hora, o_, cl in velas:
    cu = round((cl - o_) * 100)
    cC, cV, _ = C.get(hora, (0.0, 0.0, 0))
    pC, pV, _ = P.get(hora, (0.0, 0.0, 0))
    sC, sV, sN = S.get(hora, (0.0, 0.0, 0))
    ac_call += cC - cV
    ac_put += pC - pV
    acum += sC - sV
    dig = len(str(abs(int(round(acum)))))   # cifras del acumulado, sin el signo
    # sin ticks ese minuto no hay division posible: se marca "-" en vez de inventar un 0
    apt = f"{acum/sN:+14.0f}" if sN else f"{'-':>14}"
    dir_ = "UP" if cu > 0 else ("DOWN" if cu < 0 else "DOJI")
    O.append(f"{hora:>7} {cl:9.2f} {dir_:>7} "
             f"{ac_call:+14.0f} {ac_put:+14.0f} {acum:+15.0f} "
             f"{dig:8} {apt} {sN:10}")

with open(TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(O) + "\n")
print(f"escrito {TXT}  ({len(O)} lineas)")
