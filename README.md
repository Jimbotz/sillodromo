# Sillódromo - Aplicación de Escritorio Accesible en Docker (PyQt5 + X11)

Aplicación de escritorio desarrollada en **Python** con **PyQt5**, totalmente contenida y lista para ejecutarse mediante **Docker** con soporte de interfaz gráfica por **X11 Forwarding**. Diseñada bajo rigurosos criterios de accesibilidad visual (**WCAG 2.1 nivel AA / AAA**), amigable para personas con daltonismo (deuteranopía, protanopía y tritanopía), baja visión y fotofobia / sensibilidad lumínica.

---

## Criterios de Diseño Accesible y Sistema de Color

1. **Modo Oscuro Suave Anti-Fatiga**:
   - Evita el negro puro (`#000000`) y el blanco puro (`#FFFFFF`) para prevenir el efecto halo generado por astigmatismo y reducir el cansancio visual.
   - **Fondo de ventana**: Carbón suave `#1E1E24`.
   - **Superficies y Paneles**: `#2B2D42`.
   - **Texto Principal**: Marfil suave `#F4F4F6` (Ratio de contraste **14.6:1**, superando holgadamente el umbral AAA de 7.0:1).
2. **Paleta Inclusiva para Daltonismo (Basada en Okabe-Ito)**:
   - **Regla Fundamental**: Ningún estado o alerta depende únicamente del color. Cada componente combina **Icono de texto + Color + Etiqueta explicativa**.
   - **Acción Principal**: Azul Cobalto `#0072B2` con texto blanco `#FFFFFF` (Ratio > 4.7:1, cumple AA).
   - **Indicador de Foco**: Ámbar / Dorado `#E69F00` (Grosor de 3px de alto impacto visual, ratio > 7.5:1).
   - **Éxito**: Verde Azulado `#009E73` con badge textual `[✓] ÉXITO:`.
   - **Advertencia**: Ámbar `#E69F00` con badge textual `[!] ADVERTENCIA:`.
   - **Error**: Bermellón `#D55E00` con badge textual `[✖] ERROR:`.
   - **Información**: Azul Cielo `#56B4E9` con badge textual `[ℹ] INFORMACIÓN:`.
3. **Ergonomía y Navegación por Teclado**:
   - Indicador de foco visual evidente (`border: 3px solid #E69F00`) en todos los controles interactivos en estado `:focus`.
   - Orden secuencial de tabulación (`Tab` / `Shift+Tab`) en todos los formularios y vistas.
   - Áreas de interacción aumentadas (inputs de 40px+ de alto y casillas de verificación de 22x22px).

---

## Estructura del Proyecto

```text
sillodromo/
├── Dockerfile                  # Imagen Debian slim con PyQt5 de apt (amd64 y arm64) + usuario no-root
├── docker-compose.yml          # Mapeo del socket X11, variables de entorno y recarga en caliente
├── requirements.txt            # Dependencias Python (PyQt5, MediaPipe)
├── README.md                   # Documentación y guía de despliegue multiplataforma
└── app/
    ├── main.py                 # Vistas Menú, Navegación, Configuración e Interacción
    ├── control.py              # Calibración, gestos, mirada filtrada y máquina de estados
    ├── voz.py                  # Texto a voz no bloqueante con pyttsx3 o spd-say
    ├── camara.py               # Cámara, CLAHE y MediaPipe en un hilo aparte
    ├── modelos/face_landmarker.task  # Modelo de MediaPipe para la detección de rostro
    ├── palette.py              # Definición matemática de colores, luminancia y ratios WCAG
    └── styles.qss              # Hoja de estilos Qt accesible WCAG 2.1
```

---

## Guía de Despliegue Paso a Paso (X11 Forwarding)

Para que el contenedor Docker pueda proyectar su ventana gráfica en tu monitor, debes permitir la conexión al servidor de ventanas X11 del host según tu sistema operativo:

### Opción A: Linux (Ubuntu, Debian, Fedora, Arch)

1. **Permitir conexiones locales al servidor X11**:
   ```bash
   xhost +local:docker
   # O de manera permisiva temporalmente:
   xhost +local:root
   ```

2. **Construir y levantar la aplicación**:
   ```bash
   docker compose build
   docker compose up
   ```

3. **Restablecer los permisos de acceso al terminar (recomendado por seguridad)**:
   ```bash
   xhost -local:docker
   ```

---

### Opción B: macOS (Apple Silicon M1/M2/M3/M4 e Intel)

En macOS se utiliza el servidor X11 libre **XQuartz**:

1. **Instalar XQuartz** (si aún no lo tienes):
   ```bash
   brew install --cask xquartz
   ```

2. **Configurar XQuartz**:
   - Abre XQuartz.
   - Ve a **XQuartz** > **Ajustes** (Preferences) > pestaña **Seguridad** (Security).
   - Marca la casilla: **"Permitir conexiones desde clientes de red"** (*Allow connections from network clients*).
   - Cierra y vuelve a abrir XQuartz para aplicar la configuración.

3. **Habilitar acceso y configurar la variable DISPLAY**:
   Ejecuta en tu terminal:
   ```bash
   # Autorizar la dirección IP local de tu Mac en XQuartz
   IP=$(ipconfig getifaddr en0)
   /opt/X11/bin/xhost + $IP
   /opt/X11/bin/xhost + 127.0.0.1

   # Levantar con docker-compose apuntando a tu host
   DISPLAY=host.docker.internal:0 docker compose up --build
   ```

---

### Opción C: Windows

#### 1. Con WSL2 y WSLg (Windows 11 o Windows 10 actualizado):
Windows 11 incluye **WSLg** nativo, por lo que el socket X11 en `/tmp/.X11-unix` ya está integrado.
Simplemente abre tu terminal de WSL2 (Ubuntu) y ejecuta:
```bash
docker compose up --build
```

#### 2. Con VcXsrv / Xming (Windows clásico):
1. Descarga e instala **VcXsrv Windows X Server**.
2. Al iniciarlo mediante *XLaunch*, selecciona:
   - *Multiple windows*, Display number: `0`.
   - Marca la casilla **"Disable access control"** (crucial para permitir la conexión desde Docker).
3. En PowerShell o CMD:
   ```powershell
   $env:DISPLAY="host.docker.internal:0"
   docker compose up --build
   ```

---

## Atajos de Teclado de Accesibilidad

| Tecla / Atajo | Acción |
| :--- | :--- |
| `Tab` | Avanzar al siguiente elemento interactivo |
| `Shift + Tab` | Retroceder al elemento interactivo anterior |
| `Espacio` / `Enter` | Activar el botón o casilla seleccionada |
| `Flechas Izquierda/Derecha` | Cambiar de vista con la barra de pestañas enfocada |

---

## Ejecución Nativa (sin Docker)

En Windows, macOS o Linux con Python 3 instalado:
```bash
pip install -r requirements.txt
python app/main.py
```

En Linux arm64 (Raspberry Pi, etc.) pip no tiene PyQt5 precompilado. Usa el de apt y MediaPipe desde pip:
```bash
sudo apt install python3-pyqt5 libgles2
python3 -m venv --system-site-packages .venv
.venv/bin/pip install mediapipe==1.0.1
.venv/bin/python app/main.py
```

### Cámara

- **macOS**: la primera vez el sistema pide permiso de cámara para la terminal desde la que lanzas la app. Si no aparece o lo negaste, actívalo en *Ajustes del Sistema > Privacidad y seguridad > Cámara*.
- **Mac Intel**: MediaPipe no publica paquete para esta plataforma; la app arranca igual y el panel de la cámara indica que no está disponible.
- La aplicación usa el índice de cámara `1`, que corresponde a la segunda cámara del prototipo.
- Al iniciar se calibra primero el centro facial y después la mirada con cinco puntos que cubren el centro y las cuatro esquinas de la pantalla. La calibración ocular también puede repetirse desde Configuración.
- **Docker**: solo en hosts Linux, descomentando `/dev/video1` en `docker-compose.yml`. Docker Desktop (macOS/Windows) no puede pasar la webcam al contenedor; allí ejecuta la app de forma nativa.

---

### Voz

Las tarjetas de Cafetera, Ventilador, Secadora y Lavadora emiten órdenes como "Alexa, activa Cafetera". Se usa `pyttsx3` y, como respaldo en Linux, `spd-say`. En Docker el contenedor no tiene salida de audio configurada, así que para probar TTS se recomienda la ejecución nativa.

## Desarrollo y Modificación en Vivo (Hot Reload)

El archivo `docker-compose.yml` mapea la carpeta local `./app` hacia `/app` dentro del contenedor. Esto significa que puedes editar `app/styles.qss` o `app/main.py` directamente desde tu editor de código y reiniciar el contenedor instantáneamente sin tener que volver a compilar la imagen Docker.

Para reiniciar rápidamente:
```bash
docker compose restart
```
