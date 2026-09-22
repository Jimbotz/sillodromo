"""
buttons/factory.py - Cómo se arma y colorea un bloque (QPushButton): que crezca para repartirse la
pantalla, que un botón de "volver" sea grande y vaya en una esquina, y de qué color según su acción.

Colores de "encender"/"apagar" (ver styles.qss y tools.palette.AccessibleColors): un apoyo extra
además del texto y el icono, nunca el único aviso, así que sigue sirviendo igual para daltonismo
rojo-verde. Solo la primera palabra del bloque cuenta, para no colorear "Subir volumen" a medias.
"""

from PyQt5.QtWidgets import QPushButton, QSizePolicy

_PALABRAS_ON = {"encender", "prender", "activar", "poner"}
_PALABRAS_OFF = {"apagar", "detener", "desactivar"}


def llenar(boton: QPushButton) -> QPushButton:
    """El botón crece para repartirse la pantalla con los demás."""
    boton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return boton


def volver(boton: QPushButton) -> QPushButton:
    """Los botones de volver van en una esquina, pero grandes: la mirada no apunta al píxel.
    El tamaño va en styles.qss (#volverBtn): el min-height de la hoja de estilos manda sobre setMinimumSize."""
    boton.setObjectName("volverBtn")
    return boton


def clasificar_accion(texto: str) -> str:
    """"on" (verde), "off" (rojo) o "" (sin color) según la primera palabra del texto del bloque."""
    primera = texto.strip().split()[0].casefold() if texto.strip() else ""
    if primera in _PALABRAS_ON:
        return "on"
    if primera in _PALABRAS_OFF:
        return "off"
    return ""


if __name__ == "__main__":
    assert clasificar_accion("Encender foco 1") == "on"
    assert clasificar_accion("Apagar") == "off"
    assert clasificar_accion("Poner música") == "on"
    assert clasificar_accion("Detener música") == "off"
    assert clasificar_accion("Subir 10 %") == clasificar_accion("YouTube") == clasificar_accion("") == ""
    print("factory: OK")
