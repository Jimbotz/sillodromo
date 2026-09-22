"""
tools/geometry.py - Geometría de widgets en coordenadas de pantalla: usada por window.py para
mover la selección con la cruceta (vecino más cercano) y para saber qué bloque queda bajo la mirada.
"""

import math

from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtWidgets import QWidget


def caja(w: QWidget) -> QRect:
    """Rectángulo del widget en coordenadas de pantalla."""
    return QRect(w.mapToGlobal(QPoint(0, 0)), w.size())


def distancia(punto: QPoint, rect: QRect) -> float:
    """Distancia en píxeles de un punto a un rectángulo (0 si está dentro)."""
    dx = max(rect.left() - punto.x(), 0, punto.x() - rect.right())
    dy = max(rect.top() - punto.y(), 0, punto.y() - rect.bottom())
    return math.hypot(dx, dy)
