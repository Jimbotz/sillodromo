"""
icono.py - Iconos SVG de app/iconos (Lucide, licencia ISC en iconos/LICENSE) para los bloques.
Se colorean según el estado del bloque y siempre acompañan al texto, nunca lo sustituyen.
"""

import os
from functools import lru_cache

from PyQt5.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QAbstractButton

from palette import AccessibleColors as C

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iconos")
TAMANO, TAMANO_VOLVER = 44, 30
ESPACIO = 0.35  # aire a la derecha del icono (fracción de su tamaño): Qt solo deja 4 px hasta el texto
POR_DEFECTO = "message-square-text"  # para comandos o categorías sin icono (o con uno que ya no existe)


def catalogo() -> list:
    """Nombres de los iconos disponibles, para elegir al crear comandos y categorías."""
    return sorted(n[:-4] for n in os.listdir(CARPETA) if n.endswith(".svg"))


@lru_cache(maxsize=None)
def icono(nombre: str, aire: bool = True) -> QIcon:
    """Icono coloreado para cada estado del botón: el color del texto en reposo, blanco cuando está
    seleccionado (Qt usa el modo Active con el foco) y gris si está bloqueado. aire=False lo deja
    cuadrado (p. ej. en el selector de iconos). Si falta el archivo, devuelve un icono vacío."""
    try:
        with open(os.path.join(CARPETA, f"{nombre}.svg"), encoding="utf-8") as f:
            svg = f.read()
    except OSError:
        print(f"Falta el icono {nombre}.svg", flush=True)
        return QIcon()
    resultado = QIcon()
    # Selected: el elemento elegido de una lista (fondo azul oscuro, como el bloque seleccionado)
    for modo, color in ((QIcon.Normal, C.TEXT_PRIMARY), (QIcon.Active, C.SELECTED_TEXT),
                        (QIcon.Selected, C.SELECTED_TEXT), (QIcon.Disabled, C.TEXT_DISABLED)):
        dibujo = QSvgRenderer(QByteArray(svg.replace("currentColor", color).encode("utf-8")))
        lado = TAMANO * 2  # doble resolución: nítido en pantallas HiDPI
        imagen = QPixmap(int(lado * (1 + ESPACIO)) if aire else lado, lado)
        imagen.fill(Qt.transparent)
        pintor = QPainter(imagen)
        dibujo.render(pintor, QRectF(0, 0, lado, lado))  # a la izquierda; el resto es el aire hasta el texto
        pintor.end()
        resultado.addPixmap(imagen, modo)
    return resultado


def con_icono(boton: QAbstractButton, nombre: str, tamano: int = TAMANO) -> QAbstractButton:
    boton.setIcon(icono(nombre))
    boton.setIconSize(QSize(int(tamano * (1 + ESPACIO)), tamano))
    return boton
