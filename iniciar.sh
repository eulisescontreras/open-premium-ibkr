#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TOGGLE del sistema vivo SPY 0DTE.
#   1er click  -> ARRANCA el sistema (en background, escribiendo logs).
#   2do click  -> lo APAGA.
# Doble-clic en Git Bash, o `./iniciar.sh` desde la terminal.
# ─────────────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")" || exit 1
PIDFILE="sys2/vivo/.vivo.pid"
LOGDIR="sys2/vivo/logs"
mkdir -p "$LOGDIR"
HOY="$(date +%Y-%m-%d)"
LOG="$LOGDIR/vivo_$HOY.log"

esta_vivo() {
  [ -f "$PIDFILE" ] || return 1
  local pid; pid="$(cat "$PIDFILE" 2>/dev/null)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null            # 0 si el proceso existe
}

if esta_vivo; then
  PID="$(cat "$PIDFILE")"
  echo "🛑 Apagando el sistema vivo (PID $PID)..."
  kill "$PID" 2>/dev/null
  sleep 2
  kill -9 "$PID" 2>/dev/null
  rm -f "$PIDFILE"
  echo "✅ Sistema DETENIDO."
else
  echo "🚀 Arrancando el sistema vivo SPY 0DTE (todo activo)..."
  # nohup para que siga vivo aunque se cierre la ventana; log al archivo del día
  nohup python -m sys2.vivo.sistema >> "$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  echo "✅ Sistema EN MARCHA (PID $(cat "$PIDFILE"))."
  echo "   Logs:  $LOG"
  echo "   (volvé a hacer click en este archivo para APAGARLO)"
fi
echo ""
read -n 1 -s -r -p "Presioná una tecla para cerrar esta ventana..."
echo ""
