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
├── BENCHMARK.md                # Uso de CPU, memoria, hilos y procesos; hallazgos y recomendaciones
├── benchmark.py                # Repite las mediciones de BENCHMARK.md (macOS y Linux)
└── app/
    ├── main.py                 # Pantalla completa: Menú, Navegación (flecha según la cabeza) y Activadores (dispositivo → acción)
    ├── comandos.py             # Comandos personalizados: lee y valida ~/.sillodromo/comandos.json
    ├── voz.py                  # Texto a voz con pyttsx3 (lo que dicen los bloques y la calibración)
    ├── camara.py               # Captura de cámara + detección de rostro con MediaPipe (en un hilo aparte)
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

## Control con la cabeza (cruceta)

La app se maneja por bloques. Girar la cabeza (izquierda, derecha, arriba o abajo) mueve la selección al bloque vecino, que se ilumina en ámbar. Cada giro cuenta una sola vez: hay que volver al centro antes del siguiente. **Abrir la boca** pulsa el bloque seleccionado. Los ojos no se usan.

Las perillas de calibración (`UMBRAL_GIRO`, `BOCA_ABIERTA`, `BOCA_CERRADA`, `CUADROS_ESTABLES`) están en `app/camara.py`.

## Calibración inicial

**Todo el texto de la calibración se lee en voz alta** para quien no ve bien la pantalla, y cada paso espera a que termine la lectura antes de empezar a medir. En la calibración de pantalla también se dice dónde está cada punto ("Punto 7 de 16: a la derecha, al centro"). Sin `pyttsx3`, la calibración funciona igual, pero en silencio.

Con cámara, la app arranca calibrando (unos 25 s) antes de mostrar el menú. Cada paso muestra la instrucción en texto grande, una flecha hacia dónde girar y una barra de progreso. El tiempo de cada paso solo corre mientras la cámara ve la cara.

1. **Iluminación.** Se revisa una sola vez. Si la imagen está oscura o tiene poco contraste, se calcula CLAHE una vez y su efecto se aplica después a cada cuadro como una curva fija (`cv2.LUT`), que es casi gratis. Con buena luz no se corrige nada.
2. **Centro.** Unos segundos mirando al frente fijan la postura de reposo del usuario y su boca cerrada.
3. **Rangos.** Girar a la izquierda, a la derecha, arriba y abajo tanto como se pueda, volviendo al centro entre cada uno. Cada dirección se activa con el 30 % de lo que el usuario alcanza (`FRACCION_RANGO`). Si no hay movimiento suficiente hacia un lado, se avisa en pantalla y esa dirección usa el valor por defecto.
4. **Boca.** Abrirla todo lo posible fija cuánto debe abrirse para pulsar.

`Esc` omite la calibración y usa los valores por defecto. El resultado se imprime en la terminal. Las perillas de calibración (`FRACCION_RANGO`, `UMBRAL_MINIMO`, `LUZ_MINIMA`, `CONTRASTE_MINIMO`, etc.) están en `app/camara.py`.

## Puntero con ojos y cara (permanencia)

Tras la calibración inicial se calibra la pantalla: aparecen, de uno en uno, 16 blancos en el borde (5 arriba, 5 abajo y 3 en cada lado). Hay que mirar cada blanco moviendo los ojos, la cabeza o ambos, lo que haga falta. Con esas muestras se ajusta un modelo que convierte la posición de los iris y de la cabeza en un punto de la pantalla.

- **Se selecciona el bloque más cercano al puntero**, aunque la mirada no esté encima de ninguno. El bloque seleccionado se ilumina y una barra se llena; a los 1,5 s se activa (`TIEMPO_PERMANENCIA`). Salirse menos de 0,3 s, por ejemplo al parpadear, no reinicia el tiempo (`GRACIA`).
- **La barra solo carga con la mirada quieta.** Si el puntero se mueve más del 5 % de la pantalla en 0,3 s (la mirada se está desviando), la carga se pausa sin perder lo acumulado (`DISPERSION_MAXIMA`, `VENTANA_FIJACION`).
- **Una acción a la vez.** Mientras la acción anterior no termina (por ejemplo, la frase de Alexa), los bloques se atenúan, aparece el aviso "Espera a que termine la acción" y nada se puede activar, ni con la mirada, ni con la boca, ni con el teclado.
- **No se activa en cadena:** después de activar algo, nada cuenta hasta que la mirada se mueve (`REARME`). Así, si al cambiar de pantalla queda otro bloque bajo la mirada, no se activa solo.
- **Abrir la boca** sigue pulsando al instante el bloque seleccionado. En este modo, girar la cabeza no mueve la selección: mueve el puntero.
- **Si la calibración de pantalla es imprecisa** (error medio > 15 % de la pantalla, `ERROR_MAXIMO`), se avisa y se usa la cruceta. `Esc` omite ambas calibraciones.

El puntero se suaviza con un **filtro 1€**: con la mirada quieta suaviza mucho y quita el temblor, y cuando la mirada salta casi no suaviza, así que no hay retraso.

Perillas: `TIEMPO_PERMANENCIA`, `GRACIA`, `RIDGE`, `CORTE_MIN` y `BETA` (filtro 1€) en `app/camara.py`; `ASENTAR`, `MUESTREO`, `REARME` y `ERROR_MAXIMO` en `app/main.py`. Si el puntero tiembla, baja `CORTE_MIN`; si se queda atrás al mover la mirada, sube `BETA`.

## Comandos personalizados

En Activadores, el dispositivo **Comandos** muestra un bloque por cada comando del archivo `~/.sillodromo/comandos.json`. En Windows es `C:\Users\<usuario>\.sillodromo\comandos.json`. Lo edita quien acompaña, y la app lo lee al abrirse. Si no existe, la app lo crea con tres ejemplos:

```json
[
  {"texto": "Buenas noches", "frase": "Alexa, buenas noches"},
  {"texto": "Abrir persianas", "frase": "Alexa, abre las persianas"}
]
```

- `texto` es lo que dice el bloque y `frase` es lo que se le dice a Alexa. Si la frase no empieza por "Alexa", se añade sola.
- Lo que hace cada frase se configura en la app de Alexa como una **Rutina**, por ejemplo "buenas noches" para apagar todo. Aquí solo se dice la frase.
- Se muestran como máximo 12 comandos (3 filas de 4). Un archivo mal escrito no impide que la app arranque: el problema se explica al pie de la página de Comandos.
- En Docker el archivo vive dentro del contenedor y se pierde al recrearlo.

| Tecla / Atajo | Acción |
| :--- | :--- |
| `Tab` | Avanzar al siguiente elemento interactivo |
| `Shift + Tab` | Retroceder al elemento interactivo anterior |
| `Espacio` | Pulsar el bloque seleccionado (igual que abrir la boca) |
| `Flechas` | Mover la selección al bloque vecino (igual que girar la cabeza) |

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
- **Docker**: solo en hosts Linux, descomentando el bloque `devices` de `docker-compose.yml`. Docker Desktop (macOS/Windows) no puede pasar la webcam al contenedor; allí ejecuta la app de forma nativa.

---

### Voz

En Activadores, cada bloque le dice su orden a Alexa en voz alta con `pyttsx3` ("Alexa…" y, tras 1 s, "encender foco 1"). Hay cuatro dispositivos: Focos, Televisiones y Enchufes (encender y apagar las unidades 1, 2 y 3) y Alexa (géneros de música). Se definen en `DISPOSITIVOS` (`app/main.py`). Se usa usando una voz en español si el sistema tiene alguna. En Linux necesita `espeak-ng` (`sudo apt install espeak-ng`). En Docker el contenedor no tiene salida de audio, así que las frases no se oyen.

## Desarrollo y Modificación en Vivo (Hot Reload)

El archivo `docker-compose.yml` mapea la carpeta local `./app` hacia `/app` dentro del contenedor. Esto significa que puedes editar `app/styles.qss` o `app/main.py` directamente desde tu editor de código y reiniciar el contenedor instantáneamente sin tener que volver a compilar la imagen Docker.

Para reiniciar rápidamente:
```bash
docker compose restart
```
