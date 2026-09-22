"""
tools/scale.py - Escala de pantalla: styles.qss, los iconos y el espaciado de la rejilla están
pensados para una pantalla de ANCHO_DISENO x ALTO_DISENO. En una más chica (o con más escala de
Windows, que reduce la resolución lógica) todo se achica en la misma proporción para que ningún
texto ni columna se corte; en una más grande, crece igual de proporcionado.
establecer_escala() la fija en main(), antes de armar la ventana. El resto del código lee
TAMANO_ICONO/TAMANO_ICONO_VOLVER/ESPACIADO/MARGEN_VISTA como atributos de este módulo (nunca los
importa por valor), para ver siempre la versión ya escalada.
"""

import re

ANCHO_DISENO, ALTO_DISENO = 1920, 1080
ESCALA = 1.0
TAMANO_ICONO, TAMANO_ICONO_VOLVER = 44, 30  # valores para ESCALA = 1.0 (ver buttons.icons)
ESPACIADO, MARGEN_VISTA = 14, 16


def establecer_escala(factor: float):
    global ESCALA, TAMANO_ICONO, TAMANO_ICONO_VOLVER, ESPACIADO, MARGEN_VISTA
    ESCALA = max(0.55, min(1.3, factor))  # ni tan chico que no se lea, ni tan grande que rompa la rejilla
    TAMANO_ICONO, TAMANO_ICONO_VOLVER = round(44 * ESCALA), round(30 * ESCALA)
    ESPACIADO, MARGEN_VISTA = round(14 * ESCALA), round(16 * ESCALA)


def escalar_qss(texto: str, factor: float) -> str:
    """Multiplica cada valor en píxeles de la hoja de estilos por factor, sin llegar a 0."""
    return re.sub(r"(\d+)px", lambda m: f"{max(1, round(int(m.group(1)) * factor))}px", texto)


if __name__ == "__main__":
    assert escalar_qss("a { font-size: 10px; }", 0.5) == "a { font-size: 5px; }"
    assert escalar_qss("border: 2px solid", 3) == "border: 6px solid"
    assert escalar_qss("x: 1px", 0.01) == "x: 1px"  # nunca desaparece del todo

    establecer_escala(1280 / ANCHO_DISENO)
    assert ESCALA == 1280 / 1920 and TAMANO_ICONO == round(44 * ESCALA)
    establecer_escala(0.1)
    assert ESCALA == 0.55  # no baja del piso
    establecer_escala(5)
    assert ESCALA == 1.3  # no pasa del techo
    print("scale: OK")
