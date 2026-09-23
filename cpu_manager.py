#!/usr/bin/env python3
"""
CPU Power Manager
=================
Detecta el procesador instalado, el driver del kernel de frecuencia activo
(intel_pstate, amd-pstate-epp, acpi-cpufreq) y sus capacidades reales
(HWP, EPP, EPB, RAPL, Turbo Boost) para construir perfiles de consumo seguros
y 100 % reversibles sin modificar voltajes de hardware.

Perfiles disponibles:
  ⚙️  De Fábrica — restaura el estado original del sistema.
  🍃  Óptimo     — mismo rendimiento perceptible, -20 % consumo/calor.
  🌱  Eco        — silencioso y eficiente bajo carga media.
  🌿  Eco Plus   — máximo ahorro energético (sin Turbo, ideal ofimática).
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CpuProfile:
    """Representa un único perfil de consumo para la CPU."""
    key: str                  # Identificador interno ('factory', 'optimal', 'eco', 'eco_plus')
    name: str                 # Nombre para mostrar en la UI
    emoji: str
    description_short: str
    description_long: str
    governor: str             # powersave | performance
    epp: str                  # energy_performance_preference value
    epb: int                  # energy_perf_bias (0=rendimiento … 15=ahorro)
    turbo: bool               # True = Turbo habilitado, False = sin Turbo
    max_freq_pct: float       # Porcentaje de la frecuencia máxima a aplicar (1.0 = sin límite)
    rapl_long_term_w: float   # Límite RAPL long_term en vatios. 0 = sin límite.


@dataclass
class CpuInfo:
    """Información completa del procesador detectado."""
    name: str
    vendor: str               # 'Intel' | 'AMD' | 'Unknown'
    num_cpus: int
    min_freq_mhz: int
    max_freq_mhz: int
    base_freq_mhz: int        # Frecuencia de reloj base (sin Turbo)
    turbo_max_freq_mhz: int   # Frecuencia máxima con Turbo
    driver: str               # 'intel_pstate' | 'amd-pstate-epp' | 'acpi-cpufreq' | 'unknown'
    has_hwp: bool             # Hardware P-States disponibles
    has_epp: bool             # Energy Performance Preference via sysfs
    has_epb: bool             # Energy Performance Bias via sysfs
    has_rapl: bool            # Interfaz RAPL powercap disponible
    rapl_max_uw: int          # Máximo TDP RAPL en microwatios (0 si no hay RAPL)
    available_epps: List[str]
    profiles: List[CpuProfile]


# ---------------------------------------------------------------------------
# Rutas sysfs
# ---------------------------------------------------------------------------

CPUFREQ_PATH   = "/sys/devices/system/cpu/cpu{i}/cpufreq"
POWER_PATH     = "/sys/devices/system/cpu/cpu{i}/power"
PSTATE_PATH    = "/sys/devices/system/cpu/intel_pstate"
RAPL_PKG_PATH  = "/sys/class/powercap/intel-rapl:0"
THERMAL_PATH   = "/sys/class/thermal"


# ---------------------------------------------------------------------------
# Helpers sysfs
# ---------------------------------------------------------------------------

def _read_sysfs(path: str) -> Optional[str]:
    """Lee un fichero sysfs y devuelve su contenido como cadena limpia, o None."""
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except (OSError, PermissionError, FileNotFoundError):
        return None


def _write_sysfs(path: str, value: str) -> bool:
    """Escribe un valor en sysfs. Devuelve True si tuvo éxito."""
    try:
        with open(path, "w") as f:
            f.write(str(value) + "\n")
        return True
    except (OSError, PermissionError, FileNotFoundError):
        return False


def _read_int(path: str) -> Optional[int]:
    val = _read_sysfs(path)
    if val is None:
        return None
    try:
        return int(val.split()[0])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Construcción de perfiles
# ---------------------------------------------------------------------------

def _build_profiles(info_partial: dict) -> List[CpuProfile]:
    """
    Construye los 4 perfiles de consumo adaptados al hardware detectado.
    info_partial contiene: max_freq_mhz, base_freq_mhz, has_epp, has_epb,
    has_rapl, rapl_max_uw.
    """
    max_f    = info_partial.get("max_freq_mhz", 3500)
    base_f   = info_partial.get("base_freq_mhz", 2600)
    has_epp  = info_partial.get("has_epp", False)
    has_rapl = info_partial.get("has_rapl", False)
    rapl_max = info_partial.get("rapl_max_uw", 0)

    # Calcular límites RAPL proporcionales al TDP máximo real
    # rapl_max_uw viene del kernel como el cap hardware real (ej. 45W = 45_000_000 µW)
    rapl_max_w = rapl_max / 1_000_000 if rapl_max > 0 else 45.0

    # Perfiles de RAPL (solo si está disponible)
    rapl_opt_w      = round(rapl_max_w * 0.78, 1)  # ~78% → -22% calor
    rapl_eco_w      = round(rapl_max_w * 0.56, 1)  # ~56% → reducción notable
    rapl_eco_plus_w = round(rapl_max_w * 0.40, 1)  # ~40% → máximo ahorro

    # EPP: si no hay EPP usar governor como aproximación
    epp_opt      = "balance_power"  if has_epp else "powersave"
    epp_eco      = "power"          if has_epp else "powersave"
    epp_factory  = "balance_performance" if has_epp else "powersave"

    # Frecuencia Eco: 85% de la máx (con Turbo), Eco Plus: frecuencia base (sin Turbo)
    eco_max_mhz      = int(max_f * 0.85 // 100 * 100)
    eco_plus_max_mhz = base_f

    rapl_eco_str      = f" + RAPL {rapl_eco_w:.0f}W"      if has_rapl else ""
    rapl_opt_str      = f" + RAPL {rapl_opt_w:.0f}W"      if has_rapl else ""
    rapl_ecoplus_str  = f" + RAPL {rapl_eco_plus_w:.0f}W" if has_rapl else ""

    profiles = [
        CpuProfile(
            key="factory",
            name="De Fábrica",
            emoji="⚙️",
            description_short="De Fábrica (Stock) — Configuración original del sistema",
            description_long=(
                "• Restaura el governor, EPP, EPB y frecuencia máxima al estado original.\n"
                "• Turbo Boost activado sin restricciones de TDP.\n"
                "• Desactiva el inicio automático del daemon CPU."
            ),
            governor="powersave",
            epp=epp_factory,
            epb=6,
            turbo=True,
            max_freq_pct=1.0,
            rapl_long_term_w=0.0,
        ),
        CpuProfile(
            key="optimal",
            name="Óptimo",
            emoji="🍃",
            description_short=f"Óptimo — EPP ahorro{rapl_opt_str} (mismo rendimiento perceptible)",
            description_long=(
                f"• EPP «balance_power»: el firmware prioriza ahorro sin sacrificar respuesta.\n"
                f"• {'Límite TDP ' + str(rapl_opt_w) + ' W (long-term).' if has_rapl else 'Sin límite de TDP.'}"
                f" Turbo Boost activo para picos de carga.\n"
                "• Reduce temperatura y ruido de ventiladores ~15-20 % en uso normal."
            ),
            governor="powersave",
            epp=epp_opt,
            epb=8,
            turbo=True,
            max_freq_pct=1.0,
            rapl_long_term_w=rapl_opt_w if has_rapl else 0.0,
        ),
        CpuProfile(
            key="eco",
            name="Eco",
            emoji="🌱",
            description_short=f"Eco — {eco_max_mhz} MHz máx.{rapl_eco_str} (eficiente y silencioso)",
            description_long=(
                f"• EPP «power»: máxima prioridad al ahorro en cada P-State.\n"
                f"• Frecuencia limitada a {eco_max_mhz} MHz (85 % del máx.). Turbo activo.\n"
                f"• {'TDP sostenido ' + str(rapl_eco_w) + ' W.' if has_rapl else ''}"
                " Ideal para multitarea, compilación ligera y trabajo creativo."
            ),
            governor="powersave",
            epp=epp_eco,
            epb=12,
            turbo=True,
            max_freq_pct=0.85,
            rapl_long_term_w=rapl_eco_w if has_rapl else 0.0,
        ),
        CpuProfile(
            key="eco_plus",
            name="Eco Plus",
            emoji="🌿",
            description_short=f"Eco Plus <span color='#e5a50a'><b>[Alfa]</b></span> — {eco_plus_max_mhz} MHz base, sin Turbo{rapl_ecoplus_str} (máximo ahorro)",
            description_long=(
                f"• EPP «power» + Turbo Boost desactivado.\n"
                f"• Frecuencia máxima: {eco_plus_max_mhz} MHz (reloj base, sin picos).\n"
                f"• {'TDP ' + str(rapl_eco_plus_w) + ' W máx.' if has_rapl else ''}"
                " Recomendado para ofimática, navegación y reposo activo con batería."
            ),
            governor="powersave",
            epp=epp_eco,
            epb=15,
            turbo=False,
            max_freq_pct=0.0,   # 0.0 = usar base_freq directamente
            rapl_long_term_w=rapl_eco_plus_w if has_rapl else 0.0,
        ),
    ]
    return profiles


# ---------------------------------------------------------------------------
# Detección de hardware
# ---------------------------------------------------------------------------

def _detect_num_cpus() -> int:
    val = _read_sysfs("/sys/devices/system/cpu/present")
    if val and "-" in val:
        try:
            return int(val.split("-")[-1]) + 1
        except ValueError:
            pass
    try:
        import os
        return os.cpu_count() or 1
    except Exception:
        return 1


def _detect_driver() -> str:
    driver = _read_sysfs("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver")
    return driver or "unknown"


def _detect_available_epps() -> List[str]:
    val = _read_sysfs("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_available_preferences")
    if not val:
        return []
    return val.split()


def _detect_has_epp() -> bool:
    return bool(_read_sysfs("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference"))


def _detect_has_epb() -> bool:
    return os.path.exists("/sys/devices/system/cpu/cpu0/power/energy_perf_bias")


def _detect_rapl() -> Tuple[bool, int]:
    """Devuelve (disponible, max_power_uw)."""
    max_path = f"{RAPL_PKG_PATH}/constraint_0_max_power_uw"
    val = _read_int(max_path)
    if val and val > 0:
        return True, val
    # Fallback: leer límite actual si no hay max
    cur = _read_int(f"{RAPL_PKG_PATH}/constraint_0_power_limit_uw")
    if cur and cur > 0:
        return True, cur
    # Comprobar si el directorio existe aunque no podamos leer
    if os.path.isdir(RAPL_PKG_PATH):
        return True, 45_000_000  # Valor conservador para Skylake (45W)
    return False, 0


def _detect_cpu_model() -> Tuple[str, str]:
    """Devuelve (nombre, vendor)."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            content = f.read()
        name_m = re.search(r"model name\s*:\s*(.+)", content)
        vend_m = re.search(r"vendor_id\s*:\s*(\S+)", content)
        name = name_m.group(1).strip() if name_m else "Procesador desconocido"
        vendor_raw = vend_m.group(1).strip() if vend_m else "Unknown"
        vendor = "Intel" if "Intel" in vendor_raw or "Genuine" in vendor_raw else (
            "AMD" if "AMD" in vendor_raw or "AuthenticAMD" in vendor_raw else "Unknown"
        )
        return name, vendor
    except Exception:
        return "Procesador desconocido", "Unknown"


def _detect_freqs() -> Tuple[int, int, int, int]:
    """Devuelve (min_mhz, max_mhz, base_mhz, turbo_max_mhz)."""
    min_khz  = _read_int("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq") or 800_000
    max_khz  = _read_int("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq") or 3_500_000
    base_khz = _read_int("/sys/devices/system/cpu/cpu0/cpufreq/base_frequency")

    min_mhz  = min_khz  // 1000
    max_mhz  = max_khz  // 1000
    base_mhz = (base_khz // 1000) if base_khz else int(max_mhz * 0.74)  # ~74% como estimación

    # turbo_max es cpuinfo_max (ya incluye turbo)
    return min_mhz, max_mhz, base_mhz, max_mhz


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def detect_cpu() -> CpuInfo:
    """
    Detecta la CPU instalada, sus capacidades y construye los perfiles.
    Nunca lanza excepción: siempre devuelve un CpuInfo válido.
    """
    name, vendor        = _detect_cpu_model()
    num_cpus            = _detect_num_cpus()
    driver              = _detect_driver()
    min_mhz, max_mhz, base_mhz, turbo_max = _detect_freqs()
    has_epp             = _detect_has_epp()
    has_epb             = _detect_has_epb()
    has_rapl, rapl_max  = _detect_rapl()
    available_epps      = _detect_available_epps()

    # HWP: disponible cuando intel_pstate está en modo active con EPP
    has_hwp = driver == "intel_pstate" and has_epp

    info_partial = {
        "max_freq_mhz":  max_mhz,
        "base_freq_mhz": base_mhz,
        "has_epp":       has_epp,
        "has_epb":       has_epb,
        "has_rapl":      has_rapl,
        "rapl_max_uw":   rapl_max,
    }
    profiles = _build_profiles(info_partial)

    return CpuInfo(
        name=name,
        vendor=vendor,
        num_cpus=num_cpus,
        min_freq_mhz=min_mhz,
        max_freq_mhz=max_mhz,
        base_freq_mhz=base_mhz,
        turbo_max_freq_mhz=turbo_max,
        driver=driver,
        has_hwp=has_hwp,
        has_epp=has_epp,
        has_epb=has_epb,
        has_rapl=has_rapl,
        rapl_max_uw=rapl_max,
        available_epps=available_epps,
        profiles=profiles,
    )


def read_cpu_state() -> dict:
    """
    Lee el estado actual de la CPU directamente del hardware.
    Devuelve un dict con claves: governor, epp, epb, turbo, max_freq_mhz,
    rapl_limit_w, temp_celsius, cur_freq_mhz.
    """
    governor  = _read_sysfs("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") or "?"
    epp       = _read_sysfs("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference") or "?"
    epb_raw   = _read_int("/sys/devices/system/cpu/cpu0/power/energy_perf_bias")
    epb       = epb_raw if epb_raw is not None else -1
    no_turbo  = _read_int(f"{PSTATE_PATH}/no_turbo")
    turbo     = (no_turbo == 0) if no_turbo is not None else True

    max_freq_khz = _read_int("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq") or 0
    max_freq_mhz = max_freq_khz // 1000

    rapl_uw = _read_int(f"{RAPL_PKG_PATH}/constraint_0_power_limit_uw") or 0
    rapl_w  = rapl_uw / 1_000_000 if rapl_uw > 0 else 0.0

    # Temperatura del paquete CPU: buscar la zona "x86_pkg_temp"
    temp = _read_package_temp()

    # Frecuencia media actual (promedio de todos los cores)
    cur_freq_mhz = _read_avg_cur_freq()

    return {
        "governor":      governor,
        "epp":           epp,
        "epb":           epb,
        "turbo":         turbo,
        "max_freq_mhz":  max_freq_mhz,
        "rapl_limit_w":  rapl_w,
        "temp_celsius":  temp,
        "cur_freq_mhz":  cur_freq_mhz,
    }


def _read_package_temp() -> Optional[float]:
    """Lee la temperatura del paquete CPU (zona x86_pkg_temp o thermal_zone0)."""
    best_temp = None
    try:
        thermal_dir = "/sys/class/thermal"
        zones = sorted(os.listdir(thermal_dir)) if os.path.isdir(thermal_dir) else []
        for zone in zones:
            if not zone.startswith("thermal_zone"):
                continue
            type_path = os.path.join(thermal_dir, zone, "type")
            temp_path = os.path.join(thermal_dir, zone, "temp")
            zone_type = _read_sysfs(type_path) or ""
            temp_raw  = _read_int(temp_path)
            if temp_raw is None:
                continue
            temp_c = temp_raw / 1000.0
            # Priorizar la zona del paquete (x86_pkg_temp)
            if "pkg" in zone_type.lower() or "package" in zone_type.lower():
                return round(temp_c, 1)
            # Guardar como fallback
            if best_temp is None:
                best_temp = round(temp_c, 1)
    except Exception:
        pass
    return best_temp


def _read_avg_cur_freq() -> int:
    """Lee la frecuencia actual promediada sobre todos los cores."""
    total = 0
    count = 0
    cpu_dir = "/sys/devices/system/cpu"
    try:
        for entry in sorted(os.listdir(cpu_dir)):
            if not re.match(r"^cpu\d+$", entry):
                continue
            freq_path = os.path.join(cpu_dir, entry, "cpufreq", "scaling_cur_freq")
            val = _read_int(freq_path)
            if val:
                total += val
                count += 1
    except Exception:
        pass
    return (total // count) // 1000 if count > 0 else 0


def identify_active_profile(cpu_info: CpuInfo) -> Optional[CpuProfile]:
    """
    Intenta identificar cuál de los perfiles está actualmente activo
    comparando el estado real del hardware con los parámetros de cada perfil.
    """
    state = read_cpu_state()
    cur_epp   = state.get("epp", "")
    cur_turbo = state.get("turbo", True)
    cur_epb   = state.get("epb", -1)
    max_info  = cpu_info.max_freq_mhz

    # Eco Plus: sin Turbo, EPB máximo
    if not cur_turbo and cur_epb >= 13:
        for p in cpu_info.profiles:
            if p.key == "eco_plus":
                return p

    # Eco: EPP power y EPB alto, con Turbo
    if cur_epp == "power" and cur_turbo and cur_epb >= 10:
        for p in cpu_info.profiles:
            if p.key == "eco":
                return p

    # Óptimo: EPP balance_power
    if cur_epp == "balance_power" and cur_turbo:
        for p in cpu_info.profiles:
            if p.key == "optimal":
                return p

    # De Fábrica: EPP balance_performance
    if cur_epp in ("balance_performance", "default", "performance"):
        for p in cpu_info.profiles:
            if p.key == "factory":
                return p

    return None


def get_cpu_daemon_status() -> bool:
    """Comprueba si el servicio de inicio automático de CPU está habilitado."""
    try:
        res = subprocess.run(
            ["systemctl", "is-enabled", "cpu-power-optimizer.service"],
            capture_output=True, text=True, timeout=5,
        )
        return res.stdout.strip() == "enabled"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Test rápido CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  CPU Power Manager — Diagnóstico")
    print("=" * 60)

    cpu = detect_cpu()
    print(f"\n  Modelo:   {cpu.name}")
    print(f"  Vendor:   {cpu.vendor}")
    print(f"  CPUs:     {cpu.num_cpus} hilos lógicos")
    print(f"  Driver:   {cpu.driver}")
    print(f"  HWP:      {'✅' if cpu.has_hwp else '❌'}")
    print(f"  EPP:      {'✅' if cpu.has_epp else '❌'}  ({', '.join(cpu.available_epps)})")
    print(f"  EPB:      {'✅' if cpu.has_epb else '❌'}")
    print(f"  RAPL:     {'✅' if cpu.has_rapl else '❌'}  (max {cpu.rapl_max_uw/1e6:.1f} W)")
    print(f"  Frecuencias: {cpu.min_freq_mhz} MHz mín — {cpu.base_freq_mhz} MHz base — {cpu.max_freq_mhz} MHz máx (Turbo)")

    print(f"\n  Estado actual del hardware:")
    state = read_cpu_state()
    print(f"    Governor:   {state['governor']}")
    print(f"    EPP:        {state['epp']}")
    print(f"    EPB:        {state['epb']}")
    print(f"    Turbo:      {'ON' if state['turbo'] else 'OFF'}")
    print(f"    Max freq:   {state['max_freq_mhz']} MHz")
    print(f"    RAPL lim:   {state['rapl_limit_w']:.1f} W")
    print(f"    Temp CPU:   {state['temp_celsius']} °C")
    print(f"    Freq avg:   {state['cur_freq_mhz']} MHz")

    active = identify_active_profile(cpu)
    print(f"\n  Perfil activo detectado: {active.emoji + ' ' + active.name if active else 'No identificado'}")

    print(f"\n  Perfiles disponibles ({len(cpu.profiles)}):")
    for p in cpu.profiles:
        rapl = f"RAPL {p.rapl_long_term_w:.0f}W" if p.rapl_long_term_w > 0 else "sin límite RAPL"
        turbo = "Turbo ON" if p.turbo else "sin Turbo"
        print(f"    {p.emoji}  {p.name}: EPP={p.epp}  EPB={p.epb}  {turbo}  {rapl}")

    print("\n" + "=" * 60 + "\n")
