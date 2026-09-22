"""
views/menu.py - Pantalla de inicio: ir a Navegación o Activadores, y "Volver a calibrar".
"""

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from buttons.factory import llenar, volver
from buttons.icons import con_icono
from tools import scale


def crear(ventana) -> QWidget:
    menu = QWidget()
    layout = QVBoxLayout(menu)
    layout.setContentsMargins(40, 40, 40, 40)
    layout.setSpacing(16)

    titulo = QLabel("Menú", menu)
    titulo.setObjectName("tituloVista")
    layout.addWidget(titulo)
    for indice, nombre, nombre_icono in ((1, "Navegación", "navigation"), (2, "Activadores", "zap")):
        # bloques grandes: blancos fáciles para la mirada
        boton = con_icono(llenar(QPushButton(nombre, menu)), nombre_icono)
        boton.setObjectName("primaryBtn")
        boton.setAccessibleName(f"Ir a la vista {nombre}")
        boton.clicked.connect(lambda _, i=indice: ventana._ir_a(i))
        layout.addWidget(boton, 1)
    # La calibración se guarda: si se mueve la silla o la pantalla, hay que poder repetirla
    ventana.boton_recalibrar = con_icono(volver(QPushButton("Volver a calibrar", menu)), "crosshair",
                                         scale.TAMANO_ICONO_VOLVER)
    ventana.boton_recalibrar.setAccessibleName("Borrar la calibración guardada y calibrar de nuevo")
    # Borra la calibración: pide confirmación (con la mirada se podría activar sin querer)
    ventana.boton_recalibrar.clicked.connect(lambda: ventana._ir_a(5))
    ventana.boton_recalibrar.setVisible(ventana.HiloCamara is not None)  # sin cámara no se puede calibrar
    fila = QHBoxLayout()
    fila.addStretch(1)
    fila.addWidget(ventana.boton_recalibrar)
    layout.addLayout(fila)
    return menu
