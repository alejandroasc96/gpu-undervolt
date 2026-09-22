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
| NVIDIA GeForce GTX 1060 Mobile / Max-Q | 80 W / 60 W | 3 modos PowerMizer | Portátil |
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

Las GPUs de portátil (como la GTX 1060 Mobile o GT 840M) no permiten cambiar el TDP en vatios vía `nvidia-smi`. Para estas GPUs se ofrecen 3 modos optimizados mediante **PowerMizer** manteniendo la misma coherencia que en escritorio:

| Modo | Descripción |
|:---|:---|
| 🌱 **Ultra Eco** | PowerMizer Adaptativo — baja frecuencias a ~139 MHz en reposo para máximo ahorro y batería |
| ⚡ **Punto Dulce** | PowerMizer Máximo Rendimiento (P0) — frecuencias sostenidas para evitar caídas de FPS en juegos |
| ⚙️ **De Fábrica (Stock)** | PowerMizer Automático — restaura el comportamiento original del driver y elimina persistencia |

---

## ✨ Características

* **Detección automática:** Funciona con cualquier GPU NVIDIA sin configuración manual.
* **Multi-GPU:** Si tienes varias GPUs NVIDIA, puedes elegir cuál configurar desde la propia app.
* **Interfaz gráfica moderna con pestañas:** Conmutación entre GPU y Utils integrada en GTK3 (Cinnamon, GNOME, XFCE, MATE).
* **Monitor en tiempo real:** Lectura en vivo de la GPU (vatios, temperatura, uso, relojes) y monitor de uso de disco en `/`.
* **Estado visible al abrir:** Indica el perfil de energía realmente aplicado (detectado del hardware) y si el daemon de arranque está activo.
* **Pestaña Utils (Limpieza de Disco):** Suite de herramientas para recuperar espacio del sistema:
  - Limpieza de caché de paquetes (`apt clean`).
  - Desinstalación de dependencias huérfanas (`apt autoremove --purge`).
  - Reducción y aspirado de registros del sistema (`journalctl --vacuum-size=100M` y `7d`).
  - Limpieza de runtimes Flatpak huérfanos (`flatpak uninstall --unused`).
  - Limpieza de miniaturas (`~/.cache/thumbnails`) y papelera de reciclaje.
  - Estimación y análisis de espacio recuperable antes de limpiar.
* **Persistencia en el arranque:** Servicio `systemd` ultraligero por GPU para aplicar el perfil automáticamente en cada arranque.
* **Perfil De Fábrica sin redundancias:** Al aplicar «De Fábrica» el inicio automático se desactiva automáticamente (no tiene sentido persistirlo).
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
