"""
widgets/camera_preview.py - Dibuja la imagen de la cámara recortada en un círculo, con la flecha
de dirección de la cabeza encima (calibración y vista de Navegación).
"""

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QWidget

from tools.palette import AccessibleColors as C

# Ángulo de la flecha de navegación (0 = hacia arriba, sentido horario)
ANGULOS = {"arriba": 0, "derecha": 90, "abajo": 180, "izquierda": 270}


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
        p.fillPath(ruta, QColor(C.BG_GUIDE))

        if self.imagen is not None:
            # Escalado tipo "cover": llena el círculo y recorta el sobrante centrado
            esc = self.imagen.scaled(int(lado), int(lado), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.setClipPath(ruta)
            p.drawImage(QPointF(circulo.center().x() - esc.width() / 2, circulo.center().y() - esc.height() / 2), esc)
            p.setClipping(False)

        p.setPen(QPen(QColor(C.BORDER_DEFAULT), 3))
        p.drawEllipse(circulo)

        if self.flecha and self.direccion:
            # Azul con borde oscuro: 6,9:1 sobre el círculo; se distingue también sobre la imagen
            p.setPen(QPen(QColor(C.SELECTED_BORDER), 4))
            p.setBrush(QColor(C.SELECTED))
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
