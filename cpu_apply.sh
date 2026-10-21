#!/bin/bash
# cpu_apply.sh — Aplica un perfil de consumo a la CPU y gestiona el daemon systemd.
#
# Uso:
#   cpu_apply.sh <perfil> <enable_daemon> <app_dir>
#
# Parámetros:
#   perfil        — Identificador del perfil: factory | optimal | eco | eco_plus
#   enable_daemon — 1 = crear/activar servicio systemd; 0 = eliminar servicio;
#                   apply_only = solo aplicar ajustes sysfs (uso interno del servicio)
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
# Detectar RAPL y calcular límites proporcionales (PL1 long_term y PL2 short_term)
# --------------------------------------------------------------------------
RAPL_AVAILABLE=0
RAPL_MAX_UW=0
RAPL_CONSTRAINT="${RAPL_PKG}/constraint_0_power_limit_uw"
RAPL_MAX_FILE="${RAPL_PKG}/constraint_0_max_power_uw"

RAPL_PL2_AVAILABLE=0
RAPL_CONSTRAINT_1="${RAPL_PKG}/constraint_1_power_limit_uw"

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

    if [ -w "$RAPL_CONSTRAINT_1" ]; then
        RAPL_PL2_AVAILABLE=1
    fi
fi

# Calcular límites RAPL PL1 (long_term) para cada perfil (en microwatios)
RAPL_OPT_UW=$(( RAPL_MAX_UW * 78 / 100 ))       # ~35W
RAPL_ECO_UW=$(( RAPL_MAX_UW * 56 / 100 ))       # ~25W (sostenido)
RAPL_ECO_PLUS_UW=$(( RAPL_MAX_UW * 40 / 100 ))  # ~18W (máximo ahorro sostenido)

# Calcular límites RAPL PL2 (short_term / ráfagas) para cada perfil
RAPL_OPT_PL2_UW=$(( RAPL_MAX_UW * 100 / 100 ))       # 45W
RAPL_ECO_PL2_UW=$(( RAPL_MAX_UW * 93 / 100 ))        # ~42W (margen para picos en juegos indie sin desbocarse a 200W)
RAPL_ECO_PLUS_PL2_UW=$(( RAPL_MAX_UW * 50 / 100 ))   # ~22.5W (estricto, ráfagas contenidas)

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
        RAPL_UW=0       # 0 = sin límite (restaurar máximo)
        RAPL_PL2_UW=0   # 0 = restaurar sin límite (200W)
        ;;
    optimal)
        GOVERNOR="powersave"
        EPP_VAL="balance_power"
        EPB_VAL=8
        NO_TURBO=0
        MAX_FREQ_KHZ="$CPUINFO_MAX_KHZ"
        RAPL_UW="$RAPL_OPT_UW"
        RAPL_PL2_UW="$RAPL_OPT_PL2_UW"
        ;;
    eco)
        GOVERNOR="powersave"
        EPP_VAL="power"
        EPB_VAL=12
        NO_TURBO=0
        MAX_FREQ_KHZ="$ECO_MAX_KHZ"
        RAPL_UW="$RAPL_ECO_UW"
        RAPL_PL2_UW="$RAPL_ECO_PL2_UW"
        ;;
    eco_plus)
        GOVERNOR="powersave"
        EPP_VAL="power"
        EPB_VAL=15
        NO_TURBO=1
        MAX_FREQ_KHZ="$BASE_FREQ_KHZ"
        RAPL_UW="$RAPL_ECO_PLUS_UW"
        RAPL_PL2_UW="$RAPL_ECO_PLUS_PL2_UW"
        ;;
    *)
        echo "Error: perfil desconocido '$PROFILE'. Usa: factory | optimal | eco | eco_plus" >&2
        exit 1
        ;;
esac

# --------------------------------------------------------------------------
# Sincronización con power-profiles-daemon (Cinnamon / GNOME / FreeDesktop)
# --------------------------------------------------------------------------
if command -v powerprofilesctl >/dev/null 2>&1; then
    case "$PROFILE" in
        eco|eco_plus)
            powerprofilesctl set power-saver 2>/dev/null || true
            ;;
        optimal|factory)
            powerprofilesctl set balanced 2>/dev/null || true
            ;;
    esac
fi

echo "=== Aplicando perfil CPU: ${PROFILE} ==="
echo "    Governor:  ${GOVERNOR}"
echo "    EPP:       ${EPP_VAL}  (disponible: ${HAS_EPP})"
echo "    EPB:       ${EPB_VAL}  (disponible: ${HAS_EPB})"
echo "    Turbo:     $([ "$NO_TURBO" -eq 0 ] && echo 'ON' || echo 'OFF')"
echo "    Max freq:  $((MAX_FREQ_KHZ / 1000)) MHz"
echo "    RAPL PL1:  $([ "$RAPL_UW" -gt 0 ] && echo "$((RAPL_UW / 1000000)) W" || echo 'sin límite')"
echo "    RAPL PL2:  $([ "$RAPL_PL2_UW" -gt 0 ] && echo "$((RAPL_PL2_UW / 1000000)) W" || echo 'sin límite')"

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
# RAPL: límites de potencia (PL1 long_term y PL2 short_term) del paquete
# --------------------------------------------------------------------------
if [ "$RAPL_AVAILABLE" -eq 1 ] && [ -w "$RAPL_CONSTRAINT" ]; then
    if [ "$RAPL_UW" -gt 0 ]; then
        write_sysfs "$RAPL_CONSTRAINT" "$RAPL_UW"
    else
        # Restaurar al máximo detectado
        write_sysfs "$RAPL_CONSTRAINT" "$RAPL_MAX_UW"
    fi
fi

if [ "$RAPL_PL2_AVAILABLE" -eq 1 ]; then
    if [ "$RAPL_PL2_UW" -gt 0 ]; then
        write_sysfs "$RAPL_CONSTRAINT_1" "$RAPL_PL2_UW"
    else
        # Restaurar al límite por defecto de fábrica sin restricción (200 W)
        write_sysfs "$RAPL_CONSTRAINT_1" "200000000"
    fi
fi

# --------------------------------------------------------------------------
# Fallback max_perf_pct para intel_pstate (blindaje si el kernel ignora scaling_max_freq)
# --------------------------------------------------------------------------
if [ "$HAS_PSTATE" -eq 1 ] && [ -w "${PSTATE_BASE}/max_perf_pct" ]; then
    if [ "$PROFILE" = "factory" ]; then
        write_sysfs "${PSTATE_BASE}/max_perf_pct" "100"
    else
        PERF_PCT=$(( MAX_FREQ_KHZ * 100 / CPUINFO_MAX_KHZ ))
        [ "$PERF_PCT" -gt 100 ] && PERF_PCT=100
        [ "$PERF_PCT" -lt 20 ] && PERF_PCT=20
        write_sysfs "${PSTATE_BASE}/max_perf_pct" "$PERF_PCT"
    fi
fi

# --------------------------------------------------------------------------
# Gestión de servicios systemd (Arranque y Suspensión/Resume)
# --------------------------------------------------------------------------
SERVICE_NAME="cpu-power-optimizer.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
RESUME_SERVICE_NAME="cpu-power-optimizer-resume.service"
RESUME_SERVICE_FILE="/etc/systemd/system/${RESUME_SERVICE_NAME}"

# Resolver ruta al script dentro del directorio de instalación
SCRIPT_PATH="${APP_DIR}/cpu_apply.sh"

# Si el script se ejecuta invocado por systemd (INVOCATION_ID presente) o con
# ENABLE_DAEMON="apply_only", solo se aplican los parámetros de hardware sysfs
# y no se modifica ni elimina la unidad de systemd.
if [ -n "${INVOCATION_ID:-}" ] || [ "$ENABLE_DAEMON" = "apply_only" ]; then
    echo "=== Ejecución como servicio systemd: omitiendo gestión de unidad ==="
elif [ "$ENABLE_DAEMON" = "1" ] && [ "$PROFILE" != "factory" ]; then
    echo "=== Creando servicios systemd: ${SERVICE_NAME} y ${RESUME_SERVICE_NAME} ==="
    cat > "$SERVICE_FILE" << UNIT_EOF
[Unit]
Description=CPU Power Profile Optimizer (${PROFILE})
Documentation=https://github.com/alejandroasc96/gpu-undervolt
After=multi-user.target

[Service]
Type=oneshot
# apply_only: solo aplica los límites sysfs en el arranque sin reescribir ni borrar el servicio
ExecStart=/bin/bash ${SCRIPT_PATH} ${PROFILE} apply_only ${APP_DIR}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT_EOF

    cat > "$RESUME_SERVICE_FILE" << RESUME_EOF
[Unit]
Description=CPU Power Profile Optimizer Resume (${PROFILE})
Documentation=https://github.com/alejandroasc96/gpu-undervolt
After=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target

[Service]
Type=oneshot
# apply_only: solo aplica los límites sysfs tras reanudar de suspensión
ExecStart=/bin/bash ${SCRIPT_PATH} ${PROFILE} apply_only ${APP_DIR}

[Install]
WantedBy=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
RESUME_EOF

    /bin/systemctl daemon-reload
    /bin/systemctl enable "$SERVICE_NAME"
    /bin/systemctl enable "$RESUME_SERVICE_NAME"
    echo "✓ Servicios habilitados: ${SERVICE_NAME} y ${RESUME_SERVICE_NAME}"

elif [ "$ENABLE_DAEMON" = "0" ] || [ "$PROFILE" = "factory" ]; then
    # Deshabilitar y eliminar los servicios si existen
    if [ -f "$SERVICE_FILE" ] || [ -f "$RESUME_SERVICE_FILE" ]; then
        echo "=== Deshabilitando servicios CPU: ${SERVICE_NAME} y ${RESUME_SERVICE_NAME} ==="
        /bin/systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        /bin/systemctl disable "$RESUME_SERVICE_NAME" 2>/dev/null || true
        /bin/rm -f "$SERVICE_FILE" "$RESUME_SERVICE_FILE"
        /bin/systemctl daemon-reload
        echo "✓ Servicios eliminados."
    fi
fi

echo "SUCCESS"
