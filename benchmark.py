"""
benchmark.py - Mide CPU, memoria, hilos y procesos de Sillódromo con una cámara simulada.
Resultados y conclusiones: BENCHMARK.md. Funciona en macOS y Linux (no en Windows).

Uso (desde la raíz del repo, con el entorno de la app):
    python benchmark.py                # tres escenarios, 15 s cada uno
    python benchmark.py --segundos 30  # mediciones más largas
    python benchmark.py --serie 60     # memoria cada 5 s durante 60 s: detecta fugas
    python benchmark.py --voz          # procesos que abre una frase de Alexa (en silencio)

La cámara simulada entrega una foto a 30 fps en lugar de la webcam, así el resultado no depende
del permiso de cámara ni de lo que haya delante. No mide el costo de capturar de una cámara real.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections import Counter

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
FOTO_URL = "https://storage.googleapis.com/mediapipe-assets/portrait.jpg"  # foto de prueba de MediaPipe
FOTO = os.path.join(tempfile.gettempdir(), "sillodromo_retrato.jpg")
FPS = 30
CALENTAMIENTO = 5  # segundos: carga del modelo antes de medir
ESCENARIOS = {
    "sin_camara": "App sin cámara",
    "sin_imagen": "Cámara sin vista previa (uso normal)",
    "con_imagen": "Cámara con vista previa (SILLODROMO_VISTA_PREVIA=1)",
}


def rss_mb(pid=None) -> float:
    pid = pid or os.getpid()
    if sys.platform == "linux":
        with open(f"/proc/{pid}/status") as f:
            return int(next(l for l in f if l.startswith("VmRSS")).split()[1]) / 1024
    return int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout) / 1024


def hilos_nativos() -> Counter:
    """Hilos del sistema operativo de este proceso, agrupados por nombre."""
    pid = os.getpid()
    if sys.platform == "linux":
        return Counter(open(f"/proc/{pid}/task/{t}/comm").read().strip() for t in os.listdir(f"/proc/{pid}/task"))
    # macOS: `sample` lista cada hilo como "    <n> Thread_<id>[: nombre]"; sin nombre -> "sin nombre"
    salida = subprocess.run(["sample", str(pid), "1"], capture_output=True, text=True).stdout
    nombres = Counter()
    for linea in salida.splitlines():
        if linea.startswith("    ") and linea[4:5].isdigit() and "Thread_" in linea:
            resto = linea.split("Thread_", 1)[1]
            nombres[resto.split(":", 1)[1].split("(")[0].strip() if ":" in resto else "sin nombre"] += 1
    return nombres


def medir_escenario(escenario: str, segundos: float, serie: bool):
    """Se ejecuta en un proceso nuevo por escenario para que las mediciones no se mezclen."""
    sys.path.insert(0, APP)
    import cv2
    import camara
    import main
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    foto = cv2.imread(FOTO)

    class CamaraSimulada:
        def __init__(self, *_):
            self.siguiente = time.monotonic()

        def isOpened(self):
            return True

        def read(self):
            self.siguiente += 1 / FPS
            time.sleep(max(0, self.siguiente - time.monotonic()))
            return True, foto.copy()

        def release(self):
            pass

    camara.cv2.VideoCapture = CamaraSimulada
    if escenario == "sin_camara":
        main.HiloCamara, main.ERROR_CAMARA = None, "sin cámara"
    main.VISTA_PREVIA = escenario == "con_imagen"

    app = QApplication(sys.argv[:1])
    with open(os.path.join(APP, "styles.qss"), encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    ventana = main.VentanaPrincipal()
    ventana.resize(1440, 900)
    ventana.show()
    ventana._ir_a(1)  # Navegación: la vista que usa la cámara
    cuadros = [0]
    if ventana.hilo:
        ventana.hilo.calibracion.omitida = True  # se mide el uso normal, no la calibración inicial
        ventana.hilo.fotograma.connect(lambda *_: cuadros.__setitem__(0, cuadros[0] + 1))

    inicio = {}
    t0 = time.monotonic()

    def empezar():
        inicio.update(cpu=time.process_time(), t=time.monotonic(), cuadros=cuadros[0])

    def muestra_serie():
        print(f"  t={time.monotonic() - t0:4.0f} s  memoria {rss_mb():6.0f} MB  cuadros {cuadros[0]}", flush=True)

    def terminar():
        dt = time.monotonic() - inicio["t"]
        nativos = hilos_nativos()
        print(f"{ESCENARIOS[escenario]}\n"
              f"  CPU {100 * (time.process_time() - inicio['cpu']) / dt:.1f} % de un núcleo | memoria {rss_mb():.0f} MB | "
              f"cuadros procesados {(cuadros[0] - inicio['cuadros']) / dt:.1f} fps | hilos de OpenCV {cv2.getNumThreads()}\n"
              f"  hilos Python: {[t.name for t in threading.enumerate()]}\n"
              f"  hilos nativos: {sum(nativos.values())} -> {dict(nativos.most_common())}", flush=True)
        ventana.close()
        app.quit()

    if serie:
        temporizador = QTimer()
        temporizador.timeout.connect(muestra_serie)
        temporizador.start(5000)
    QTimer.singleShot(CALENTAMIENTO * 1000, empezar)
    QTimer.singleShot(int((CALENTAMIENTO + segundos) * 1000), terminar)
    app.exec_()


def medir_voz():
    """Procesos de una frase de dos partes. Volumen 0 y frase neutra: no activa ninguna Alexa real."""
    sys.path.insert(0, APP)
    import voz

    if not voz.DISPONIBLE:
        sys.exit("pyttsx3 no está instalado")
    original = "sys.stdin.readline()\nmotor.say(sys.argv[1])\n"
    assert original in voz._SCRIPT, "voz._SCRIPT cambió; actualiza medir_voz()"
    voz._SCRIPT = voz._SCRIPT.replace(
        original, "motor.setProperty('volume', 0.0)\nsys.stdin.readline()\nmotor.say('prueba de voz')\n")

    def hijos():
        salida = subprocess.run(["ps", "-A", "-o", "pid=,command="], capture_output=True, text=True).stdout
        return [int(l.split()[0]) for l in salida.splitlines() if "import sys, pyttsx3" in l]

    t0 = time.monotonic()
    voz.hablar("Alexa, encender foco 1")
    max_procesos, max_mb, vida = 0, 0.0, 0.0
    while time.monotonic() - t0 < 10:
        pids = hijos()
        mb = 0.0
        for pid in pids:
            try:
                mb += rss_mb(pid)
            except (ValueError, OSError, StopIteration):  # el proceso terminó entre ps y la lectura
                pass
        if pids:
            vida = time.monotonic() - t0
        max_procesos, max_mb = max(max_procesos, len(pids)), max(max_mb, mb)
        time.sleep(0.2)
    print(f"Voz (frase de 2 partes)\n  hasta {max_procesos} procesos a la vez | {max_mb:.0f} MB en total | "
          f"viven ~{vida:.1f} s | procesos que quedan al terminar: {len(hijos())}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--segundos", type=float, default=15)
    parser.add_argument("--serie", type=float, metavar="SEGUNDOS", help="memoria cada 5 s (sin vista previa)")
    parser.add_argument("--voz", action="store_true")
    parser.add_argument("--escenario", choices=ESCENARIOS, help=argparse.SUPPRESS)  # uso interno
    args = parser.parse_args()

    if args.voz:
        return medir_voz()
    if not os.path.exists(FOTO):
        urllib.request.urlretrieve(FOTO_URL, FOTO)
    if args.escenario:
        return medir_escenario(args.escenario, args.segundos, serie=args.serie is not None)

    entorno = dict(os.environ, QT_QPA_PLATFORM="offscreen")  # sin ventana: no ocupa la pantalla
    escenarios = ["sin_imagen"] if args.serie else list(ESCENARIOS)
    segundos = args.serie or args.segundos
    for escenario in escenarios:
        comando = [sys.executable, __file__, "--escenario", escenario, "--segundos", str(segundos)]
        if args.serie:
            comando.append("--serie=1")
        salida = subprocess.run(comando, env=entorno, capture_output=True, text=True)
        # MediaPipe y Qt escriben avisos por stderr; solo se muestra el resultado
        print(salida.stdout, end="" if salida.returncode == 0 else salida.stderr[-2000:])


if __name__ == "__main__":
    main()
