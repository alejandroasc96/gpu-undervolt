#!/usr/bin/env python3
"""
Optimizador de Energia NVIDIA & Utilidades del Sistema (Linux)
Soporta optimizacion de GPUs NVIDIA (perfiles de consumo + daemon de arranque)
y herramientas de limpieza de espacio en disco (pestana Utils).
"""
import sys
import os
import re
import subprocess
import threading
import tempfile
from typing import Optional, Tuple, List, Dict
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APPLY_SCRIPT = os.path.join(SCRIPT_DIR, "apply.sh")
CPU_APPLY_SCRIPT = os.path.join(SCRIPT_DIR, "cpu_apply.sh")

# --- Almacenamiento de configuracion persistente -----------------------------
CONFIG_DIR = os.path.expanduser("~/.config/nvidia-optimizer")

def _get_saved_profile_path(gpu_index: int) -> str:
    return os.path.join(CONFIG_DIR, f"saved_profile_gpu{gpu_index}.txt")

def _get_saved_profile(gpu_index: int) -> Optional[str]:
    path = _get_saved_profile_path(gpu_index)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    return None

def _save_profile(gpu_index: int, profile_name: str):
    """Guarda siempre el perfil aplicado para poder informar de el al reabrir
    la app, tenga o no inicio automatico."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = _get_saved_profile_path(gpu_index)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(profile_name)
    except Exception:
        pass

def _get_saved_cpu_profile_path() -> str:
    return os.path.join(CONFIG_DIR, "saved_profile_cpu.txt")

def _get_saved_cpu_profile() -> Optional[str]:
    path = _get_saved_cpu_profile_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    return None

def _save_cpu_profile(profile_key: str):
    """Guarda el perfil de CPU aplicado."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = _get_saved_cpu_profile_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(profile_key)
    except Exception:
        pass

# Importar modulos auxiliares
sys.path.insert(0, SCRIPT_DIR)
try:
    from gpu_detector import (
        detect_all_gpus,
        check_nvidia_driver_status,
        GpuInfo,
        PowerProfile,
    )
except ImportError as e:
    import traceback
    dialog = Gtk.MessageDialog(
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text="Error al cargar gpu_detector.py"
    )
    dialog.format_secondary_text(str(e))
    dialog.run()
    sys.exit(1)

try:
    from disk_cleaner import DiskCleaner, DiskInfo, format_size, CleanerTask
except ImportError as e:
    import traceback
    dialog = Gtk.MessageDialog(
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text="Error al cargar disk_cleaner.py"
    )
    dialog.format_secondary_text(str(e))
    dialog.run()
    sys.exit(1)

try:
    from cpu_manager import (
        detect_cpu,
        read_cpu_state,
        identify_active_profile,
        get_cpu_daemon_status,
        CpuInfo,
        CpuProfile,
    )
    _CPU_MANAGER_OK = True
except ImportError:
    _CPU_MANAGER_OK = False


class NvidiaOptimizerApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Optimizador NVIDIA & Herramientas")
        self.set_default_size(640, 720)
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        self.set_icon_name("nvidia-settings")

        # Estado interno GPU
        self.gpus = []
        self.current_gpu = None
        self._profile_widgets = []
        self.profile_radio_buttons = []
        self._initial_driver_err = None

        # Estado interno Utils
        self.disk_cleaner = DiskCleaner()
        self.cleaner_tasks = self.disk_cleaner.get_tasks_definitions()
        self.task_check_buttons = {}  # key -> Gtk.CheckButton
        self.task_size_labels = {}    # key -> Gtk.Label

        # Comprobar salud del driver NVIDIA y detectar GPUs
        driver_ok, driver_err = check_nvidia_driver_status()
        if not driver_ok:
            self.gpus = []
            self._initial_driver_err = driver_err
        else:
            self._initial_driver_err = None
            self.gpus = detect_all_gpus()

        # Estado interno CPU
        self.cpu_info = None
        self.cpu_profile_radio_buttons = []  # list of (radio_btn, CpuProfile)
        self._cpu_apply_in_progress = False

        if _CPU_MANAGER_OK:
            self.cpu_info = detect_cpu()

        # Contenedor Principal: Notebook (Pestañas)
        self.notebook = Gtk.Notebook()
        self.notebook.set_tab_pos(Gtk.PositionType.TOP)
        self.add(self.notebook)

        # 1. Pestaña GPU
        gpu_tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        gpu_tab_icon = Gtk.Image.new_from_icon_name("nvidia-settings", Gtk.IconSize.MENU)
        gpu_tab_label = Gtk.Label(label="<b>GPU</b>")
        gpu_tab_label.set_use_markup(True)
        gpu_tab_box.pack_start(gpu_tab_icon, False, False, 0)
        gpu_tab_box.pack_start(gpu_tab_label, False, False, 0)
        gpu_tab_box.show_all()

        gpu_page = self._build_gpu_page()
        self.notebook.append_page(gpu_page, gpu_tab_box)

        # 2. Pestaña CPU
        cpu_tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        cpu_tab_icon = Gtk.Image.new_from_icon_name("computer", Gtk.IconSize.MENU)
        cpu_tab_label = Gtk.Label(label="<b>CPU</b>")
        cpu_tab_label.set_use_markup(True)
        cpu_tab_box.pack_start(cpu_tab_icon, False, False, 0)
        cpu_tab_box.pack_start(cpu_tab_label, False, False, 0)
        cpu_tab_box.show_all()

        cpu_page = self._build_cpu_page()
        self.notebook.append_page(cpu_page, cpu_tab_box)

        # 3. Pestaña Utils
        utils_tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        utils_tab_icon = Gtk.Image.new_from_icon_name("drive-harddisk", Gtk.IconSize.MENU)
        utils_tab_label = Gtk.Label(label="<b>Utils</b>")
        utils_tab_label.set_use_markup(True)
        utils_tab_box.pack_start(utils_tab_icon, False, False, 0)
        utils_tab_box.pack_start(utils_tab_label, False, False, 0)
        utils_tab_box.show_all()

        utils_page = self._build_utils_page()
        self.notebook.append_page(utils_page, utils_tab_box)

        # Inicializacion GPU
        if not self.gpus:
            self._show_no_gpu_error(self._initial_driver_err)
        else:
            for gpu in self.gpus:
                self.gpu_combo.append_text(f"GPU {gpu.gpu_index}: {gpu.display_name}")

            if len(self.gpus) > 1:
                self.gpu_selector_box.set_no_show_all(False)
                self.gpu_selector_box.show_all()

            self.gpu_combo.set_active(0)

        # Inicializacion Utils
        self._refresh_disk_info()
        # Iniciar escaneo de disco en segundo plano al arrancar
        self._start_scan_async(silent=True)

        # Inicialización CPU
        if _CPU_MANAGER_OK and self.cpu_info:
            self._cpu_refresh_status()

    # =========================================================================
    # PESTAÑA GPU (Construcción y Lógica)
    # =========================================================================

    def _build_gpu_page(self):
        """Construye el contenedor completo de la pestaña GPU."""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_border_width(8)

        # --- Tarjeta de cabecera ----------------------------------------
        header_frame = Gtk.Frame()
        header_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        header_box.set_border_width(10)

        icon_image = Gtk.Image.new_from_icon_name("nvidia-settings", Gtk.IconSize.DIALOG)
        header_box.pack_start(icon_image, False, False, 0)

        info_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)

        self.title_label = Gtk.Label()
        self.title_label.set_markup("<b><big>Detectando GPU...</big></b>")
        self.title_label.set_xalign(0)
        info_vbox.pack_start(self.title_label, False, False, 0)

        # Perfil de energia detectado al abrir la aplicacion
        self.profile_status_label = Gtk.Label()
        self.profile_status_label.set_xalign(0)
        info_vbox.pack_start(self.profile_status_label, False, False, 0)

        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        info_vbox.pack_start(self.status_label, False, False, 0)

        self.clocks_label = Gtk.Label()
        self.clocks_label.set_xalign(0)
        info_vbox.pack_start(self.clocks_label, False, False, 0)

        self.daemon_status_label = Gtk.Label()
        self.daemon_status_label.set_xalign(0)
        info_vbox.pack_start(self.daemon_status_label, False, False, 0)

        # Nota para GPU movil (oculta por defecto)
        self.mobile_note_label = Gtk.Label()
        self.mobile_note_label.set_markup(
            "<small><span color='#e65100'>⚠ GPU movil: solo control PowerMizer. "
            "El ajuste se resetea al reiniciar.</span></small>"
        )
        self.mobile_note_label.set_xalign(0)
        self.mobile_note_label.set_no_show_all(True)
        info_vbox.pack_start(self.mobile_note_label, False, False, 0)

        header_box.pack_start(info_vbox, True, True, 0)

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh_btn.set_tooltip_text("Actualizar datos")
        refresh_btn.connect("clicked", lambda b: self.refresh_status())
        header_box.pack_end(refresh_btn, False, False, 0)

        header_frame.add(header_box)
        main_box.pack_start(header_frame, False, False, 0)

        # --- Selector de GPU (solo si hay mas de 1) ----------------------
        self.gpu_selector_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.gpu_selector_box.set_no_show_all(True)

        gpu_sel_label = Gtk.Label(label="GPU activa:")
        gpu_sel_label.set_xalign(0)
        self.gpu_selector_box.pack_start(gpu_sel_label, False, False, 0)

        self.gpu_combo = Gtk.ComboBoxText()
        self.gpu_combo.connect("changed", self._on_gpu_changed)
        self.gpu_selector_box.pack_start(self.gpu_combo, True, True, 0)

        main_box.pack_start(self.gpu_selector_box, False, False, 0)

        # --- Seccion de perfiles -----------------------------------------
        self.profiles_frame = Gtk.Frame(label=" Perfiles de Consumo ")
        self.profiles_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.profiles_vbox.set_border_width(10)
        self.profiles_frame.add(self.profiles_vbox)
        main_box.pack_start(self.profiles_frame, True, True, 0)

        # --- Persistencia systemd ----------------------------------------
        persist_frame = Gtk.Frame(label=" Inicio Automatico (Daemon / Systemd) ")
        persist_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        persist_box.set_border_width(8)

        self.cb_daemon = Gtk.CheckButton(label="Activar siempre al encender el PC")
        persist_box.pack_start(self.cb_daemon, False, False, 0)

        self.persist_info = Gtk.Label()
        self.persist_info.set_markup(
            "<small><span color='#555'>Aplica el perfil seleccionado "
            "automaticamente en cada arranque del sistema.</span></small>"
        )
        self.persist_info.set_xalign(0)
        self.persist_info.set_margin_left(24)
        persist_box.pack_start(self.persist_info, False, False, 0)

        persist_frame.add(persist_box)
        self.persist_frame = persist_frame
        main_box.pack_start(persist_frame, False, False, 0)

        # --- Botones de accion -------------------------------------------
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)

        close_btn = Gtk.Button(label="Cerrar")
        close_btn.connect("clicked", lambda b: self.close())
        button_box.pack_start(close_btn, False, False, 0)

        self.apply_btn = Gtk.Button(label=" Aplicar Configuracion ")
        self.apply_btn.get_style_context().add_class("suggested-action")
        self.apply_btn.connect("clicked", self.on_apply_clicked)
        button_box.pack_start(self.apply_btn, False, False, 0)

        main_box.pack_start(button_box, False, False, 0)

        return main_box

    def _on_gpu_changed(self, combo):
        idx = combo.get_active()
        if idx < 0 or idx >= len(self.gpus):
            return
        self.current_gpu = self.gpus[idx]
        self._update_gpu_header()
        self._build_profile_widgets()
        self.refresh_status()

    def _update_gpu_header(self):
        gpu = self.current_gpu
        if gpu is None:
            return
        self.title_label.set_markup(f"<b><big>{gpu.display_name}</big></b>")

        # Ajustar controles segun si es GPU movil o escritorio
        if gpu.is_mobile:
            self.mobile_note_label.set_markup(
                "<small><span color='#0277bd'>ℹ GPU de portátil: control optimizado PowerMizer adaptado al hardware.</span></small>"
            )
            self.mobile_note_label.show()
            self.cb_daemon.set_sensitive(True)
            self.cb_daemon.set_label("Activar perfil al iniciar sesión")
            self.persist_frame.set_sensitive(True)
            self.persist_frame.set_label(" Inicio Automático (Sesión de Usuario) ")
            self.persist_info.set_markup(
                "<small><span color='#555'>Aplica el perfil de PowerMizer seleccionado "
                "automáticamente cada vez que inicies sesión.</span></small>"
            )
            self.profiles_frame.set_label(" Perfiles de Energía (PowerMizer) ")
        else:
            self.mobile_note_label.hide()
            self.cb_daemon.set_sensitive(True)
            self.cb_daemon.set_label("Activar siempre al encender el PC")
            self.persist_frame.set_sensitive(True)
            self.persist_frame.set_label(" Inicio Automatico (Daemon / Systemd) ")
            self.persist_info.set_markup(
                "<small><span color='#555'>Aplica el perfil seleccionado "
                "automaticamente en cada arranque del sistema.</span></small>"
            )
            self.profiles_frame.set_label(" Perfiles de Consumo ")

    def _build_profile_widgets(self):
        """Reconstruye los radio buttons segun la GPU seleccionada sin seleccion inicial por defecto."""
        for w in self._profile_widgets:
            self.profiles_vbox.remove(w)
        self._profile_widgets = []
        self.profile_radio_buttons = []

        gpu = self.current_gpu
        if gpu is None:
            return

        # RadioButton oculto del grupo que absorbe la seleccion inicial
        self._dummy_rb = Gtk.RadioButton.new_with_label(None, "None")
        self._dummy_rb.set_active(True)

        for profile in gpu.profiles:
            label_text = f"{profile.emoji} {profile.description_short}"
            rb = Gtk.RadioButton.new_with_label_from_widget(self._dummy_rb, label_text)
            rb.set_active(False)
            rb.connect("toggled", self._on_profile_toggled)

            sub = Gtk.Label()
            desc = profile.description_long.replace("&", "&amp;")
            sub.set_markup(f"<small><span color='#555'>{desc}</span></small>")
            sub.set_xalign(0)
            sub.set_margin_left(24)

            self.profiles_vbox.pack_start(rb, False, False, 0)
            self.profiles_vbox.pack_start(sub, False, False, 0)
            self._profile_widgets.extend([rb, sub])
            self.profile_radio_buttons.append((rb, profile))

        self.apply_btn.set_sensitive(False)
        self.profiles_vbox.show_all()

    def _on_profile_toggled(self, rb):
        """Habilita el boton de aplicar y gestiona el checkbox de persistencia segun la opcion."""
        if not rb.get_active():
            return
        profile = self._get_selected_profile()
        if profile is not None:
            self.apply_btn.set_sensitive(True)
            if profile.name == "De Fabrica":
                self.cb_daemon.set_active(False)
                self.cb_daemon.set_sensitive(False)
                self.cb_daemon.set_tooltip_text(
                    "El modo De Fábrica no necesita inicio automático (resultaría redundante)."
                )
            else:
                self.cb_daemon.set_sensitive(True)
                self.cb_daemon.set_tooltip_text("")

    def get_gpu_data(self):
        if self.current_gpu is None:
            return 0.0, "N/A", "N/A", "N/A", "N/A"
        try:
            cmd = [
                "nvidia-smi",
                f"--id={self.current_gpu.gpu_index}",
                "--query-gpu=power.draw,temperature.gpu,utilization.gpu,clocks.current.graphics,clocks.current.memory",
                "--format=csv,noheader,nounits",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                watts = float(parts[0]) if parts[0] != "[N/A]" else 0.0
                temp = f"{parts[1]} C" if len(parts) > 1 else "N/A"
                util = f"{parts[2]}%" if len(parts) > 2 else "N/A"
                c_core = f"{parts[3]} MHz" if len(parts) > 3 else "N/A"
                c_mem = f"{parts[4]} MHz" if len(parts) > 4 else "N/A"
                return watts, temp, util, c_core, c_mem
        except Exception:
            pass
        return 0.0, "N/A", "N/A", "N/A", "N/A"

    def is_daemon_enabled(self) -> bool:
        if self.current_gpu is None:
            return False
        if self.current_gpu.is_mobile:
            gpu_idx = self.current_gpu.gpu_index
            candidates = [
                os.path.expanduser(
                    f"~/.config/autostart/nvidia-optimizer-powermizer-gpu{gpu_idx}.desktop"
                ),
                f"/etc/xdg/autostart/nvidia-optimizer-powermizer-gpu{gpu_idx}.desktop",
            ]
            return any(os.path.isfile(p) for p in candidates)
        try:
            res = subprocess.run(
                ["systemctl", "is-enabled", self.current_gpu.service_name],
                capture_output=True, text=True,
            )
            # "enabled"/"enabled-runtime" indican que esta activo al arranque.
            return res.stdout.strip().startswith("enabled")
        except Exception:
            return False

    def _stale_autostart_path(self) -> Optional[str]:
        """Devuelve la ruta de una copia de autostart mal ubicada en /root.

        Una version anterior de apply.sh escribia el autostart en el HOME de
        root al ejecutarse via pkexec, dejando un archivo inerte y haciendo que
        el daemon pareciera desactivado al reabrir la app.
        """
        if self.current_gpu is None or not self.current_gpu.is_mobile:
            return None
        path = (f"/root/.config/autostart/"
                f"nvidia-optimizer-powermizer-gpu{self.current_gpu.gpu_index}.desktop")
        return path if os.path.isfile(path) else None

    # -------------------------------------------------------------------------
    # Deteccion del perfil de energia realmente aplicado
    # -------------------------------------------------------------------------

    _POWERMIZER_NAMES = {0: "Adaptativo", 1: "Maximo Rendimiento", 2: "Automatico"}

    def _profile_detail(self, profile) -> str:
        """Texto corto con el valor concreto del perfil (vatios o modo PowerMizer)."""
        gpu = self.current_gpu
        if gpu is not None and gpu.supports_power_limit:
            detail = f"{profile.watts} W"
            if profile.eco_max_clock:
                detail += f" + {profile.eco_max_clock} MHz"
            return detail
        return "PowerMizer " + self._POWERMIZER_NAMES.get(
            profile.powermizer_mode, str(profile.powermizer_mode)
        )

    def _detect_profile_by_hardware(self):
        """Lee el estado real de la GPU e intenta identificar el perfil aplicado.

        - Escritorio: el limite de potencia (nvidia-smi) identifica univocamente
          cada perfil, ya que cada uno usa unos vatios distintos.
        - Movil / sin power limit: el modo PowerMizer activo (nvidia-settings).
        Devuelve un PowerProfile o None si no se puede determinar.
        """
        gpu = self.current_gpu
        if gpu is None or not gpu.profiles:
            return None

        if gpu.supports_power_limit:
            limit = None
            try:
                res = subprocess.run(
                    ["nvidia-smi",
                     f"--id={gpu.gpu_index}",
                     "--query-gpu=power.limit",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5, check=True,
                )
                limit = float(res.stdout.strip().split(",")[0])
            except Exception:
                limit = None
            if limit is None:
                return None
            for profile in gpu.profiles:
                if profile.watts > 0 and abs(profile.watts - limit) <= 1.0:
                    return profile
            return None

        # GPU sin power limit: identificar por modo PowerMizer activo
        out = ""
        try:
            res = subprocess.run(
                ["nvidia-settings", "-q",
                 f"[gpu:{gpu.gpu_index}]/GPUPowerMizerMode", "-t"],
                capture_output=True, text=True, timeout=5,
            )
            out = res.stdout.strip()
        except Exception:
            out = ""

        mode = None
        match = re.search(r":\s*(\d+)\s*$", out)
        if match:
            mode = int(match.group(1))
        elif out.isdigit():
            mode = int(out)
        if mode is None:
            return None

        for profile in gpu.profiles:
            if profile.powermizer_mode == mode:
                return profile
        return None

    def get_current_profile(self):
        """Devuelve (perfil, origen) del perfil actual.

        origen = "hw"   -> leido directamente del hardware (fiable).
        origen = "saved" -> ultimo perfil guardado por la app (no verificado).
        (None, None)    -> no hay forma de saber que perfil esta aplicado.
        """
        gpu = self.current_gpu
        if gpu is None or not gpu.profiles:
            return None, None

        profile = self._detect_profile_by_hardware()
        if profile is not None:
            return profile, "hw"

        saved_name = _get_saved_profile(gpu.gpu_index)
        if saved_name:
            for profile in gpu.profiles:
                if profile.name == saved_name:
                    return profile, "saved"
        return None, None

    def refresh_status(self):
        gpu = self.current_gpu
        if gpu is None:
            return

        watts, temp, util, c_core, c_mem = self.get_gpu_data()
        self.status_label.set_markup(
            f"<b>Consumo:</b> {watts:.1f} W   |   "
            f"<b>Temp:</b> {temp}   |   "
            f"<b>Uso GPU:</b> {util}"
        )
        self.clocks_label.set_markup(
            f"<b>Reloj Nucleo:</b> {c_core}   |   "
            f"<b>VRAM:</b> {c_mem}"
        )

        # ---- Inicio automatico (daemon) ----------------------------------
        daemon_active = self.is_daemon_enabled()
        self.cb_daemon.set_active(daemon_active)

        # ---- Perfil de energia actual ------------------------------------
        profile, source = self.get_current_profile()

        if profile is not None and self.profile_radio_buttons:
            for rb, p in self.profile_radio_buttons:
                if p.name == profile.name:
                    if not rb.get_active():
                        rb.set_active(True)   # dispara _on_profile_toggled
                    break
            self.apply_btn.set_sensitive(True)

            note = ""
            saved_name = _get_saved_profile(gpu.gpu_index)
            if source == "hw":
                if saved_name and saved_name != profile.name:
                    note = (f" <span color='#e65100'>(perfil guardado: "
                            f"{GLib.markup_escape_text(saved_name)}, sin aplicar "
                            f"al arrancar)</span>")
            else:
                note = " <span color='#757575'>(último perfil guardado, sin verificar)</span>"

            detail = GLib.markup_escape_text(self._profile_detail(profile))
            self.profile_status_label.set_markup(
                f"Perfil actual: <b>{profile.emoji} "
                f"{GLib.markup_escape_text(profile.name)}</b> — {detail}{note}"
            )
        else:
            if getattr(self, "_dummy_rb", None):
                self._dummy_rb.set_active(True)
            self.apply_btn.set_sensitive(False)
            self.profile_status_label.set_markup(
                "Perfil actual: <span color='#757575'>no detectado "
                "(aún no se ha aplicado ninguno)</span>"
            )

        # ---- Aviso del estado del daemon ---------------------------------
        if daemon_active:
            desc = "autostart de sesión" if gpu.is_mobile else "servicio systemd"
            if profile is not None and profile.name == "De Fabrica":
                self.daemon_status_label.set_markup(
                    "Inicio automático: <span color='#e65100'><b>ACTIVO</b></span> "
                    f"({desc}) — <span color='#e65100'>redundante con el perfil "
                    "De Fábrica: pulsa «Aplicar Configuracion» para desactivarlo.</span>"
                )
            else:
                target = (f"«{GLib.markup_escape_text(profile.name)}»"
                          if profile is not None else "el perfil guardado")
                self.daemon_status_label.set_markup(
                    "Inicio automático: <span color='#2e7d32'><b>ACTIVO</b></span> "
                    f"({desc}) — aplicará {target} al arrancar"
                )
        else:
            stale_warn = ""
            stale_path = self._stale_autostart_path()
            if stale_path:
                stale_warn = (
                    " <span color='#e65100'>⚠ Se detectó una copia antigua del "
                    "inicio automático en /root procedente de una versión anterior. "
                    "Marca la casilla y pulsa «Aplicar Configuracion» para corregirla.</span>"
                )
            self.daemon_status_label.set_markup(
                "Inicio automático: <span color='#757575'><b>DESACTIVADO</b></span> "
                "— el perfil solo se aplica en esta sesión" + stale_warn
            )

    def _get_selected_profile(self):
        for rb, profile in self.profile_radio_buttons:
            if rb.get_active():
                return profile
        return None

    def execute_privileged(self, profile, enable_daemon: bool):
        gpu = self.current_gpu
        args = [
            APPLY_SCRIPT,
            str(profile.watts),
            str(gpu.gpu_index),
            "1" if enable_daemon else "0",
            str(profile.eco_min_clock),
            str(profile.eco_max_clock),
            str(profile.powermizer_mode),
        ]

        # 1. Intentar pkexec
        try:
            proc = subprocess.run(["pkexec"] + args, capture_output=True, text=True)
            if proc.returncode == 0:
                subprocess.run(
                    ["nvidia-settings", "-a",
                     f"[gpu:{gpu.gpu_index}]/GPUPowerMizerMode={profile.powermizer_mode}"],
                    capture_output=True
                )
                return True, "Configuracion aplicada con exito."
            elif proc.returncode in (126, 127):
                pass
            else:
                stderr_l = proc.stderr.lower()
                if "dismissed" in stderr_l or proc.returncode == 1:
                    return False, "Operacion cancelada por el usuario."
        except Exception:
            pass

        # 2. Fallback con zenity + sudo -S
        try:
            res = subprocess.run(
                ["zenity", "--password",
                 "--title=Permisos de Administrador",
                 "--text=Introduce tu contrasena para aplicar los cambios de energia:"],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                return False, "Operacion cancelada."
            pwd = res.stdout.strip()
            if not pwd:
                return False, "Contrasena vacia."

            proc = subprocess.run(
                ["sudo", "-S"] + args,
                input=pwd + "\n", capture_output=True, text=True,
            )
            if proc.returncode == 0:
                subprocess.run(
                    ["nvidia-settings", "-a",
                     f"[gpu:{gpu.gpu_index}]/GPUPowerMizerMode={profile.powermizer_mode}"],
                    capture_output=True
                )
                return True, "Configuracion aplicada con exito."
            else:
                return False, f"Error al aplicar: {proc.stderr}"
        except Exception as e:
            return False, str(e)

    def on_apply_clicked(self, widget):
        profile = self._get_selected_profile()
        if profile is None:
            return

        enable_daemon = self.cb_daemon.get_active()
        if profile.name == "De Fabrica":
            enable_daemon = False

        self.apply_btn.set_sensitive(False)
        while Gtk.events_pending():
            Gtk.main_iteration()

        success, msg = self.execute_privileged(profile, enable_daemon)
        self.apply_btn.set_sensitive(True)

        if success:
            # Guardar siempre el perfil aplicado para poder informar de él al
            # volver a abrir la app, tenga o no inicio automático.
            _save_profile(self.current_gpu.gpu_index, profile.name)

            self.refresh_status()

            if profile.name == "De Fabrica":
                daemon_msg = (
                    "Se ha restaurado el estado De Fábrica original y se ha "
                    "desactivado el inicio automático (resultaba redundante en "
                    "este modo, por lo que no se volverá a aplicar al arrancar)."
                )
                if self.is_daemon_enabled():
                    daemon_msg += (
                        "\n\n⚠ El inicio automático sigue activo. Vuelve a pulsar "
                        "«Aplicar Configuracion» para intentar desactivarlo."
                    )
            elif self.current_gpu and not self.current_gpu.is_mobile:
                daemon_msg = (
                    "El servicio de arranque queda ACTIVADO."
                    if enable_daemon else
                    "Ajuste aplicado únicamente para la sesión actual."
                )
            else:
                daemon_msg = (
                    "El perfil de PowerMizer se aplicará al iniciar sesión."
                    if enable_daemon else
                    "Ajuste aplicado únicamente para la sesión actual."
                )

            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Ajustes aplicados correctamente!",
            )
            dialog.format_secondary_text(
                f"Perfil: {profile.emoji} {profile.name}\n\n{daemon_msg}"
            )
            dialog.run()
            dialog.destroy()
        else:
            if "cancelada" not in msg.lower():
                dialog = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="No se pudo aplicar la configuracion",
                )
                dialog.format_secondary_text(msg)
                dialog.run()
                dialog.destroy()

    def _show_no_gpu_error(self, custom_msg=None):
        """Muestra un mensaje de error si no se detecta ninguna GPU NVIDIA o el driver falla."""
        self.apply_btn.set_sensitive(False)
        self.cb_daemon.set_sensitive(False)

        if custom_msg and "version mismatch" in custom_msg.lower():
            self.title_label.set_markup(
                "<b><big><span color='#e65100'>⚠ Reinicio Requerido (Driver NVIDIA)</span></big></b>"
            )
            self.status_label.set_markup(
                "<span color='#bf360c'><b>Conflicto de versiones (Driver mismatch)</b></span>\n"
                "<small>Se ha actualizado el driver pero el kernel sigue usando la versión anterior.\n"
                "<b>Reinicia el equipo ('sudo reboot')</b> para activar el driver.</small>"
            )
        elif custom_msg:
            self.title_label.set_markup(
                "<b><big><span color='#c62828'>Problema con el Driver NVIDIA</span></big></b>"
            )
            safe_msg = GLib.markup_escape_text(custom_msg)
            self.status_label.set_markup(f"<small><span color='#555'>{safe_msg}</span></small>")
        else:
            self.title_label.set_markup(
                "<b><big><span color='#c62828'>Sin GPU NVIDIA detectada</span></big></b>"
            )
            self.status_label.set_markup(
                "<span color='#555'>Asegúrate de tener el driver propietario NVIDIA instalado.\n"
                "Comprueba en la terminal con: <tt>nvidia-smi</tt></span>"
            )

        self.clocks_label.set_text("")
        self.daemon_status_label.set_text("")
        self.profile_status_label.set_text("")

    # =========================================================================
    # PESTAÑA CPU (Construcción y Lógica de Gestión de Energía)
    # =========================================================================

    def _build_cpu_page(self):
        """Construye el panel completo de gestión de energía y undervolt de la CPU."""
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_border_width(10)
        scrolled.add(vbox)

        # 1. Cabecera / Tarjeta informativa de la CPU
        header_frame = Gtk.Frame()
        header_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        header_box.set_border_width(10)

        cpu_icon = Gtk.Image.new_from_icon_name("computer", Gtk.IconSize.DIALOG)
        header_box.pack_start(cpu_icon, False, False, 0)

        info_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)

        self.cpu_title_label = Gtk.Label()
        self.cpu_title_label.set_markup("<b><big>Detectando procesador...</big></b>")
        self.cpu_title_label.set_xalign(0)
        info_vbox.pack_start(self.cpu_title_label, False, False, 0)

        self.cpu_profile_status_label = Gtk.Label()
        self.cpu_profile_status_label.set_xalign(0)
        info_vbox.pack_start(self.cpu_profile_status_label, False, False, 0)

        self.cpu_status_label = Gtk.Label()
        self.cpu_status_label.set_xalign(0)
        info_vbox.pack_start(self.cpu_status_label, False, False, 0)

        self.cpu_telemetry_label = Gtk.Label()
        self.cpu_telemetry_label.set_xalign(0)
        info_vbox.pack_start(self.cpu_telemetry_label, False, False, 0)

        self.cpu_daemon_status_label = Gtk.Label()
        self.cpu_daemon_status_label.set_xalign(0)
        info_vbox.pack_start(self.cpu_daemon_status_label, False, False, 0)

        header_box.pack_start(info_vbox, True, True, 0)

        cpu_refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        cpu_refresh_btn.set_tooltip_text("Actualizar estado de la CPU")
        cpu_refresh_btn.connect("clicked", lambda b: self._cpu_refresh_status())
        header_box.pack_end(cpu_refresh_btn, False, False, 0)

        header_frame.add(header_box)
        vbox.pack_start(header_frame, False, False, 0)

        # 2. Sección de Selección de Perfiles
        self.cpu_profiles_frame = Gtk.Frame(label=" Perfiles de Consumo CPU ")
        cpu_profiles_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cpu_profiles_vbox.set_border_width(10)

        self.cpu_profile_radio_buttons = []
        first_rb = None

        if self.cpu_info and self.cpu_info.profiles:
            for profile in self.cpu_info.profiles:
                p_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

                rb = Gtk.RadioButton.new_from_widget(first_rb)
                if first_rb is None:
                    first_rb = rb

                rb_label = Gtk.Label()
                rb_label.set_markup(f"<b>{profile.emoji} {profile.description_short}</b>")
                rb_label.set_xalign(0)
                rb.add(rb_label)

                desc_label = Gtk.Label()
                desc_label.set_markup(
                    f"<small><span color='#555'>{profile.description_long}</span></small>"
                )
                desc_label.set_xalign(0)
                desc_label.set_margin_left(24)

                p_box.pack_start(rb, False, False, 0)
                p_box.pack_start(desc_label, False, False, 0)
                cpu_profiles_vbox.pack_start(p_box, False, False, 0)

                self.cpu_profile_radio_buttons.append((rb, profile))
        else:
            no_cpu_lbl = Gtk.Label(label="No se detectaron perfiles compatibles para esta CPU.")
            cpu_profiles_vbox.pack_start(no_cpu_lbl, False, False, 0)

        self.cpu_profiles_frame.add(cpu_profiles_vbox)
        vbox.pack_start(self.cpu_profiles_frame, False, False, 0)

        # 3. Sección de Persistencia (Systemd)
        cpu_persist_frame = Gtk.Frame(label=" Inicio Automático (Daemon / Systemd) ")
        cpu_persist_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cpu_persist_box.set_border_width(8)

        self.cb_cpu_daemon = Gtk.CheckButton(
            label="Activar este perfil en cada arranque del sistema (servicio systemd)"
        )
        self.cb_cpu_daemon.set_tooltip_text(
            "Crea el servicio cpu-power-optimizer.service para aplicar el perfil "
            "automáticamente al iniciar el equipo."
        )
        cpu_persist_box.pack_start(self.cb_cpu_daemon, False, False, 0)

        cpu_daemon_note = Gtk.Label()
        cpu_daemon_note.set_markup(
            "<small><span color='#555'>Si marcas esta opción, el perfil se mantendrá "
            "tras reiniciar. Al pulsar «De Fábrica», el daemon se desactivará automáticamente.</span></small>"
        )
        cpu_daemon_note.set_xalign(0)
        cpu_daemon_note.set_margin_left(24)
        cpu_persist_box.pack_start(cpu_daemon_note, False, False, 0)

        cpu_persist_frame.add(cpu_persist_box)
        vbox.pack_start(cpu_persist_frame, False, False, 0)

        # 4. Botón de Aplicar
        cpu_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.cpu_apply_btn = Gtk.Button(label=" ⚡ Aplicar Configuración CPU ")
        self.cpu_apply_btn.get_style_context().add_class("suggested-action")
        self.cpu_apply_btn.connect("clicked", self._on_apply_cpu_clicked)
        cpu_btn_box.pack_start(self.cpu_apply_btn, False, False, 0)

        self.cpu_spinner = Gtk.Spinner()
        cpu_btn_box.pack_start(self.cpu_spinner, False, False, 0)

        vbox.pack_start(cpu_btn_box, False, False, 0)

        # 5. Registro de Salida (Expander)
        self.cpu_log_expander = Gtk.Expander(label="Detalles y registro de operaciones (CPU)")
        cpu_log_scroll = Gtk.ScrolledWindow()
        cpu_log_scroll.set_min_content_height(100)
        cpu_log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.cpu_log_view = Gtk.TextView()
        self.cpu_log_view.set_editable(False)
        self.cpu_log_view.set_monospace(True)
        self.cpu_log_buffer = self.cpu_log_view.get_buffer()
        cpu_log_scroll.add(self.cpu_log_view)

        self.cpu_log_expander.add(cpu_log_scroll)
        vbox.pack_start(self.cpu_log_expander, False, False, 0)

        return scrolled

    def _append_cpu_log(self, text: str):
        """Añade una línea al buffer de log de la CPU."""
        end_iter = self.cpu_log_buffer.get_end_iter()
        self.cpu_log_buffer.insert(end_iter, text + "\n")
        self.cpu_log_view.scroll_to_iter(self.cpu_log_buffer.get_end_iter(), 0.0, False, 0.0, 0.0)

    def _get_selected_cpu_profile(self) -> Optional[CpuProfile]:
        for rb, profile in self.cpu_profile_radio_buttons:
            if rb.get_active():
                return profile
        return None

    def _cpu_refresh_status(self):
        """Actualiza la telemetría e indicadores de estado de la CPU."""
        if not _CPU_MANAGER_OK or not self.cpu_info:
            self.cpu_title_label.set_markup("<b><big><span color='#c62828'>Gestor de CPU no disponible</span></big></b>")
            return

        cpu = self.cpu_info
        self.cpu_title_label.set_markup(f"<b><big>{cpu.name}</big></b>")

        # Telemetría y estado actual
        state = read_cpu_state()
        temp_str = f"{state['temp_celsius']} °C" if state.get("temp_celsius") is not None else "N/A"
        freq_str = f"{state['cur_freq_mhz']} MHz" if state.get("cur_freq_mhz", 0) > 0 else "N/A"
        max_f_str = f"{state['max_freq_mhz']} MHz" if state.get("max_freq_mhz", 0) > 0 else "N/A"
        turbo_str = "ON" if state.get("turbo", True) else "OFF"
        rapl_str = f" | TDP: <b>{state['rapl_limit_w']:.0f} W</b>" if state.get("rapl_limit_w", 0) > 0 else ""

        self.cpu_status_label.set_markup(
            f"<b>Temp:</b> {temp_str}   |   "
            f"<b>Frecuencia actual:</b> {freq_str}   |   "
            f"<b>Máx:</b> {max_f_str}"
        )

        self.cpu_telemetry_label.set_markup(
            f"<b>Governor:</b> {state.get('governor', 'powersave')}   |   "
            f"<b>EPP:</b> {state.get('epp', 'balance_performance')}   |   "
            f"<b>Turbo:</b> {turbo_str}{rapl_str}"
        )

        # Estado del daemon
        daemon_active = get_cpu_daemon_status()
        self.cb_cpu_daemon.set_active(daemon_active)

        if daemon_active:
            self.cpu_daemon_status_label.set_markup(
                "Inicio automático: <span color='#2e7d32'><b>ACTIVADO</b></span> "
                "(se mantendrá tras reiniciar el equipo)"
            )
        else:
            self.cpu_daemon_status_label.set_markup(
                "Inicio automático: <span color='#757575'><b>DESACTIVADO</b></span> "
                "(el ajuste solo se aplica en esta sesión)"
            )

        # Perfil activo
        active_profile = identify_active_profile(cpu)
        saved_key = _get_saved_cpu_profile()

        target_profile = active_profile
        if target_profile is None and saved_key:
            for p in cpu.profiles:
                if p.key == saved_key:
                    target_profile = p
                    break

        if target_profile:
            for rb, p in self.cpu_profile_radio_buttons:
                if p.key == target_profile.key:
                    if not rb.get_active():
                        rb.set_active(True)
                    break

            source_txt = "detectado del hardware" if active_profile else "último aplicado"
            alfa_badge = " <span color='#e5a50a'><b>[Alfa]</b></span>" if target_profile.key == "eco_plus" else ""
            self.cpu_profile_status_label.set_markup(
                f"Perfil activo: <span color='#1565c0'><b>{target_profile.emoji} {target_profile.name}</b></span>{alfa_badge} "
                f"<small>({source_txt})</small>"
            )
        else:
            self.cpu_profile_status_label.set_markup(
                "Perfil activo: <span color='#e65100'><b>Personalizado / No identificado</b></span>"
            )

    def execute_cpu_privileged(self, profile: CpuProfile, enable_daemon: bool) -> Tuple[bool, str]:
        """Ejecuta cpu_apply.sh con privilegios root (pkexec o zenity fallback)."""
        args = [
            CPU_APPLY_SCRIPT,
            profile.key,
            "1" if enable_daemon else "0",
            SCRIPT_DIR,
        ]

        # 1. Intentar pkexec
        try:
            proc = subprocess.run(["pkexec"] + args, capture_output=True, text=True)
            if proc.returncode == 0:
                return True, proc.stdout
            elif proc.returncode in (126, 127):
                pass
            else:
                stderr_l = proc.stderr.lower()
                if "dismissed" in stderr_l or proc.returncode == 1:
                    return False, "Operación cancelada por el usuario."
        except Exception:
            pass

        # 2. Fallback zenity + sudo -S
        try:
            res = subprocess.run(
                ["zenity", "--password",
                 "--title=Permisos de Administrador",
                 "--text=Introduce tu contraseña para aplicar la configuración de energía de la CPU:"],
                capture_output=True, text=True
            )
            if res.returncode != 0:
                return False, "Operación cancelada."
            pwd = res.stdout.strip()
            if not pwd:
                return False, "Contraseña vacía."

            proc = subprocess.run(
                ["sudo", "-S"] + args,
                input=pwd + "\n", capture_output=True, text=True
            )
            if proc.returncode == 0:
                return True, proc.stdout
            else:
                return False, f"Error al aplicar: {proc.stderr}"
        except Exception as e:
            return False, str(e)

    def _on_apply_cpu_clicked(self, widget):
        """Manejador del botón aplicar configuración de CPU."""
        profile = self._get_selected_cpu_profile()
        if profile is None:
            return

        enable_daemon = self.cb_cpu_daemon.get_active()
        if profile.key == "factory":
            enable_daemon = False

        self.cpu_apply_btn.set_sensitive(False)
        self.cpu_spinner.start()
        self.cpu_log_expander.set_expanded(True)
        self._append_cpu_log(f"\n=== APLICANDO PERFIL CPU: {profile.emoji} {profile.name} ===")

        def cpu_worker():
            ok, output = self.execute_cpu_privileged(profile, enable_daemon)

            def on_finish():
                self.cpu_spinner.stop()
                self.cpu_apply_btn.set_sensitive(True)
                for line in output.splitlines():
                    self._append_cpu_log(line)

                self._cpu_refresh_status()

                if ok:
                    _save_cpu_profile(profile.key)
                    if profile.key == "factory":
                        daemon_msg = (
                            "Se ha restaurado el estado De Fábrica original y se ha "
                            "desactivado el inicio automático de la CPU."
                        )
                    else:
                        daemon_msg = (
                            "El servicio de arranque queda ACTIVADO (cpu-power-optimizer.service)."
                            if enable_daemon else
                            "El servicio de arranque queda DESACTIVADO (solo activo en esta sesión)."
                        )

                    dlg = Gtk.MessageDialog(
                        transient_for=self,
                        flags=0,
                        message_type=Gtk.MessageType.INFO,
                        buttons=Gtk.ButtonsType.OK,
                        text=f"¡Perfil CPU «{profile.name}» aplicado con éxito!",
                    )
                    dlg.format_secondary_text(daemon_msg)
                    dlg.run()
                    dlg.destroy()
                else:
                    if "cancelada" not in output.lower():
                        dlg = Gtk.MessageDialog(
                            transient_for=self,
                            flags=0,
                            message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK,
                            text="Error al aplicar el perfil de CPU",
                        )
                        dlg.format_secondary_text(output)
                        dlg.run()
                        dlg.destroy()

            GLib.idle_add(on_finish)

        threading.Thread(target=cpu_worker, daemon=True).start()

    # =========================================================================
    # PESTAÑA UTILS (Construcción y Lógica de Limpieza)
    # =========================================================================

    def _build_utils_page(self):
        """Construye el panel completo de utilidades de disco y limpieza del sistema."""
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_border_width(10)
        scrolled.add(vbox)

        # 1. Cabecera / Tarjeta de Almacenamiento
        disk_frame = Gtk.Frame()
        disk_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        disk_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        disk_box.set_border_width(10)

        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        disk_icon = Gtk.Image.new_from_icon_name("drive-harddisk", Gtk.IconSize.DIALOG)
        header_row.pack_start(disk_icon, False, False, 0)

        disk_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label()
        title.set_markup("<b><big>Almacenamiento del Sistema (/)</big></b>")
        title.set_xalign(0)
        disk_info_box.pack_start(title, False, False, 0)

        self.disk_stats_label = Gtk.Label()
        self.disk_stats_label.set_markup("Leyendo estado del disco...")
        self.disk_stats_label.set_xalign(0)
        disk_info_box.pack_start(self.disk_stats_label, False, False, 0)

        header_row.pack_start(disk_info_box, True, True, 0)

        disk_refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        disk_refresh_btn.set_tooltip_text("Actualizar estado del almacenamiento")
        disk_refresh_btn.connect("clicked", lambda b: self._refresh_disk_info())
        header_row.pack_end(disk_refresh_btn, False, False, 0)

        disk_box.pack_start(header_row, False, False, 0)

        # Barra de progreso del disco
        self.disk_progress = Gtk.ProgressBar()
        self.disk_progress.set_show_text(True)
        self.disk_progress.set_fraction(0.0)
        disk_box.pack_start(self.disk_progress, False, False, 0)

        # Fila de optimización TRIM para SSD
        trim_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        trim_row.set_margin_top(4)

        trim_info = Gtk.Label()
        trim_info.set_markup("<small><span color='#555'>Mantenimiento SSD: libera bloques físicos no utilizados para preservar velocidad y vida útil.</span></small>")
        trim_info.set_xalign(0)
        trim_row.pack_start(trim_info, True, True, 0)

        self.trim_btn = Gtk.Button(label=" ⚡ Optimizar SSD (TRIM) ")
        self.trim_btn.set_tooltip_text("Ejecuta fstrim para recortar bloques no usados en el SSD (requiere root)")
        self.trim_btn.connect("clicked", self._on_trim_clicked)
        trim_row.pack_end(self.trim_btn, False, False, 0)

        disk_box.pack_start(trim_row, False, False, 0)

        disk_frame.add(disk_box)
        vbox.pack_start(disk_frame, False, False, 0)

        # 2. Frame de Limpieza de Espacio
        cleanup_frame = Gtk.Frame(label=" Herramientas de Liberación de Espacio ")
        cleanup_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cleanup_box.set_border_width(10)

        # Barra de acciones de escaneo
        scan_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.scan_summary_label = Gtk.Label()
        self.scan_summary_label.set_markup("<small><span color='#555'>Pulsa 'Analizar' para calcular el espacio recuperable.</span></small>")
        self.scan_summary_label.set_xalign(0)
        scan_bar.pack_start(self.scan_summary_label, True, True, 0)

        self.scan_spinner = Gtk.Spinner()
        scan_bar.pack_start(self.scan_spinner, False, False, 0)

        self.scan_btn = Gtk.Button(label=" Analizar Espacio ")
        self.scan_btn.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.scan_btn.set_always_show_image(True)
        self.scan_btn.connect("clicked", lambda b: self._start_scan_async(silent=False))
        scan_bar.pack_end(self.scan_btn, False, False, 0)

        cleanup_box.pack_start(scan_bar, False, False, 0)
        cleanup_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)

        # Lista de tareas
        for task in self.cleaner_tasks:
            task_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

            # Checkbox + info
            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            cb = Gtk.CheckButton(label=task.title)
            cb.set_active(task.default_enabled)
            self.task_check_buttons[task.key] = cb

            # Si requiere root, añadir distintivo sutil
            if task.requires_root:
                cb.get_children()[0].set_markup(f"<b>{task.title}</b> <small><span color='#777'>(Requiere root)</span></small>")
            else:
                cb.get_children()[0].set_markup(f"<b>{task.title}</b>")

            desc = Gtk.Label()
            desc.set_markup(f"<small><span color='#666'>{task.description}</span></small>")
            desc.set_xalign(0)
            desc.set_margin_left(24)

            text_box.pack_start(cb, False, False, 0)
            text_box.pack_start(desc, False, False, 0)
            task_row.pack_start(text_box, True, True, 0)

            # Label de tamaño estimado
            size_lbl = Gtk.Label(label="--")
            size_lbl.set_xalign(1.0)
            size_lbl.set_valign(Gtk.Align.CENTER)
            self.task_size_labels[task.key] = size_lbl
            task_row.pack_end(size_lbl, False, False, 0)

            cleanup_box.pack_start(task_row, False, False, 2)

        # Enlaces de seleccionar / deseleccionar todos
        select_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        select_bar.set_margin_top(4)

        btn_select_all = Gtk.Button(label="Seleccionar todo")
        btn_select_all.set_relief(Gtk.ReliefStyle.NONE)
        btn_select_all.connect("clicked", lambda b: self._set_all_tasks(True))
        select_bar.pack_start(btn_select_all, False, False, 0)

        btn_deselect_all = Gtk.Button(label="Deseleccionar todo")
        btn_deselect_all.set_relief(Gtk.ReliefStyle.NONE)
        btn_deselect_all.connect("clicked", lambda b: self._set_all_tasks(False))
        select_bar.pack_start(btn_deselect_all, False, False, 0)

        cleanup_box.pack_start(select_bar, False, False, 0)

        cleanup_frame.add(cleanup_box)
        vbox.pack_start(cleanup_frame, False, False, 0)

        # 3. Consola / Visor de salida (Expander)
        self.log_expander = Gtk.Expander(label=" Ver salida de la consola de limpieza ")
        log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        log_box.set_border_width(6)

        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_min_content_height(120)
        log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.log_text_view = Gtk.TextView()
        self.log_text_view.set_editable(False)
        self.log_text_view.set_cursor_visible(False)
        self.log_text_view.override_font(Pango.FontDescription("monospace 9"))
        log_scroll.add(self.log_text_view)
        log_box.pack_start(log_scroll, True, True, 0)

        self.log_expander.add(log_box)
        vbox.pack_start(self.log_expander, False, False, 0)

        # 4. Botones de acción inferiores
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_bar.set_halign(Gtk.Align.END)
        action_bar.set_margin_top(6)

        utils_close_btn = Gtk.Button(label="Cerrar")
        utils_close_btn.connect("clicked", lambda b: self.close())
        action_bar.pack_start(utils_close_btn, False, False, 0)

        self.clean_btn = Gtk.Button(label=" Limpiar Seleccionados ")
        self.clean_btn.get_style_context().add_class("suggested-action")
        self.clean_btn.set_image(Gtk.Image.new_from_icon_name("edit-clear-all-symbolic", Gtk.IconSize.BUTTON))
        self.clean_btn.set_always_show_image(True)
        self.clean_btn.connect("clicked", self._on_clean_clicked)
        action_bar.pack_start(self.clean_btn, False, False, 0)

        vbox.pack_start(action_bar, False, False, 0)

        return scrolled

    def _set_all_tasks(self, active: bool):
        for cb in self.task_check_buttons.values():
            cb.set_active(active)

    def _append_log(self, text: str):
        buffer = self.log_text_view.get_buffer()
        end_iter = buffer.get_end_iter()
        buffer.insert(end_iter, text + "\n")
        # Scroll al final
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.log_text_view.scroll_to_mark(mark, 0.05, True, 0.0, 1.0)

    def _clear_log(self):
        buffer = self.log_text_view.get_buffer()
        buffer.set_text("")

    def _refresh_disk_info(self):
        """Actualiza la barra de progreso y etiquetas de disco."""
        usage = DiskInfo.get_mount_usage("/")
        if usage["valid"]:
            pct = usage["percent"]
            self.disk_progress.set_fraction(pct / 100.0)
            self.disk_progress.set_text(f"{pct:.1f}% usado")

            self.disk_stats_label.set_markup(
                f"<b>Espacio Usado:</b> {usage['used_str']}   |   "
                f"<b>Libre:</b> <span color='#2e7d32'><b>{usage['free_str']}</b></span>   |   "
                f"<b>Total:</b> {usage['total_str']}"
            )
        else:
            self.disk_stats_label.set_text("No se pudo obtener información del disco.")

    def _start_scan_async(self, silent: bool = False):
        """Inicia el análisis de espacio recuperable en segundo plano para no congelar la UI."""
        self.scan_btn.set_sensitive(False)
        self.scan_spinner.start()
        if not silent:
            self.scan_summary_label.set_markup("<small><span color='#0277bd'>Analizando espacio recuperable en disco...</span></small>")

        def worker():
            total_recoverable = 0
            results = {}
            for task in self.cleaner_tasks:
                size = self.disk_cleaner.scan_task_size(task.key)
                task.estimated_bytes = size
                task.estimated_str = format_size(size)
                results[task.key] = (size, task.estimated_str)
                total_recoverable += size

            def on_done():
                self.scan_spinner.stop()
                self.scan_btn.set_sensitive(True)
                for key, (size, s_str) in results.items():
                    lbl = self.task_size_labels.get(key)
                    if lbl:
                        if size > 0:
                            lbl.set_markup(f"<b><span color='#2e7d32'>{s_str}</span></b>")
                        else:
                            lbl.set_markup(f"<span color='#888'>{s_str}</span>")

                sum_str = format_size(total_recoverable)
                self.scan_summary_label.set_markup(
                    f"<b>Espacio total recuperable estimado:</b> <span color='#2e7d32'><b>{sum_str}</b></span>"
                )

            GLib.idle_add(on_done)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _get_selected_tasks(self) -> list:
        return [k for k, cb in self.task_check_buttons.items() if cb.get_active()]

    def _execute_root_script(self, script_content: str) -> tuple:
        """Ejecuta un script bash como root usando pkexec o fallback con zenity."""
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sh") as tmp:
            tmp.write(script_content)
            tmp_path = tmp.name

        os.chmod(tmp_path, 0o755)

        # 1. Intentar pkexec
        try:
            proc = subprocess.run(["pkexec", "/bin/bash", tmp_path], capture_output=True, text=True)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            if proc.returncode == 0:
                return True, proc.stdout
            elif proc.returncode in (126, 127):
                pass
            else:
                stderr_l = proc.stderr.lower()
                if "dismissed" in stderr_l or proc.returncode == 1:
                    return False, "Operación cancelada por el usuario."
        except Exception:
            pass

        # 2. Fallback zenity + sudo -S
        try:
            res = subprocess.run(
                ["zenity", "--password",
                 "--title=Permisos de Administrador",
                 "--text=Introduce tu contraseña para ejecutar la limpieza del sistema:"],
                capture_output=True, text=True
            )
            if res.returncode != 0:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return False, "Operación cancelada."

            pwd = res.stdout.strip()
            if not pwd:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return False, "Contraseña vacía."

            proc = subprocess.run(
                ["sudo", "-S", "/bin/bash", tmp_path],
                input=pwd + "\n", capture_output=True, text=True
            )
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

            if proc.returncode == 0:
                return True, proc.stdout
            else:
                return False, f"Error: {proc.stderr}\n{proc.stdout}"
        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return False, str(e)

    def _on_clean_clicked(self, widget):
        selected = self._get_selected_tasks()
        if not selected:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="No has seleccionado ninguna tarea",
            )
            dialog.format_secondary_text("Marca al menos una casilla para realizar la limpieza.")
            dialog.run()
            dialog.destroy()
            return

        # Diálogo de confirmación
        has_root = any(t.requires_root for t in self.cleaner_tasks if t.key in selected)
        msg_text = "¿Deseas proceder con la limpieza de los elementos seleccionados?"
        sec_text = "Se liberará espacio en el disco eliminando los elementos marcados."
        if "trash" in selected:
            sec_text += "\n\n⚠ Se vaciará la papelera de reciclaje de forma permanente."
        if has_root:
            sec_text += "\n\nSe solicitarán permisos de administrador para las tareas del sistema."

        confirm_dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=msg_text
        )
        confirm_dialog.format_secondary_text(sec_text)
        response = confirm_dialog.run()
        confirm_dialog.destroy()

        if response != Gtk.ResponseType.YES:
            return

        self.clean_btn.set_sensitive(False)
        self.scan_btn.set_sensitive(False)
        self.log_expander.set_expanded(True)
        self._clear_log()
        self._append_log("=== INICIANDO TAREAS DE LIMPIEZA ===")

        # Ejecución en hilo
        def clean_worker():
            # 1. Tareas de usuario
            user_keys = [k for k in selected if not any(t.key == k and t.requires_root for t in self.cleaner_tasks)]
            if user_keys:
                GLib.idle_add(self._append_log, "--- Limpiando espacio de usuario ---")
                u_ok, u_logs = self.disk_cleaner.clean_user_space(user_keys)
                for line in u_logs:
                    GLib.idle_add(self._append_log, line)

            # 2. Tareas de root
            root_keys = [k for k in selected if any(t.key == k and t.requires_root for t in self.cleaner_tasks)]
            root_success = True
            root_out = ""
            if root_keys:
                GLib.idle_add(self._append_log, "\n--- Solicitando permisos de administrador ---")
                script_text = self.disk_cleaner.build_root_script(root_keys)
                r_ok, r_msg = self._execute_root_script(script_text)
                root_success = r_ok
                root_out = r_msg
                for line in r_msg.splitlines():
                    GLib.idle_add(self._append_log, line)

            def on_finish():
                self.clean_btn.set_sensitive(True)
                self.scan_btn.set_sensitive(True)
                self._append_log("\n=== TAREAS FINALIZADAS ===")
                self._refresh_disk_info()
                self._start_scan_async(silent=True)

                if root_success:
                    succ_dialog = Gtk.MessageDialog(
                        transient_for=self,
                        flags=0,
                        message_type=Gtk.MessageType.INFO,
                        buttons=Gtk.ButtonsType.OK,
                        text="¡Limpieza completada con éxito!",
                    )
                    succ_dialog.format_secondary_text(
                        "Se han ejecutado las tareas de liberación de espacio.\n"
                        "Revisa la consola inferior para ver el detalle de cada acción."
                    )
                    succ_dialog.run()
                    succ_dialog.destroy()
                else:
                    if "cancelada" not in root_out.lower():
                        err_dialog = Gtk.MessageDialog(
                            transient_for=self,
                            flags=0,
                            message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK,
                            text="Hubo un problema durante la limpieza",
                        )
                        err_dialog.format_secondary_text(root_out)
                        err_dialog.run()
                        err_dialog.destroy()

            GLib.idle_add(on_finish)

        threading.Thread(target=clean_worker, daemon=True).start()

    def _on_trim_clicked(self, widget):
        confirm_dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="¿Deseas optimizar las celdas del disco SSD (TRIM)?"
        )
        confirm_dialog.format_secondary_text(
            "La operación fstrim informará al controlador de tu unidad de estado sólido (SSD) "
            "cuáles bloques de datos ya no se usan, mejorando la velocidad de escritura y prolongando "
            "la vida útil del dispositivo.\n\n"
            "Se solicitarán permisos de administrador para ejecutar la orden."
        )
        response = confirm_dialog.run()
        confirm_dialog.destroy()

        if response != Gtk.ResponseType.YES:
            return

        self.trim_btn.set_sensitive(False)
        self.log_expander.set_expanded(True)
        self._append_log("\n=== INICIANDO OPTIMIZACIÓN SSD (TRIM) ===")

        def trim_worker():
            script = self.disk_cleaner.build_trim_script()
            ok, output = self._execute_root_script(script)

            def on_finish():
                self.trim_btn.set_sensitive(True)
                for line in output.splitlines():
                    self._append_log(line)
                self._refresh_disk_info()

                if ok:
                    summary = ""
                    for line in output.splitlines():
                        if "bytes" in line or "recortados" in line or "trimmed" in line or "/" in line:
                            summary += line.strip() + "\n"
                    if not summary.strip():
                        summary = "Operación completada correctamente."

                    dlg = Gtk.MessageDialog(
                        transient_for=self,
                        flags=0,
                        message_type=Gtk.MessageType.INFO,
                        buttons=Gtk.ButtonsType.OK,
                        text="¡Optimización SSD (TRIM) completada!",
                    )
                    dlg.format_secondary_text(f"Resultado:\n{summary}")
                    dlg.run()
                    dlg.destroy()
                else:
                    if "cancelada" not in output.lower():
                        dlg = Gtk.MessageDialog(
                            transient_for=self,
                            flags=0,
                            message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK,
                            text="Error al ejecutar fstrim",
                        )
                        dlg.format_secondary_text(output)
                        dlg.run()
                        dlg.destroy()

            GLib.idle_add(on_finish)

        threading.Thread(target=trim_worker, daemon=True).start()


if __name__ == "__main__":
    app = NvidiaOptimizerApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()
