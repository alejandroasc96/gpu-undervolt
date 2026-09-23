#!/bin/bash
set -e

echo "=================================================="
echo " Instalador: Optimizador de Energia NVIDIA (Linux)"
echo "=================================================="

# 1. Verificar dependencias requeridas
MISSING_DEPS=""
command -v nvidia-smi >/dev/null 2>&1 || MISSING_DEPS="$MISSING_DEPS nvidia-smi"
command -v python3 >/dev/null 2>&1    || MISSING_DEPS="$MISSING_DEPS python3"
python3 -c "import gi; gi.require_version('Gtk', '3.0')" 2>/dev/null \
    || MISSING_DEPS="$MISSING_DEPS python3-gi (PyGObject)"

if [ -n "$MISSING_DEPS" ]; then
    echo "Faltan dependencias en tu sistema:"
    echo "$MISSING_DEPS"
    echo "Puedes instalarlas con: sudo apt install python3 python3-gi gir1.2-gtk-3.0"
    exit 1
fi

# 1.1 Diagnóstico de comunicación con el driver NVIDIA
DRIVER_REBOOT_REQUIRED=0
if command -v nvidia-smi >/dev/null 2>&1; then
    SMI_TEST=$(nvidia-smi 2>&1 || true)
    if echo "$SMI_TEST" | grep -qi "version mismatch"; then
        DRIVER_REBOOT_REQUIRED=1
        echo ""
        echo "╔══════════════════════════════════════════════════════════════════╗"
        echo "║  ¡AVISO IMPORTANTE: REINICIO DEL EQUIPO REQUERIDO!              ║"
        echo "╠══════════════════════════════════════════════════════════════════╣"
        echo "║ Se detectó: 'Driver/library version mismatch' en nvidia-smi.     ║"
        echo "║ El sistema ha actualizado los paquetes del driver NVIDIA pero   ║"
        echo "║ el kernel aún tiene cargado en memoria el módulo anterior.       ║"
        echo "║                                                                  ║"
        echo "║ La instalación se completará, pero para que el optimizador       ║"
        echo "║ reconozca tu GPU debes REINICIAR el ordenador:                   ║"
        echo "║   sudo reboot                                                    ║"
        echo "╚══════════════════════════════════════════════════════════════════╝"
        echo ""
    elif echo "$SMI_TEST" | grep -qi "couldn't communicate"; then
        echo ""
        echo "AVISO: nvidia-smi no pudo comunicarse con el driver NVIDIA."
        echo "Verifica que el driver esté cargado o si Secure Boot está bloqueándolo."
        echo ""
    fi
fi

# 2. Determinar directorios de destino
APP_DIR="$HOME/.local/share/nvidia-optimizer"
APPS_MENU_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Escritorio")"

if [ ! -d "$DESKTOP_DIR" ]; then
    if [ -d "$HOME/Desktop" ]; then
        DESKTOP_DIR="$HOME/Desktop"
    elif [ -d "$HOME/Escritorio" ]; then
        DESKTOP_DIR="$HOME/Escritorio"
    else
        mkdir -p "$DESKTOP_DIR"
    fi
fi

mkdir -p "$APP_DIR"
mkdir -p "$APPS_MENU_DIR"

# 3. Copiar archivos y otorgar permisos
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Copiando archivos del optimizador a $APP_DIR..."
cp "$SCRIPT_DIR/gui.py"          "$APP_DIR/"
cp "$SCRIPT_DIR/apply.sh"        "$APP_DIR/"
cp "$SCRIPT_DIR/gpu_detector.py" "$APP_DIR/"
cp "$SCRIPT_DIR/disk_cleaner.py" "$APP_DIR/"
cp "$SCRIPT_DIR/cpu_manager.py"  "$APP_DIR/"
cp "$SCRIPT_DIR/cpu_apply.sh"    "$APP_DIR/"
chmod +x "$APP_DIR/gui.py"
chmod +x "$APP_DIR/apply.sh"
chmod +x "$APP_DIR/disk_cleaner.py"
chmod +x "$APP_DIR/cpu_apply.sh"

# 4. Crear el archivo .desktop para el escritorio
DESKTOP_FILE="$DESKTOP_DIR/nvidia-optimizer.desktop"
echo "Creando acceso directo en el Escritorio ($DESKTOP_FILE)..."

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Optimizador NVIDIA
Comment=Configura perfiles de consumo para GPUs NVIDIA (Ultra Eco, Maximo Rendimiento, etc.) con deteccion automatica de hardware
Exec=$APP_DIR/gui.py
Icon=nvidia-settings
Terminal=false
Categories=Settings;HardwareSettings;System;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

# Marcar como confiable en Cinnamon/Nemo si gio esta presente
if command -v gio >/dev/null 2>&1; then
    gio set -t string "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi

# 5. Instalar tambien en el menu de aplicaciones del sistema
cp "$DESKTOP_FILE" "$APPS_MENU_DIR/"

echo "=================================================="
echo "Instalacion completada con exito!"
echo "Acceso directo creado en: $DESKTOP_FILE"
echo "Disponible tambien en el Menu de Aplicaciones."
if [ "$DRIVER_REBOOT_REQUIRED" = "1" ]; then
    echo ""
    echo "⚠  RECUERDA: Debes reiniciar tu PC ('sudo reboot') para"
    echo "   activar el nuevo driver y permitir la deteccion de la GPU."
fi
echo "=================================================="
