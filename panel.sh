#!/usr/bin/env bash
# Abre el PANEL del sistema SPY 0DTE (ventana chica). Lee sys2/vivo/estado.json (de la BD),
# NO consulta IBKR. Doble-clic, o `./panel.sh`.
cd "$(dirname "$0")" || exit 1
python -m sys2.vivo.panel
