"""
palette.py - Colores de Sillódromo y comprobación de contraste WCAG 2.1.
Tema en blancos y azules atenuados (menos brillo: el fondo refleja ~37 % menos luz que un blanco
casi puro), pensado para baja visión, fotofobia y daltonismo:
- Nada de blanco puro de fondo ni negro puro de texto: el fondo es un blanco azulado y el texto
  un azul casi negro. Menos deslumbramiento y menos halo con astigmatismo.
- Texto normal con contraste AAA (7:1 o más) sobre todos los fondos donde aparece.
- Bordes de los bloques con 3:1 o más frente al fondo (WCAG 1.4.11): se ve dónde empieza cada bloque.
- El bloque seleccionado cambia de claro a azul oscuro con texto blanco y borde grueso: se nota por
  luminosidad y por grosor, no solo por el tono, así que sirve igual con cualquier tipo de daltonismo.
styles.qss repite estos valores (QSS no puede importar Python): al cambiar uno, cambiar los dos.
Comprobar: python app/palette.py
"""

from typing import Tuple


class AccessibleColors:
    # Fondos
    BG_WINDOW = "#BFC9DA"  # fondo de la ventana: azul grisáceo claro
    BG_SURFACE = "#DDE4EF"  # barra de permanencia y centro del puntero
    BG_BLOCK = "#CFD8E6"  # bloque en reposo
    BG_HOVER = "#C3CEDF"  # bloque con el ratón encima
    BG_DISABLED = "#C8CFDB"  # bloque bloqueado (mientras termina una acción)
    BG_GUIDE = "#C9D2E1"  # círculo de la flecha y barra de progreso

    # Bordes
    BORDER_DEFAULT = "#4B5B7E"  # borde de bloques y guías
    BORDER_DISABLED = "#A3AEC2"

    # Texto (e iconos, que usan el mismo color que el texto de su bloque)
    TEXT_PRIMARY = "#111B31"
    TEXT_MUTED = "#2B3650"  # ayudas y notas al pie
    TEXT_DISABLED = "#56617B"  # exento de contraste (WCAG 1.4.3), pero legible
    TEXT_ERROR = "#6B0F0F"  # mensajes de error del editor (siempre con texto, nunca solo color)

    # Selección (cruceta o mirada): el "bloque iluminado"
    SELECTED = "#1D4C8F"  # relleno
    SELECTED_PRESSED = "#173F75"
    SELECTED_BORDER = "#0A2657"  # borde grueso; también contorno de la flecha y del puntero
    SELECTED_TEXT = "#FFFFFF"  # única excepción al "sin blanco puro": texto sobre azul oscuro

    # Semántico: bloques de "encender" (verde) y "apagar" (rojo). Es un apoyo extra, nunca el único
    # aviso: el texto ("Encender"/"Apagar") y el icono (power/power-off) ya lo dicen, así que sigue
    # sirviendo igual para daltonismo rojo-verde (deuteranopía/protanopía). Ver main.clasificar_accion.
    BG_ON = "#CFE3D3"
    BG_ON_HOVER = "#C3D9CC"
    ON = "#1B5E33"  # relleno cuando el bloque de encender está seleccionado
    ON_BORDER = "#0F3A1F"
    BG_OFF = "#E9CFCF"
    BG_OFF_HOVER = "#DDC5C8"
    OFF = "#7A1B1B"  # relleno cuando el bloque de apagar está seleccionado
    OFF_BORDER = "#4A0F0F"


# Pares que aparecen en la interfaz: (qué es, primer plano, fondo, contraste mínimo)
C = AccessibleColors
PARES = [
    ("texto sobre fondo", C.TEXT_PRIMARY, C.BG_WINDOW, 7),
    ("texto sobre bloque", C.TEXT_PRIMARY, C.BG_BLOCK, 7),
    ("texto sobre bloque con ratón", C.TEXT_PRIMARY, C.BG_HOVER, 7),
    ("texto en campos y listas del editor", C.TEXT_PRIMARY, C.BG_SURFACE, 7),
    ("borde de campo frente al fondo", C.BORDER_DEFAULT, C.BG_WINDOW, 3),
    ("mensaje de error sobre el fondo", C.TEXT_ERROR, C.BG_WINDOW, 7),
    ("icono sobre bloque", C.TEXT_PRIMARY, C.BG_BLOCK, 3),
    ("icono del bloque seleccionado", C.SELECTED_TEXT, C.SELECTED, 3),
    ("nota al pie sobre fondo", C.TEXT_MUTED, C.BG_WINDOW, 7),
    ("nota al pie sobre bloque", C.TEXT_MUTED, C.BG_BLOCK, 7),
    ("texto del bloque seleccionado", C.SELECTED_TEXT, C.SELECTED, 7),
    ("texto del bloque pulsado", C.SELECTED_TEXT, C.SELECTED_PRESSED, 7),
    ("barra de permanencia sobre el bloque seleccionado", C.BG_SURFACE, C.SELECTED, 3),
    ("aviso: texto sobre su recuadro", C.SELECTED_TEXT, C.SELECTED_BORDER, 7),
    ("borde de bloque frente al fondo", C.BORDER_DEFAULT, C.BG_WINDOW, 3),
    ("borde de bloque frente a su relleno", C.BORDER_DEFAULT, C.BG_BLOCK, 3),
    ("bloque seleccionado frente al fondo", C.SELECTED, C.BG_WINDOW, 3),
    ("bloque seleccionado frente a sus vecinos", C.SELECTED, C.BG_BLOCK, 3),
    ("flecha y blanco de calibración sobre su círculo", C.SELECTED, C.BG_GUIDE, 3),
    ("contorno del puntero sobre el fondo", C.SELECTED_BORDER, C.BG_WINDOW, 3),
    ("contorno claro del puntero sobre el bloque seleccionado", C.BG_SURFACE, C.SELECTED, 3),
    ("progreso de calibración sobre su barra", C.SELECTED, C.BG_GUIDE, 3),
    ("texto sobre bloque de encender", C.TEXT_PRIMARY, C.BG_ON, 7),
    ("texto sobre bloque de encender con ratón", C.TEXT_PRIMARY, C.BG_ON_HOVER, 7),
    ("texto del bloque de encender seleccionado", C.SELECTED_TEXT, C.ON, 7),
    ("bloque de encender seleccionado frente al fondo", C.ON, C.BG_WINDOW, 3),
    ("texto sobre bloque de apagar", C.TEXT_PRIMARY, C.BG_OFF, 7),
    ("texto sobre bloque de apagar con ratón", C.TEXT_PRIMARY, C.BG_OFF_HOVER, 7),
    ("texto del bloque de apagar seleccionado", C.SELECTED_TEXT, C.OFF, 7),
    ("bloque de apagar seleccionado frente al fondo", C.OFF, C.BG_WINDOW, 3),
]


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convierte un color hexadecimal '#RRGGBB' a tupla (R, G, B)."""
    hex_color = hex_color.lstrip("#")
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)


def calculate_relative_luminance(hex_color: str) -> float:
    """
    Calcula la luminancia relativa según la fórmula estándar de WCAG 2.1.
    """
    r, g, b = [c / 255.0 for c in hex_to_rgb(hex_color)]
    r_lum = r / 12.92 if r <= 0.04045 else ((r + 0.055) / 1.055) ** 2.4
    g_lum = g / 12.92 if g <= 0.04045 else ((g + 0.055) / 1.055) ** 2.4
    b_lum = b / 12.92 if b <= 0.04045 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r_lum + 0.7152 * g_lum + 0.0722 * b_lum


def calculate_contrast_ratio(color_a: str, color_b: str) -> float:
    """
    Calcula el ratio de contraste entre dos colores (ej. (L1 + 0.05) / (L2 + 0.05)).
    Rango resultante: 1.0 a 21.0.
    """
    lum_a = calculate_relative_luminance(color_a)
    lum_b = calculate_relative_luminance(color_b)
    l1 = max(lum_a, lum_b)
    l2 = min(lum_a, lum_b)
    return (l1 + 0.05) / (l2 + 0.05)


def check_wcag_compliance(fg: str, bg: str, is_large_text: bool = False) -> dict:
    """
    Verifica si un par de colores cumple con WCAG 2.1 nivel AA y AAA.
    """
    ratio = calculate_contrast_ratio(fg, bg)
    min_aa = 3.0 if is_large_text else 4.5
    min_aaa = 4.5 if is_large_text else 7.0

    return {
        "ratio": round(ratio, 2),
        "aa_compliant": ratio >= min_aa,
        "aaa_compliant": ratio >= min_aaa,
        "required_aa": min_aa,
        "required_aaa": min_aaa,
    }


if __name__ == "__main__":
    fallos = []
    for nombre, frente, fondo, minimo in PARES:
        ratio = calculate_contrast_ratio(frente, fondo)
        print(f"{'OK ' if ratio >= minimo else 'NO '} {ratio:5.2f}:1 (mínimo {minimo}:1)  {nombre}")
        if ratio < minimo:
            fallos.append(nombre)
    assert not fallos, f"Contraste insuficiente: {fallos}"
    print("palette: OK")
