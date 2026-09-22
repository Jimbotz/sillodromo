"""
main.py - Punto de entrada de Sillódromo: arma la QApplication, calcula la escala de pantalla,
carga la hoja de estilos ya escalada y levanta la ventana (ver window.VentanaPrincipal).
Funciona en Windows, macOS y Linux (nativo o en Docker vía X11).
"""

import os
import sys
import traceback

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from tools import scale
from window import VentanaPrincipal


def _informar_error(tipo, valor, rastro):
    """Red de seguridad: sin esto, PyQt5 cierra toda la app ante cualquier error dentro de una señal de
    Qt. Para quien depende de la app para moverse, es peor quedarse sin ella que un fallo puntual:
    el error se escribe en la terminal (para arreglarlo) y la app sigue."""
    traceback.print_exception(tipo, valor, rastro)


def main():
    sys.excepthook = _informar_error
    # Atributos High-DPI: deben fijarse antes de crear QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Sillódromo")

    pantalla = app.primaryScreen().availableGeometry()
    scale.establecer_escala(min(pantalla.width() / scale.ANCHO_DISENO, pantalla.height() / scale.ALTO_DISENO))

    qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles.qss")
    with open(qss_path, encoding="utf-8") as f:
        app.setStyleSheet(scale.escalar_qss(f.read(), scale.ESCALA))

    ventana = VentanaPrincipal()
    ventana.showFullScreen()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
