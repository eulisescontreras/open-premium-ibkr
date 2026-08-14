# -*- coding: utf-8 -*-
"""CORRIDA EN FRIO de _metodo_que_manda(): funcion REAL, no reimplementada.
Comprueba que replica la precedencia del if/elif de _update_signal (ST3 -> MEDIA -> M1 ->
CLASICO) y que con la config REAL de hoy dice ST3.
"""
import os, sys, logging, py_compile
REPO = r"C:\Users\eulis\proyectos\open-premium-ibkr"
sys.path.insert(0, REPO); os.chdir(REPO)

print("=" * 74)
print("0) SINTAXIS del modulo (los cambios de la GUI viven dentro de run_gui)")
print("=" * 74)
try:
    py_compile.compile(os.path.join(REPO, "spy_direction.py"), doraise=True)
    print("  OK  spy_direction.py compila")
except Exception as e:
    print("  FAIL  %s" % e); sys.exit(1)

import spy_direction as S
for _l in (S.ACT, S.LOG):
    _l.handlers = []; _l.addHandler(logging.NullHandler())

print("\n" + "=" * 74)
print("1) CONFIG REAL DE HOY (tal cual esta en el archivo)")
print("=" * 74)
print("  USAR_ST3=%s  USAR_MEDIA=%s  USAR_M1=%s" % (S.USAR_ST3, S.USAR_MEDIA, S.USAR_M1))
real = S._metodo_que_manda()
print("  _metodo_que_manda() = %r" % real)
ok0 = real == "ST3"
print("  => %s" % ("OK: la vista y los logs diran ST3" if ok0 else "FAIL: dice %r" % real))

print("\n" + "=" * 74)
print("2) PRECEDENCIA: las 4 combinaciones, con la FUNCION REAL")
print("=" * 74)
casos = [
    # (ST3,  MEDIA, M1,    esperado)   -- espejo del if/elif de _update_signal
    (True,  True,  True,  "ST3"),
    (True,  False, False, "ST3"),
    (False, True,  True,  "MEDIA"),
    (False, True,  False, "MEDIA"),
    (False, False, True,  "M1"),
    (False, False, False, "CLASICO"),
]
bak = (S.USAR_ST3, S.USAR_MEDIA, S.USAR_M1)
okc = True
for st3, med, m1, esp in casos:
    S.USAR_ST3, S.USAR_MEDIA, S.USAR_M1 = st3, med, m1
    got = S._metodo_que_manda()
    good = got == esp
    okc = okc and good
    print("  ST3=%-5s MEDIA=%-5s M1=%-5s -> %-8s esperado %-8s  %s"
          % (st3, med, m1, got, esp, "OK" if good else "FAIL"))
S.USAR_ST3, S.USAR_MEDIA, S.USAR_M1 = bak

print("\n" + "=" * 74)
print("3) LO QUE ANTES MENTIA (formulas viejas vs la nueva, config de hoy)")
print("=" * 74)
S.USAR_ST3, S.USAR_MEDIA, S.USAR_M1 = True, True, True
viejo_gui = "M1" if S.USAR_M1 else "CLASICO"
viejo_log = "MEDIA" if S.USAR_MEDIA else ("M1" if S.USAR_M1 else "CLASICO")
nuevo = S._metodo_que_manda()
print("  GUI  ANTES: MANDA: %-8s  AHORA: MANDA: %s" % (viejo_gui, nuevo))
print("  LOG  ANTES: MANDA %-9s  AHORA: MANDA %s" % (viejo_log, nuevo))
ok3 = viejo_gui != nuevo and viejo_log != nuevo
print("  => %s" % ("OK: ambas mentian y ahora coinciden con quien decide" if ok3
                   else "revisar"))
S.USAR_ST3, S.USAR_MEDIA, S.USAR_M1 = bak

print("\n" + "=" * 74)
todo = ok0 and okc and ok3
print("  %s" % ("VERIFICADO" if todo else "*** HAY FALLOS ***"))
sys.exit(0 if todo else 1)
