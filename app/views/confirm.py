"""
views/confirm.py - "¿Borrar la calibración guardada y calibrar de nuevo?", con "No" seleccionado
de partida (con la mirada se podría activar sin querer).
"""

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from buttons.factory import llenar
from buttons.icons import con_icono


def crear(ventana) -> QWidget:
    vista = QWidget()
    layout = QVBoxLayout(vista)
    layout.setContentsMargins(40, 40, 40, 40)
    layout.setSpacing(16)
    pregunta = QLabel("¿Borrar la calibración guardada y calibrar de nuevo?\n"
                      "Hazlo si se movió la silla, la cámara o la pantalla.", vista)
    pregunta.setObjectName("tituloVista")
    pregunta.setWordWrap(True)
    layout.addWidget(pregunta)
    fila = QHBoxLayout()
    fila.setSpacing(16)
    # "No" va primero: _ir_a selecciona el primer bloque, así la opción segura es la de partida
    no = con_icono(llenar(QPushButton("No, volver al menú", vista)), "x")
    no.clicked.connect(lambda: ventana._ir_a(0))
    si = con_icono(llenar(QPushButton("Sí, calibrar de nuevo", vista)), "rotate-ccw")
    si.clicked.connect(ventana._recalibrar)
    fila.addWidget(no)
    fila.addWidget(si)
    layout.addLayout(fila, 1)
    return vista
