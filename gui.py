#!/usr/bin/env python3
import sys
import os
import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APPLY_SCRIPT = os.path.join(SCRIPT_DIR, "apply.sh")
SERVICE_NAME = "nvidia-power-limit.service"

class NvidiaOptimizerApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Optimizador de Energía - NVIDIA GTX 1660")
        self.set_default_size(550, 580)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(16)
        self.set_icon_name("nvidia-settings")

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(main_box)

        # Header Info Card
        header_frame = Gtk.Frame()
        header_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        header_box.set_border_width(10)

        icon_image = Gtk.Image.new_from_icon_name("nvidia-settings", Gtk.IconSize.DIALOG)
        header_box.pack_start(icon_image, False, False, 0)

        info_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title_label = Gtk.Label()
        title_label.set_markup("<b><big>NVIDIA GeForce GTX 1660 (ZOTAC)</big></b>")
        title_label.set_xalign(0)
        info_vbox.pack_start(title_label, False, False, 0)

        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        info_vbox.pack_start(self.status_label, False, False, 0)

        self.clocks_label = Gtk.Label()
        self.clocks_label.set_xalign(0)
        info_vbox.pack_start(self.clocks_label, False, False, 0)

        self.daemon_status_label = Gtk.Label()
        self.daemon_status_label.set_xalign(0)
        info_vbox.pack_start(self.daemon_status_label, False, False, 0)

        header_box.pack_start(info_vbox, True, True, 0)

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh_btn.set_tooltip_text("Actualizar datos")
        refresh_btn.connect("clicked", lambda b: self.refresh_status())
        header_box.pack_end(refresh_btn, False, False, 0)

        header_frame.add(header_box)
        main_box.pack_start(header_frame, False, False, 0)

        # Profiles Section
        profiles_frame = Gtk.Frame(label=" Perfiles de Consumo ")
        profiles_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        profiles_vbox.set_border_width(10)

        # Radio button 1: Ultra Eco / Ofimática
        self.rb_eco = Gtk.RadioButton.new_with_label(None, "🌱 Modo Ultra Eco — 70 W + 650 MHz (Máximo Ahorro)")
        sub_eco = Gtk.Label()
        sub_eco.set_markup("<small><span color='#555'>• Acota el reloj a 650 MHz, fuerza VRAM a ~405 MHz y activa PowerMizer Ahorro.\n• Consumo real mínimo (~12W–16W). Fluidez total en YouTube 1080p, escritorio y oficina.</span></small>")
        sub_eco.set_xalign(0)
        sub_eco.set_margin_left(24)
        profiles_vbox.pack_start(self.rb_eco, False, False, 0)
        profiles_vbox.pack_start(sub_eco, False, False, 0)

        # Radio button 2: Máxima Eficiencia (Gaming ligero / normal)
        self.rb_eff = Gtk.RadioButton.new_with_label_from_widget(self.rb_eco, "🍃 Máxima Eficiencia — 80 W")
        sub_eff = Gtk.Label()
        sub_eff.set_markup("<small><span color='#555'>• -35% de consumo jugando sin pérdida perceptible de FPS.\n• Silencioso y muy fresco bajo carga de juegos.</span></small>")
        sub_eff.set_xalign(0)
        sub_eff.set_margin_left(24)
        profiles_vbox.pack_start(self.rb_eff, False, False, 0)
        profiles_vbox.pack_start(sub_eff, False, False, 0)

        # Radio button 3: Punto Dulce
        self.rb_sweet = Gtk.RadioButton.new_with_label_from_widget(self.rb_eco, "⚡ Punto Dulce — 90 W (Recomendado Gaming Pesado)")
        sub_sweet = Gtk.Label()
        sub_sweet.set_markup("<small><span color='#555'>• ~98% de rendimiento de fábrica con un ahorro de -25% de energía.\n• Ideal para exprimir juegos exigentes manteniendo la torre fresca.</span></small>")
        sub_sweet.set_xalign(0)
        sub_sweet.set_margin_left(24)
        profiles_vbox.pack_start(self.rb_sweet, False, False, 0)
        profiles_vbox.pack_start(sub_sweet, False, False, 0)

        # Radio button 4: Stock
        self.rb_stock = Gtk.RadioButton.new_with_label_from_widget(self.rb_eco, "⚙️ De Fábrica (Stock) — 120 W")
        sub_stock = Gtk.Label()
        sub_stock.set_markup("<small><span color='#555'>• Límite original de 120W y frecuencias de fábrica sin restricciones.</span></small>")
        sub_stock.set_xalign(0)
        sub_stock.set_margin_left(24)
        profiles_vbox.pack_start(self.rb_stock, False, False, 0)
        profiles_vbox.pack_start(sub_stock, False, False, 0)

        profiles_frame.add(profiles_vbox)
        main_box.pack_start(profiles_frame, True, True, 0)

        # Daemon Persistence Toggle
        persist_frame = Gtk.Frame(label=" Inicio Automático (Daemon / Systemd) ")
        persist_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        persist_box.set_border_width(8)

        self.cb_daemon = Gtk.CheckButton(label="Activar siempre al encender el PC")
        persist_box.pack_start(self.cb_daemon, False, False, 0)

        persist_info = Gtk.Label()
        persist_info.set_markup("<small><span color='#555'>Aplica el perfil seleccionado automáticamente en cada arranque del sistema.</span></small>")
        persist_info.set_xalign(0)
        persist_info.set_margin_left(24)
        persist_box.pack_start(persist_info, False, False, 0)

        persist_frame.add(persist_box)
        main_box.pack_start(persist_frame, False, False, 0)

        # Action Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)

        close_btn = Gtk.Button(label="Cerrar")
        close_btn.connect("clicked", lambda b: self.close())
        button_box.pack_start(close_btn, False, False, 0)

        self.apply_btn = Gtk.Button(label=" Aplicar Configuración ")
        self.apply_btn.get_style_context().add_class("suggested-action")
        self.apply_btn.connect("clicked", self.on_apply_clicked)
        button_box.pack_start(self.apply_btn, False, False, 0)

        main_box.pack_start(button_box, False, False, 0)

        # Initial data load
        self.refresh_status()

    def get_gpu_data(self):
        try:
            cmd = ["nvidia-smi", "--query-gpu=power.limit,temperature.gpu,utilization.gpu,clocks.current.memory,clocks.current.graphics", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            limit = float(parts[0])
            temp = parts[1]
            util = parts[2]
            mem_clock = parts[3]
            gpu_clock = parts[4]
            return limit, temp, util, mem_clock, gpu_clock
        except Exception:
            return 120.0, "N/A", "N/A", "N/A", "N/A"

    def is_daemon_enabled(self):
        try:
            res = subprocess.run(["systemctl", "is-enabled", SERVICE_NAME], capture_output=True, text=True)
            return res.stdout.strip() == "enabled"
        except Exception:
            return False

    def refresh_status(self):
        limit, temp, util, mem_clock, gpu_clock = self.get_gpu_data()
        self.status_label.set_markup(f"Límite actual: <b>{limit:.0f} W</b>   |   Temp: <b>{temp}°C</b>   |   Uso: <b>{util}%</b>")
        self.clocks_label.set_markup(f"<small>Reloj GPU: <b>{gpu_clock} MHz</b>   |   Reloj VRAM: <b>{mem_clock} MHz</b></small>")

        daemon_active = self.is_daemon_enabled()
        self.cb_daemon.set_active(daemon_active)

        if daemon_active:
            self.daemon_status_label.set_markup("Inicio con PC: <span color='#2e7d32'><b>Activado</b> (Servicio en arranque)</span>")
        else:
            self.daemon_status_label.set_markup("Inicio con PC: <span color='#757575'>Desactivado (Solo sesión actual)</span>")

        # Select matching radio button
        if limit <= 72.0:
            self.rb_eco.set_active(True)
        elif abs(limit - 80.0) < 3:
            self.rb_eff.set_active(True)
        elif abs(limit - 90.0) < 3:
            self.rb_sweet.set_active(True)
        else:
            self.rb_stock.set_active(True)

    def execute_privileged(self, watts, enable_daemon):
        args = [APPLY_SCRIPT, str(watts), "1" if enable_daemon else "0"]
        
        # 1. Try pkexec
        try:
            proc = subprocess.run(["pkexec"] + args, capture_output=True, text=True)
            if proc.returncode == 0:
                # Also apply PowerMizer in current user X11 session directly
                pm_val = "0" if watts == 70 else "2"
                subprocess.run(["nvidia-settings", "-a", f"[gpu:0]/GPUPowerMizerMode={pm_val}"], capture_output=True)
                return True, "Configuración aplicada con éxito."
            elif proc.returncode == 126 or proc.returncode == 127:
                pass
            else:
                if "dismissed" in proc.stderr.lower() or proc.returncode == 1:
                    return False, "Operación cancelada por el usuario."
        except Exception:
            pass

        # 2. Zenity fallback
        try:
            res = subprocess.run(
                ["zenity", "--password", "--title=Permisos de Administrador", "--text=Introduce tu contraseña para aplicar los cambios de energía:"],
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
                pm_val = "0" if watts == 70 else "2"
                subprocess.run(["nvidia-settings", "-a", f"[gpu:0]/GPUPowerMizerMode={pm_val}"], capture_output=True)
                return True, "Configuración aplicada con éxito."
            else:
                return False, f"Error al aplicar: {proc.stderr}"
        except Exception as e:
            return False, str(e)

    def on_apply_clicked(self, widget):
        if self.rb_eco.get_active():
            watts = 70
            profile_name = "Modo Ultra Eco (70 W + 650 MHz)"
        elif self.rb_eff.get_active():
            watts = 80
            profile_name = "Máxima Eficiencia (80 W)"
        elif self.rb_sweet.get_active():
            watts = 90
            profile_name = "Punto Dulce (90 W)"
        else:
            watts = 120
            profile_name = "De Fábrica (120 W)"

        enable_daemon = self.cb_daemon.get_active()

        self.apply_btn.set_sensitive(False)
        while Gtk.events_pending():
            Gtk.main_iteration()

        success, msg = self.execute_privileged(watts, enable_daemon)
        self.apply_btn.set_sensitive(True)

        if success:
            self.refresh_status()
            daemon_msg = "El servicio de arranque queda ACTIVADO." if enable_daemon else "El inicio automático queda DESACTIVADO."
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="¡Ajustes aplicados correctamente!"
            )
            dialog.format_secondary_text(f"Perfil seleccionado: {profile_name}\n\n{daemon_msg}")
            dialog.run()
            dialog.destroy()
        else:
            if "cancelada" not in msg.lower():
                dialog = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="No se pudo aplicar la configuración"
                )
                dialog.format_secondary_text(msg)
                dialog.run()
                dialog.destroy()

if __name__ == "__main__":
    app = NvidiaOptimizerApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()
