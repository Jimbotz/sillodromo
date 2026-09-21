"""
palette.py - Sistema de Diseño y Accesibilidad WCAG 2.1 AA/AAA
Paleta universal segura para daltonismo (Deuteranopía, Protanopía, Tritanopía)
y optimizada para baja visión y fotofobia.
"""

from typing import Tuple


class AccessibleColors:
    """
    Paleta de colores con ratios de contraste validados según WCAG 2.1.
    Evita negros puros (#000000) y blancos puros (#FFFFFF) para reducir la fatiga
    visual y los halos provocados por el astigmatismo.
    """
    # Fondos y superficies (Modo oscuro suave / Carbón)
    BG_WINDOW = "#1E1E24"          # Fondo principal de la ventana
    BG_SURFACE = "#2B2D42"         # Superficie de tarjetas, paneles y contenedores
    BG_INPUT = "#363953"           # Fondo de inputs, comboboxes y campos de texto
    BG_HOVER = "#434766"           # Estado hover de elementos interactivos
    BG_TABLE_ALT = "#242638"       # Filas alternas de tablas para seguimiento ocular

    # Bordes y separadores
    BORDER_DEFAULT = "#595F85"     # Borde visible de controles (mínimo 1.5px - 2px)
    BORDER_FOCUS = "#E69F00"       # Borde de foco por teclado de alto contraste (3px)

    # Tipografía
    TEXT_PRIMARY = "#F4F4F6"       # Marfil suave (Contraste > 14:1 contra BG_WINDOW)
    TEXT_SECONDARY = "#D8D8E0"     # Gris claro para descripciones (Contraste > 10:1)
    TEXT_MUTED = "#B8B9C8"         # Texto atenuado accesible (Contraste > 7:1)
    TEXT_DISABLED = "#8E92AA"      # Texto deshabilitado

    # Acciones principales (Paleta Okabe-Ito)
    PRIMARY_BUTTON = "#0072B2"     # Azul cobalto accesible
    PRIMARY_BUTTON_HOVER = "#005A9C"
    PRIMARY_BUTTON_TEXT = "#FFFFFF"

    SECONDARY_BUTTON = "#3E425E"
    SECONDARY_BUTTON_HOVER = "#4D5275"
    SECONDARY_BUTTON_TEXT = "#F4F4F6"

    # Estados informativos y notificaciones (SIEMPRE combinan Icono + Texto + Color)
    # Éxito (Verde azulado seguro para daltonismo)
    SUCCESS_BG = "#103B32"
    SUCCESS_BORDER = "#009E73"
    SUCCESS_TEXT = "#A3F7DF"
    SUCCESS_BADGE = "[✓] ÉXITO"

    # Advertencia (Ámbar / Naranja accesible)
    WARNING_BG = "#4A3305"
    WARNING_BORDER = "#E69F00"
    WARNING_TEXT = "#FFE2A8"
    WARNING_BADGE = "[!] ADVERTENCIA"

    # Error (Bermellón / Rojo de alto contraste)
    ERROR_BG = "#471A1A"
    ERROR_BORDER = "#D55E00"
    ERROR_TEXT = "#FFD1D1"
    ERROR_BADGE = "[✖] ERROR"

    # Información (Azul cielo accesible)
    INFO_BG = "#11324D"
    INFO_BORDER = "#56B4E9"
    INFO_TEXT = "#CBEBFC"
    INFO_BADGE = "[ℹ] INFORMACIÓN"


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
