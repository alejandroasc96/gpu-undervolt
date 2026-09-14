#!/bin/bash
echo "=================================================="
echo " Desinstalando: Optimizador de Energía NVIDIA"
echo "=================================================="

APP_DIR="$HOME/.local/share/nvidia-optimizer"
APPS_MENU_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Escritorio")"
SERVICE_FILE="/etc/systemd/system/nvidia-power-limit.service"

# Eliminar accesos directos
echo "➡️ Eliminando accesos directos..."
rm -f "$DESKTOP_DIR/nvidia-optimizer.desktop" 2>/dev/null || true
rm -f "$HOME/Desktop/nvidia-optimizer.desktop" 2>/dev/null || true
rm -f "$HOME/Escritorio/nvidia-optimizer.desktop" 2>/dev/null || true
rm -f "$APPS_MENU_DIR/nvidia-optimizer.desktop" 2>/dev/null || true

# Eliminar carpeta de la aplicación
echo "➡️ Eliminando archivos de la aplicación..."
rm -rf "$APP_DIR"

# Desactivar servicio systemd si existe
if [ -f "$SERVICE_FILE" ]; then
    echo "➡️ Desactivando y eliminando servicio systemd..."
    pkexec bash -c "systemctl disable --now nvidia-power-limit.service 2>/dev/null; rm -f $SERVICE_FILE; systemctl daemon-reload" 2>/dev/null || true
fi

echo "=================================================="
echo "✅ Desinstalación completada con éxito."
echo "=================================================="
