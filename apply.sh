#!/bin/bash
set -e

WATTS="$1"
ENABLE_DAEMON="$2"

if [ -z "$WATTS" ]; then
    echo "Error: no watts specified" >&2
    exit 1
fi

SERVICE_FILE="/etc/systemd/system/nvidia-power-limit.service"

# Activar modo persistencia del driver
/usr/bin/nvidia-smi -pm 1

# Exportar variables de pantalla para nvidia-settings si están disponibles
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

if [ "$WATTS" = "70" ]; then
    # Perfil Eco Ultra: Límite de 70W, reloj acotado a 300-650 MHz (fuerza VRAM a 405 MHz) y PowerMizer Ahorro
    /usr/bin/nvidia-smi -pl 70
    /usr/bin/nvidia-smi -lgc 300,650 2>/dev/null || true
    /usr/bin/nvidia-settings -a "[gpu:0]/GPUPowerMizerMode=0" >/dev/null 2>&1 || true

    if [ "$ENABLE_DAEMON" = "1" ]; then
        cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=NVIDIA Power Limit Service (70W Eco Ultra)
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/nvidia-smi -pm 1
ExecStart=/usr/bin/nvidia-smi -pl 70
ExecStart=/usr/bin/nvidia-smi -lgc 300,650

[Install]
WantedBy=multi-user.target
EOF
        /bin/systemctl daemon-reload
        /bin/systemctl enable nvidia-power-limit.service
    fi
else
    # Perfiles estándar / Gaming: liberar frecuencias del reloj y restaurar PowerMizer
    /usr/bin/nvidia-smi -rgc 2>/dev/null || true
    /usr/bin/nvidia-smi -pl "$WATTS"
    /usr/bin/nvidia-settings -a "[gpu:0]/GPUPowerMizerMode=2" >/dev/null 2>&1 || true

    if [ "$ENABLE_DAEMON" = "1" ]; then
        cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=NVIDIA Power Limit Service (${WATTS}W)
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/nvidia-smi -pm 1
ExecStart=/usr/bin/nvidia-smi -rgc
ExecStart=/usr/bin/nvidia-smi -pl ${WATTS}

[Install]
WantedBy=multi-user.target
EOF
        /bin/systemctl daemon-reload
        /bin/systemctl enable nvidia-power-limit.service
    fi
fi

if [ "$ENABLE_DAEMON" = "0" ]; then
    if [ -f "$SERVICE_FILE" ]; then
        /bin/systemctl disable nvidia-power-limit.service 2>/dev/null || true
        /bin/rm -f "$SERVICE_FILE"
        /bin/systemctl daemon-reload
    fi
fi

echo "SUCCESS"
