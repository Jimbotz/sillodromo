"""
camara.py - Captura de la cámara con detección de rostro (MediaPipe FaceLandmarker).
Se importa aparte para que la interfaz arranque aunque falten OpenCV o MediaPipe.
"""

import os
import sys
import time

import cv2

# Las ruedas de OpenCV para Linux traen sus propios plugins de Qt y apuntan esta
# variable hacia ellos, lo que impide arrancar PyQt5 ("Could not load the Qt platform plugin").
os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision
from mediapipe.tasks.python.vision import drawing_styles, drawing_utils
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

MODELO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos", "face_landmarker.task")
# MediaPipe 1.0.1 en macOS aborta el proceso con el delegado CPU (usa Metal internamente);
# allí se usa GPU. En Linux y Windows, CPU: no requiere drivers de GPU (Docker, Raspberry Pi).
DELEGADO = BaseOptions.Delegate.GPU if sys.platform == "darwin" else BaseOptions.Delegate.CPU

MAX_CAMARAS = 4  # índices de OpenCV que se prueban al buscar una cámara
MENSAJE_SIN_CAMARA = "No se pudo abrir ninguna cámara."
if sys.platform == "darwin":
    # macOS atribuye el permiso a la app que lanza el proceso (Terminal, VS Code...), no a Python
    MENSAJE_SIN_CAMARA += (
        " Permite el acceso a la app desde la que lanzas Sillódromo en"
        " Ajustes del Sistema > Privacidad y seguridad > Cámara."
    )

# Puntos del modelo de 468: punta de la nariz, mejillas (lados de la cara), frente y mentón
NARIZ, MEJILLA_A, MEJILLA_B, FRENTE, MENTON = 1, 234, 454, 10, 152
# Perillas de calibración: cuánto debe girar la cabeza (fracción del ancho/alto de la cara)
# para contar como dirección, y dónde queda la nariz en vertical al mirar de frente.
UMBRAL_GIRO = 0.12
CENTRO_VERTICAL = 0.55


def direccion_cabeza(puntos) -> str:
    """Devuelve "izquierda", "derecha", "arriba", "abajo" o "centro" según la posición de
    la nariz dentro de la cara. La imagen ya viene en espejo, así que izquierda es la de la persona."""
    nariz = puntos[NARIZ]
    lado_izq, lado_der = sorted((puntos[MEJILLA_A].x, puntos[MEJILLA_B].x))
    horizontal = (nariz.x - lado_izq) / max(lado_der - lado_izq, 1e-6) - 0.5
    vertical = (nariz.y - puntos[FRENTE].y) / max(puntos[MENTON].y - puntos[FRENTE].y, 1e-6) - CENTRO_VERTICAL
    # ponytail: umbral fijo sin suavizado; añadir media móvil si la flecha parpadea
    if max(abs(horizontal), abs(vertical)) < UMBRAL_GIRO:
        return "centro"
    if abs(horizontal) >= abs(vertical):
        return "izquierda" if horizontal < 0 else "derecha"
    return "arriba" if vertical < 0 else "abajo"


class HiloCamara(QThread):
    """Lee la cámara y ejecuta MediaPipe fuera del hilo de la interfaz."""

    fotograma = pyqtSignal(QImage, int, float, str)  # imagen, rostros detectados, fps, dirección
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Se abre en el hilo principal: en macOS OpenCV solo puede pedir el permiso de cámara desde ahí.
        # Se prueban los primeros índices hasta dar con una cámara que entregue imagen.
        self.cap, self.indice = None, None
        for i in range(MAX_CAMARAS):
            cap = cv2.VideoCapture(i)
            if cap.isOpened() and cap.read()[0]:
                self.cap, self.indice = cap, i
                break
            cap.release()

    def run(self):
        if self.cap is None:
            self.error.emit(MENSAJE_SIN_CAMARA)
            return
        try:
            self._procesar(self.cap)
        except Exception as e:  # p. ej. falta el modelo .task
            self.error.emit(f"Error de MediaPipe: {e}")
        finally:
            self.cap.release()

    def _procesar(self, cap):
        opciones = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODELO, delegate=DELEGADO),
            running_mode=vision.RunningMode.VIDEO,
        )
        with vision.FaceLandmarker.create_from_options(opciones) as detector:
            marca_ms = 0
            anterior = time.monotonic()
            while not self.isInterruptionRequested():
                ok, bgr = cap.read()
                if not ok:
                    self.error.emit("La cámara dejó de enviar imagen")
                    break

                rgb = cv2.cvtColor(cv2.flip(bgr, 1), cv2.COLOR_BGR2RGB)  # espejo, como un selfie
                # VIDEO exige marcas de tiempo estrictamente crecientes
                marca_ms = max(marca_ms + 1, int(time.monotonic() * 1000))
                # SRGBA: el delegado GPU no acepta imágenes de 3 canales
                entrada = mp.Image(image_format=mp.ImageFormat.SRGBA, data=cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA))
                resultado = detector.detect_for_video(entrada, marca_ms)

                for rostro in resultado.face_landmarks:
                    drawing_utils.draw_landmarks(
                        rgb,
                        rostro,
                        vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=drawing_styles.get_default_face_mesh_tesselation_style(),
                    )

                # Dirección de la primera cara; vacío si no hay nadie
                direccion = direccion_cabeza(resultado.face_landmarks[0]) if resultado.face_landmarks else ""

                ahora = time.monotonic()
                fps = 1.0 / max(ahora - anterior, 1e-6)
                anterior = ahora
                alto, ancho, _ = rgb.shape
                # .copy(): QImage no copia el buffer de numpy, que se reutiliza en la siguiente vuelta
                imagen = QImage(rgb.data, ancho, alto, 3 * ancho, QImage.Format_RGB888).copy()
                self.fotograma.emit(imagen, len(resultado.face_landmarks), fps, direccion)



if __name__ == "__main__":
    # Autoverificación de direccion_cabeza con caras sintéticas (x, y normalizados)
    from types import SimpleNamespace as P

    def cara(nx, ny):
        puntos = [P(x=0.5, y=0.5)] * 468
        puntos[MEJILLA_A], puntos[MEJILLA_B] = P(x=0.3, y=0.5), P(x=0.7, y=0.5)
        puntos[FRENTE], puntos[MENTON] = P(x=0.5, y=0.2), P(x=0.5, y=0.8)
        puntos[NARIZ] = P(x=nx, y=ny)
        return puntos

    assert direccion_cabeza(cara(0.5, 0.53)) == "centro"
    assert direccion_cabeza(cara(0.38, 0.53)) == "izquierda"
    assert direccion_cabeza(cara(0.62, 0.53)) == "derecha"
    assert direccion_cabeza(cara(0.5, 0.40)) == "arriba"
    assert direccion_cabeza(cara(0.5, 0.66)) == "abajo"
    print("direccion_cabeza: OK")
