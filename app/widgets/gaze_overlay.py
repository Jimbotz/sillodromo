"""
widgets/gaze_overlay.py - Capa transparente encima de toda la ventana: el punto de la mirada y, en
el bloque seleccionado, una barra que se llena hasta activarlo. No recibe clics.
"""

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from tools.palette import AccessibleColors as C


class CapaMirada(QWidget):
    """Capa transparente encima de todo: el punto de la mirada y, en el bloque seleccionado, una
    barra que se llena hasta activarlo. No recibe clics."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.punto, self.caja, self.progreso = None, None, 0.0
        self.aviso = ""  # texto arriba al centro, p. ej. mientras una acción está en curso

    def mostrar(self, punto, caja_local, progreso: float):
        self.punto, self.caja, self.progreso = punto, caja_local, progreso
        self.update()

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.caja is not None and self.progreso > 0:
            # Clara sobre el azul del bloque seleccionado: contraste 6,6:1
            barra = QRectF(self.caja.left() + 8, self.caja.bottom() - 20, (self.caja.width() - 16) * self.progreso, 12)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C.BG_SURFACE))
            p.drawRoundedRect(barra, 4, 4)
        if self.aviso:
            fuente = p.font()
            fuente.setPixelSize(26)
            fuente.setBold(True)
            p.setFont(fuente)
            caja_texto = p.fontMetrics().boundingRect(self.aviso).adjusted(-24, -14, 24, 14)
            caja_texto.moveCenter(QPoint(self.width() // 2, 60))
            p.setPen(QPen(QColor(C.BG_SURFACE), 3))
            p.setBrush(QColor(C.SELECTED_BORDER))
            p.drawRoundedRect(QRectF(caja_texto), 8, 8)
            p.setPen(QColor(C.SELECTED_TEXT))
            p.drawText(caja_texto, Qt.AlignCenter, self.aviso)
        if self.punto is not None:
            centro = QPointF(*self.punto)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(C.SELECTED_BORDER), 7))  # contorno oscuro: se ve sobre el fondo claro
            p.drawEllipse(centro, 16, 16)
            p.setPen(QPen(QColor(C.BG_SURFACE), 3))
            p.drawEllipse(centro, 16, 16)
