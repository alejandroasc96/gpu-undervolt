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

    # Desactivar y eliminar servicio de CPU
    if [ -f /etc/systemd/system/cpu-power-optimizer.service ]; then
        systemctl disable --now cpu-power-optimizer.service 2>/dev/null || true
        rm -f /etc/systemd/system/cpu-power-optimizer.service 2>/dev/null
    fi
    systemctl daemon-reload

    # Restaurar CPU a valores por defecto (De Fábrica)
    NUM_CPUS=$(nproc 2>/dev/null || grep -c "^processor" /proc/cpuinfo 2>/dev/null || echo 1)
    for i in $(seq 0 $((NUM_CPUS - 1))); do
        CPUB="/sys/devices/system/cpu/cpu${i}"
        [ -w "${CPUB}/cpufreq/scaling_governor" ] && echo "powersave" > "${CPUB}/cpufreq/scaling_governor" 2>/dev/null || true
        [ -w "${CPUB}/cpufreq/energy_performance_preference" ] && echo "balance_performance" > "${CPUB}/cpufreq/energy_performance_preference" 2>/dev/null || true
        if [ -r "${CPUB}/cpufreq/cpuinfo_max_freq" ] && [ -w "${CPUB}/cpufreq/scaling_max_freq" ]; then
            cat "${CPUB}/cpufreq/cpuinfo_max_freq" > "${CPUB}/cpufreq/scaling_max_freq" 2>/dev/null || true
        fi
        [ -w "${CPUB}/power/energy_perf_bias" ] && echo 6 > "${CPUB}/power/energy_perf_bias" 2>/dev/null || true
    done
    [ -w /sys/devices/system/cpu/intel_pstate/no_turbo ] && echo 0 > /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || true

    RAPL_PKG="/sys/class/powercap/intel-rapl:0"
    if [ -d "$RAPL_PKG" ] && [ -w "${RAPL_PKG}/constraint_0_power_limit_uw" ]; then
        MAX_UW=$(cat "${RAPL_PKG}/constraint_0_max_power_uw" 2>/dev/null || echo 45000000)
        [ -z "$MAX_UW" ] || [ "$MAX_UW" -eq 0 ] 2>/dev/null && MAX_UW=45000000
        echo "$MAX_UW" > "${RAPL_PKG}/constraint_0_power_limit_uw" 2>/dev/null || true
    fi
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
    echo "    systemctl disable --now nvidia-power-limit*.service 2>/dev/null"
    echo "    systemctl disable --now cpu-power-optimizer.service 2>/dev/null"
    echo "    rm -f /etc/systemd/system/nvidia-power-limit*.service"
    echo "    rm -f /etc/systemd/system/cpu-power-optimizer.service"
    echo "    systemctl daemon-reload"
fi

echo "=================================================="
echo "✅ Desinstalación completada con éxito."
echo "=================================================="