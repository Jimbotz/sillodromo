"""
views/calibration.py - Pantalla de calibración de la cara (luz, centro, rangos y boca). La
calibración de pantalla (los 16 puntos) es widgets.calibration_points.VistaPuntos; toda la lógica
de avance vive en window.py (ver _calibrando/_calibrado y compañía).
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from widgets.camera_preview import VistaCamara


def crear(ventana) -> QWidget:
    vista = QWidget()
    layout = QVBoxLayout(vista)
    layout.setContentsMargins(40, 30, 40, 30)
    layout.setSpacing(16)

    titulo = QLabel("Calibración", vista)
    titulo.setObjectName("tituloTarjeta")

    ventana.lbl_instruccion = QLabel("Preparando la cámara...", vista)
    ventana.lbl_instruccion.setObjectName("instruccion")
    ventana.lbl_instruccion.setAlignment(Qt.AlignCenter)
    ventana.lbl_instruccion.setWordWrap(True)

    # La flecha señala hacia dónde girar; el texto siempre dice lo mismo con palabras
    ventana.guia_calibracion = VistaCamara(vista, flecha=True)
    ventana.guia_calibracion.setAccessibleName("Hacia dónde girar la cabeza")

    ventana.barra_calibracion = QProgressBar(vista)
    ventana.barra_calibracion.setRange(0, 1000)
    ventana.barra_calibracion.setTextVisible(False)

    ayuda = QLabel("Esc: omitir la calibración y usar los valores por defecto", vista)
    ayuda.setAlignment(Qt.AlignCenter)

    layout.addWidget(titulo)
    layout.addWidget(ventana.lbl_instruccion)
    layout.addWidget(ventana.guia_calibracion, 1)
    layout.addWidget(ventana.barra_calibracion)
    layout.addWidget(ayuda)
    return vista
