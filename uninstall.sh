#!/bin/bash
echo "=================================================="
echo " Desinstalando: Optimizador de Energía NVIDIA"
echo "=================================================="

APP_DIR="$HOME/.local/share/nvidia-optimizer"
APPS_MENU_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Escritorio")"

# Eliminar accesos directos
echo "➡️ Eliminando accesos directos..."
rm -f "$DESKTOP_DIR/nvidia-optimizer.desktop" 2>/dev/null || true
rm -f "$HOME/Desktop/nvidia-optimizer.desktop" 2>/dev/null || true
rm -f "$HOME/Escritorio/nvidia-optimizer.desktop" 2>/dev/null || true
rm -f "$APPS_MENU_DIR/nvidia-optimizer.desktop" 2>/dev/null || true

# Eliminar carpeta de la aplicación
echo "➡️ Eliminando archivos de la aplicación..."
rm -rf "$APP_DIR"

# Eliminar configuración guardada (perfiles persistidos por la app)
echo "➡️ Eliminando configuración guardada..."
rm -rf "$HOME/.config/nvidia-optimizer"

# Eliminar autostart de sesión del usuario (sin privilegios)
rm -f "$HOME/.config/autostart/nvidia-optimizer-powermizer-gpu"*.desktop 2>/dev/null || true

# Eliminar con privilegios: autostart de sistema y de root + servicios systemd.
# apply.sh crea un servicio por GPU (nvidia-power-limit-gpu<N>.service); aquí se
# limpian todos, incluido el nombre legacy nvidia-power-limit.service.
ROOT_CLEANUP='
    rm -f /root/.config/autostart/nvidia-optimizer-powermizer-gpu*.desktop 2>/dev/null
    rm -f /etc/xdg/autostart/nvidia-optimizer-powermizer-gpu*.desktop 2>/dev/null
    rm -f /root/.config/autostart/nvidia-optimizer*.desktop 2>/dev/null
    rm -f /etc/xdg/autostart/nvidia-optimizer*.desktop 2>/dev/null
    for svc in /etc/systemd/system/nvidia-power-limit*.service; do
        [ -e "$svc" ] || continue
        systemctl disable --now "$(basename "$svc")" 2>/dev/null || true
    done
    rm -f /etc/systemd/system/nvidia-power-limit*.service 2>/dev/null
    systemctl daemon-reload
'

echo "➡️ Desactivando y eliminando servicios systemd y autostart de sistema..."
if command -v pkexec >/dev/null 2>&1; then
    if ! pkexec bash -c "$ROOT_CLEANUP" 2>/dev/null; then
        echo ""
        echo "⚠  No se pudo completar la limpieza con privilegios (pkexec cancelado o fallido)."
    fi
else
    echo ""
    echo "⚠  pkexec no está disponible. Ejecuta manualmente como root:"
    echo "    rm -f /root/.config/autostart/nvidia-optimizer*.desktop"
    echo "    rm -f /etc/xdg/autostart/nvidia-optimizer*.desktop"
    echo "    systemctl disable --now nvidia-power-limit.service 2>/dev/null"
    echo "    systemctl disable --now nvidia-power-limit-gpu*.service 2>/dev/null"
    echo "    rm -f /etc/systemd/system/nvidia-power-limit*.service"
    echo "    systemctl daemon-reload"
fi

echo "=================================================="
echo "✅ Desinstalación completada con éxito."
echo "=================================================="