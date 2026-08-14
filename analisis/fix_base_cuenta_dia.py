# Pone acct_net_open a NULL en estado_intradia del dia, para que la app RECAPTURE la base
# con el saldo real tras el reinicio de la cuenta paper a 400$.
# La app DEBE estar parada antes de ejecutar esto.
import sqlite3, os, shutil, sys

BASE = r"C:\Users\eulis\proyectos\open-premium-ibkr"
DB = os.path.join(BASE, "spy_history_20260814.db")
BAK = os.path.join(BASE, "spy_history_backup_pre-reset-cuenta_20260814.db")
FECHA = "2026-08-14"

shutil.copy2(DB, BAK)
print("BACKUP: %s (%.2f MB)" % (os.path.basename(BAK), os.path.getsize(BAK) / 1024 / 1024))

c = sqlite3.connect(DB, timeout=20)
q = ("SELECT fecha,hora,acct_net_open,n_trades,pnl_realizado,net_call,net_put,estado "
     "FROM estado_intradia WHERE fecha=?")
antes = c.execute(q, (FECHA,)).fetchall()
print("\nANTES  :", antes)

c.execute("UPDATE estado_intradia SET acct_net_open=NULL WHERE fecha=?", (FECHA,))
c.commit()

desp = c.execute(q, (FECHA,)).fetchall()
print("DESPUES:", desp)

# comprobacion: solo debe haber cambiado acct_net_open
ok = True
for a, d in zip(antes, desp):
    for i, (va, vd) in enumerate(zip(a, d)):
        if i == 2:
            if vd is not None:
                ok = False
                print("  FAIL: acct_net_open no quedo en NULL -> %r" % (vd,))
        elif va != vd:
            ok = False
            print("  FAIL: cambio la columna %d: %r -> %r" % (i, va, vd))
n = c.execute("SELECT COUNT(*) FROM trades WHERE fecha=?", (FECHA,)).fetchone()[0]
print("\ntrades de hoy (debe ser 0): %d" % n)
c.close()
print("\n%s" % ("OK: solo se anulo la base del dia, el resto intacto" if ok and n == 0
               else "*** REVISAR ***"))
sys.exit(0 if ok else 1)
