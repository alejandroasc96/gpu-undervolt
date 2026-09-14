# Optimizador de Energía y Undervolt NVIDIA (Linux)

Herramienta gráfica (GUI) nativa para Linux desarrollada con **Python y GTK3** para optimizar el consumo eléctrico, temperatura y rendimiento de tarjetas gráficas **NVIDIA** (especialmente optimizado para la **GTX 1660** y arquitecturas Turing / Pascal / Ampere).

En Linux, el controlador propietario de NVIDIA no permite editar la curva de voltajes tradicional de Windows. Esta herramienta aplica la técnica estándar y más efectiva en Linux: **control dinámico de Power Limit, bloqueo de frecuencias óptimas (Clock Locking) y gestión de PowerMizer**.

---

## 🚀 Perfiles Incluidos

| Perfil | Límite Potencia | Reloj Núcleo | Reloj VRAM | Uso recomendado |
| :--- | :---: | :---: | :---: | :--- |
| **🌱 Modo Ultra Eco** | **70 W** | 300 - 650 MHz | ~405 MHz | Máximo ahorro para YouTube, Netflix, ofimática y tareas ligeras (~12W - 16W reales). |
| **🍃 Máxima Eficiencia** | **80 W** | Dinámico | 4001 MHz | Gaming fluido ahorrando 35% de consumo sin pérdida perceptible de FPS. |
| **⚡ Punto Dulce** | **90 W** | Dinámico | 4001 MHz | Exprimir el 98% del rendimiento en juegos exigentes con -25% de consumo. |
| **⚙️ De Fábrica (Stock)** | **120 W** | Fábrica | 4001 MHz | Restaura los valores de fábrica originales sin límites. |

---

## ✨ Características

* **Interfaz gráfica moderna:** Integrada de forma nativa con el tema de escritorio GTK (Cinnamon, GNOME, XFCE, MATE).
* **Monitor en tiempo real:** Lectura en vivo de vatios actuales, temperatura, porcentaje de uso, reloj del núcleo y reloj de la memoria VRAM.
* **Persistencia en el arranque (Daemon / Systemd):** Permite marcar una casilla para que el perfil elegido se aplique automáticamente cada vez que enciendas el ordenador mediante un servicio ultraligero de `systemd`.
* **Cero consumo en segundo plano:** La aplicación y el servicio no quedan residentes en memoria gastando recursos.

---

## 📦 Instalación Rápida

Solo necesitas clonar el repositorio y ejecutar el instalador:

```bash
git clone https://github.com/alejandroasc96/gpu-undervolt.git
cd gpu-undervolt
chmod +x install.sh
./install.sh
```

El instalador automáticamente:
1. Instalará la aplicación en `~/.local/share/nvidia-optimizer/`.
2. Creará el acceso directo con icono oficial en tu **Escritorio** (`~/Desktop` o `~/Escritorio`).
3. Lo añadirá a tu **Menú de Aplicaciones**.

---

## 🗑️ Desinstalación

Para eliminar la aplicación y sus accesos directos por completo:

```bash
chmod +x uninstall.sh
./uninstall.sh
```

---

## 📋 Requisitos del Sistema

* Distribución Linux (Linux Mint, Ubuntu, Debian o derivadas).
* Controlador propietario oficial de NVIDIA instalado (`nvidia-driver`).
* `python3`, `python3-gi`, `gir1.2-gtk-3.0` y `zenity` (instalados por defecto en Linux Mint y Ubuntu).
