# Benchmark de recursos: hilos, procesos, CPU y memoria

Medición del 21 de septiembre de 2026, para saber qué corre hoy en Sillódromo y qué se puede ajustar antes de añadir las funciones de paro de la silla. Los números salen de `benchmark.py`; ver [Cómo repetir las mediciones](#cómo-repetir-las-mediciones).

## Resumen

- **Hallazgo crítico, ya corregido:** en macOS, MediaPipe 1.0.1 con GPU retenía una copia de cada cuadro de la cámara. La memoria crecía unos **98 MB por segundo** (de 727 MB a 6,1 GB en un minuto). Ahora macOS usa MediaPipe 0.10.35 con CPU y la memoria se mantiene plana en unos **205 MB**.
- **Uso normal (cámara activa, sin vista previa):** 18,7 % de un núcleo en macOS y 37,7 % en Linux, con 30 cuadros por segundo procesados.
- **La vista previa casi duplica la CPU** en macOS (33,6 %), porque dibuja la malla de la cara y escala la imagen. Por eso está apagada para el usuario final.
- **Voz:** cada frase de Alexa abre 2 procesos (137 MB en total) que viven unos 4 segundos y luego se cierran.
- **Hoy nada vigila de forma independiente.** Todo corre en un solo proceso de Python. Antes de las funciones de paro hace falta un vigilante aparte (ver [Funciones de paro](#qué-significa-para-las-funciones-de-paro-de-la-silla)).

## Entorno

| | macOS | Linux |
|---|---|---|
| Máquina | MacBook Air, Apple M4 (10 núcleos), 24 GB | Docker arm64 en la misma Mac |
| Sistema | macOS 26.6.2 | Debian trixie: los mismos paquetes del `Dockerfile` sobre `python:3.12-slim`, usando el Python del sistema |
| Python | 3.12.13 | 3.13.5 |
| PyQt5 / Qt | 5.15.10 / 5.15.11 | Debian `python3-pyqt5` |
| MediaPipe | 0.10.35 (CPU) | 1.0.1 (CPU) |
| OpenCV | 5.0.0 | 5.0.0 |

- **Cámara simulada:** una foto de 1024×820 entregada a 30 cuadros por segundo, en lugar de la webcam. Así el resultado no depende del permiso de cámara ni de lo que haya delante, pero no incluye el costo de capturar de una cámara real.
- **Método:** la app corre sin ventana visible (`QT_QPA_PLATFORM=offscreen`) en la vista Navegación, que es la que usa la cámara. Hay 5 s de calentamiento para cargar el modelo y luego 15 s de medición.
- **Unidad de CPU:** porcentaje de un núcleo. 100 % equivale a un núcleo completo.

## Resultados

| Escenario | CPU macOS | Memoria macOS | Hilos macOS | CPU Linux | Memoria Linux | Hilos Linux |
|---|---|---|---|---|---|---|
| App sin cámara | 0,0 % | 139 MB | 4 | 0,0 % | 141 MB | 19 |
| **Cámara sin vista previa (uso normal)** | **18,7 %** | **204 MB** | **34** | **37,7 %** | **232 MB** | **37** |
| Cámara con vista previa | 33,6 % | 293 MB | 45 | 46,1 % | 240 MB | 48 |

- **Cuadros procesados:** 30 por segundo en todos los escenarios con cámara, sin perder cuadros.
- **Cruceta:** desde que se añadió la cruceta, la detección de la boca (`output_face_blendshapes`) está activada, y el uso normal en macOS sube de 18,7 % a 20,1 % de CPU (medido después, con el mismo script).
- **Memoria en el tiempo** (macOS, uso normal, `--serie 60`): pasó de 201 MB a los 5 s a 207 MB a los 60 s, tras 1.805 cuadros. No hay fuga.
- **Voz** (`--voz`): una frase de 2 partes ("Alexa" + orden) abre hasta 2 procesos a la vez, con 137 MB en total. Viven unos 3,9 s y no queda ninguno al terminar.
- **Linux:** usa el doble de CPU que macOS con el mismo trabajo. En una Raspberry Pi será bastante más lento que en el M4; hay que medirlo allí antes de fijar cuántos cuadros por segundo procesar.

## Calibración inicial y CLAHE

`benchmark.py` omite la calibración inicial (equivale a pulsar `Esc`), así que mide el uso normal. La calibración usa lo mismo que el uso normal y no abre hilos ni procesos nuevos. Costo de la corrección de luz, en macOS con un cuadro de 1280×720:

| Operación | Tiempo | CPU a 30 fps |
|---|---|---|
| Calcular la curva CLAHE (una sola vez, al inicio) | 3,9 ms | una vez |
| Aplicar la curva a cada cuadro (`cv2.LUT`) | 0,18 ms | 0,5 % de un núcleo |
| CLAHE completo en cada cuadro (lo que se evita) | 1,86 ms | 5,6 % de un núcleo |

Con buena luz, corregir la imagen no ayuda y sube el uso normal de ~19 % a ~23 % de CPU: MediaPipe tarda más con la imagen retocada. Por eso la curva solo se aplica si al inicio el cuadro está oscuro (brillo medio < 60) o tiene poco contraste (desviación < 40). Con la foto de prueba oscurecida al 40 % y al 25 % sí se aplica, y la cara se detecta en todos los cuadros.

## Hallazgo: fuga de memoria de MediaPipe 1.0.1 en macOS (corregida)

**Síntoma:** con la cámara activa, la memoria de la app crecía sin parar.

| Tiempo | 5 s | 10 s | 20 s | 30 s | 40 s | 55 s | 60 s |
|---|---|---|---|---|---|---|---|
| Memoria | 727 MB | 1.240 MB | 2.218 MB | 3.196 MB | 4.174 MB | 5.641 MB | 6.135 MB |

Son unos 3,26 MB por cuadro, justo el tamaño de una imagen RGBA de 1024×820: MediaPipe se quedaba con una copia de cada imagen. La memoria solo se liberaba al cerrar el detector.

**Aislamiento** (300 detecciones seguidas, crecimiento de memoria):

| Variante | Por cuadro |
|---|---|
| MediaPipe 1.0.1, macOS, GPU, modo VIDEO, RGBA | +3,26 MB |
| MediaPipe 1.0.1, macOS, GPU, modo IMAGE, RGBA | +6,52 MB |
| MediaPipe 1.0.1, Linux, CPU, modo VIDEO, RGBA o RGB | 0 MB |
| MediaPipe 0.10.35, macOS, CPU, modo VIDEO, RGBA o RGB | 0 MB |

**Por qué se usaba la GPU:** en macOS, MediaPipe 1.0.1 con CPU aborta el proceso entero al crear el detector (`Check failed: service_ Service is unavailable`, dentro de `DrishtiMetalHelper`).

**Arreglo:**
- **Versiones:** `requirements.txt` instala MediaPipe 0.10.35 en macOS y 1.0.1 en el resto. La 1.0.1 es la única con paquete para Linux arm64 (Raspberry Pi), y la imagen de Docker también la usa.
- **Código:** `app/camara.py` usa siempre CPU con imágenes RGB. Se quitaron el caso especial de GPU y la conversión a RGBA de cada cuadro.

**Regla:** antes de cambiar la versión de MediaPipe en macOS, correr `python benchmark.py --serie 60` y comprobar que la memoria no crece.

## Inventario de hilos y procesos

### Proceso principal (la app)

| Hilo | Cantidad | Qué hace | ¿Lo controlamos? |
|---|---|---|---|
| Principal de Qt (`MainThread`) | 1 | Dibuja la interfaz y recibe los resultados de la cámara | Sí (`main.py`) |
| `HiloCamara` (en Python aparece como `Dummy-1`) | 1 | Lee la cámara, ejecuta MediaPipe y calcula la dirección de la cabeza. Hace casi todo el trabajo | Sí (`camara.py`) |
| Hilos internos de MediaPipe (`drishti`) | macOS: 10; Linux: 4–5 + ~14 que heredan el nombre `HiloCamara` | Ejecutan el modelo de detección | No directamente |
| `ThreadPoolExecutor-0_0` | 1 | Despachador de MediaPipe en Python (`mediapipe/tasks/python/core/serial_dispatcher.py`) | No |
| Hilos sin nombre (macOS) | ~10 | Probablemente el pool de OpenCV (`cv2.getNumThreads()` = 10) para girar la imagen y convertir colores | Con `cv2.setNumThreads(n)` |
| Hilos `python3` (Linux) | 19, incluso sin cámara | Se crean al importar las librerías nativas y quedan en reposo (origen exacto no identificado) | No medido |
| Pool de Qt (`Thread (pooled)`) | 10 | Solo con vista previa: escalado de la imagen | Se evita sin vista previa |
| Del sistema (macOS) | ~12 | Trabajadores de GCD (`com.apple.root.default-qos`), audio (`caulk.messenger`) y otros | No |

### Procesos de voz

| Proceso | Cantidad | Memoria | Vida | Qué hace |
|---|---|---|---|---|
| Parte de una frase | 2 por frase de Alexa ("Alexa" y la orden) | ~68 MB cada uno | ~4 s | Arranca el motor de voz (~1 s), espera su turno y habla |
| Hilo coordinador en la app | 1 por frase | mínima | mientras dura la frase | Da la señal a cada parte con 1 s de pausa y cancela las pendientes si llega otra frase |

## Qué significa para las funciones de paro de la silla

- **Nada vigila de forma independiente.** Si `HiloCamara` falla o la cámara se desconecta, solo se muestra un mensaje en pantalla; ningún componente reacciona.
- **Todo corre en un solo proceso de Python.** Si la interfaz se congela o Python se cae, cae todo junto, incluido lo que debería detener la silla. Además, los hilos de Python comparten el GIL; MediaPipe y OpenCV lo liberan mientras calculan, pero el código Python de cualquier hilo puede retrasar a los demás.

Recomendación, en orden:

1. **Paro de emergencia físico** que no dependa del software. El software es solo una segunda capa.
2. **Un proceso vigilante aparte**, separado de la interfaz y de la cámara, con una sola tarea. Cada componente le envía una señal de "sigo vivo" cada pocos milisegundos. Si alguna falta, el vigilante detiene la silla. El motor solo se mueve mientras le llegue la señal de "seguir" (principio de hombre muerto).
3. **Prioridad alta para el vigilante:** `os.nice` en Linux y macOS. En Linux, además, fijarlo a un núcleo propio (`os.sched_setaffinity`).
4. **Medirlo en el hardware real** (Raspberry Pi u otro) con la cámara real, con la app cargada al máximo.

## Ajustes disponibles

| Ajuste | Dónde | Efecto | Estado |
|---|---|---|---|
| Vista previa | `SILLODROMO_VISTA_PREVIA=1` | Con vista previa, 33,6 % de CPU; sin ella, 18,7 % (macOS) | Hecho: apagada por defecto |
| Cuadros por segundo procesados | Bucle de `HiloCamara._procesar` (saltar cuadros) | La CPU baja casi en proporción; para la dirección de la cabeza podrían bastar 10–15 | No implementado |
| Resolución de la cámara | `cap.set(cv2.CAP_PROP_FRAME_WIDTH/HEIGHT, ...)` en `HiloCamara.__init__` | Menos datos por cuadro | No implementado |
| Hilos de OpenCV | `cv2.setNumThreads(n)` | Menos hilos en reposo; poco efecto en CPU con imágenes pequeñas | No implementado |
| Voz | Un proceso de voz fijo en lugar de 2 nuevos por frase | Ahorra el segundo de arranque y los 137 MB por frase | No implementado |
| Prioridad | `os.nice`, `os.sched_setaffinity` (Linux) | Reserva CPU para lo crítico (el vigilante) | No implementado |

## Lo que no se midió

- **Cámara real:** el costo de capturar y decodificar una webcam real (la medición usó una foto).
- **Otro hardware:** una Raspberry Pi y Windows.
- **GPU y consumo de energía.**
- **Origen exacto de algunos hilos:** los 19 hilos `python3` de Linux sin cámara y los hilos sin nombre de macOS.

## Cómo repetir las mediciones

Desde la raíz del repo, con el entorno de la app (macOS o Linux):

```bash
python benchmark.py                # tres escenarios, 15 s cada uno
python benchmark.py --segundos 30  # mediciones más largas
python benchmark.py --serie 60     # memoria cada 5 s durante 60 s: detecta fugas
python benchmark.py --voz          # procesos de voz (volumen 0, frase neutra: no activa ninguna Alexa)
```

La primera vez, `benchmark.py` descarga la foto de prueba de MediaPipe. En Linux con Docker, con este repo montado en `/repo`:

```bash
docker compose build
docker compose run --rm -v "$PWD:/repo:ro" sillodromo-gui python3 /repo/benchmark.py
```
