#!/bin/bash
# cpu_apply.sh — Aplica un perfil de consumo a la CPU y gestiona el daemon systemd.
#
# Uso:
#   cpu_apply.sh <perfil> <enable_daemon> <app_dir>
#
# Parámetros:
#   perfil        — Identificador del perfil: factory | optimal | eco | eco_plus
#   enable_daemon — 1 = crear/activar servicio systemd; 0 = eliminar servicio
#   app_dir       — Ruta de instalación de la app (para el ExecStart del servicio)
#
# Mecanismos utilizados (todos 100 % reversibles via sysfs):
#   • scaling_governor          → powersave (intel_pstate always uses powersave)
#   • energy_performance_preference (EPP)
#   • energy_perf_bias          (EPB, 0=rendimiento … 15=ahorro máximo)
#   • intel_pstate/no_turbo     → 0=Turbo ON, 1=Turbo OFF
#   • scaling_max_freq          → límite de frecuencia máxima
#   • RAPL constraint_0_power_limit_uw (long_term TDP en microwatios)
#
# Nota de seguridad: solo se modifican parámetros de política energética del
# kernel. No se accede a registros MSR de voltaje ni se realizan operaciones
# irreversibles. En cualquier momento, aplicar el perfil "factory" restaura
# el estado original.

set -euo pipefail

PROFILE="${1:-factory}"
ENABLE_DAEMON="${2:-0}"
APP_DIR="${3:-/usr/local/share/nvidia-optimizer}"

SERVICE_NAME="cpu-power-optimizer.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

CPUFREQ_BASE="/sys/devices/system/cpu"
PSTATE_BASE="/sys/devices/system/cpu/intel_pstate"
RAPL_PKG="/sys/class/powercap/intel-rapl:0"

# --------------------------------------------------------------------------
# Función para escribir de forma segura en sysfs (no aborta si falla)
# --------------------------------------------------------------------------
write_sysfs() {
    local path="$1"
    local value="$2"
    if [ -w "$path" ]; then
        echo "$value" > "$path" 2>/dev/null || true
    fi
}

# --------------------------------------------------------------------------
# Detectar número de CPUs lógicos
# --------------------------------------------------------------------------
NUM_CPUS=$(nproc 2>/dev/null || grep -c "^processor" /proc/cpuinfo 2>/dev/null || echo 1)

# --------------------------------------------------------------------------
# Detectar frecuencias reales del hardware
# --------------------------------------------------------------------------
CPUINFO_MAX_KHZ=$(cat "${CPUFREQ_BASE}/cpu0/cpufreq/cpuinfo_max_freq" 2>/dev/null || echo "3500000")
CPUINFO_MIN_KHZ=$(cat "${CPUFREQ_BASE}/cpu0/cpufreq/cpuinfo_min_freq" 2>/dev/null || echo "800000")
BASE_FREQ_KHZ=$(cat "${CPUFREQ_BASE}/cpu0/cpufreq/base_frequency" 2>/dev/null || echo "2600000")

# Frecuencia Eco: 85 % de la máxima, redondeada a 100 MHz
ECO_MAX_KHZ=$(( (CPUINFO_MAX_KHZ * 85 / 100 / 100000) * 100000 ))

# --------------------------------------------------------------------------
# Detectar RAPL y calcular límites proporcionales
# --------------------------------------------------------------------------
RAPL_AVAILABLE=0
RAPL_MAX_UW=0
RAPL_CONSTRAINT="${RAPL_PKG}/constraint_0_power_limit_uw"
RAPL_MAX_FILE="${RAPL_PKG}/constraint_0_max_power_uw"

if [ -d "$RAPL_PKG" ]; then
    RAPL_AVAILABLE=1
    if [ -r "$RAPL_MAX_FILE" ]; then
        RAW=$(cat "$RAPL_MAX_FILE" 2>/dev/null || echo "0")
        if [ "$RAW" -gt 0 ] 2>/dev/null; then
            RAPL_MAX_UW="$RAW"
        fi
    fi
    # Si no hay max real, intentar leer el límite actual como referencia
    if [ "$RAPL_MAX_UW" -eq 0 ] && [ -r "$RAPL_CONSTRAINT" ]; then
        RAPL_MAX_UW=$(cat "$RAPL_CONSTRAINT" 2>/dev/null || echo "45000000")
        # Si también es 0, usar valor conservador Skylake
        [ "$RAPL_MAX_UW" -eq 0 ] && RAPL_MAX_UW=45000000
    fi
    # Valor mínimo de seguridad
    [ "$RAPL_MAX_UW" -eq 0 ] && RAPL_MAX_UW=45000000
fi

# Calcular límites RAPL para cada perfil (en microwatios)
RAPL_OPT_UW=$(( RAPL_MAX_UW * 78 / 100 ))
RAPL_ECO_UW=$(( RAPL_MAX_UW * 56 / 100 ))
RAPL_ECO_PLUS_UW=$(( RAPL_MAX_UW * 40 / 100 ))

# --------------------------------------------------------------------------
# Verificar disponibilidad de EPP y EPB
# --------------------------------------------------------------------------
HAS_EPP=0
EPP_PATH="${CPUFREQ_BASE}/cpu0/cpufreq/energy_performance_preference"
[ -w "$EPP_PATH" ] && HAS_EPP=1

HAS_EPB=0
EPB_PATH="${CPUFREQ_BASE}/cpu0/power/energy_perf_bias"
[ -w "$EPB_PATH" ] && HAS_EPB=1

HAS_PSTATE=0
[ -d "$PSTATE_BASE" ] && HAS_PSTATE=1

# --------------------------------------------------------------------------
# Definir parámetros de cada perfil
# --------------------------------------------------------------------------
case "$PROFILE" in
    factory)
        GOVERNOR="powersave"
        EPP_VAL="balance_performance"
        EPB_VAL=6
        NO_TURBO=0
        MAX_FREQ_KHZ="$CPUINFO_MAX_KHZ"
        RAPL_UW=0   # 0 = sin límite (restaurar máximo)
        ;;
    optimal)
        GOVERNOR="powersave"
        EPP_VAL="balance_power"
        EPB_VAL=8
        NO_TURBO=0
        MAX_FREQ_KHZ="$CPUINFO_MAX_KHZ"
        RAPL_UW="$RAPL_OPT_UW"
        ;;
    eco)
        GOVERNOR="powersave"
        EPP_VAL="power"
        EPB_VAL=12
        NO_TURBO=0
        MAX_FREQ_KHZ="$ECO_MAX_KHZ"
        RAPL_UW="$RAPL_ECO_UW"
        ;;
    eco_plus)
        GOVERNOR="powersave"
        EPP_VAL="power"
        EPB_VAL=15
        NO_TURBO=1
        MAX_FREQ_KHZ="$BASE_FREQ_KHZ"
        RAPL_UW="$RAPL_ECO_PLUS_UW"
        ;;
    *)
        echo "Error: perfil desconocido '$PROFILE'. Usa: factory | optimal | eco | eco_plus" >&2
        exit 1
        ;;
esac

echo "=== Aplicando perfil CPU: ${PROFILE} ==="
echo "    Governor:  ${GOVERNOR}"
echo "    EPP:       ${EPP_VAL}  (disponible: ${HAS_EPP})"
echo "    EPB:       ${EPB_VAL}  (disponible: ${HAS_EPB})"
echo "    Turbo:     $([ "$NO_TURBO" -eq 0 ] && echo 'ON' || echo 'OFF')"
echo "    Max freq:  $((MAX_FREQ_KHZ / 1000)) MHz"
echo "    RAPL:      $([ "$RAPL_UW" -gt 0 ] && echo "$((RAPL_UW / 1000000)) W" || echo 'sin límite')"

# --------------------------------------------------------------------------
# Aplicar en todos los cores
# --------------------------------------------------------------------------
for i in $(seq 0 $((NUM_CPUS - 1))); do
    CPU_PATH="${CPUFREQ_BASE}/cpu${i}/cpufreq"
    PWR_PATH="${CPUFREQ_BASE}/cpu${i}/power"

    # Governor
    write_sysfs "${CPU_PATH}/scaling_governor" "$GOVERNOR"

    # Frecuencia máxima (establecer ANTES de EPP para evitar conflictos)
    write_sysfs "${CPU_PATH}/scaling_max_freq" "$MAX_FREQ_KHZ"

    # EPP
    if [ "$HAS_EPP" -eq 1 ]; then
        write_sysfs "${CPU_PATH}/energy_performance_preference" "$EPP_VAL"
    fi

    # EPB
    if [ "$HAS_EPB" -eq 1 ]; then
        write_sysfs "${PWR_PATH}/energy_perf_bias" "$EPB_VAL"
    fi
done

# --------------------------------------------------------------------------
# Turbo Boost (a nivel de paquete, no por core)
# --------------------------------------------------------------------------
if [ "$HAS_PSTATE" -eq 1 ]; then
    write_sysfs "${PSTATE_BASE}/no_turbo" "$NO_TURBO"
fi

# --------------------------------------------------------------------------
# RAPL: límite de potencia long_term del paquete
# --------------------------------------------------------------------------
if [ "$RAPL_AVAILABLE" -eq 1 ] && [ -w "$RAPL_CONSTRAINT" ]; then
    if [ "$RAPL_UW" -gt 0 ]; then
        write_sysfs "$RAPL_CONSTRAINT" "$RAPL_UW"
    else
        # Restaurar al máximo detectado
        write_sysfs "$RAPL_CONSTRAINT" "$RAPL_MAX_UW"
    fi
fi

# --------------------------------------------------------------------------
# Gestión del servicio systemd
# --------------------------------------------------------------------------

# Resolver ruta al script dentro del directorio de instalación
SCRIPT_PATH="${APP_DIR}/cpu_apply.sh"

if [ "$ENABLE_DAEMON" = "1" ] && [ "$PROFILE" != "factory" ]; then
    echo "=== Creando servicio systemd: ${SERVICE_NAME} ==="
    cat > "$SERVICE_FILE" << UNIT_EOF
[Unit]
Description=CPU Power Profile Optimizer (${PROFILE})
Documentation=https://github.com/alejandroasc96/gpu-undervolt
After=multi-user.target

[Service]
Type=oneshot
# enable_daemon=0 para evitar recursión en la gestión del propio servicio
ExecStart=/bin/bash ${SCRIPT_PATH} ${PROFILE} 0 ${APP_DIR}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT_EOF

    /bin/systemctl daemon-reload
    /bin/systemctl enable "$SERVICE_NAME"
    echo "✓ Servicio habilitado: ${SERVICE_NAME}"

elif [ "$ENABLE_DAEMON" = "0" ] || [ "$PROFILE" = "factory" ]; then
    # Deshabilitar y eliminar el servicio si existe
    if [ -f "$SERVICE_FILE" ]; then
        echo "=== Deshabilitando servicio CPU: ${SERVICE_NAME} ==="
        /bin/systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        /bin/rm -f "$SERVICE_FILE"
        /bin/systemctl daemon-reload
        echo "✓ Servicio eliminado."
    fi
fi

echo "SUCCESS"
