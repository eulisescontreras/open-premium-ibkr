# SISTEMA SPY 0DTE — CÓMO PROBARLO EN PAPER (mañana)

## Antes de arrancar (requisitos)
1. **IB Gateway PAPER abierto y logueado**, API habilitada, puerto **4002**.
   (Si usás TWS paper, cambiá `IBKR_PORT` a 7497 en `sys2/config.py`.)
2. Suscripción de datos de mercado de opciones activa en la cuenta paper.
3. `sys2.db` existe (si no: `python -m sys2.db.migrar`).

## Arrancar / apagar
- **Doble-clic en `iniciar.sh`** (Git Bash) → arranca el sistema (todo activo, en background).
- **Doble-clic de nuevo en `iniciar.sh`** → lo apaga.
- O desde la terminal: `./iniciar.sh`
- (Si el doble-clic no lo abre con Git Bash: clic derecho → "Git Bash Here" → `./iniciar.sh`.)

## Ver qué hace (sin dashboard, solo logs + notificaciones)
- Log del día: `sys2/vivo/logs/vivo_AAAA-MM-DD.log` (todo, exhaustivo).
- Notificaciones (compras/ventas/arranque/errores) salen resaltadas con `🔔` en el log y consola.
- Seguir en vivo:  `tail -f sys2/vivo/logs/vivo_$(date +%F).log`

## Subir todo a GitHub (código + logs + datos de la sesión)
- **Doble-clic en `subir.sh`** → hace commit + push de `sys2/` (incluye logs y BD de sesión).

## Qué hace el sistema al arrancar
1. Conecta a IBKR (clientId 17).
2. Lee el saldo → **autocalibra** (elige ancho/tope/unidades según la tabla §13.1, tope 3 contratos).
3. **Backfill**: trae el premarket del SPY (desde 04:00), DIA/TLT y el día anterior → `sys2.db`.
4. Cada minuto (09:30–16:00): captura la cadena 0DTE con greeks reales, calcula las señales
   (6 entradas + 5 reglas + rebote), gestiona la posición (rodar/piramidar) y ejecuta órdenes
   **combinadas BAG** (vertical de débito 4pts) o single. Aplana **15:50**, mercado 15:55,
   verifica plana <16:00. Persiste TODO (bars/premium/operaciones).

## ⚠️ Esto es la PRIMERA vez que corre contra IBKR real
El backtest está reproducido (+72.375$/2 años, +1.4%) y el grafo de decisión pasó un smoke sobre
datos reales, PERO la integración IBKR (conexión, órdenes BAG, fills, greeks reales) se valida
MAÑANA. Cosas a vigilar (los "cabos sueltos" típicos de integración):
- que el backfill traiga ≥390 barras sin huecos;
- que la cadena traiga bid/ask/greeks (no NaN);
- que la orden BAG del vertical **se llene en ambas patas** (si >5% parciales → pasar a single);
- que a las 15:50/15:55 aplane y quede **plana antes de 16:00** (riesgo de asignación).
Ante cualquier rareza: apagar con `iniciar.sh` y revisar el log.
