SPY Direction — Open-Premium casero via IBKR (proyecto independiente)
====================================================================

QUE HACE
--------
Solo SPY. Toma el vencimiento MAS CERCANO (0DTE) y los strikes ATM/ITM
(call con strike <= precio, put con strike >= precio; nunca OTM).
Acumula el NETO de premium call vs put desde la apertura y muestra en pantalla:
   UP  (verde)   -> el flujo de calls domina  -> sesgo alcista
   DOWN (rojo)   -> el flujo de puts domina   -> sesgo bajista
   -    (gris)   -> aun sin senal / dentro del umbral
Objetivo: apoyo para SCALPING de SPY. Sin base de datos, todo en memoria.

REQUISITOS
----------
1) IB Gateway abierto y LOGUEADO (cuenta paper).
2) API habilitada en IB Gateway:
   Configure > Settings > API > Settings:
     - [x] Enable ActiveX and Socket Clients
     - Socket port: 4002   (paper)   [live = 4001]
     - [x] Allow connections from localhost / Trusted IP 127.0.0.1
     - (opcional) [x] Read-Only API
3) Suscripcion de datos de opciones en TIEMPO REAL (OPRA) en la cuenta.
   * Sin OPRA en vivo, la app corre pero mostrara "DELAYED" y NO habra
     flujo por-trade real (los datos delayed no traen la cinta tick-by-tick).

COMO CORRER (con Python)
------------------------
   python spy_direction.py

COMO CORRER (ejecutable)
------------------------
   Doble clic en dist\spy_direction.exe  (con IB Gateway abierto).

CONFIG (editar arriba de spy_direction.py)
------------------------------------------
   PORT             4002 paper / 4001 live / 7497-7496 si usas TWS
   CLIENT_ID        7 (cambialo si choca con otra app)
   SIGNAL_THRESHOLD 5000  (US$ de premium neto para cambiar de estado)

NOTIFICACION
------------
Solo BANNER visual (sin sonido). Al detectar un cambio:
  - Banner NARANJA = aviso anticipado "posible giro" (heuristica de momentum).
  - Banner ROJO    = giro CONFIRMADO (el neto call-put cruzo el umbral).
La ventana salta al frente para que lo veas junto a tu grafica.

HISTORIAL (SQLite)
------------------
Se guarda en spy_history.db (JUNTO al .exe). Viaja con la carpeta: si copias
la app a otra maquina, el historial va con ella y se ve al abrirla.
Sin servidor ni configuracion: es un solo archivo.

NOTA HONESTA
------------
Este "Open Premium" es casero (neto de premium call vs put por lado agresor).
NO es identico al numero de MarketSnack (su formula es propietaria/desconocida),
pero captura el mismo concepto direccional. Validar en la apertura del lunes.
