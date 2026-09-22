#!/usr/bin/env python3
"""
Módulo de Utilidades de Disco y Limpieza de Sistema (Linux)
Proporciona análisis de almacenamiento y comandos seguros de optimización de espacio.
"""
import os
import sys
import shutil
import subprocess
from typing import Dict, Any, List, Tuple


def format_size(bytes_size: int) -> str:
    """Convierte bytes a un formato legible (B, KB, MB, GB)."""
    if bytes_size <= 0:
        return "0 MB"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def get_dir_size(path: str) -> int:
    """Calcula el tamaño acumulado de un directorio de forma segura."""
    if not os.path.exists(path):
        return 0
    total = 0
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        for root, dirs, files in os.walk(path, followlinks=False):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return total


class DiskInfo:
    @staticmethod
    def get_mount_usage(path: str = "/") -> Dict[str, Any]:
        """Devuelve el estado de uso de un punto de montaje."""
        try:
            usage = shutil.disk_usage(path)
            total = usage.total
            used = usage.used
            free = usage.free
            percent = (used / total * 100.0) if total > 0 else 0.0
            return {
                "mount": path,
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "percent": percent,
                "total_str": format_size(total),
                "used_str": format_size(used),
                "free_str": format_size(free),
                "percent_str": f"{percent:.1f}%",
                "valid": True
            }
        except Exception as e:
            return {
                "mount": path,
                "total_bytes": 0,
                "used_bytes": 0,
                "free_bytes": 0,
                "percent": 0.0,
                "total_str": "N/A",
                "used_str": "N/A",
                "free_str": "N/A",
                "percent_str": "N/A",
                "valid": False,
                "error": str(e)
            }

    @staticmethod
    def get_all_relevant_mounts() -> List[Dict[str, Any]]:
        """Retorna el uso de la raíz (/) y de /home si está en un dispositivo separado."""
        mounts = [DiskInfo.get_mount_usage("/")]
        home_path = os.path.expanduser("~")
        try:
            root_stat = os.stat("/")
            home_stat = os.stat(home_path)
            if root_stat.st_dev != home_stat.st_dev:
                mounts.append(DiskInfo.get_mount_usage(home_path))
        except Exception:
            pass
        return mounts


class CleanerTask:
    def __init__(self, key: str, title: str, description: str, requires_root: bool = False, default_enabled: bool = True):
        self.key = key
        self.title = title
        self.description = description
        self.requires_root = requires_root
        self.default_enabled = default_enabled
        self.estimated_bytes = 0
        self.estimated_str = "No escaneado"
        self.available = True


class DiskCleaner:
    def __init__(self):
        self.has_flatpak = shutil.which("flatpak") is not None
        self.has_apt = shutil.which("apt-get") is not None

    def get_tasks_definitions(self) -> List[CleanerTask]:
        """Define la lista de tareas de limpieza disponibles."""
        tasks = []

        if self.has_apt:
            tasks.append(CleanerTask(
                key="apt_clean",
                title="Caché de paquetes (APT)",
                description="Elimina paquetes .deb descargados durante instalaciones y actualizaciones (/var/cache/apt/archives).",
                requires_root=True,
                default_enabled=True
            ))
            tasks.append(CleanerTask(
                key="apt_autoremove",
                title="Dependencias huérfanas (APT autoremove)",
                description="Desinstala paquetes y librerías que se instalaron automáticamente y ya no son necesarios.",
                requires_root=True,
                default_enabled=True
            ))

        tasks.append(CleanerTask(
            key="journal_vacuum",
            title="Reducir registros del sistema (Journalctl)",
            description="Limpia registros antiguos de systemd manteniendo un límite máximo de 100 MB de logs.",
            requires_root=True,
            default_enabled=True
        ))

        if self.has_flatpak:
            tasks.append(CleanerTask(
                key="flatpak_unused",
                title="Runtimes y paquetes Flatpak huérfanos",
                description="Desinstala runtimes, extensiones y bibliotecas Flatpak sin usar (flatpak uninstall --unused).",
                requires_root=True,
                default_enabled=True
            ))

        tasks.append(CleanerTask(
            key="thumbnails",
            title="Caché de miniaturas de imágenes y vídeos",
            description="Elimina miniaturas almacenadas en ~/.cache/thumbnails generadas por el explorador de archivos.",
            requires_root=False,
            default_enabled=True
        ))

        tasks.append(CleanerTask(
            key="trash",
            title="Papelera de reciclaje",
            description="Vacía los archivos enviados a la papelera del usuario (~/.local/share/Trash).",
            requires_root=False,
            default_enabled=False
        ))

        tasks.append(CleanerTask(
            key="user_cache",
            title="Cachés de usuario no esenciales",
            description="Limpia cachés temporales de pip, npm y archivos residuales en ~/.cache.",
            requires_root=False,
            default_enabled=False
        ))

        return tasks

    def scan_task_size(self, task_key: str) -> int:
        """Calcula el tamaño recuperable aproximado para una tarea dada."""
        size = 0
        if task_key == "apt_clean":
            apt_cache_dir = "/var/cache/apt/archives"
            if os.path.exists(apt_cache_dir):
                for f in os.listdir(apt_cache_dir):
                    if f.endswith(".deb"):
                        fp = os.path.join(apt_cache_dir, f)
                        try:
                            size += os.path.getsize(fp)
                        except (OSError, PermissionError):
                            pass

        elif task_key == "apt_autoremove":
            try:
                proc = subprocess.run(
                    ["apt-get", "-s", "autoremove"],
                    capture_output=True, text=True, timeout=5
                )
                for line in proc.stdout.splitlines():
                    if "se liberarán" in line or "will be freed" in line or "disks space will be freed" in line:
                        parts = line.strip().split()
                        for i, p in enumerate(parts):
                            if p in ["MB", "GB", "kB", "KB"]:
                                num = parts[i - 1].replace(",", ".")
                                factor = {"kB": 1024, "KB": 1024, "MB": 1024**2, "GB": 1024**3}.get(p, 1)
                                size = int(float(num) * factor)
                                break
            except Exception:
                size = 0

        elif task_key == "journal_vacuum":
            try:
                proc = subprocess.run(
                    ["journalctl", "--disk-usage"],
                    capture_output=True, text=True, timeout=5
                )
                out = proc.stdout.strip()
                import re
                m = re.search(r'([0-9.]+)\s*([KMG]?)B?', out, re.IGNORECASE)
                if m:
                    val = float(m.group(1))
                    unit = (m.group(2) or "M").upper()
                    mult = {"K": 1024, "M": 1024**2, "G": 1024**3}.get(unit, 1024**2)
                    total_journal = int(val * mult)
                    target_limit = 100 * 1024 * 1024
                    size = max(0, total_journal - target_limit)
                    if size == 0 and total_journal > 0:
                        size = total_journal // 2
            except Exception:
                size = 0

        elif task_key == "flatpak_unused":
            if self.has_flatpak:
                try:
                    proc = subprocess.run(
                        ["flatpak", "list", "--unused", "--columns=size"],
                        capture_output=True, text=True, timeout=6
                    )
                    for line in proc.stdout.splitlines():
                        line = line.strip()
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                num = float(parts[0].replace(",", "."))
                                unit = parts[1].upper()
                                mult = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}.get(unit, 1024**2)
                                size += int(num * mult)
                            except ValueError:
                                pass
                except Exception:
                    size = 0

        elif task_key == "thumbnails":
            thumb_dir = os.path.expanduser("~/.cache/thumbnails")
            size = get_dir_size(thumb_dir)

        elif task_key == "trash":
            trash_files = os.path.expanduser("~/.local/share/Trash")
            size = get_dir_size(trash_files)

        elif task_key == "user_cache":
            pip_cache = os.path.expanduser("~/.cache/pip")
            npm_cache = os.path.expanduser("~/.npm/_cacache")
            size += get_dir_size(pip_cache)
            size += get_dir_size(npm_cache)

        return size

    def clean_user_space(self, selected_keys: List[str]) -> Tuple[bool, List[str]]:
        """Ejecuta las tareas que corresponden al espacio de usuario sin permisos de root."""
        logs = []
        success = True

        if "thumbnails" in selected_keys:
            thumb_dir = os.path.expanduser("~/.cache/thumbnails")
            if os.path.exists(thumb_dir):
                logs.append("→ Limpiando miniaturas en ~/.cache/thumbnails...")
                try:
                    for root, dirs, files in os.walk(thumb_dir, topdown=False):
                        for f in files:
                            try:
                                os.unlink(os.path.join(root, f))
                            except Exception:
                                pass
                        for d in dirs:
                            try:
                                os.rmdir(os.path.join(root, d))
                            except Exception:
                                pass
                    logs.append("✓ Miniaturas eliminadas correctamente.")
                except Exception as e:
                    logs.append(f"✗ Error al limpiar miniaturas: {e}")
                    success = False
            else:
                logs.append("• No existe la carpeta de miniaturas ~/.cache/thumbnails.")

        if "trash" in selected_keys:
            logs.append("→ Vaciando papelera de reciclaje...")
            emptied = False
            if shutil.which("gio"):
                try:
                    res = subprocess.run(["gio", "trash", "--empty"], capture_output=True, text=True, timeout=10)
                    if res.returncode == 0:
                        emptied = True
                except Exception:
                    pass

            if not emptied:
                trash_dir = os.path.expanduser("~/.local/share/Trash")
                try:
                    for sub in ["files", "info"]:
                        sub_dir = os.path.join(trash_dir, sub)
                        if os.path.exists(sub_dir):
                            for item in os.listdir(sub_dir):
                                item_path = os.path.join(sub_dir, item)
                                try:
                                    if os.path.isdir(item_path) and not os.path.islink(item_path):
                                        shutil.rmtree(item_path, ignore_errors=True)
                                    else:
                                        os.unlink(item_path)
                                except Exception:
                                    pass
                    emptied = True
                except Exception as e:
                    logs.append(f"✗ Error al vaciar papelera: {e}")
                    success = False

            if emptied:
                logs.append("✓ Papelera vaciada correctamente.")

        if "user_cache" in selected_keys:
            logs.append("→ Limpiando cachés adicionales de usuario (pip/npm)...")
            pip_cache = os.path.expanduser("~/.cache/pip")
            if os.path.exists(pip_cache):
                shutil.rmtree(pip_cache, ignore_errors=True)
                logs.append("✓ Caché de pip eliminada.")
            npm_cache = os.path.expanduser("~/.npm/_cacache")
            if os.path.exists(npm_cache):
                shutil.rmtree(npm_cache, ignore_errors=True)
                logs.append("✓ Caché de npm eliminada.")

        return success, logs

    def build_root_script(self, selected_keys: List[str]) -> str:
        """Genera un script en bash con los comandos que requieren permisos de administrador."""
        cmds = [
            "#!/bin/bash",
            "echo '--- Iniciando limpieza del sistema ---'"
        ]

        if "apt_clean" in selected_keys and self.has_apt:
            cmds.extend([
                "echo '→ Limpiando caché de paquetes APT (apt-get clean)...'",
                "apt-get clean",
                "echo '✓ Caché APT limpiada con éxito.'"
            ])

        if "apt_autoremove" in selected_keys and self.has_apt:
            cmds.extend([
                "echo '→ Eliminando dependencias huérfanas (apt-get autoremove --purge)...'",
                "DEBIAN_FRONTEND=noninteractive apt-get autoremove --purge -y",
                "echo '✓ Dependencias huérfanas eliminadas.'"
            ])

        if "journal_vacuum" in selected_keys:
            cmds.extend([
                "echo '→ Reduciendo registros de journalctl (límite 100MB y 7 días)...'",
                "journalctl --vacuum-size=100M",
                "journalctl --vacuum-time=7d",
                "echo '✓ Registros de journalctl reducidos.'"
            ])

        if "flatpak_unused" in selected_keys and self.has_flatpak:
            cmds.extend([
                "echo '→ Desinstalando runtimes Flatpak sin usar (flatpak uninstall --unused)...'",
                "flatpak uninstall --unused -y || true",
                "echo '✓ Flatpaks huérfanos eliminados.'"
            ])

        cmds.append("echo '--- Limpieza del sistema finalizada ---'")
        return "\n".join(cmds) + "\n"
