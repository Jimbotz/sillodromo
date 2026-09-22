# Sillódromo - Aplicación de Escritorio Accesible en Docker (PyQt5 + X11)

Aplicación de escritorio desarrollada en **Python** con **PyQt5**, totalmente contenida y lista para ejecutarse mediante **Docker** con soporte de interfaz gráfica por **X11 Forwarding**. Diseñada bajo rigurosos criterios de accesibilidad visual (**WCAG 2.1 nivel AA / AAA**), amigable para personas con daltonismo (deuteranopía, protanopía y tritanopía), baja visión y fotofobia / sensibilidad lumínica.

---

## Criterios de Diseño Accesible y Sistema de Color

Tema claro en blancos y azules. Los colores están en `app/palette.py`, y `python app/palette.py` comprueba el contraste de cada par que aparece en la interfaz.

1. **Claro, pero atenuado.** El fondo es un azul grisáceo (`#BFC9DA`), que refleja un 37 % menos de luz que un blanco casi puro, y el texto es un azul casi negro (`#111B31`). Nunca se usan blanco ni negro puros: hay menos deslumbramiento, menos molestia con fotofobia y menos halo con astigmatismo. El texto de los bloques es grande (22 px) porque se lee de lejos.
2. **Contraste medido.** Todo el texto tiene nivel **AAA**, 7:1 o más sobre su fondo; el texto de los bloques llega a 11,9:1. Los bordes de los bloques tienen 4,1:1 frente al fondo (WCAG 1.4.11 pide 3:1), así que se ve dónde empieza cada bloque.
3. **Selección que no depende del tono.** El bloque seleccionado (con la cruceta o la mirada) pasa de azul claro a **azul oscuro `#1D4C8F` con texto blanco** (8,5:1) y **borde el doble de grueso**. Se distingue por luminosidad y por grosor, así que funciona igual con cualquier tipo de daltonismo, tritanopía incluida. Encima, la barra de permanencia es clara (7,8:1) y el puntero tiene contorno oscuro y centro claro, para verse sobre cualquier fondo.
4. **Estados con texto.** Nada se comunica solo con color: mientras una acción está en curso, los bloques se atenúan **y** aparece el aviso "Espera a que termine la acción". En la calibración, la flecha siempre va con la instrucción escrita y hablada.
5. **Iconos vectoriales, sin emojis.** Cada bloque lleva un icono de [Lucide](https://lucide.dev) (licencia ISC, en `app/iconos/`), que siempre acompaña al texto y nunca lo sustituye. El icono toma el color del texto: oscuro en reposo, blanco en el bloque seleccionado y gris mientras una acción está en curso. Cada bloque tiene además un nombre accesible con su dispositivo, por ejemplo "Televisiones, Televisión 2: YouTube".

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
    ├── comandos.py             # Comandos personalizados por categorías: lee, valida y guarda datos/comandos.json
    ├── editor.py               # Pantalla para crear y editar comandos y categorías (para quien acompaña)
    ├── icono.py                # Iconos SVG coloreados según el estado del bloque
    ├── datos/                  # comandos.json y calibracion.json (fuera de git: son de cada equipo)
    ├── iconos/                 # Iconos SVG de Lucide (licencia ISC en iconos/LICENSE)
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

La app se maneja por bloques. Girar la cabeza (izquierda, derecha, arriba o abajo) mueve la selección al bloque vecino, que se ilumina (azul oscuro con borde grueso). Cada giro cuenta una sola vez: hay que volver al centro antes del siguiente. **Abrir la boca** pulsa el bloque seleccionado. Los ojos no se usan.

**En la vista Navegación la cabeza conduce:** girar solo mueve la flecha, y ni la cabeza ni la mirada seleccionan bloques, así no se sale de la vista sin querer. **Abrir la boca vuelve al menú.** Al llegar al menú, la mirada no activa nada hasta que se mueva.

Las perillas de calibración (`UMBRAL_GIRO`, `BOCA_ABIERTA`, `BOCA_CERRADA`, `CUADROS_ESTABLES`) están en `app/camara.py`.

## Calibración inicial

**La calibración se guarda** en `app/datos/calibracion.json`, dentro del proyecto. Esa carpeta no va a git, porque la calibración es de cada equipo. En Docker persiste porque `./app` está montado como volumen. Se guardan dos partes:

- **La cara:** el centro de reposo, el umbral de cada dirección y la apertura de la boca.
- **La pantalla:** el modelo de la mirada.

Al abrir la app:

- **Con las dos partes guardadas**, va directo al menú. La luz se sigue revisando sola en cada arranque, sin pantalla ni voz, porque cambia entre el día y la noche.
- **Con una sola parte guardada**, solo pide la que falta.
- **Sin nada guardado**, pide la calibración, o `Esc` para usar los valores por defecto. Lo que se omite con `Esc` no se guarda, así que la próxima vez se vuelve a pedir. Una calibración de pantalla imprecisa tampoco se guarda.
- **Si el archivo está dañado** o es de otra versión, la app no se rompe: calibra de nuevo la parte que no pudo leer.

**Volver a calibrar:** está en el menú. Sirve si se movió la silla, la cámara o la pantalla. Pide confirmación, con "No" seleccionado de partida, porque con la mirada se podría activar sin querer. Al confirmar, borra lo guardado y repite todo.

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

En Activadores, el dispositivo **Comandos** muestra primero las **categorías** (por ejemplo, "Solicitar atención" o "Casa") y, al elegir una, sus comandos. Cada comando es un bloque con icono. Al pulsarlo, la voz dice su frase tal cual: "Ir al baño" dice "Por favor, llévenme al baño".

**Se crean desde la app.** En la página de Comandos, **"Editar comandos"** abre una pantalla normal, con teclado y ratón, para quien acompaña:

- **Categorías:** crear, editar (nombre e icono) y borrar. Al borrar una categoría también se borran sus comandos, y la app pide confirmación.
- **Comandos:** crear, editar y borrar. Cada comando tiene un **título** (lo que dice el bloque), la **frase que dirá la voz** (con un botón "Probar voz"), su **categoría** (se puede mover a otra) y un **icono**, elegido de una rejilla con todos los iconos a la vista. Como máximo caben 12 comandos por categoría.
- **La mirada y la cruceta no actúan en el editor**, para que la persona en la silla no borre nada sin querer. Las flechas del teclado mueven las listas.

Todo se guarda al momento en `app/datos/comandos.json`. Un archivo dañado no impide que la app arranque, y el formato antiguo (una lista suelta) se convierte solo.

Las frases para una persona se escriben tal cual. Si una frase empieza por "Alexa", la voz hace la pausa de 1 s tras "Alexa", y lo que hace esa orden se configura en las **Rutinas** de la app de Alexa.

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

En Activadores, cada bloque le dice su orden a Alexa en voz alta con `pyttsx3` ("Alexa…" y, tras 1 s, "encender foco 1"). Los dispositivos son estos, y se definen en `DISPOSITIVOS` (`app/main.py`):

- **Focos** y **Enchufes:** encender y apagar las unidades 1, 2 y 3.
- **Televisiones:** para cada televisión 1, 2 y 3, encender, apagar, YouTube, Netflix y subir o bajar el volumen un 10 %.
- **Música:** poner, detener, subir o bajar el volumen un 10 %, y los géneros.

Las frases exactas dependen de cómo tenga Alexa configurado cada aparato; si alguna no la entiende, se cambia en `DISPOSITIVOS`. Se usa una voz en español si el sistema tiene alguna. En Linux necesita `espeak-ng` (`sudo apt install espeak-ng`). En Docker el contenedor no tiene salida de audio, así que las frases no se oyen.

## Desarrollo y Modificación en Vivo (Hot Reload)

El archivo `docker-compose.yml` mapea la carpeta local `./app` hacia `/app` dentro del contenedor. Esto significa que puedes editar `app/styles.qss` o `app/main.py` directamente desde tu editor de código y reiniciar el contenedor instantáneamente sin tener que volver a compilar la imagen Docker.

Para reiniciar rápidamente:
```bash
docker compose restart
```
