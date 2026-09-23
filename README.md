# Optimizador de Energía y Undervolt NVIDIA (Linux) + Utilidades de Sistema

Herramienta gráfica (GUI) nativa para Linux desarrollada con **Python y GTK3** para optimizar el consumo eléctrico, temperatura y rendimiento de tarjetas gráficas **NVIDIA**, junto con una suite completa de **mantenimiento, limpieza y optimización de almacenamiento SSD/disco**.

Detecta automáticamente cualquier GPU instalada, calcula los perfiles de consumo ideales según el TDP real del hardware y permite gestionar la persistencia y la salud del sistema desde una interfaz moderna e integrada.

---

## 🧭 Estructura y Navegación de la Aplicación

La aplicación se organiza en una ventana GTK3 con **pestañas principales**:

1. **Pestaña GPU:** Gestión de energía, límites de TDP, relojes, PowerMizer, persistencia de arranque y telemetría en tiempo real.
2. **Pestaña CPU:** Gestión energética y undervolt del procesador (HWP, EPP, RAPL, Turbo Boost) con 4 modos optimizados y servicio systemd.
3. **Pestaña Utils (Disco y Sistema):** Diagnóstico de almacenamiento, cálculo en vivo de espacio recuperable, suite de limpieza segura y optimización física de bloques para unidades SSD (TRIM).

---

## 🔍 Detección Inteligente y Soporte Multi-GPU

La aplicación consulta el driver NVIDIA (`nvidia-smi` y `nvidia-settings`) al arrancar para inspeccionar las capacidades reales del hardware:

- **Soporte Multi-GPU:** Si dispones de varias tarjetas gráficas NVIDIA (ej. GPU integrada + dedicada o múltiples GPUs de cómputo/render), un selector dinámico en la cabecera te permite cambiar y configurar cada tarjeta de forma independiente.
- **Diagnóstico proactivo del driver:** Detecta desajustes entre la versión del paquete y el módulo del kernel cargado (*Driver/library version mismatch*) o bloqueos de comunicación (como Secure Boot), guiando al usuario con avisos claros.
- **Lectura de TDP y relojes reales:** Calcula los perfiles proporcionales al rango de vatios soportado por el firmware/VBIOS de la tarjeta.
- **Detección de estado al iniciar:** Inspecciona el hardware para mostrar qué perfil está actualmente activo y si el servicio de persistencia en arranque está habilitado.
- **Diferenciación Escritorio vs. Portátil (Móvil):** Si el driver no permite ajustar el límite de potencia por hardware (típico en GPUs de portátil con TDP bloqueado), conmuta automáticamente al control adaptativo de **PowerMizer**.

### Ejemplos de hardware soportado

| GPU | TDP Nominal | Perfiles Disponibles | Tipo |
|:---|:---:|:---:|:---:|
| NVIDIA GeForce GTX 1660 / Ti / Super | 120–125 W | 4 perfiles en vatios | Escritorio |
| NVIDIA GeForce GTX 1060 6G / 3G | 120 W | 4 perfiles en vatios | Escritorio |
| NVIDIA GeForce RTX 5060 Ti / Serie RTX 30/40/50 | 160–220 W+ | 4 perfiles en vatios | Escritorio |
| NVIDIA GeForce GTX 1060 Mobile / Max-Q | 60–80 W | 3 modos PowerMizer | Portátil |
| NVIDIA GeForce GT 840M / 940MX / MX series | 25–35 W | 3 modos PowerMizer | Portátil |
| **Cualquier otra GPU NVIDIA** | Auto-detectado | Calculado a medida | Auto |

---

## 🚀 Perfiles de Consumo (GPU)

### GPUs de Escritorio (ajuste de TDP y relojes)

Los perfiles se calculan de manera adaptativa como **porcentajes del TDP real** de la tarjeta:

| Perfil | % TDP | GTX 1660 (120W) | RTX 5060 Ti (180W) | Uso recomendado y comportamiento |
|:---|:---:|:---:|:---:|:---|
| 🌱 **Ultra Eco** | ~58% | 70 W | 105 W | Máximo silencio y ahorro: streaming, ofimática y reposo. Limita la frecuencia de reloj del núcleo para evitar picos de consumo. |
| 🍃 **Máxima Eficiencia** | ~67% | 80 W | 120 W | Gaming eficiente: reduce considerablemente la temperatura sin pérdidas perceptibles de FPS. |
| ⚡ **Punto Dulce** | ~75% | 90 W | 135 W | ~98% del rendimiento máximo con un 25% menos de consumo y calor. |
| ⚙️ **De Fábrica (Stock)** | 100% | 120 W | 180 W | Restaura las especificaciones originales del fabricante. Desactiva el inicio automático para no interferir con el comportamiento por defecto. |

### GPUs Móviles (Portátiles)

Para tarjetas portátiles donde `nvidia-smi` no permite alterar el límite en vatios, se proporcionan 3 modos correspondientes mediante **PowerMizer**:

| Modo | Descripción técnica |
|:---|:---|
| 🌱 **Ultra Eco** | PowerMizer Adaptativo: reduce frecuencias dinámicamente (~139 MHz en reposo) para maximizar la autonomía de la batería. |
| ⚡ **Punto Dulce** | PowerMizer Rendimiento Máximo (P0): fuerza frecuencias altas constantes para evitar tirones y caídas de FPS en juegos. |
| ⚙️ **De Fábrica (Stock)** | PowerMizer Automático: restaura la lógica estándar gestionada por el controlador. |

---

## ⚡ Perfiles de Consumo y Optimización (CPU)

La pestaña **CPU** aprovecha los mecanismos nativos del kernel Linux (`intel_pstate`, HWP y RAPL) para optimizar el consumo del procesador de forma segura y **100 % reversible**:

| Perfil | Governor | EPP | Turbo Boost | Límite Frecuencia | Límite RAPL (TDP) | Uso recomendado |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| ⚙️ **De Fábrica** | powersave | balance_performance | ON | Máxima del hardware | Sin límite | Valores originales del sistema. Desactiva el inicio automático. |
| 🍃 **Óptimo** | powersave | balance_power | ON | Máxima del hardware | ~78% TDP (~35W) | Mismo rendimiento perceptible con ~20% menos de temperatura y ventiladores más silenciosos. |
| 🌱 **Eco** | powersave | power | ON | 85% de máxima | ~56% TDP (~25W) | Silencioso y fresco bajo multitarea o compilación ligera. |
| 🌿 **Eco Plus** | powersave | power | **OFF** | Reloj base (~2600 MHz) | ~40% TDP (~18W) | Máximo ahorro de batería/energía. Elimina picos térmicos, ideal para ofimática y streaming. |

> **Seguridad y reversibilidad:**
> - No modifica voltajes analógicos directamente en registros MSR (sin riesgos de inestabilidad ni corrupción).
> - Ajusta únicamente políticas energéticas estándar del kernel a través del subsistema `/sys`.
> - Al desinstalar la aplicación con `uninstall.sh`, la CPU se restaura automáticamente a sus valores originales de fábrica y se elimina el servicio de arranque.

---

## 🧹 Pestaña Utils: Limpieza de Sistema y Optimización SSD

Una suite integral para diagnosticar y recuperar espacio en disco, manteniendo el rendimiento y la durabilidad del almacenamiento:

### 1. Optimización Física SSD (TRIM)
- **Ejecución de `fstrim`:** Botón dedicado para recortar bloques no usados en el SSD.
- **Protección de vida útil:** Ayuda a la recolección de basura (*garbage collection*) del controlador SSD, reduce la amplificación de escritura y mantiene la velocidad de escritura como el primer día.
- **Soporte multi-partición:** Detecta automáticamente si `/home` reside en un disco o partición independiente de `/` y optimiza ambas.

### 2. Tareas de Limpieza y Recuperación de Espacio
- **Caché de Navegadores Web:** Limpieza segura de archivos temporales de navegación en Firefox, Google Chrome, Chromium y Brave (`~/.cache/`), **sin tocar perfiles, contraseñas, historial ni sesiones**.
- **Caché de Shaders (Steam y NVIDIA):** Limpieza de compilaciones intermedias en `~/.local/share/Steam/steamapps/shadercache` y `~/.nv/GLCache` (libera múltiples gigabytes tras actualizaciones o desinstalaciones de juegos; se regeneran automáticamente).
- **Reportes de fallos y volcados (Core Dumps):** Limpieza de volcados y archivos en `/var/crash`, `/var/lib/systemd/coredump` y aspirado mediante `coredumpctl vacuum`.
- **Caché de paquetes del sistema (APT):** Eliminación de archivos `.deb` antiguos descargados en `/var/cache/apt/archives`.
- **Dependencias huérfanas:** `apt autoremove --purge` para paquetes y librerías que quedaron sin uso.
- **Registros del sistema (Systemd Journal):** Compactado y aspirado con `journalctl --vacuum-size=100M` y retención de 7 días.
- **Runtimes Flatpak huérfanos:** Desinstalación de bibliotecas y runtimes en desuso (`flatpak uninstall --unused`).
- **Miniaturas del explorador:** Limpieza de `~/.cache/thumbnails`.
- **Papelera de reciclaje:** Vaciado seguro de la papelera del usuario (`~/.local/share/Trash`).
- **Cachés de desarrollo:** Limpieza opcional de restos temporales de `pip` y `npm`.

### 3. Escaneo y Seguridad
- **Análisis previo en vivo:** Calcula el espacio ocupado antes de ejecutar ninguna acción.
- **Selector individual:** Permite elegir exactamente qué tareas ejecutar mediante casillas de verificación.
- **Vaciado seguro de directorios:** Utiliza rutinas que respetan enlaces simbólicos para no salir de las rutas designadas y no eliminan las carpetas base del sistema.

---

## ⚙️ Persistencia y Funcionamiento en Segundo Plano

- **Servicio Systemd por GPU:** Permite activar inicio automático para mantener el perfil elegido tras reiniciar el equipo (`nvidia-power-optimizer-gpuX.service`).
- **Cero consumo en segundo plano:** Ni la aplicación ni los servicios quedan residentes en RAM. Se aplican los valores en el arranque o al pulsar el botón y el proceso finaliza inmediatamente.
- **Elevación de privilegios transparente:** Utiliza `pkexec` (con fallback a `zenity`) para solicitar la contraseña de administrador únicamente al aplicar cambios en el hardware o en el sistema.

---

## 📦 Instalación Rápida

```bash
git clone https://github.com/alejandroasc96/gpu-undervolt.git
cd gpu-undervolt
chmod +x install.sh
./install.sh
```

El asistente de instalación realiza automáticamente:
1. Verificación de dependencias (`nvidia-smi`, `python3`, `python3-gi`, `gir1.2-gtk-3.0`).
2. Diagnóstico de comunicación con el driver NVIDIA.
3. Copia de la aplicación a `~/.local/share/nvidia-optimizer/`.
4. Creación del acceso directo con icono oficial en el **Escritorio** y en el **Menú de Aplicaciones**.

---

## 🗑️ Desinstalación

Para eliminar completamente la aplicación, los accesos directos y deshabilitar los servicios de inicio automático:

```bash
chmod +x uninstall.sh
./uninstall.sh
```

---

## 📋 Requisitos del Sistema

- **Sistema Operativo:** Distribución Linux (Linux Mint, Ubuntu, Debian o derivadas con GTK3).
- **Controlador Gráfico:** Driver propietario oficial de NVIDIA instalado (`nvidia-driver`).
- **Paquetes requeridos:** `python3`, `python3-gi`, `gir1.2-gtk-3.0`.
- **Autenticación gráfica:** `pkexec` (Polkit) o `zenity` (instalado habitualmente por defecto).

---

## 🛠️ Herramienta CLI de Diagnóstico

Puedes comprobar el reconocimiento de GPUs y el cálculo de perfiles sin abrir la interfaz gráfica:

```bash
python3 gpu_detector.py
```
Muestra por terminal el modelo detectado, arquitectura, rango de TDP, límites de reloj y los perfiles asignados.
