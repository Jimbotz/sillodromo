"""
views/common.py - Piezas compartidas por varias pantallas: el constructor genérico de una rejilla
de bloques (crear_vista), los datos de Activadores (DISPOSITIVOS y compañía), los índices de cada
pantalla dentro de VentanaPrincipal.vistas, y la calibración de pantalla (los 16 puntos del borde).
"""

import os

from PyQt5.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from buttons.factory import clasificar_accion, llenar, volver
from buttons.icons import con_icono
from features import voice as voz
from tools import scale

# Géneros que se le pueden pedir a Alexa: cada botón dice "Alexa, pon música de <género>"
GENEROS = ["cumbia", "salsa", "reguetón", "rock", "banda", "corridos", "pop", "jazz"]
# Iconos (app/iconos, de Lucide): siempre acompañan al texto, nunca lo sustituyen
ICONOS_GENERO = {"cumbia": "drum", "salsa": "music-2", "reguetón": "disc-3", "rock": "guitar",
                 "banda": "music-3", "corridos": "music-4", "pop": "mic-vocal", "jazz": "piano"}
ICONOS_DISPOSITIVO = {"Focos": "lightbulb", "Televisiones": "tv", "Enchufes": "plug", "Música": "music",
                      "Comandos": "message-square-text"}


def unidades(nombre: str, acciones: list) -> list:
    """Una fila por unidad (1, 2, 3) con su nombre a la izquierda ("Foco 1") y sus acciones.
    acciones: (texto, frase con {n}, icono)."""
    return [(f"{nombre} {n}", [(texto, frase.format(n=n), icono) for texto, frase, icono in acciones]) for n in (1, 2, 3)]


# Dispositivos de Activadores: filas de (etiqueta de la fila o None, [(texto, frase dicha, icono), ...]).
# "Alexa" va delante de cada frase para activarla (ver voz.hablar). El volumen sube o baja un 10 %
# por pulsación. Las frases exactas dependen de cómo tenga Alexa configurado cada aparato: si alguna
# no la entiende, se cambia solo aquí.
DISPOSITIVOS = {
    "Focos": unidades("Foco", [("Encender", "Alexa, encender foco {n}", "lightbulb"),
                               ("Apagar", "Alexa, apagar foco {n}", "lightbulb-off")]),
    "Televisiones": unidades("Televisión", [
        ("Encender", "Alexa, encender televisión {n}", "power"),
        ("Apagar", "Alexa, apagar televisión {n}", "power-off"),
        ("YouTube", "Alexa, abre YouTube en la televisión {n}", "monitor-play"),
        ("Netflix", "Alexa, abre Netflix en la televisión {n}", "clapperboard"),
        ("Subir 10 %", "Alexa, sube el volumen de la televisión {n} un 10 por ciento", "volume-2"),
        ("Bajar 10 %", "Alexa, baja el volumen de la televisión {n} un 10 por ciento", "volume-1"),
    ]),
    "Enchufes": unidades("Enchufe", [("Encender", "Alexa, encender enchufe {n}", "plug-zap"),
                                     ("Apagar", "Alexa, apagar enchufe {n}", "unplug")]),
    "Música": [
        # En los Echo el volumen va de 0 a 10: cada "sube el volumen" es un 10 %
        (None, [("Poner música", "Alexa, pon música", "play"), ("Detener música", "Alexa, detén la música", "square"),
                ("Subir 10 %", "Alexa, sube el volumen", "volume-2"), ("Bajar 10 %", "Alexa, baja el volumen", "volume-1")]),
        (None, [(g.capitalize(), f"Alexa, pon música de {g}", ICONOS_GENERO[g]) for g in GENEROS[:4]]),
        (None, [(g.capitalize(), f"Alexa, pon música de {g}", ICONOS_GENERO[g]) for g in GENEROS[4:]]),
    ],
}
# Solo para desarrollo: SILLODROMO_VISTA_PREVIA=1 muestra la imagen de la cámara en Navegación.
# Sin ella, el hilo de la cámara ni siquiera dibuja la malla ni crea la imagen (ahorra CPU).
VISTA_PREVIA = os.environ.get("SILLODROMO_VISTA_PREVIA") == "1"

# Índices de VentanaPrincipal.vistas (ver window.py)
VISTA_NAVEGACION = 1  # la cabeza conduce: girar no selecciona nada y abrir la boca vuelve al menú
VISTA_EDITOR = 6  # editor de comandos: sin mirada ni cruceta
VISTAS_NORMALES = (0, 1, 2, 5)  # menú, navegación, activadores y confirmación (no las de calibración)

# Calibración de pantalla del puntero: 5 puntos arriba, 5 abajo y 3 en cada lado, lo más cerca
# del borde que se pueda sin que el blanco quede cortado
MARGEN_PUNTOS = 0.04
# Nombre de cada punto de calibración, en el mismo orden que puntos_calibracion(): se muestra y se
# dice en voz alta para quien no ve bien dónde está el blanco
NOMBRES_PUNTOS = [
    "arriba a la izquierda", "arriba, entre la izquierda y el centro", "arriba al centro",
    "arriba, entre el centro y la derecha", "arriba a la derecha",
    "a la derecha, arriba del centro", "a la derecha, al centro", "a la derecha, abajo del centro",
    "abajo a la derecha", "abajo, entre la derecha y el centro", "abajo al centro",
    "abajo, entre el centro y la izquierda", "abajo a la izquierda",
    "a la izquierda, abajo del centro", "a la izquierda, al centro", "a la izquierda, arriba del centro",
]


def puntos_calibracion() -> list:
    """16 puntos (x, y de 0 a 1) en el sentido del reloj desde la esquina superior izquierda."""
    m = MARGEN_PUNTOS
    xs = [m + (1 - 2 * m) * i / 4 for i in range(5)]
    ys = (0.25, 0.5, 0.75)
    return ([(x, m) for x in xs] + [(1 - m, y) for y in ys]
            + [(x, 1 - m) for x in reversed(xs)] + [(m, y) for y in reversed(ys)])


def bloques_visibles(contenedor: QWidget) -> list:
    return [b for b in contenedor.findChildren(QPushButton) if b.isVisible() and b.isEnabled()]


def primer_bloque(contenedor: QWidget) -> QPushButton:
    """Primer botón visible dentro del contenedor (orden de creación), o None si no hay."""
    return next((b for b in contenedor.findChildren(QPushButton) if b.isVisible()), None)


def boton_volver(ventana, parent) -> QPushButton:
    boton = con_icono(volver(QPushButton("Volver al menú", parent)), "arrow-left", scale.TAMANO_ICONO_VOLVER)
    boton.clicked.connect(lambda: ventana._ir_a(0))
    return boton


def crear_vista(titulo: str, filas: list, nota: str = "") -> QWidget:
    """Título y una rejilla de bloques con icono; cada bloque dice su frase al pulsarlo.
    filas: (etiqueta o None, [(texto, frase o función, icono[, accion]), ...]). nota: texto al pie."""
    vista = QWidget()
    layout = QVBoxLayout(vista)
    layout.setContentsMargins(0, scale.MARGEN_VISTA, 0, scale.MARGEN_VISTA)
    layout.setSpacing(scale.ESPACIADO)

    encabezado = QLabel(titulo, vista)
    encabezado.setObjectName("tituloVista")
    layout.addWidget(encabezado)

    rejilla = QGridLayout()
    rejilla.setSpacing(scale.ESPACIADO)
    con_etiquetas = int(any(etiqueta for etiqueta, _ in filas))  # la columna 0 es para "Televisión 1"...
    for f, (etiqueta, bloques) in enumerate(filas):
        if etiqueta:
            nombre_fila = QLabel(etiqueta, vista)
            nombre_fila.setObjectName("etiquetaFila")
            rejilla.addWidget(nombre_fila, f, 0)
        for c, bloque in enumerate(bloques):
            texto, frase, nombre_icono = bloque[:3]
            accion = (bloque[3] if len(bloque) > 3 else "") or clasificar_accion(texto)
            boton = con_icono(llenar(QPushButton(texto, vista)), nombre_icono, scale.TAMANO_ICONO)
            if accion:
                boton.setProperty("accion", accion)
            boton.setAccessibleName(f"{titulo}, {etiqueta}: {texto}" if etiqueta else f"{titulo}, {texto}")
            # frase: lo que dice la voz; o una función (p. ej. abrir una categoría de comandos)
            boton.clicked.connect(frase if callable(frase) else (lambda _, fr=frase: voz.hablar(fr)))
            rejilla.addWidget(boton, f, c + con_etiquetas)
            rejilla.setColumnStretch(c + con_etiquetas, 1)  # los bloques se reparten el ancho; la etiqueta no
    layout.addLayout(rejilla, 1)

    if nota:
        pie = QLabel(nota, vista)
        pie.setObjectName("ayudaCalibracion")
        pie.setWordWrap(True)
        layout.addWidget(pie)
    if not voz.DISPONIBLE:
        layout.addWidget(QLabel("Voz no disponible: instala pyttsx3", vista))
    return vista
