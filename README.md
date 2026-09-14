# Optimizador de Energía y Undervolt NVIDIA (Linux)

Herramienta gráfica (GUI) nativa para Linux desarrollada con **Python y GTK3** para optimizar el consumo eléctrico, temperatura y rendimiento de tarjetas gráficas **NVIDIA**.

Detecta automáticamente la GPU instalada y calcula los perfiles óptimos de consumo según el TDP real del hardware. Compatible con cualquier PC Linux que tenga el driver propietario NVIDIA.

---

## 🔍 Detección Automática de GPU

La herramienta consulta `nvidia-smi` al arrancar para leer las capacidades reales de tu GPU:

- **Nombre del modelo** → mostrado en la cabecera de la app.
- **TDP mínimo y máximo** → calcula perfiles como porcentaje del TDP real.
- **Relojes máximos** → configura el límite de reloj del modo Eco apropiado.
- **Soporte de power management** → si el driver no permite cambiar el TDP (GPUs móviles), solo controla el modo PowerMizer.

### GPUs con soporte garantizado

| GPU | TDP | Perfiles | Tipo |
|:---|:---:|:---:|:---:|
| NVIDIA GeForce GTX 1660 / Ti / Super | 120–125 W | 4 perfiles | Escritorio |
| NVIDIA GeForce GTX 1060 6G / 3G | 120 W | 4 perfiles | Escritorio |
| NVIDIA GeForce RTX 5060 Ti 16G | 180 W | 4 perfiles | Escritorio |
| NVIDIA GeForce GT 840M | 33 W | 3 modos PowerMizer | Portátil |
| **Cualquier otra GPU NVIDIA** | Detectado | Calculado | Auto |

---

## 🚀 Perfiles de Consumo (adaptados automáticamente)

Los perfiles se calculan como **porcentajes del TDP real** de la GPU detectada:

| Perfil | % TDP | GTX 1660 (120W) | RTX 5060 Ti (180W) | Uso recomendado |
|:---|:---:|:---:|:---:|:---|
| 🌱 **Ultra Eco** | ~58% | 70 W | 105 W | Máximo ahorro: YouTube, ofimática, escritorio |
| 🍃 **Máxima Eficiencia** | ~67% | 80 W | 120 W | Gaming sin pérdida perceptible de FPS |
| ⚡ **Punto Dulce** | ~75% | 90 W | 135 W | ~98% rendimiento con -25% de consumo |
| ⚙️ **De Fábrica (Stock)** | 100% | 120 W | 180 W | Sin restricciones, valores originales |

> El modo **Ultra Eco** también bloquea el reloj del núcleo (ej. 650 MHz en GTX 1660, 800 MHz en RTX 5060 Ti) para minimizar el consumo en tareas ligeras.

### GPUs móviles (portátil)

Las GPUs de portátil (como la GT 840M) no permiten cambiar el TDP vía `nvidia-smi`. Para estas GPUs se ofrecen 3 modos **PowerMizer**:

| Modo | Descripción |
|:---|:---|
| 🌱 Ahorro de Energía | PowerMizer Adaptativo — baja frecuencias en reposo |
| 🍃 Equilibrado | PowerMizer Automático — el driver decide |
| ⚡ Máximo Rendimiento | PowerMizer Máximo — frecuencias siempre al tope |

---

## ✨ Características

* **Detección automática:** Funciona con cualquier GPU NVIDIA sin configuración manual.
* **Multi-GPU:** Si tienes varias GPUs NVIDIA, puedes elegir cuál configurar desde la propia app.
* **Interfaz gráfica moderna:** Integrada de forma nativa con el tema GTK (Cinnamon, GNOME, XFCE, MATE).
* **Monitor en tiempo real:** Lectura en vivo de vatios, temperatura, uso, reloj del núcleo y de la VRAM.
* **Persistencia en el arranque:** Servicio `systemd` ultraligero por GPU para aplicar el perfil automáticamente en cada arranque.
* **Cero consumo en segundo plano:** La app y el servicio no quedan residentes en memoria.

---

## 📦 Instalación Rápida

```bash
git clone https://github.com/alejandroasc96/gpu-undervolt.git
cd gpu-undervolt
chmod +x install.sh
./install.sh
```

El instalador automáticamente:
1. Instalará la aplicación en `~/.local/share/nvidia-optimizer/`.
2. Creará el acceso directo con icono oficial en tu **Escritorio**.
3. Lo añadirá a tu **Menú de Aplicaciones**.

---

## 🗑️ Desinstalación

```bash
chmod +x uninstall.sh
./uninstall.sh
```

---

## 📋 Requisitos del Sistema

* Distribución Linux (Linux Mint, Ubuntu, Debian o derivadas).
* Driver propietario oficial de NVIDIA instalado (`nvidia-driver`).
* `python3`, `python3-gi`, `gir1.2-gtk-3.0` (instalados por defecto en Linux Mint y Ubuntu).
* `zenity` (fallback de autenticación, preinstalado en la mayoría de entornos GNOME/GTK).

---

## 🛠️ Prueba rápida del detector

Puedes comprobar qué detecta el sistema en tu PC sin abrir la GUI:

```bash
python3 gpu_detector.py
```

Mostrará el modelo de GPU, rango de TDP, relojes máximos y los perfiles calculados para tu hardware.
