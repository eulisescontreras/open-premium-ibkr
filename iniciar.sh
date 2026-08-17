#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TOGGLE del sistema vivo SPY 0DTE + PANEL.
#   1er click  -> ARRANCA el sistema (background, logs) y ABRE el panel.
#   2do click  -> APAGA el sistema y CIERRA el panel.
# Doble-clic en Git Bash, o `./iniciar.sh` desde la terminal.
# ─────────────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")" || exit 1
PIDFILE="sys2/vivo/.vivo.pid"
PANELPID="sys2/vivo/.panel.pid"
LOGDIR="sys2/vivo/logs"
mkdir -p "$LOGDIR"
HOY="$(date +%Y-%m-%d)"
LOG="$LOGDIR/vivo_$HOY.log"

# vive el proceso de $1 (por defecto el del sistema)?
esta_vivo() {
  local pf="${1:-$PIDFILE}"
  [ -f "$pf" ] || return 1
  local pid; pid="$(cat "$pf" 2>/dev/null)"
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
  if esta_vivo "$PANELPID"; then
    PPID_="$(cat "$PANELPID")"
    echo "🛑 Cerrando el panel (PID $PPID_)..."
    kill "$PPID_" 2>/dev/null
    sleep 1
    kill -9 "$PPID_" 2>/dev/null
    echo "✅ Panel CERRADO."
  fi
  rm -f "$PANELPID"
else
  echo "🚀 Arrancando el sistema vivo SPY 0DTE (todo activo)..."
  # nohup para que siga vivo aunque se cierre la ventana; log al archivo del día
  nohup python -m sys2.vivo.sistema >> "$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  echo "✅ Sistema EN MARCHA (PID $(cat "$PIDFILE"))."
  echo "   Logs:  $LOG"
  # PANEL (ventana chica): lee sys2/vivo/estado.json, NO consulta IBKR.
  # pythonw = sin consola negra en Windows; si no existe, python normal.
  if esta_vivo "$PANELPID"; then
    echo "ℹ️  Panel ya abierto (PID $(cat "$PANELPID"))."
  else
    PY_GUI="pythonw"
    command -v pythonw >/dev/null 2>&1 || PY_GUI="python"
    nohup "$PY_GUI" -m sys2.vivo.panel >> "$LOG" 2>&1 &
    echo $! > "$PANELPID"
    echo "✅ Panel ABIERTO (PID $(cat "$PANELPID")) con $PY_GUI."
  fi
  echo "   (volvé a hacer click en este archivo para APAGAR sistema + panel)"
fi
echo ""
read -n 1 -s -r -p "Presioná una tecla para cerrar esta ventana..."
echo ""
