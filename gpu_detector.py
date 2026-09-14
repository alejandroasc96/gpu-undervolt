#!/usr/bin/env python3
"""
NVIDIA GPU Auto-Detector
========================
Detecta automáticamente las capacidades de cualquier GPU NVIDIA mediante
nvidia-smi y calcula perfiles óptimos de consumo adaptados al hardware real.

Flujo:
  1. Consulta nvidia-smi para nombre, TDP (min/max) y relojes máximos.
  2. Si el driver reporta power management -> perfiles dinámicos por %.
  3. Si no (GPU móvil o legacy) -> perfiles PowerMizer + BD de fallback.

GPUs con soporte completo en la BD (fallback si nvidia-smi falla parcialmente):
  - NVIDIA GeForce GTX 1660 / 1660 Ti / 1660 Super
  - NVIDIA GeForce GTX 1060 6G / 3G
  - NVIDIA GeForce RTX 5060 Ti 16G (Blackwell, 2025)
  - NVIDIA GeForce GT 840M (Maxwell, portatil)
"""

import subprocess
from dataclasses import dataclass, field
from typing import Optional, List


# --- Data classes -------------------------------------------------------------

@dataclass
class PowerProfile:
    """Representa un unico perfil de consumo/rendimiento."""
    name: str
    emoji: str
    watts: int              # Vatios objetivo. 0 = solo PowerMizer (GPU movil)
    description_short: str  # Texto corto para el radio button
    description_long: str   # Descripcion expandida (2 lineas)
    eco_min_clock: int = 300    # Reloj minimo MHz en modo eco (para -lgc)
    eco_max_clock: int = 0      # Reloj maximo MHz en modo eco. 0 = sin bloqueo
    powermizer_mode: int = 2    # GPUPowerMizerMode: 0=Adaptativo, 1=MaxPerf, 2=Auto


@dataclass
class GpuInfo:
    """Informacion completa de una GPU y sus perfiles calculados."""
    name: str
    gpu_index: int
    max_tdp: float
    min_tdp: float
    supports_power_limit: bool
    supports_clock_lock: bool
    max_gpu_clock: int
    max_mem_clock: int
    is_mobile: bool
    profiles: List[PowerProfile]

    @property
    def display_name(self) -> str:
        """Nombre limpio para la UI (sin prefijo 'NVIDIA GeForce')."""
        name = self.name
        for prefix in ("NVIDIA GeForce ", "NVIDIA Quadro ", "NVIDIA Tesla ", "NVIDIA "):
            if name.startswith(prefix):
                return name[len(prefix):].strip()
        return name.strip()

    @property
    def service_name(self) -> str:
        """Nombre del servicio systemd para esta GPU."""
        return f"nvidia-power-limit-gpu{self.gpu_index}.service"


# --- Base de datos de GPUs conocidas -----------------------------------------
# Usada como fallback cuando nvidia-smi no reporta power management completo.
# La deteccion automatica tiene prioridad.

_GPU_DATABASE = {
    # Turing (GTX 16xx)
    "GTX 1660 Ti": {
        "max_tdp": 120.0, "min_tdp": 70.0,
        "supports_power_limit": True, "supports_clock_lock": True,
        "max_gpu_clock": 1770, "max_mem_clock": 6001, "is_mobile": False,
    },
    "GTX 1660 Super": {
        "max_tdp": 125.0, "min_tdp": 70.0,
        "supports_power_limit": True, "supports_clock_lock": True,
        "max_gpu_clock": 1815, "max_mem_clock": 7000, "is_mobile": False,
    },
    "GTX 1660": {
        "max_tdp": 120.0, "min_tdp": 70.0,
        "supports_power_limit": True, "supports_clock_lock": True,
        "max_gpu_clock": 2100, "max_mem_clock": 4001, "is_mobile": False,
    },
    # Pascal (GTX 10xx)
    "GTX 1060 6": {
        "max_tdp": 120.0, "min_tdp": 75.0,
        "supports_power_limit": True, "supports_clock_lock": True,
        "max_gpu_clock": 2002, "max_mem_clock": 4008, "is_mobile": False,
    },
    "GTX 1060 3": {
        "max_tdp": 120.0, "min_tdp": 75.0,
        "supports_power_limit": True, "supports_clock_lock": True,
        "max_gpu_clock": 1987, "max_mem_clock": 4008, "is_mobile": False,
    },
    "GTX 1060": {
        "max_tdp": 120.0, "min_tdp": 75.0,
        "supports_power_limit": True, "supports_clock_lock": True,
        "max_gpu_clock": 2002, "max_mem_clock": 4008, "is_mobile": False,
    },
    # Blackwell (RTX 50xx)
    "5060 Ti": {
        "max_tdp": 180.0, "min_tdp": 75.0,
        "supports_power_limit": True, "supports_clock_lock": True,
        "max_gpu_clock": 2572, "max_mem_clock": 9251, "is_mobile": False,
    },
    # Maxwell Mobile
    "840M": {
        "max_tdp": 33.0, "min_tdp": 33.0,
        "supports_power_limit": False, "supports_clock_lock": False,
        "max_gpu_clock": 1124, "max_mem_clock": 2500, "is_mobile": True,
    },
}

_MOBILE_SUFFIXES = {"M", "MX", "GO", "MAX-Q", "MAX-P"}


# --- Helpers de calculo -------------------------------------------------------

def _round5(value: float) -> int:
    return int(round(value / 5.0) * 5)

def _round50(value: float) -> int:
    return int(round(value / 50.0) * 50)

def _parse_float(val: str) -> Optional[float]:
    if not val or val.strip().upper() in ("N/A", "[N/A]", "NOT SUPPORTED", ""):
        return None
    try:
        return float(val.strip())
    except ValueError:
        return None

def _parse_int(val: str) -> Optional[int]:
    f = _parse_float(val)
    return int(f) if f is not None else None


# --- Construccion de perfiles -------------------------------------------------

def _build_mobile_profiles() -> List[PowerProfile]:
    """Perfiles para GPUs moviles/legacy: solo control PowerMizer."""
    return [
        PowerProfile(
            name="Ahorro de Energia",
            emoji="🌱",
            watts=0,
            description_short="Ahorro de Energia (PowerMizer Adaptativo)",
            description_long=(
                "• Activa el modo Adaptativo de NVIDIA PowerMizer.\n"
                "• Reduce voltaje y relojes automaticamente en reposo.\n"
                "• Ideal para ofimática, video y uso ligero."
            ),
            powermizer_mode=0,
        ),
        PowerProfile(
            name="Equilibrado",
            emoji="🍃",
            watts=0,
            description_short="Equilibrado (PowerMizer Automatico)",
            description_long=(
                "• El driver ajusta frecuencias dinamicamente segun la carga.\n"
                "• Buen equilibrio entre rendimiento y consumo."
            ),
            powermizer_mode=2,
        ),
        PowerProfile(
            name="Maximo Rendimiento",
            emoji="⚡",
            watts=0,
            description_short="Maximo Rendimiento (PowerMizer Maximo)",
            description_long=(
                "• Mantiene la GPU a maxima frecuencia en todo momento.\n"
                "• Mejor opcion para gaming y cargas pesadas continuas."
            ),
            powermizer_mode=1,
        ),
    ]


def _build_desktop_profiles(max_tdp, min_tdp, max_gpu_clock, max_mem_clock):
    """Calcula los 4 perfiles estandar para GPUs de escritorio con power limit."""
    eco_w  = max(_round5(max_tdp * 0.58), int(min_tdp))
    eff_w  = max(_round5(max_tdp * 0.67), int(min_tdp) + 5)
    swt_w  = max(_round5(max_tdp * 0.75), int(min_tdp) + 10)
    stk_w  = int(max_tdp)

    eco_clk = max(300, _round50(max_gpu_clock * 0.31))

    eco_pct = int((1 - eco_w / max_tdp) * 100)
    eff_pct = int((1 - eff_w / max_tdp) * 100)
    swt_pct = int((1 - swt_w / max_tdp) * 100)

    return [
        PowerProfile(
            name="Ultra Eco",
            emoji="🌱",
            watts=eco_w,
            description_short=f"Ultra Eco — {eco_w} W + {eco_clk} MHz (Maximo Ahorro)",
            description_long=(
                f"• Acota el reloj a {eco_clk} MHz y activa PowerMizer Ahorro.\n"
                f"• -{eco_pct}% de consumo. Ideal para YouTube, escritorio y ofimatica."
            ),
            eco_min_clock=300,
            eco_max_clock=eco_clk,
            powermizer_mode=0,
        ),
        PowerProfile(
            name="Maxima Eficiencia",
            emoji="🍃",
            watts=eff_w,
            description_short=f"Maxima Eficiencia — {eff_w} W",
            description_long=(
                f"• -{eff_pct}% de consumo sin perdida perceptible de FPS.\n"
                "• Silencioso y fresco bajo carga de gaming."
            ),
            powermizer_mode=2,
        ),
        PowerProfile(
            name="Punto Dulce",
            emoji="⚡",
            watts=swt_w,
            description_short=f"Punto Dulce — {swt_w} W (Recomendado Gaming)",
            description_long=(
                f"• ~98% del rendimiento de fabrica con -{swt_pct}% de energia.\n"
                "• Ideal para juegos exigentes manteniendo la temperatura baja."
            ),
            powermizer_mode=2,
        ),
        PowerProfile(
            name="De Fabrica",
            emoji="⚙️",
            watts=stk_w,
            description_short=f"De Fabrica (Stock) — {stk_w} W",
            description_long="• Limite original de fabrica y frecuencias sin restricciones.",
            powermizer_mode=2,
        ),
    ]


# --- Deteccion via nvidia-smi -------------------------------------------------

def _run_smi(*args) -> Optional[str]:
    try:
        res = subprocess.run(
            ["nvidia-smi"] + list(args),
            capture_output=True, text=True, timeout=8,
        )
        return res.stdout.strip() if res.returncode == 0 else None
    except Exception:
        return None


def _query_fields(gpu_index: int, fields) -> Optional[List[str]]:
    out = _run_smi(
        f"--id={gpu_index}",
        f"--query-gpu={','.join(fields)}",
        "--format=csv,noheader,nounits",
    )
    if out is None:
        return None
    parts = [p.strip() for p in out.split(",")]
    return parts if len(parts) == len(fields) else None


def _is_mobile_by_name(name: str) -> bool:
    tokens = name.upper().split()
    if not tokens:
        return False
    last = tokens[-1]
    for suffix in _MOBILE_SUFFIXES:
        if last.endswith(suffix):
            return True
    name_u = name.upper()
    return any(s in name_u for s in ("MAX-Q", "MAX-P", "MOBILE"))


def _find_db_entry(name: str) -> Optional[dict]:
    name_u = name.upper()
    for key in sorted(_GPU_DATABASE.keys(), key=len, reverse=True):
        if key.upper() in name_u:
            return _GPU_DATABASE[key]
    return None


# --- API publica --------------------------------------------------------------

def detect_gpu(gpu_index: int = 0) -> Optional[GpuInfo]:
    """
    Detecta una GPU NVIDIA y calcula sus perfiles de consumo.
    Devuelve None si la GPU no se puede detectar.
    """
    data = _query_fields(gpu_index, [
        "name", "power.min_limit", "power.max_limit",
        "clocks.max.graphics", "clocks.max.memory",
    ])
    if data is None:
        return None

    name      = data[0]
    min_tdp_q = _parse_float(data[1])
    max_tdp_q = _parse_float(data[2])
    max_gc_q  = _parse_int(data[3])
    max_mc_q  = _parse_int(data[4])

    supports_pl  = (min_tdp_q is not None and max_tdp_q is not None
                    and max_tdp_q > min_tdp_q)
    supports_clk = (max_gc_q is not None and max_mc_q is not None)

    db        = _find_db_entry(name)
    is_mobile = _is_mobile_by_name(name) or (db is not None and db.get("is_mobile", False))

    # Si la BD declara explicitamente que no soporta power limit -> override
    if db is not None and not db.get("supports_power_limit", True):
        supports_pl = False
        is_mobile   = True

    # TDP: nvidia-smi primero, BD como fallback
    min_tdp = min_tdp_q if supports_pl else (db["min_tdp"] if db else 0.0)
    max_tdp = max_tdp_q if supports_pl else (db["max_tdp"] if db else 0.0)

    # Relojes: nvidia-smi primero, BD como fallback
    max_gc = max_gc_q if supports_clk else (db["max_gpu_clock"] if db else 1500)
    max_mc = max_mc_q if supports_clk else (db["max_mem_clock"] if db else 4000)

    if is_mobile or not supports_pl:
        profiles = _build_mobile_profiles()
    else:
        profiles = _build_desktop_profiles(max_tdp, min_tdp, max_gc, max_mc)

    return GpuInfo(
        name=name,
        gpu_index=gpu_index,
        max_tdp=max_tdp,
        min_tdp=min_tdp,
        supports_power_limit=supports_pl and not is_mobile,
        supports_clock_lock=(supports_clk or bool(db and db.get("supports_clock_lock"))) and not is_mobile,
        max_gpu_clock=max_gc,
        max_mem_clock=max_mc,
        is_mobile=is_mobile,
        profiles=profiles,
    )


def detect_all_gpus() -> List[GpuInfo]:
    """Detecta todas las GPUs NVIDIA presentes en el sistema."""
    out = _run_smi("--query-gpu=name", "--format=csv,noheader")
    if not out:
        return []
    count = len([l for l in out.splitlines() if l.strip()])
    result = []
    for i in range(count):
        gpu = detect_gpu(i)
        if gpu is not None:
            result.append(gpu)
    return result


# --- Test rapido --------------------------------------------------------------

if __name__ == "__main__":
    gpus = detect_all_gpus()
    if not gpus:
        print("No se detecto ninguna GPU NVIDIA.")
        print("Asegurate de tener el driver NVIDIA propietario instalado.")
    else:
        for gpu in gpus:
            print(f"\n{'=' * 58}")
            print(f"  GPU {gpu.gpu_index}: {gpu.name}")
            print(f"  TDP soportado: {gpu.min_tdp:.0f} W - {gpu.max_tdp:.0f} W")
            print(f"  Relojes max -- Nucleo: {gpu.max_gpu_clock} MHz | VRAM: {gpu.max_mem_clock} MHz")
            print(f"  Movil: {gpu.is_mobile} | Power limit: {gpu.supports_power_limit} | Clock lock: {gpu.supports_clock_lock}")
            print(f"\n  Perfiles calculados ({len(gpu.profiles)}):")
            for p in gpu.profiles:
                w_str = f"{p.watts} W" if p.watts > 0 else "PowerMizer"
                clk = f" | Eco clk: {p.eco_max_clock} MHz" if p.eco_max_clock else ""
                print(f"    {p.emoji} {p.name}: {w_str}{clk} (PM={p.powermizer_mode})")
        print(f"\n{'=' * 58}\n")
