"""
widgets/calibration_points.py - Calibración de pantalla: un blanco por punto; su anillo se cierra
mientras se mide (ver views.calibration para la calibración de la cara).
"""

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from tools.palette import AccessibleColors as C


class VistaPuntos(QWidget):
    """Calibración de pantalla: un blanco por punto; su anillo se cierra mientras se mide."""

    def __init__(self):
        super().__init__()
        self.punto, self.progreso = (0.5, 0.5), 0.0
        self.texto = QLabel(self)
        self.texto.setObjectName("instruccion")
        self.texto.setAlignment(Qt.AlignCenter)
        self.texto.setWordWrap(True)
        # Ayuda para quien acompaña; no se lee en voz alta
        ayuda = QLabel("Esc: omitir la calibración", self)
        ayuda.setAlignment(Qt.AlignCenter)
        ayuda.setObjectName("ayudaCalibracion")
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.texto)
        layout.addStretch(1)
        layout.addWidget(ayuda)
        self.setAccessibleName("Calibración de la mirada")

    def mostrar(self, punto, progreso: float, texto: str = None):
        self.punto, self.progreso = punto, progreso
        if texto is not None:
            self.texto.setText(texto)
        self.update()

    def paintEvent(self, _evento):
        if self.punto is None:
            return  # solo texto (p. ej. el resultado)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        centro = QPointF(self.punto[0] * self.width(), self.punto[1] * self.height())
        r = min(self.width(), self.height()) * 0.03
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(C.BORDER_DEFAULT), 4))
        p.drawEllipse(centro, r, r)
        p.setPen(QPen(QColor(C.SELECTED), 6))
        p.drawArc(QRectF(centro.x() - r, centro.y() - r, 2 * r, 2 * r), 90 * 16, -int(360 * 16 * self.progreso))
        p.setPen(QPen(QColor(C.SELECTED_BORDER), 2))
        p.setBrush(QColor(C.SELECTED))
        p.drawEllipse(centro, r * 0.35, r * 0.35)
