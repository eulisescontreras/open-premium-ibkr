#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Sube TODO lo de sys2/ (código, cold runs, docs, LOGS y datos de sesión) a GitHub.
# Doble-clic en Git Bash, o `./subir.sh`.
# NO sube massive_premium.db ni sys2.db (grandes / regenerables).
# ─────────────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")" || exit 1
echo "📦 Subiendo el sistema a GitHub..."
echo ""

# solo sys2/ (código + cold runs + docs + logs de vivo). Nunca las .db grandes.
git add sys2/
git add iniciar.sh subir.sh 2>/dev/null

if git diff --cached --quiet; then
  echo "ℹ️  No hay cambios nuevos para subir."
else
  MSG="vivo: sesion $(date '+%Y-%m-%d %H:%M') (codigo/logs/datos)"
  git commit --no-verify -m "$MSG"
  echo ""
  echo "⬆️  Empujando a origin/main..."
  if git push origin main; then
    echo "✅ Subido a GitHub."
  else
    echo "❌ Falló el push (revisá conexión / credenciales)."
  fi
fi
echo ""
read -n 1 -s -r -p "Presioná una tecla para cerrar esta ventana..."
echo ""
