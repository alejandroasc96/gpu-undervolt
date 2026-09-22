#!/bin/bash
# apply.sh — Aplica perfil de consumo NVIDIA con soporte multi-GPU
# Uso: apply.sh <watts> <gpu_index> <enable_daemon> <eco_min_clock> <eco_max_clock> <powermizer_mode>
#
# Parametros:
#   watts          — Limite de potencia en W. 0 = solo PowerMizer (GPU movil).
#   gpu_index      — Indice de la GPU (0, 1, 2...).
#   enable_daemon  — 1 = crear/activar servicio systemd; 0 = eliminar servicio.
#   eco_min_clock  — Reloj minimo MHz para modo eco (normalmente 300). 0 si no aplica.
#   eco_max_clock  — Reloj maximo MHz para modo eco. 0 = no bloquear relojes (gaming/stock).
#   powermizer_mode — GPUPowerMizerMode de nvidia-settings (0=Adaptativo, 1=MaxPerf, 2=Auto).
set -e

WATTS="${1}"
GPU_INDEX="${2:-0}"
ENABLE_DAEMON="${3:-0}"
ECO_MIN_CLOCK="${4:-300}"
ECO_MAX_CLOCK="${5:-0}"
POWERMIZER_MODE="${6:-2}"

if [ -z "$WATTS" ]; then
    echo "Error: no se especificaron vatios" >&2
    exit 1
fi

SERVICE_NAME="nvidia-power-limit-gpu${GPU_INDEX}.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

# ---- GPU movil: solo PowerMizer, sin power limit ----------------------------
if [ "$WATTS" = "0" ]; then
    /usr/bin/nvidia-settings -a "[gpu:${GPU_INDEX}]/GPUPowerMizerMode=${POWERMIZER_MODE}" \
        >/dev/null 2>&1 || true

    # Directorio autostart del usuario real (incluso si se invoca con sudo/pkexec).
    # pkexec NO propaga SUDO_USER y deja $HOME en /root, pero define PKEXEC_UID
    # con el uid del proceso que lo invoco; sudo -S define SUDO_UID/SUDO_USER.
    TARGET_USER=""
    if [ -n "${PKEXEC_UID}" ] && [ "${PKEXEC_UID}" != "0" ]; then
        TARGET_USER="$(getent passwd "${PKEXEC_UID}" | cut -d: -f1)"
    fi
    if [ -z "${TARGET_USER}" ] && [ -n "${SUDO_UID}" ] && [ "${SUDO_UID}" != "0" ]; then
        TARGET_USER="$(getent passwd "${SUDO_UID}" | cut -d: -f1)"
    fi
    if [ -z "${TARGET_USER}" ]; then
        TARGET_USER="${SUDO_USER:-$USER}"
    fi

    if [ -n "${TARGET_USER}" ] && [ "${TARGET_USER}" != "root" ]; then
        USER_HOME="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
    else
        USER_HOME="$HOME"
    fi

    AUTOSTART_DIR="${USER_HOME}/.config/autostart"
    AUTOSTART_FILE="${AUTOSTART_DIR}/nvidia-optimizer-powermizer-gpu${GPU_INDEX}.desktop"

    # Limpiar la copia antigua que una version previa pudo escribir por error
    # en el HOME de root al ejecutarse via pkexec (autostart inerte).
    rm -f "/root/.config/autostart/nvidia-optimizer-powermizer-gpu${GPU_INDEX}.desktop" \
        2>/dev/null || true

    if [ "$ENABLE_DAEMON" = "1" ] && [ "$POWERMIZER_MODE" != "2" ]; then
        mkdir -p "$AUTOSTART_DIR"
        cat > "$AUTOSTART_FILE" << EOF
[Desktop Entry]
Type=Application
Name=NVIDIA PowerMizer GPU${GPU_INDEX}
Exec=/usr/bin/nvidia-settings -a "[gpu:${GPU_INDEX}]/GPUPowerMizerMode=${POWERMIZER_MODE}"
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
Comment=Aplica el perfil de PowerMizer al iniciar sesion
EOF
        chmod +x "$AUTOSTART_FILE"
        if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ]; then
            chown "$TARGET_USER:$TARGET_USER" "$AUTOSTART_FILE" 2>/dev/null || true
        fi
    else
        rm -f "$AUTOSTART_FILE" 2>/dev/null || true
    fi

    echo "SUCCESS"
    exit 0
fi

# ---- GPU de escritorio con control de consumo --------------------------------

# Activar modo persistencia del driver
/usr/bin/nvidia-smi -i "$GPU_INDEX" -pm 1

if [ "$ECO_MAX_CLOCK" != "0" ] && [ "${ECO_MAX_CLOCK}" -gt 0 ] 2>/dev/null; then
    # ---- Modo Eco: bloquear relojes del nucleo + limitar potencia ----
    /usr/bin/nvidia-smi -i "$GPU_INDEX" -pl "$WATTS"
    /usr/bin/nvidia-smi -i "$GPU_INDEX" -lgc "${ECO_MIN_CLOCK},${ECO_MAX_CLOCK}" \
        2>/dev/null || true
    /usr/bin/nvidia-settings -a "[gpu:${GPU_INDEX}]/GPUPowerMizerMode=${POWERMIZER_MODE}" \
        >/dev/null 2>&1 || true

    if [ "$ENABLE_DAEMON" = "1" ]; then
        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=NVIDIA Power Limit GPU${GPU_INDEX} (${WATTS}W Eco - ${ECO_MAX_CLOCK}MHz)
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/nvidia-smi -i ${GPU_INDEX} -pm 1
ExecStart=/usr/bin/nvidia-smi -i ${GPU_INDEX} -pl ${WATTS}
ExecStart=/usr/bin/nvidia-smi -i ${GPU_INDEX} -lgc ${ECO_MIN_CLOCK},${ECO_MAX_CLOCK}

[Install]
WantedBy=multi-user.target
EOF
        /bin/systemctl daemon-reload
        /bin/systemctl enable "$SERVICE_NAME"
    fi

else
    # ---- Modo Gaming/Stock: liberar bloqueo de relojes + limitar potencia ----
    /usr/bin/nvidia-smi -i "$GPU_INDEX" -rgc 2>/dev/null || true
    /usr/bin/nvidia-smi -i "$GPU_INDEX" -pl "$WATTS"
    /usr/bin/nvidia-settings -a "[gpu:${GPU_INDEX}]/GPUPowerMizerMode=${POWERMIZER_MODE}" \
        >/dev/null 2>&1 || true

    if [ "$ENABLE_DAEMON" = "1" ]; then
        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=NVIDIA Power Limit GPU${GPU_INDEX} (${WATTS}W)
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/nvidia-smi -i ${GPU_INDEX} -pm 1
ExecStart=/usr/bin/nvidia-smi -i ${GPU_INDEX} -rgc
ExecStart=/usr/bin/nvidia-smi -i ${GPU_INDEX} -pl ${WATTS}

[Install]
WantedBy=multi-user.target
EOF
        /bin/systemctl daemon-reload
        /bin/systemctl enable "$SERVICE_NAME"
    fi
fi

# ---- Desactivar daemon si se pide -------------------------------------------
if [ "$ENABLE_DAEMON" = "0" ]; then
    if [ -f "$SERVICE_FILE" ]; then
        /bin/systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        /bin/rm -f "$SERVICE_FILE"
        /bin/systemctl daemon-reload
    fi
fi

echo "SUCCESS"
