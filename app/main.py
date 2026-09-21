"""
main.py - Sillódromo: aplicación de escritorio PyQt5 con tres vistas (módulos).
Funciona en Windows, macOS y Linux (nativo o en Docker vía X11).
"""

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

MODULOS = ["Módulo 1: Silla", "Módulo 2: Alexa 1", "Módulo 3: Secadora 3"]


def crear_vista(titulo: str) -> QWidget:
    vista = QWidget()
    layout = QVBoxLayout(vista)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)

    encabezado = QLabel(titulo, vista)
    encabezado.setObjectName("tituloVista")
    layout.addWidget(encabezado)

    for n in range(1, 4):
        boton = QPushButton(f"Opción {n}", vista)
        # Nombre único para lectores de pantalla: "Opción 1" se repite en cada vista
        boton.setAccessibleName(f"{titulo}, Opción {n}")
        layout.addWidget(boton)

    layout.addStretch(1)
    return vista


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sillódromo")
        self.resize(800, 500)

        pestanas = QTabWidget(self)
        for titulo in MODULOS:
            pestanas.addTab(crear_vista(titulo), titulo)
        self.setCentralWidget(pestanas)


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
