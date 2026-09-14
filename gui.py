#!/usr/bin/env python3
"""
Optimizador de Energia NVIDIA (Linux) - GUI
Soporta cualquier GPU NVIDIA con deteccion automatica de perfiles.
"""
import sys
import os
import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APPLY_SCRIPT = os.path.join(SCRIPT_DIR, "apply.sh")

# Importar el modulo de deteccion
sys.path.insert(0, SCRIPT_DIR)
try:
    from gpu_detector import detect_all_gpus, GpuInfo, PowerProfile
except ImportError as e:
    # Si falla el import, mostrar error y salir
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


class NvidiaOptimizerApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Optimizador de Energia NVIDIA")
        self.set_default_size(580, 640)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(16)
        self.set_icon_name("nvidia-settings")

        # Estado interno
        self.gpus = []
        self.current_gpu = None
        self._profile_widgets = []
        self.profile_radio_buttons = []  # lista de (RadioButton, PowerProfile)

        # Detectar GPUs
        self.gpus = detect_all_gpus()

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(main_box)

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

        # --- Inicializacion ----------------------------------------------
        if not self.gpus:
            self._show_no_gpu_error()
            return

        # Poblar el combo de GPU
        for gpu in self.gpus:
            self.gpu_combo.append_text(f"GPU {gpu.gpu_index}: {gpu.display_name}")

        if len(self.gpus) > 1:
            self.gpu_selector_box.set_no_show_all(False)
            self.gpu_selector_box.show_all()

        self.gpu_combo.set_active(0)
        # _on_gpu_changed se dispara automaticamente al set_active

    # -------------------------------------------------------------------------
    # Cambio de GPU seleccionada
    # -------------------------------------------------------------------------

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

        # Mostrar/ocultar nota de GPU movil
        if gpu.is_mobile:
            self.mobile_note_label.show()
            self.cb_daemon.set_sensitive(False)
            self.persist_frame.set_sensitive(False)
            self.profiles_frame.set_label(" Perfiles de Energia (PowerMizer) ")
        else:
            self.mobile_note_label.hide()
            self.cb_daemon.set_sensitive(True)
            self.persist_frame.set_sensitive(True)
            self.profiles_frame.set_label(" Perfiles de Consumo ")

    def _build_profile_widgets(self):
        """Reconstruye los radio buttons segun la GPU seleccionada."""
        # Limpiar widgets anteriores
        for w in self._profile_widgets:
            self.profiles_vbox.remove(w)
        self._profile_widgets = []
        self.profile_radio_buttons = []

        gpu = self.current_gpu
        if gpu is None:
            return

        first_rb = None
        for profile in gpu.profiles:
            label_text = f"{profile.emoji} {profile.description_short}"
            if first_rb is None:
                rb = Gtk.RadioButton.new_with_label(None, label_text)
                first_rb = rb
            else:
                rb = Gtk.RadioButton.new_with_label_from_widget(first_rb, label_text)

            sub = Gtk.Label()
            desc = profile.description_long.replace("&", "&amp;")
            sub.set_markup(f"<small><span color='#555'>{desc}</span></small>")
            sub.set_xalign(0)
            sub.set_margin_left(24)

            self.profiles_vbox.pack_start(rb, False, False, 0)
            self.profiles_vbox.pack_start(sub, False, False, 0)
            self._profile_widgets.extend([rb, sub])
            self.profile_radio_buttons.append((rb, profile))

        self.profiles_vbox.show_all()

    # -------------------------------------------------------------------------
    # Lectura de datos en tiempo real
    # -------------------------------------------------------------------------

    def get_gpu_data(self):
        """Consulta nvidia-smi para la GPU actualmente seleccionada."""
        if self.current_gpu is None:
            return 0.0, "N/A", "N/A", "N/A", "N/A"
        try:
            gpu_id = self.current_gpu.gpu_index
            cmd = [
                "nvidia-smi",
                f"--id={gpu_id}",
                "--query-gpu=power.limit,temperature.gpu,utilization.gpu,"
                "clocks.current.memory,clocks.current.graphics",
                "--format=csv,noheader,nounits",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            limit   = float(parts[0]) if parts[0] not in ("N/A", "[N/A]") else 0.0
            temp    = parts[1]
            util    = parts[2]
            mem_clk = parts[3]
            gpu_clk = parts[4]
            return limit, temp, util, mem_clk, gpu_clk
        except Exception:
            return 0.0, "N/A", "N/A", "N/A", "N/A"

    def is_daemon_enabled(self) -> bool:
        if self.current_gpu is None:
            return False
        try:
            res = subprocess.run(
                ["systemctl", "is-enabled", self.current_gpu.service_name],
                capture_output=True, text=True,
            )
            return res.stdout.strip() == "enabled"
        except Exception:
            return False

    def refresh_status(self):
        gpu = self.current_gpu
        if gpu is None:
            return

        limit, temp, util, mem_clk, gpu_clk = self.get_gpu_data()

        if gpu.supports_power_limit:
            self.status_label.set_markup(
                f"Limite actual: <b>{limit:.0f} W</b>   |   "
                f"Temp: <b>{temp}°C</b>   |   Uso: <b>{util}%</b>"
            )
            self.clocks_label.set_markup(
                f"<small>Reloj GPU: <b>{gpu_clk} MHz</b>   |   "
                f"Reloj VRAM: <b>{mem_clk} MHz</b></small>"
            )
        else:
            # GPU movil: sin info de wattaje
            self.status_label.set_markup(
                f"Temp: <b>{temp}°C</b>   |   Uso: <b>{util}%</b>"
            )
            self.clocks_label.set_markup(
                f"<small>Reloj GPU: <b>{gpu_clk} MHz</b>   |   "
                f"Reloj VRAM: <b>{mem_clk} MHz</b></small>"
            )

        daemon_active = self.is_daemon_enabled()
        self.cb_daemon.set_active(daemon_active)

        if daemon_active:
            self.daemon_status_label.set_markup(
                "Inicio con PC: <span color='#2e7d32'><b>Activado</b> (Servicio en arranque)</span>"
            )
        else:
            self.daemon_status_label.set_markup(
                "Inicio con PC: <span color='#757575'>Desactivado (Solo sesion actual)</span>"
            )

        # Seleccionar el radio button que coincide con el limite actual
        if gpu.supports_power_limit and limit > 0 and self.profile_radio_buttons:
            matched = False
            for rb, profile in self.profile_radio_buttons:
                if profile.watts > 0 and abs(limit - profile.watts) < 3:
                    rb.set_active(True)
                    matched = True
                    break
            if not matched:
                # Si no coincide exactamente, seleccionar el ultimo (stock)
                self.profile_radio_buttons[-1][0].set_active(True)

    # -------------------------------------------------------------------------
    # Aplicar configuracion
    # -------------------------------------------------------------------------

    def _get_selected_profile(self):
        """Devuelve el PowerProfile seleccionado actualmente."""
        for rb, profile in self.profile_radio_buttons:
            if rb.get_active():
                return profile
        return None

    def execute_privileged(self, profile, enable_daemon: bool):
        """
        Ejecuta apply.sh con privilegios de root.
        Parametros pasados al script:
          <watts> <gpu_index> <enable_daemon> <eco_min_clock> <eco_max_clock> <powermizer_mode>
        """
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
                # PowerMizer desde la sesion X11 del usuario actual
                subprocess.run(
                    ["nvidia-settings", "-a",
                     f"[gpu:{gpu.gpu_index}]/GPUPowerMizerMode={profile.powermizer_mode}"],
                    capture_output=True
                )
                return True, "Configuracion aplicada con exito."
            elif proc.returncode in (126, 127):
                pass  # pkexec no disponible, intentar zenity
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

        self.apply_btn.set_sensitive(False)
        while Gtk.events_pending():
            Gtk.main_iteration()

        success, msg = self.execute_privileged(profile, enable_daemon)
        self.apply_btn.set_sensitive(True)

        if success:
            self.refresh_status()
            if self.current_gpu and not self.current_gpu.is_mobile:
                daemon_msg = (
                    "El servicio de arranque queda ACTIVADO."
                    if enable_daemon else
                    "El inicio automatico queda DESACTIVADO."
                )
            else:
                daemon_msg = "Ajuste de PowerMizer aplicado."

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

    # -------------------------------------------------------------------------
    # Error: sin GPU
    # -------------------------------------------------------------------------

    def _show_no_gpu_error(self):
        """Muestra un mensaje de error si no se detecta ninguna GPU NVIDIA."""
        self.apply_btn.set_sensitive(False)
        self.cb_daemon.set_sensitive(False)
        self.title_label.set_markup(
            "<b><big><span color='#c62828'>Sin GPU NVIDIA detectada</span></big></b>"
        )
        self.status_label.set_markup(
            "<span color='#555'>Asegurate de tener el driver propietario NVIDIA instalado.\n"
            "Comprueba con: <tt>nvidia-smi</tt></span>"
        )
        self.clocks_label.set_text("")
        self.daemon_status_label.set_text("")


if __name__ == "__main__":
    app = NvidiaOptimizerApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()
