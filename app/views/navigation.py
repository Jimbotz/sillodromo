"""
views/navigation.py - Pantalla de Navegación: la cabeza conduce (girar mueve la flecha; abrir la
boca vuelve al menú). Ver window.py._gesto_cabeza para el resto de la lógica.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from views.common import boton_volver
from widgets.camera_preview import VistaCamara


def crear(ventana) -> QWidget:
    vista = QWidget()
    layout = QVBoxLayout(vista)
    layout.setContentsMargins(20, 20, 20, 20)

    fila = QHBoxLayout()
    fila.addWidget(boton_volver(ventana, vista))
    fila.addStretch(1)

    ventana.camara_navegacion = VistaCamara(vista, flecha=True)
    ventana.camara_navegacion.setAccessibleName("Cámara con la dirección de la cabeza")

    # La flecha nunca va sola: el texto repite la dirección
    ventana.lbl_direccion = QLabel("Dirección: buscando rostro...", vista)
    ventana.lbl_direccion.setObjectName("tituloVista")
    ventana.lbl_direccion.setAlignment(Qt.AlignCenter)
    ventana.lbl_direccion.setWordWrap(True)

    # Aquí girar la cabeza solo mueve la flecha: la única salida con la cara es abrir la boca
    salida = QLabel("Abre la boca para volver al menú", vista)
    salida.setObjectName("tituloTarjeta")
    salida.setAlignment(Qt.AlignCenter)

    layout.addLayout(fila)
    layout.addWidget(ventana.camara_navegacion, 1)
    layout.addWidget(ventana.lbl_direccion)
    layout.addWidget(salida)
    return vista
