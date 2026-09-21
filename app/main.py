"""
main.py - Sillódromo: aplicación de escritorio PyQt5 en vista partida.
Izquierda: selector de módulos, sus opciones y el estado de los dispositivos.
Derecha: cámara con detección de rostro (MediaPipe).
Funciona en Windows, macOS y Linux (nativo o en Docker vía X11).
"""

import os
import sys

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import voz

try:
    from camara import HiloCamara
    ERROR_CAMARA = None
except ImportError as e:  # p. ej. Mac Intel: MediaPipe no publica paquete para esa plataforma
    HiloCamara = None
    ERROR_CAMARA = f"MediaPipe no está disponible ({e.name})"

MODULOS = ["Silla", "Alexa 1", "Secadora 3"]
# Botones que hablan: (texto del botón, frase dicha). "Alexa" va delante para activarla.
# Los módulos que no aparecen aquí siguen con "Opción 1/2/3" sin conectar.
FRASES = {
    "Alexa 1": [
        ("Encender", "Alexa, encender"),
        ("Apagar", "Alexa, apagar"),
        ("Alexa, ponte unas cumbias", "Alexa, ponte unas cumbias"),
    ]
}
# Ángulo de la flecha de navegación (0 = hacia arriba, sentido horario)
ANGULOS = {"arriba": 0, "derecha": 90, "abajo": 180, "izquierda": 270}


def crear_vista(titulo: str, frases=()) -> QWidget:
    vista = QWidget()
    layout = QVBoxLayout(vista)
    layout.setContentsMargins(0, 16, 0, 16)
    layout.setSpacing(14)

    encabezado = QLabel(titulo, vista)
    encabezado.setObjectName("tituloVista")
    layout.addWidget(encabezado)

    for n in range(1, 4):
        texto, frase = frases[n - 1] if frases else (f"Opción {n}", "")
        boton = QPushButton(texto, vista)
        # Nombre único para lectores de pantalla: "Opción 1" se repite en cada vista
        boton.setAccessibleName(f"{titulo}, {texto}")
        if frase:
            boton.clicked.connect(lambda _, f=frase: voz.hablar(f))
        layout.addWidget(boton)

    if frases and not voz.DISPONIBLE:
        layout.addWidget(QLabel("Voz no disponible: instala pyttsx3", vista))

    layout.addStretch(1)
    return vista


def crear_estado_dispositivos() -> QFrame:
    tarjeta = QFrame()
    tarjeta.setObjectName("cardFrame")
    layout = QVBoxLayout(tarjeta)

    titulo = QLabel("Estado de los dispositivos", tarjeta)
    titulo.setObjectName("tituloTarjeta")
    layout.addWidget(titulo)
    for nombre in MODULOS:
        layout.addWidget(QLabel(f"{nombre}: sin conexión", tarjeta))
    return tarjeta


class VistaCamara(QWidget):
    """Dibuja la imagen de la cámara recortada en un círculo."""

    def __init__(self, parent=None, flecha=False):
        super().__init__(parent)
        self.imagen = None
        self.flecha = flecha  # dibuja encima la dirección de la cabeza
        self.direccion = ""
        self.setMinimumSize(220, 220)
        self.setAccessibleName("Vista de la cámara con detección de rostro")

    def set_imagen(self, imagen: QImage, direccion: str = ""):
        self.imagen = imagen
        self.direccion = direccion
        self.update()

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        lado = min(self.width(), self.height()) - 8
        circulo = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        ruta = QPainterPath()
        ruta.addEllipse(circulo)
        p.fillPath(ruta, QColor("#2B2D42"))

        if self.imagen is not None:
            # Escalado tipo "cover": llena el círculo y recorta el sobrante centrado
            esc = self.imagen.scaled(int(lado), int(lado), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.setClipPath(ruta)
            p.drawImage(QPointF(circulo.center().x() - esc.width() / 2, circulo.center().y() - esc.height() / 2), esc)
            p.setClipping(False)

        p.setPen(QPen(QColor("#595F85"), 3))
        p.drawEllipse(circulo)

        if self.flecha and self.direccion:
            # Ámbar con borde oscuro: se distingue sobre cualquier imagen
            p.setPen(QPen(QColor("#1E1E24"), 4))
            p.setBrush(QColor("#E69F00"))
            p.translate(circulo.center())
            t = lado * 0.18
            if self.direccion == "centro":
                p.drawEllipse(QPointF(0, 0), t * 0.4, t * 0.4)
            else:
                p.rotate(ANGULOS[self.direccion])
                p.drawPolygon(QPolygonF([
                    QPointF(0, -t * 1.6), QPointF(t, -t * 0.4), QPointF(t * 0.4, -t * 0.4),
                    QPointF(t * 0.4, t * 1.2), QPointF(-t * 0.4, t * 1.2), QPointF(-t * 0.4, -t * 0.4),
                    QPointF(-t, -t * 0.4),
                ]))


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sillódromo")
        self.resize(1100, 700)
        self.setMinimumSize(900, 560)

        # Vistas generales: 0 menú, 1 navegación, 2 activadores
        self.vistas = QStackedWidget(self)
        self.vistas.addWidget(self._crear_menu())
        self.vistas.addWidget(self._crear_navegacion())
        self.vistas.addWidget(self._crear_activadores())
        self.setCentralWidget(self.vistas)

        self.hilo = None
        if HiloCamara is None:
            self._error_camara(ERROR_CAMARA)
        else:
            self.hilo = HiloCamara(self)
            self.hilo.fotograma.connect(self._nuevo_fotograma)
            self.hilo.error.connect(self._error_camara)
            self.hilo.start()

    def _ir_a(self, indice: int):
        self.vistas.setCurrentIndex(indice)
        # Llevar el foco a la vista nueva para seguir navegando con el teclado
        self.vistas.currentWidget().findChild(QPushButton).setFocus()

    def _boton_volver(self, parent) -> QPushButton:
        boton = QPushButton("Volver al menú", parent)
        boton.clicked.connect(lambda: self._ir_a(0))
        return boton

    def _crear_menu(self) -> QWidget:
        menu = QWidget()
        layout = QVBoxLayout(menu)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        titulo = QLabel("Menú", menu)
        titulo.setObjectName("tituloVista")
        layout.addWidget(titulo)
        for indice, nombre in ((1, "Navegación"), (2, "Activadores")):
            boton = QPushButton(nombre, menu)
            boton.setObjectName("primaryBtn")
            boton.setAccessibleName(f"Ir a la vista {nombre}")
            boton.clicked.connect(lambda _, i=indice: self._ir_a(i))
            layout.addWidget(boton)
        layout.addStretch(1)
        return menu

    def _crear_navegacion(self) -> QWidget:
        vista = QWidget()
        layout = QVBoxLayout(vista)
        layout.setContentsMargins(20, 20, 20, 20)

        fila = QHBoxLayout()
        fila.addWidget(self._boton_volver(vista))
        fila.addStretch(1)

        self.camara_navegacion = VistaCamara(vista, flecha=True)
        self.camara_navegacion.setAccessibleName("Cámara con la dirección de la cabeza")

        # La flecha nunca va sola: el texto repite la dirección
        self.lbl_direccion = QLabel("Dirección: buscando rostro...", vista)
        self.lbl_direccion.setObjectName("tituloVista")
        self.lbl_direccion.setAlignment(Qt.AlignCenter)
        self.lbl_direccion.setWordWrap(True)

        layout.addLayout(fila)
        layout.addWidget(self.camara_navegacion, 1)
        layout.addWidget(self.lbl_direccion)
        return vista

    def _crear_activadores(self) -> QWidget:
        vista = QWidget()
        layout = QVBoxLayout(vista)
        layout.setContentsMargins(20, 12, 20, 0)

        fila = QHBoxLayout()
        fila.addWidget(self._boton_volver(vista))
        fila.addStretch(1)

        division = QSplitter(Qt.Horizontal, vista)
        division.addWidget(self._crear_panel_modulos())
        division.addWidget(self._crear_panel_camara())
        division.setChildrenCollapsible(False)
        division.setHandleWidth(2)
        division.setSizes([550, 550])

        layout.addLayout(fila)
        layout.addWidget(division, 1)
        return vista

    def _crear_panel_modulos(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)

        barra = QHBoxLayout()
        pila = QStackedWidget(panel)
        grupo = QButtonGroup(panel)  # exclusivo: solo un módulo marcado a la vez
        for i, nombre in enumerate(MODULOS):
            boton = QPushButton(nombre, panel)
            boton.setCheckable(True)
            boton.setAccessibleName(f"Ir al módulo {i + 1}: {nombre}")
            grupo.addButton(boton, i)
            barra.addWidget(boton)
            pila.addWidget(crear_vista(f"Módulo {i + 1}: {nombre}", FRASES.get(nombre, ())))
        grupo.button(0).setChecked(True)
        grupo.idClicked.connect(pila.setCurrentIndex)

        separador = QFrame(panel)
        separador.setObjectName("separador")

        fila_estado = QHBoxLayout()
        fila_estado.addWidget(crear_estado_dispositivos())
        fila_estado.addStretch(1)

        layout.addLayout(barra)
        layout.addWidget(separador)
        layout.addWidget(pila, 1)
        layout.addLayout(fila_estado)
        return panel

    def _crear_panel_camara(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)

        titulo = QLabel("Cámara: detección de rostro", panel)
        titulo.setObjectName("tituloVista")

        fila = QHBoxLayout()
        self.lbl_estado = QLabel("Estado: iniciando cámara...", panel)
        self.lbl_fps = QLabel("FPS: --", panel)
        fila.addWidget(self.lbl_estado)
        fila.addStretch(1)
        fila.addWidget(self.lbl_fps)

        self.vista_camara = VistaCamara(panel)

        self.lbl_deteccion = QLabel("Buscando rostro...", panel)
        self.lbl_deteccion.setAlignment(Qt.AlignCenter)
        self.lbl_deteccion.setWordWrap(True)

        layout.addWidget(titulo)
        layout.addLayout(fila)
        layout.addWidget(self.vista_camara, 1)
        layout.addWidget(self.lbl_deteccion)
        return panel

    def _nuevo_fotograma(self, imagen: QImage, rostros: int, fps: float, direccion: str):
        self.vista_camara.set_imagen(imagen)
        self.camara_navegacion.set_imagen(imagen, direccion)
        self.lbl_direccion.setText(f"Dirección: {direccion}" if direccion else "Dirección: ningún rostro en la imagen")
        self.lbl_estado.setText(f"Estado: cámara {self.hilo.indice} activa")
        self.lbl_fps.setText(f"FPS: {fps:.0f}")
        self.lbl_deteccion.setText("Rostro detectado" if rostros else "Ningún rostro en la imagen")

    def _error_camara(self, mensaje: str):
        self.lbl_estado.setText("Estado: cámara no disponible")
        self.lbl_fps.setText("FPS: --")
        self.lbl_deteccion.setText(mensaje)
        self.lbl_direccion.setText(mensaje)

    def closeEvent(self, evento):
        # Liberar la cámara antes de salir
        if self.hilo is not None:
            self.hilo.requestInterruption()
            self.hilo.wait()
        super().closeEvent(evento)


def main():
    # Atributos High-DPI: deben fijarse antes de crear QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Sillódromo")

    qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles.qss")
    with open(qss_path, encoding="utf-8") as f:
        app.setStyleSheet(f.read())

    ventana = VentanaPrincipal()
    ventana.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
