"""
main.py - Sillódromo: aplicación de escritorio PyQt5 a pantalla completa.
Menú con dos vistas: Navegación (flecha según la dirección de la cabeza, detectada con la
cámara y MediaPipe) y Activadores, por fases: primero se elige el dispositivo y después la acción.
La imagen de la cámara no se muestra al usuario final; ver VISTA_PREVIA.
Todo se maneja como bloques con la cruceta de la cabeza (camara.Cruceta): girar mueve la
selección al bloque vecino, que se ilumina, y abrir la boca lo pulsa. Las flechas del teclado
hacen lo mismo que girar la cabeza. Al arrancar con cámara se calibra primero (luz, reposo, rangos
de giro y apertura de la boca; ver camara.Calibracion); Esc la omite.
Después se calibra la pantalla (16 puntos en el borde) y los ojos + la cabeza mueven un puntero:
mirar un bloque lo selecciona y quedarse en él lo activa (camara.Permanencia).
Funciona en Windows, macOS y Linux (nativo o en Docker vía X11).
"""

import math
import os
import sys
import time
from collections import deque

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import comandos
import voz
from editor import EditorComandos
from icono import TAMANO as TAMANO_ICONO, TAMANO_VOLVER as TAMANO_ICONO_VOLVER, con_icono, icono
from palette import AccessibleColors as C

try:
    from camara import (Calibracion, FiltroUnEuro, HiloCamara, ModeloMirada, Permanencia, borrar_calibracion,
                        cargar_calibracion, dispersion, guardar_calibracion)
    ERROR_CAMARA = None
except ImportError as e:  # p. ej. Mac Intel: MediaPipe no publica paquete para esa plataforma
    HiloCamara = None
    ERROR_CAMARA = f"MediaPipe no está disponible ({e.name})"

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
# Ángulo de la flecha de navegación (0 = hacia arriba, sentido horario)
ANGULOS = {"arriba": 0, "derecha": 90, "abajo": 180, "izquierda": 270}
# Dirección de cada gesto de la cruceta en pantalla (x hacia la derecha, y hacia abajo)
VECTORES = {"izquierda": (-1, 0), "derecha": (1, 0), "arriba": (0, -1), "abajo": (0, 1)}


# Calibración de pantalla del puntero: 5 puntos arriba, 5 abajo y 3 en cada lado, lo más cerca
# del borde que se pueda sin que el blanco quede cortado
MARGEN_PUNTOS = 0.04
ASENTAR, MUESTREO = 0.8, 1.2  # por punto: tiempo para llevar la mirada y tiempo midiendo
# Tras activar algo, la pantalla suele cambiar y bajo la mirada queda otro bloque: nada cuenta
# hasta que la mirada se mueva esta distancia (fracción de la pantalla). Evita activar en cadena.
REARME = 0.08
ERROR_MAXIMO = 0.15  # si la calibración de pantalla falla por más que esto, se usa la cruceta
# La barra solo carga con la mirada quieta: si en la última VENTANA_FIJACION (s) el puntero se movió
# más que DISPERSION_MAXIMA (fracción de pantalla), la mirada se está desviando y la carga se pausa
VENTANA_FIJACION = 0.3
DISPERSION_MAXIMA = 0.05
VISTA_EDITOR = 6  # editor de comandos: sin mirada ni cruceta
VISTAS_NORMALES = (0, 1, 2, 5)  # menú, navegación, activadores y confirmación (no las de calibración)
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


def caja(w: QWidget) -> QRect:
    """Rectángulo del widget en coordenadas de pantalla."""
    return QRect(w.mapToGlobal(QPoint(0, 0)), w.size())


def distancia(punto: QPoint, rect: QRect) -> float:
    """Distancia en píxeles de un punto a un rectángulo (0 si está dentro)."""
    dx = max(rect.left() - punto.x(), 0, punto.x() - rect.right())
    dy = max(rect.top() - punto.y(), 0, punto.y() - rect.bottom())
    return math.hypot(dx, dy)


def bloques_visibles(contenedor: QWidget) -> list:
    return [b for b in contenedor.findChildren(QPushButton) if b.isVisible() and b.isEnabled()]


def primer_bloque(contenedor: QWidget) -> QPushButton:
    """Primer botón visible dentro del contenedor (orden de creación), o None si no hay."""
    return next((b for b in contenedor.findChildren(QPushButton) if b.isVisible()), None)


def _llenar(boton: QPushButton) -> QPushButton:
    """El botón crece para repartirse la pantalla con los demás."""
    boton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return boton


def _volver(boton: QPushButton) -> QPushButton:
    """Los botones de volver van en una esquina, pero grandes: la mirada no apunta al píxel.
    El tamaño va en styles.qss (#volverBtn): el min-height de la hoja de estilos manda sobre setMinimumSize."""
    boton.setObjectName("volverBtn")
    return boton


def crear_vista(titulo: str, filas: list, nota: str = "") -> QWidget:
    """Título y una rejilla de bloques con icono; cada bloque dice su frase al pulsarlo.
    filas: (etiqueta o None, [(texto, frase o función, icono), ...]). nota: texto pequeño al pie."""
    vista = QWidget()
    layout = QVBoxLayout(vista)
    layout.setContentsMargins(0, 16, 0, 16)
    layout.setSpacing(14)

    encabezado = QLabel(titulo, vista)
    encabezado.setObjectName("tituloVista")
    layout.addWidget(encabezado)

    rejilla = QGridLayout()
    rejilla.setSpacing(14)
    con_etiquetas = int(any(etiqueta for etiqueta, _ in filas))  # la columna 0 es para "Televisión 1"...
    for f, (etiqueta, bloques) in enumerate(filas):
        if etiqueta:
            nombre_fila = QLabel(etiqueta, vista)
            nombre_fila.setObjectName("etiquetaFila")
            rejilla.addWidget(nombre_fila, f, 0)
        for c, (texto, frase, nombre_icono) in enumerate(bloques):
            boton = con_icono(_llenar(QPushButton(texto, vista)), nombre_icono)
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


class VistaCamara(QWidget):
    """Dibuja la imagen de la cámara recortada en un círculo."""

    def __init__(self, parent=None, flecha=False):
        super().__init__(parent)
        self.imagen = None
        self.flecha = flecha  # dibuja encima la dirección de la cabeza
        self.direccion = ""
        self.setMinimumSize(220, 220)
        self.setAccessibleName("Vista de la cámara con detección de rostro")

    def set_imagen(self, imagen: QImage, direccion: str = ""):
        self.imagen = imagen
        self.direccion = direccion
        self.update()

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        lado = min(self.width(), self.height()) - 8
        circulo = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        ruta = QPainterPath()
        ruta.addEllipse(circulo)
        p.fillPath(ruta, QColor(C.BG_GUIDE))

        if self.imagen is not None:
            # Escalado tipo "cover": llena el círculo y recorta el sobrante centrado
            esc = self.imagen.scaled(int(lado), int(lado), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.setClipPath(ruta)
            p.drawImage(QPointF(circulo.center().x() - esc.width() / 2, circulo.center().y() - esc.height() / 2), esc)
            p.setClipping(False)

        p.setPen(QPen(QColor(C.BORDER_DEFAULT), 3))
        p.drawEllipse(circulo)

        if self.flecha and self.direccion:
            # Azul con borde oscuro: 6,9:1 sobre el círculo; se distingue también sobre la imagen
            p.setPen(QPen(QColor(C.SELECTED_BORDER), 4))
            p.setBrush(QColor(C.SELECTED))
            p.translate(circulo.center())
            t = lado * 0.18
            if self.direccion == "centro":
                p.drawEllipse(QPointF(0, 0), t * 0.4, t * 0.4)
            else:
                p.rotate(ANGULOS[self.direccion])
                p.drawPolygon(QPolygonF([
                    QPointF(0, -t * 1.6), QPointF(t, -t * 0.4), QPointF(t * 0.4, -t * 0.4),
                    QPointF(t * 0.4, t * 1.2), QPointF(-t * 0.4, t * 1.2), QPointF(-t * 0.4, -t * 0.4),
                    QPointF(-t, -t * 0.4),
                ]))


class VistaPuntos(QWidget):
    """Calibración de pantalla: un blanco por punto; su anillo se cierra mientras se mide."""

    def __init__(self):
        super().__init__()
        self.punto, self.progreso = (0.5, 0.5), 0.0
        self.texto = QLabel(self)
        self.texto.setObjectName("instruccion")
        self.texto.setAlignment(Qt.AlignCenter)
        self.texto.setWordWrap(True)
        # Ayuda para quien acompaña; no se lee en voz alta
        ayuda = QLabel("Esc: omitir la calibración", self)
        ayuda.setAlignment(Qt.AlignCenter)
        ayuda.setObjectName("ayudaCalibracion")
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.texto)
        layout.addStretch(1)
        layout.addWidget(ayuda)
        self.setAccessibleName("Calibración de la mirada")

    def mostrar(self, punto, progreso: float, texto: str = None):
        self.punto, self.progreso = punto, progreso
        if texto is not None:
            self.texto.setText(texto)
        self.update()

    def paintEvent(self, _evento):
        if self.punto is None:
            return  # solo texto (p. ej. el resultado)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        centro = QPointF(self.punto[0] * self.width(), self.punto[1] * self.height())
        r = min(self.width(), self.height()) * 0.03
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(C.BORDER_DEFAULT), 4))
        p.drawEllipse(centro, r, r)
        p.setPen(QPen(QColor(C.SELECTED), 6))
        p.drawArc(QRectF(centro.x() - r, centro.y() - r, 2 * r, 2 * r), 90 * 16, -int(360 * 16 * self.progreso))
        p.setPen(QPen(QColor(C.SELECTED_BORDER), 2))
        p.setBrush(QColor(C.SELECTED))
        p.drawEllipse(centro, r * 0.35, r * 0.35)


class CapaMirada(QWidget):
    """Capa transparente encima de todo: el punto de la mirada y, en el bloque seleccionado, una
    barra que se llena hasta activarlo. No recibe clics."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.punto, self.caja, self.progreso = None, None, 0.0
        self.aviso = ""  # texto arriba al centro, p. ej. mientras una acción está en curso

    def mostrar(self, punto, caja_local, progreso: float):
        self.punto, self.caja, self.progreso = punto, caja_local, progreso
        self.update()

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.caja is not None and self.progreso > 0:
            # Clara sobre el azul del bloque seleccionado: contraste 6,6:1
            barra = QRectF(self.caja.left() + 8, self.caja.bottom() - 20, (self.caja.width() - 16) * self.progreso, 12)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C.BG_SURFACE))
            p.drawRoundedRect(barra, 4, 4)
        if self.aviso:
            fuente = p.font()
            fuente.setPixelSize(26)
            fuente.setBold(True)
            p.setFont(fuente)
            caja_texto = p.fontMetrics().boundingRect(self.aviso).adjusted(-24, -14, 24, 14)
            caja_texto.moveCenter(QPoint(self.width() // 2, 60))
            p.setPen(QPen(QColor(C.BG_SURFACE), 3))
            p.setBrush(QColor(C.SELECTED_BORDER))
            p.drawRoundedRect(QRectF(caja_texto), 8, 8)
            p.setPen(QColor(C.SELECTED_TEXT))
            p.drawText(caja_texto, Qt.AlignCenter, self.aviso)
        if self.punto is not None:
            centro = QPointF(*self.punto)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(C.SELECTED_BORDER), 7))  # contorno oscuro: se ve sobre el fondo claro
            p.drawEllipse(centro, 16, 16)
            p.setPen(QPen(QColor(C.BG_SURFACE), 3))
            p.drawEllipse(centro, 16, 16)


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sillódromo")
        self.resize(1100, 700)
        self.setMinimumSize(900, 560)

        # Vistas generales: 0 menú, 1 navegación, 2 activadores, 3 calibración, 4 calibración de pantalla,
        # 5 confirmar "Volver a calibrar"
        self.vistas = QStackedWidget(self)
        self.vistas.addWidget(self._crear_menu())
        self.vistas.addWidget(self._crear_navegacion())
        self.vistas.addWidget(self._crear_activadores())
        self.vistas.addWidget(self._crear_calibracion())
        self.vista_puntos = VistaPuntos()
        self.vistas.addWidget(self.vista_puntos)
        self.vistas.addWidget(self._crear_confirmar_recalibrar())
        self.editor = EditorComandos()  # 6: para quien acompaña, con teclado y ratón
        self.editor.cambiado.connect(self._reconstruir_comandos)
        self.editor.cerrar.connect(self._cerrar_editor)
        self.vistas.addWidget(self.editor)
        self.vistas.currentChanged.connect(self._al_cambiar_vista)
        self.setCentralWidget(self.vistas)
        self.capa = CapaMirada(self)  # encima de todo; se ajusta en resizeEvent

        # Puntero de la mirada: activo cuando termina la calibración de pantalla
        self.modelo_mirada, self.mirada, self.omitir = None, None, False
        self.ancla = None  # dónde estaba la mirada al activar el último bloque (ver REARME)
        self.permanencia = Permanencia() if HiloCamara is not None else None
        self.t_rasgos = time.monotonic()
        self.recorrido = deque()  # (t, x, y) recientes del puntero, para saber si la mirada está quieta
        self.filtro = FiltroUnEuro() if HiloCamara is not None else None
        self.paso_dicho = None  # último paso de la calibración leído en voz alta
        self.calibrar_cara = True  # False si el perfil de la cara ya estaba guardado

        # Mientras una acción está en curso (hoy: una frase de voz), no se puede usar otra
        self.foco_previo = None
        self.vigia = QTimer(self)
        self.vigia.timeout.connect(self._vigilar_accion)
        self.vigia.start(100)

        self.hilo = None
        if HiloCamara is None:
            self._error_camara(ERROR_CAMARA)
        else:
            # Calibración guardada (app/datos/calibracion.json): lo que ya existe no se vuelve a pedir
            perfil_guardado, self.modelo_mirada = cargar_calibracion()
            self.calibrar_cara = perfil_guardado is None
            self.hilo = HiloCamara(self, con_imagen=VISTA_PREVIA, perfil_guardado=perfil_guardado)
            self.hilo.fotograma.connect(self._nuevo_fotograma)
            self.hilo.error.connect(self._error_camara)
            self.hilo.gesto.connect(self._gesto_cabeza)
            self.hilo.calibrando.connect(self._calibrando)
            self.hilo.calibrado.connect(self._calibrado)
            self.hilo.rasgos.connect(self._rasgos)
            self.hilo.pausa = voz.ocupada  # la calibración espera a que se termine de leer cada paso
            if self.calibrar_cara:
                self.vistas.setCurrentIndex(3)  # sin perfil guardado: arranca calibrando la cara
            elif self.modelo_mirada is None:
                QTimer.singleShot(0, self._tras_calibrar)  # cara guardada: solo falta la pantalla
            # con todo guardado se queda en el menú; la luz se revisa sola, sin pantalla ni voz
            self.hilo.start()
            # Esc: omitir las calibraciones (valores por defecto y cruceta sin puntero),
            # p. ej. si otra persona configura la silla
            QShortcut(QKeySequence(Qt.Key_Escape), self, self._omitir)

        # Las flechas del teclado hacen lo mismo que girar la cabeza (pruebas sin cámara o pulsadores)
        self.atajos_flechas = []
        for tecla, gesto in ((Qt.Key_Left, "izquierda"), (Qt.Key_Right, "derecha"),
                             (Qt.Key_Up, "arriba"), (Qt.Key_Down, "abajo")):
            self.atajos_flechas.append(QShortcut(QKeySequence(tecla), self, lambda g=gesto: self._gesto(g)))

    def _al_cambiar_vista(self, indice: int):
        # El editor es para quien acompaña: ahí las flechas mueven las listas, y ni la mirada ni la
        # cruceta pulsan nada (con "Borrar" a la vista, un gesto sin querer perdería datos)
        for atajo in self.atajos_flechas:
            atajo.setEnabled(indice != VISTA_EDITOR)
        if indice == VISTA_EDITOR:
            self.capa.mostrar(None, None, 0.0)

    def _gesto(self, gesto: str):
        """Cruceta: una dirección selecciona el bloque vecino en esa dirección; "pulsar" lo activa."""
        if self.vistas.currentIndex() == VISTA_EDITOR:
            return
        bloques = bloques_visibles(self.vistas.currentWidget())
        if not bloques:
            return  # p. ej. en la pantalla de calibración
        actual = self.focusWidget()
        if actual not in bloques:
            bloques[0].setFocus()  # sin selección, cualquier gesto selecciona el primer bloque
            return
        if gesto == "pulsar":
            actual.animateClick()  # se ve hundirse un instante antes de actuar
            return
        dx, dy = VECTORES[gesto]
        aqui = caja(actual)
        mejor, menor = None, None
        for bloque in bloques:
            otro = caja(bloque)
            # Solo cuenta si queda entero más allá del borde en esa dirección: un botón ancho
            # de la fila de arriba no está "a la derecha" aunque su centro lo esté.
            mas_alla = {(1, 0): otro.left() > aqui.right(), (-1, 0): otro.right() < aqui.left(),
                        (0, 1): otro.top() > aqui.bottom(), (0, -1): otro.bottom() < aqui.top()}
            if not mas_alla[(dx, dy)]:
                continue
            d = otro.center() - aqui.center()
            avance = d.x() * dx + d.y() * dy
            # prefiere el vecino alineado antes que uno más cercano en diagonal
            puntaje = avance + 2 * abs(d.x() * dy - d.y() * dx)
            if menor is None or puntaje < menor:
                mejor, menor = bloque, puntaje
        if mejor is None:
            return  # ya está en el borde: no da la vuelta
        mejor.setFocus()
        zona = mejor.parentWidget()
        while zona is not None and not isinstance(zona, QScrollArea):
            zona = zona.parentWidget()
        if zona is not None:
            zona.ensureWidgetVisible(mejor)

    def _ir_a(self, indice: int):
        if indice == 2:
            self.fases.setCurrentIndex(0)  # Activadores siempre empieza eligiendo el dispositivo
        self.vistas.setCurrentIndex(indice)
        # Llevar la selección a la vista nueva para seguir con la cruceta o el teclado;
        # en Activadores, al primer dispositivo en vez de a "Volver al menú"
        (self.botones_dispositivo[0] if indice == 2 else primer_bloque(self.vistas.currentWidget())).setFocus()

    def _boton_volver(self, parent) -> QPushButton:
        boton = con_icono(_volver(QPushButton("Volver al menú", parent)), "arrow-left", TAMANO_ICONO_VOLVER)
        boton.clicked.connect(lambda: self._ir_a(0))
        return boton

    def _crear_menu(self) -> QWidget:
        menu = QWidget()
        layout = QVBoxLayout(menu)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        titulo = QLabel("Menú", menu)
        titulo.setObjectName("tituloVista")
        layout.addWidget(titulo)
        for indice, nombre, nombre_icono in ((1, "Navegación", "navigation"), (2, "Activadores", "zap")):
            # bloques grandes: blancos fáciles para la mirada
            boton = con_icono(_llenar(QPushButton(nombre, menu)), nombre_icono)
            boton.setObjectName("primaryBtn")
            boton.setAccessibleName(f"Ir a la vista {nombre}")
            boton.clicked.connect(lambda _, i=indice: self._ir_a(i))
            layout.addWidget(boton, 1)
        # La calibración se guarda: si se mueve la silla o la pantalla, hay que poder repetirla
        self.boton_recalibrar = con_icono(_volver(QPushButton("Volver a calibrar", menu)), "crosshair", TAMANO_ICONO_VOLVER)
        self.boton_recalibrar.setAccessibleName("Borrar la calibración guardada y calibrar de nuevo")
        # Borra la calibración: pide confirmación (con la mirada se podría activar sin querer)
        self.boton_recalibrar.clicked.connect(lambda: self._ir_a(5))
        self.boton_recalibrar.setVisible(HiloCamara is not None)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self.boton_recalibrar)
        layout.addLayout(fila)
        return menu

    def _crear_confirmar_recalibrar(self) -> QWidget:
        vista = QWidget()
        layout = QVBoxLayout(vista)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        pregunta = QLabel("¿Borrar la calibración guardada y calibrar de nuevo?\n"
                          "Hazlo si se movió la silla, la cámara o la pantalla.", vista)
        pregunta.setObjectName("tituloVista")
        pregunta.setWordWrap(True)
        layout.addWidget(pregunta)
        fila = QHBoxLayout()
        fila.setSpacing(16)
        # "No" va primero: _ir_a selecciona el primer bloque, así la opción segura es la de partida
        no = con_icono(_llenar(QPushButton("No, volver al menú", vista)), "x")
        no.clicked.connect(lambda: self._ir_a(0))
        si = con_icono(_llenar(QPushButton("Sí, calibrar de nuevo", vista)), "rotate-ccw")
        si.clicked.connect(self._recalibrar)
        fila.addWidget(no)
        fila.addWidget(si)
        layout.addLayout(fila, 1)
        return vista

    def _recalibrar(self):
        """Borra lo guardado y repite todas las calibraciones desde cero."""
        borrar_calibracion()
        self.modelo_mirada, self.mirada, self.ancla, self.omitir = None, None, None, False
        self.calibrar_cara, self.paso_dicho = True, None
        self.permanencia, self.filtro = Permanencia(), FiltroUnEuro()
        self.capa.mostrar(None, None, 0.0)
        self.hilo.calibracion = Calibracion()  # primero la calibración nueva, después el aviso al hilo
        self.hilo.reiniciar = True
        self.vistas.setCurrentIndex(3)

    def _crear_navegacion(self) -> QWidget:
        vista = QWidget()
        layout = QVBoxLayout(vista)
        layout.setContentsMargins(20, 20, 20, 20)

        fila = QHBoxLayout()
        fila.addWidget(self._boton_volver(vista))
        fila.addStretch(1)

        self.camara_navegacion = VistaCamara(vista, flecha=True)
        self.camara_navegacion.setAccessibleName("Cámara con la dirección de la cabeza")

        # La flecha nunca va sola: el texto repite la dirección
        self.lbl_direccion = QLabel("Dirección: buscando rostro...", vista)
        self.lbl_direccion.setObjectName("tituloVista")
        self.lbl_direccion.setAlignment(Qt.AlignCenter)
        self.lbl_direccion.setWordWrap(True)

        layout.addLayout(fila)
        layout.addWidget(self.camara_navegacion, 1)
        layout.addWidget(self.lbl_direccion)
        return vista

    def _crear_activadores(self) -> QWidget:
        # Por fases: página 0 = elegir dispositivo; página 1 + i = acciones del dispositivo i
        self.fases = QStackedWidget()
        self.botones_dispositivo = []
        # Los comandos personalizados son un dispositivo más, con sus categorías (ver _crear_fase_comandos)
        self.dispositivos = {**DISPOSITIVOS, "Comandos": None}
        self.fases.addWidget(self._crear_fase_dispositivos())
        for i, nombre in enumerate(self.dispositivos):
            self.fases.addWidget(self._crear_fase_comandos(i) if nombre == "Comandos" else self._crear_fase_acciones(i, nombre))
        return self.fases

    def _crear_fase_comandos(self, i: int) -> QWidget:
        """Comandos personalizados: primero la categoría, después el comando. Se redibuja al editarlos."""
        self.i_comandos = i
        fase = QWidget()
        layout = QVBoxLayout(fase)
        layout.setContentsMargins(20, 12, 20, 20)
        self.volver_comandos = con_icono(_volver(QPushButton("Volver a dispositivos", fase)), "arrow-left", TAMANO_ICONO_VOLVER)
        self.volver_comandos.clicked.connect(self._volver_comandos)
        editar = con_icono(_volver(QPushButton("Editar comandos", fase)), "pencil", TAMANO_ICONO_VOLVER)
        editar.setAccessibleName("Editar comandos personalizados (para quien acompaña)")
        editar.clicked.connect(self._abrir_editor)
        fila = QHBoxLayout()
        fila.addWidget(self.volver_comandos)
        fila.addStretch(1)
        fila.addWidget(editar)
        fila.addWidget(self._boton_navegacion(fase))
        self.pila_comandos = QStackedWidget(fase)  # 0 = categorías; 1 + k = comandos de la categoría k
        layout.addLayout(fila)
        layout.addWidget(self.pila_comandos, 1)
        self._reconstruir_comandos()
        return fase

    def _reconstruir_comandos(self):
        while self.pila_comandos.count():
            pagina = self.pila_comandos.widget(0)
            self.pila_comandos.removeWidget(pagina)
            pagina.deleteLater()
        categorias, aviso = comandos.cargar()
        filas = lambda bloques: [(None, bloques[k:k + 4]) for k in range(0, len(bloques), 4)]
        nota = " ".join(filter(None, [aviso, "Aún no hay categorías." if not categorias else "",
                                      "Quien acompaña crea las categorías y los comandos con «Editar comandos»."]))
        self.pila_comandos.addWidget(crear_vista("Comandos", filas(
            [(c["nombre"], lambda _, k=k: self._abrir_categoria(k), c["icono"]) for k, c in enumerate(categorias)]), nota))
        for c in categorias:
            vacia = "Aún no hay comandos en esta categoría." if not c["comandos"] else ""
            self.pila_comandos.addWidget(crear_vista(c["nombre"], filas(
                [(d["titulo"], d["frase"], d["icono"]) for d in c["comandos"]]), vacia))
        self.volver_comandos.setText("Volver a dispositivos")

    def _abrir_categoria(self, k: int):
        self.pila_comandos.setCurrentIndex(1 + k)
        self.volver_comandos.setText("Volver a categorías")
        (primer_bloque(self.pila_comandos.currentWidget()) or self.volver_comandos).setFocus()

    def _volver_comandos(self):
        k = self.pila_comandos.currentIndex() - 1
        if k < 0:
            self._volver_a_dispositivos(self.i_comandos)
            return
        self.pila_comandos.setCurrentIndex(0)
        self.volver_comandos.setText("Volver a dispositivos")
        bloques = bloques_visibles(self.pila_comandos.currentWidget())
        (bloques[k] if k < len(bloques) else self.volver_comandos).setFocus()  # vuelve a la categoría de la que venía

    def _abrir_editor(self):
        self.editor.recargar()
        self.vistas.setCurrentIndex(VISTA_EDITOR)

    def _cerrar_editor(self):
        self.vistas.setCurrentIndex(2)
        self.fases.setCurrentIndex(1 + self.i_comandos)
        self.pila_comandos.setCurrentIndex(0)
        self.volver_comandos.setText("Volver a dispositivos")
        (primer_bloque(self.pila_comandos.currentWidget()) or self.volver_comandos).setFocus()

    def _boton_navegacion(self, parent) -> QPushButton:
        """Arriba a la derecha en Activadores: salto directo a Navegación."""
        boton = con_icono(_volver(QPushButton("Volver a la navegación", parent)), "navigation", TAMANO_ICONO_VOLVER)
        boton.clicked.connect(lambda: self._ir_a(1))
        return boton

    def _crear_fase_dispositivos(self) -> QWidget:
        fase = QWidget()
        layout = QVBoxLayout(fase)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(14)

        fila = QHBoxLayout()
        fila.addWidget(self._boton_volver(fase))
        fila.addStretch(1)
        fila.addWidget(self._boton_navegacion(fase))

        titulo = QLabel("Elige un dispositivo", fase)
        titulo.setObjectName("tituloVista")

        bloques = QHBoxLayout()
        bloques.setSpacing(14)
        for i, nombre in enumerate(self.dispositivos):
            boton = con_icono(_llenar(QPushButton(nombre, fase)), ICONOS_DISPOSITIVO[nombre])
            boton.setAccessibleName(f"Elegir dispositivo {i + 1}: {nombre}")
            boton.clicked.connect(lambda _, i=i: self._abrir_dispositivo(i))
            bloques.addWidget(boton)
            self.botones_dispositivo.append(boton)


        layout.addLayout(fila)
        layout.addWidget(titulo)
        layout.addLayout(bloques, 1)
        return fase

    def _crear_fase_acciones(self, i: int, nombre: str) -> QWidget:
        fase = QWidget()
        layout = QVBoxLayout(fase)
        layout.setContentsMargins(20, 12, 20, 20)

        volver = con_icono(_volver(QPushButton("Volver a dispositivos", fase)), "arrow-left", TAMANO_ICONO_VOLVER)
        volver.setAccessibleName(f"Volver a elegir dispositivo (ahora: {nombre})")
        volver.clicked.connect(lambda: self._volver_a_dispositivos(i))
        fila = QHBoxLayout()
        fila.addWidget(volver)
        fila.addStretch(1)
        fila.addWidget(self._boton_navegacion(fase))

        # Desplazamiento en vez de aplastar los botones si no caben
        desplazable = QScrollArea(fase)
        desplazable.setWidget(crear_vista(nombre, self.dispositivos[nombre]))
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        layout.addLayout(fila)
        layout.addWidget(desplazable, 1)
        return fase

    def _abrir_dispositivo(self, i: int):
        self.fases.setCurrentIndex(1 + i)
        if i == self.i_comandos:  # empieza siempre por las categorías
            self.pila_comandos.setCurrentIndex(0)
            self.volver_comandos.setText("Volver a dispositivos")
            (primer_bloque(self.pila_comandos.currentWidget()) or self.volver_comandos).setFocus()
            return
        # La selección cae en la primera acción, no en "Volver": es lo que se va a usar.
        # Sin acciones (p. ej. aún no hay comandos), en el primer bloque de la página.
        pagina = self.fases.currentWidget()
        (primer_bloque(pagina.findChild(QScrollArea)) or primer_bloque(pagina)).setFocus()

    def _volver_a_dispositivos(self, i: int):
        self.fases.setCurrentIndex(0)
        self.botones_dispositivo[i].setFocus()  # vuelve al dispositivo del que venía

    def _crear_calibracion(self) -> QWidget:
        vista = QWidget()
        layout = QVBoxLayout(vista)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        titulo = QLabel("Calibración", vista)
        titulo.setObjectName("tituloTarjeta")

        self.lbl_instruccion = QLabel("Preparando la cámara...", vista)
        self.lbl_instruccion.setObjectName("instruccion")
        self.lbl_instruccion.setAlignment(Qt.AlignCenter)
        self.lbl_instruccion.setWordWrap(True)

        # La flecha señala hacia dónde girar; el texto siempre dice lo mismo con palabras
        self.guia_calibracion = VistaCamara(vista, flecha=True)
        self.guia_calibracion.setAccessibleName("Hacia dónde girar la cabeza")

        self.barra_calibracion = QProgressBar(vista)
        self.barra_calibracion.setRange(0, 1000)
        self.barra_calibracion.setTextVisible(False)

        ayuda = QLabel("Esc: omitir la calibración y usar los valores por defecto", vista)
        ayuda.setAlignment(Qt.AlignCenter)

        layout.addWidget(titulo)
        layout.addWidget(self.lbl_instruccion)
        layout.addWidget(self.guia_calibracion, 1)
        layout.addWidget(self.barra_calibracion)
        layout.addWidget(ayuda)
        return vista

    def _calibrando(self, paso: str, instruccion: str, progreso: float, hay_cara: bool):
        if not self.calibrar_cara:
            return  # perfil guardado: el hilo solo revisa la luz, en silencio
        if paso != self.paso_dicho:  # paso nuevo: se lee en voz alta y el paso espera a que termine
            self.paso_dicho = paso
            voz.hablar(instruccion)
        if not hay_cara and paso != "luz":
            instruccion += "\n(No veo tu cara: colócate frente a la cámara)"
        self.lbl_instruccion.setText(instruccion)
        flecha = paso if paso in ANGULOS else "centro" if paso in ("centro", "volver") else ""
        self.guia_calibracion.set_imagen(None, flecha)
        self.barra_calibracion.setValue(int(progreso * 1000))

    def _calibrado(self, resumen: str, sin_calibrar: tuple, perfil):
        print(f"Calibración lista. {resumen}", flush=True)  # para ajustar las perillas de camara.py
        if not self.calibrar_cara:
            return  # perfil guardado: nada que mostrar ni guardar
        if not self.omitir:  # con Esc no se guarda: la próxima vez se vuelve a pedir
            guardar_calibracion(perfil=perfil)
        texto = "Calibración lista"
        if sin_calibrar:
            # Importante con movilidad reducida: esa dirección (o la boca) pedirá un movimiento mayor
            texto += f"\nNo detecté movimiento suficiente en: {', '.join(sin_calibrar)}.\nSe usarán los valores por defecto."
        self.lbl_instruccion.setText(texto)
        self.guia_calibracion.set_imagen(None, "")
        self.barra_calibracion.setValue(1000)
        voz.hablar(texto.replace("\n", " "))
        self._tras_hablar(3000 if sin_calibrar else 1000, lambda: self.vistas.currentIndex() == 3 and self._tras_calibrar())

    def _tras_hablar(self, minimo_ms: int, accion):
        """Ejecuta accion cuando la voz termina, y nunca antes de minimo_ms (tiempo para leer)."""
        limite = time.monotonic() + minimo_ms / 1000

        def revisar():
            if voz.ocupada() or time.monotonic() < limite:
                QTimer.singleShot(100, revisar)
            else:
                accion()
        QTimer.singleShot(100, revisar)

    def _vigilar_accion(self):
        """Bloquea los bloques mientras la acción anterior (la voz) no termina, y avisa en pantalla."""
        bloquear = voz.ocupada() and self.vistas.currentIndex() in VISTAS_NORMALES
        if bloquear != self.vistas.isEnabled():
            return  # sin cambios
        if bloquear:
            self.foco_previo = self.focusWidget()
        self.vistas.setEnabled(not bloquear)
        if not bloquear and self.foco_previo is not None and self.foco_previo.isVisible():
            self.foco_previo.setFocus()  # al terminar, la selección vuelve donde estaba
        self.capa.aviso = "Espera a que termine la acción" if bloquear else ""
        self.capa.update()

    def _tras_calibrar(self):
        if self.omitir or self.modelo_mirada is not None:
            self._ir_a(0)  # Esc (queda la cruceta) o la calibración de pantalla ya estaba guardada
            return
        self.puntos, self.i_punto, self.t_punto, self.muestras = puntos_calibracion(), 0, 0.0, []
        self.vistas.setCurrentIndex(4)
        self._empezar_punto(introduccion="Ahora mira cada punto que aparezca y mueve la cabeza lo que necesites.")

    def _omitir(self):
        self.omitir = True
        if self.hilo is not None:
            self.hilo.calibracion.omitida = True
        if self.vistas.currentIndex() == 4:
            self._ir_a(0)

    def _empezar_punto(self, introduccion: str = ""):
        """Muestra el punto nuevo y lee su texto en voz alta; el punto no se mide hasta terminar."""
        texto = f"Punto {self.i_punto + 1} de {len(self.puntos)}: {NOMBRES_PUNTOS[self.i_punto]}"
        if introduccion:
            texto = f"{introduccion}\n{texto}"
        self.vista_puntos.mostrar(self.puntos[self.i_punto], 0.0, texto)
        voz.hablar(texto.replace("\n", " "))

    def _mostrar_punto(self):
        self.vista_puntos.mostrar(self.puntos[self.i_punto], max(0.0, self.t_punto - ASENTAR) / MUESTREO)

    def _gesto_cabeza(self, gesto: str):
        # Con el puntero de la mirada, girar la cabeza mueve el puntero: solo cuenta "pulsar" (boca)
        if self.modelo_mirada is None or gesto == "pulsar":
            self._gesto(gesto)

    def _rasgos(self, rasgos):
        # Solo llegan cuadros con cara: sin cara, el tiempo de calibración y de permanencia no corre
        ahora = time.monotonic()
        dt, self.t_rasgos = min(ahora - self.t_rasgos, 0.1), ahora
        if self.vistas.currentIndex() == 4:
            if self.i_punto >= 0:
                self._medir_punto(rasgos, dt)
        elif self.modelo_mirada is not None:
            self._mover_puntero(rasgos, dt)

    def _medir_punto(self, rasgos, dt: float):
        if voz.ocupada():
            return  # se está leyendo el punto: el tiempo no corre
        self.t_punto += dt
        if self.t_punto > ASENTAR:  # el primer tramo es para llevar la mirada al punto: no se mide
            self.muestras.append((rasgos, self.puntos[self.i_punto]))
        if self.t_punto >= ASENTAR + MUESTREO:
            self.i_punto, self.t_punto = self.i_punto + 1, 0.0
            if self.i_punto == len(self.puntos):
                self._terminar_puntos()
                return
            self._empezar_punto()
            return
        self._mostrar_punto()

    def _terminar_puntos(self):
        rasgos, posiciones = zip(*self.muestras)
        modelo = ModeloMirada(rasgos, posiciones)
        error = modelo.error_medio(rasgos, posiciones)
        print(f"Calibración de pantalla: error medio {error:.3f} de la pantalla", flush=True)
        if error <= ERROR_MAXIMO:
            self.modelo_mirada = modelo
            guardar_calibracion(modelo=modelo)
            texto, espera = "Listo: mira un bloque y quédate en él para activarlo", 1000
        else:  # un puntero impreciso activaría cosas al azar: mejor la cruceta
            texto, espera = ("No pude calibrar la mirada con precisión.\n"
                             "Se usará la cabeza como cruceta. Usa Volver a calibrar para intentarlo de nuevo."), 3000
        self.vista_puntos.mostrar(None, 0.0, texto)
        self.i_punto = -1  # la calibración terminó: _rasgos ya no mide aquí
        voz.hablar(texto.replace("\n", " "))
        self._tras_hablar(espera, lambda: self.vistas.currentIndex() == 4 and self._ir_a(0))

    def _mover_puntero(self, rasgos, dt: float):
        if self.vistas.currentIndex() == VISTA_EDITOR:
            return  # ver _al_cambiar_vista
        # Filtro 1€: quita el temblor con la mirada quieta sin retrasar los saltos (camara.FiltroUnEuro)
        self.mirada = self.filtro(self.modelo_mirada.predecir(rasgos), dt)
        punto = QPoint(int(self.mirada[0] * self.width()), int(self.mirada[1] * self.height()))
        global_ = self.mapToGlobal(punto)
        # La mirada está quieta si el puntero casi no se movió en la última VENTANA_FIJACION
        ahora = time.monotonic()
        self.recorrido.append((ahora, *self.mirada))
        while ahora - self.recorrido[0][0] > VENTANA_FIJACION:
            self.recorrido.popleft()
        quieta = dispersion([(x, y) for _, x, y in self.recorrido]) <= DISPERSION_MAXIMA
        # Se selecciona el bloque más cercano al puntero (no hace falta estar encima)
        bloques = bloques_visibles(self.vistas.currentWidget())  # vacío mientras una acción está en curso
        bajo = min(bloques, key=lambda b: distancia(global_, caja(b))) if bloques else None
        if self.ancla is not None:
            if math.dist(self.mirada, self.ancla) < REARME:
                bajo = None  # recién activado: hasta que la mirada se mueva, no cuenta nada
            else:
                self.ancla = None
        if self.permanencia.bloque is not None and not self.permanencia.bloque.isVisible():
            self.permanencia = Permanencia()  # la pantalla cambió: el bloque anterior ya no está
        activar = self.permanencia.actualizar(bajo, dt, cargar=quieta)  # si la mirada se desvía, no carga
        bloque = self.permanencia.bloque  # con la gracia, puede seguir siendo el anterior un instante
        if bloque is not None and bloque is not self.focusWidget():
            bloque.setFocus()
        if activar:
            bloque.animateClick()
            self.ancla = self.mirada
        caja_local = QRect(self.capa.mapFromGlobal(caja(bloque).topLeft()), bloque.size()) if bloque is not None else None
        self.capa.mostrar((punto.x(), punto.y()), caja_local, self.permanencia.progreso)

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self.capa.setGeometry(self.rect())
        self.capa.raise_()

    def _nuevo_fotograma(self, imagen: QImage, rostros: int, fps: float, direccion: str):
        self.camara_navegacion.set_imagen(imagen if VISTA_PREVIA else None, direccion)
        self.lbl_direccion.setText(f"Dirección: {direccion}" if direccion else "Dirección: ningún rostro en la imagen")

    def _error_camara(self, mensaje: str):
        self.lbl_direccion.setText(mensaje)
        self.boton_recalibrar.hide()  # sin cámara no se puede calibrar
        if self.vistas.currentIndex() in (3, 4):  # sin cámara no hay nada que calibrar
            self._ir_a(0)

    def closeEvent(self, evento):
        # Liberar la cámara antes de salir
        if self.hilo is not None:
            self.hilo.requestInterruption()
            self.hilo.wait()
        super().closeEvent(evento)


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
    ventana.showFullScreen()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
