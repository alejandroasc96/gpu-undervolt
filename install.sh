#!/bin/bash
set -e

echo "=================================================="
echo " Instalador: Optimizador de Energía NVIDIA (Linux)"
echo "=================================================="

# 1. Verificar dependencias requeridas
MISSING_DEPS=""
command -v nvidia-smi >/dev/null 2>&1 || MISSING_DEPS="$MISSING_DEPS nvidia-smi"
command -v python3 >/dev/null 2>&1 || MISSING_DEPS="$MISSING_DEPS python3"
python3 -c "import gi; gi.require_version('Gtk', '3.0')" 2>/dev/null || MISSING_DEPS="$MISSING_DEPS python3-gi (PyGObject)"

if [ -n "$MISSING_DEPS" ]; then
    echo "⚠️ Faltan dependencias en tu sistema:"
    echo "$MISSING_DEPS"
    echo "Puedes instalarlas con: sudo apt install python3 python3-gi gir1.2-gtk-3.0"
    exit 1
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

# 3. Copiar scripts y otorgar permisos
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "➡️ Copiando archivos del optimizador a $APP_DIR..."
cp "$SCRIPT_DIR/gui.py" "$APP_DIR/"
cp "$SCRIPT_DIR/apply.sh" "$APP_DIR/"
chmod +x "$APP_DIR/gui.py"
chmod +x "$APP_DIR/apply.sh"

# 4. Crear el archivo .desktop para el escritorio
DESKTOP_FILE="$DESKTOP_DIR/nvidia-optimizer.desktop"
echo "➡️ Creando acceso directo en el Escritorio ($DESKTOP_FILE)..."

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=Optimizador GTX 1660
Comment=Configura perfiles de consumo (Ultra Eco, Máxima Eficiencia, Punto Dulce) y persistencia en arranque
Exec=$APP_DIR/gui.py
Icon=nvidia-settings
Terminal=false
Categories=Settings;HardwareSettings;System;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

# Marcar como confiable en Cinnamon/Nemo si gio está presente
if command -v gio >/dev/null 2>&1; then
    gio set -t string "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi

# 5. Instalar también en el menú de aplicaciones del sistema
cp "$DESKTOP_FILE" "$APPS_MENU_DIR/"

echo "=================================================="
echo "✅ ¡Instalación completada con éxito!"
echo "➡️ Acceso directo creado en: $DESKTOP_FILE"
echo "➡️ Disponible también en el Menú de Aplicaciones."
echo "=================================================="
