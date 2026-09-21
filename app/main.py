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

import voz

try:
    from camara import HiloCamara, ModeloMirada, Permanencia
    ERROR_CAMARA = None
except ImportError as e:  # p. ej. Mac Intel: MediaPipe no publica paquete para esa plataforma
    HiloCamara = None
    ERROR_CAMARA = f"MediaPipe no está disponible ({e.name})"

MODULOS = ["Silla", "Alexa 1", "Secadora 3"]
# Botones que hablan: (texto del botón, frase dicha). "Alexa" va delante para activarla.
# Los módulos que no aparecen aquí siguen con "Opción 1/2/3" sin conectar.
FRASES = {
    "Alexa 1": [
        ("Encender foco 1", "Alexa, encender foco 1"),
        ("Apagar foco 1", "Alexa, apagar foco 1"),
        ("Alexa, ponte unas cumbias", "Alexa, ponte unas cumbias"),
    ]
}
# Géneros que se pueden pedir desde un módulo: cada botón dice "Alexa, pon música de <género>"
GENEROS = {"Alexa 1": ["cumbia", "salsa", "reguetón", "rock", "banda", "corridos", "pop", "jazz"]}
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
SUAVIZADO = 0.25  # 0-1: cuánto sigue el puntero a cada medida nueva (bajo = estable pero lento)
# Tras activar algo, la pantalla suele cambiar y bajo la mirada queda otro bloque: nada cuenta
# hasta que la mirada se mueva esta distancia (fracción de la pantalla). Evita activar en cadena.
REARME = 0.08
ERROR_MAXIMO = 0.15  # si la calibración de pantalla falla por más que esto, se usa la cruceta


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


def bloques_visibles(contenedor: QWidget) -> list:
    return [b for b in contenedor.findChildren(QPushButton) if b.isVisible() and b.isEnabled()]


def primer_bloque(contenedor: QWidget) -> QPushButton:
    """Primer botón visible dentro del contenedor (orden de creación)."""
    return next(b for b in contenedor.findChildren(QPushButton) if b.isVisible())


def _llenar(boton: QPushButton) -> QPushButton:
    """El botón crece para repartirse la pantalla con los demás."""
    boton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return boton


def _volver(boton: QPushButton) -> QPushButton:
    """Los botones de volver van en una esquina, pero grandes: la mirada no apunta al píxel."""
    boton.setMinimumSize(360, 110)
    return boton


def crear_vista(titulo: str, frases=(), generos=()) -> QWidget:
    vista = QWidget()
    layout = QVBoxLayout(vista)
    layout.setContentsMargins(0, 16, 0, 16)
    layout.setSpacing(14)

    encabezado = QLabel(titulo, vista)
    encabezado.setObjectName("tituloVista")
    layout.addWidget(encabezado)

    for n in range(1, 4):
        texto, frase = frases[n - 1] if frases else (f"Opción {n}", "")
        boton = _llenar(QPushButton(texto, vista))
        # Nombre único para lectores de pantalla: "Opción 1" se repite en cada vista
        boton.setAccessibleName(f"{titulo}, {texto}")
        if frase:
            boton.clicked.connect(lambda _, f=frase: voz.hablar(f))
        layout.addWidget(boton, 1)  # mismo factor que los demás: se reparten la altura

    if generos:
        # Botón que despliega/oculta la lista; el texto cambia, no solo el color
        desplegar = _llenar(QPushButton("Mostrar géneros de música", vista))
        desplegar.setCheckable(True)
        desplegar.setAccessibleName(f"{titulo}, mostrar u ocultar géneros de música")
        lista = QWidget(vista)
        rejilla = QGridLayout(lista)
        rejilla.setContentsMargins(0, 0, 0, 0)
        rejilla.setSpacing(10)
        for i, genero in enumerate(generos):
            boton = _llenar(QPushButton(genero.capitalize(), lista))
            boton.setAccessibleName(f"{titulo}, poner música de {genero}")
            boton.clicked.connect(lambda _, g=genero: voz.hablar(f"Alexa, pon música de {g}"))
            rejilla.addWidget(boton, i // 4, i % 4)
        lista.hide()

        def alternar(abierta):
            lista.setVisible(abierta)
            desplegar.setText("Ocultar géneros de música" if abierta else "Mostrar géneros de música")

        desplegar.toggled.connect(alternar)
        layout.addWidget(desplegar, 1)
        layout.addWidget(lista, 2)  # dos filas de géneros

    if frases and not voz.DISPONIBLE:
        layout.addWidget(QLabel("Voz no disponible: instala pyttsx3", vista))
    return vista


def crear_estado_dispositivos() -> QFrame:
    tarjeta = QFrame()
    tarjeta.setObjectName("cardFrame")
    layout = QVBoxLayout(tarjeta)

    titulo = QLabel("Estado de los dispositivos", tarjeta)
    titulo.setObjectName("tituloTarjeta")
    layout.addWidget(titulo)
    for nombre in MODULOS:
        layout.addWidget(QLabel(f"{nombre}: sin conexión", tarjeta))
    return tarjeta


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
        p.fillPath(ruta, QColor("#2B2D42"))

        if self.imagen is not None:
            # Escalado tipo "cover": llena el círculo y recorta el sobrante centrado
            esc = self.imagen.scaled(int(lado), int(lado), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.setClipPath(ruta)
            p.drawImage(QPointF(circulo.center().x() - esc.width() / 2, circulo.center().y() - esc.height() / 2), esc)
            p.setClipping(False)

        p.setPen(QPen(QColor("#595F85"), 3))
        p.drawEllipse(circulo)

        if self.flecha and self.direccion:
            # Ámbar con borde oscuro: se distingue sobre cualquier imagen
            p.setPen(QPen(QColor("#1E1E24"), 4))
            p.setBrush(QColor("#E69F00"))
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
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.texto)
        layout.addStretch(1)
        self.setAccessibleName("Calibración de la mirada")

    def mostrar(self, punto: tuple, progreso: float, texto: str):
        self.punto, self.progreso = punto, progreso
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
        p.setPen(QPen(QColor("#595F85"), 4))
        p.drawEllipse(centro, r, r)
        p.setPen(QPen(QColor("#E69F00"), 6))
        p.drawArc(QRectF(centro.x() - r, centro.y() - r, 2 * r, 2 * r), 90 * 16, -int(360 * 16 * self.progreso))
        p.setPen(QPen(QColor("#1E1E24"), 2))
        p.setBrush(QColor("#E69F00"))
        p.drawEllipse(centro, r * 0.35, r * 0.35)


class CapaMirada(QWidget):
    """Capa transparente encima de todo: el punto de la mirada y, en el bloque seleccionado, una
    barra que se llena hasta activarlo. No recibe clics."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.punto, self.caja, self.progreso = None, None, 0.0

    def mostrar(self, punto, caja_local, progreso: float):
        self.punto, self.caja, self.progreso = punto, caja_local, progreso
        self.update()

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.caja is not None and self.progreso > 0:
            # Oscuro sobre el ámbar del bloque seleccionado: contraste 7,36:1
            barra = QRectF(self.caja.left() + 8, self.caja.bottom() - 20, (self.caja.width() - 16) * self.progreso, 12)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#1E1E24"))
            p.drawRoundedRect(barra, 4, 4)
        if self.punto is not None:
            centro = QPointF(*self.punto)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#1E1E24"), 7))  # borde oscuro: se ve sobre fondos claros y oscuros
            p.drawEllipse(centro, 16, 16)
            p.setPen(QPen(QColor("#F4F4F6"), 3))
            p.drawEllipse(centro, 16, 16)


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sillódromo")
        self.resize(1100, 700)
        self.setMinimumSize(900, 560)

        # Vistas generales: 0 menú, 1 navegación, 2 activadores, 3 calibración, 4 calibración de pantalla
        self.vistas = QStackedWidget(self)
        self.vistas.addWidget(self._crear_menu())
        self.vistas.addWidget(self._crear_navegacion())
        self.vistas.addWidget(self._crear_activadores())
        self.vistas.addWidget(self._crear_calibracion())
        self.vista_puntos = VistaPuntos()
        self.vistas.addWidget(self.vista_puntos)
        self.setCentralWidget(self.vistas)
        self.capa = CapaMirada(self)  # encima de todo; se ajusta en resizeEvent

        # Puntero de la mirada: activo cuando termina la calibración de pantalla
        self.modelo_mirada, self.mirada, self.omitir = None, None, False
        self.ancla = None  # dónde estaba la mirada al activar el último bloque (ver REARME)
        self.permanencia = Permanencia() if HiloCamara is not None else None
        self.t_rasgos = time.monotonic()

        self.hilo = None
        if HiloCamara is None:
            self._error_camara(ERROR_CAMARA)
        else:
            self.hilo = HiloCamara(self, con_imagen=VISTA_PREVIA)
            self.hilo.fotograma.connect(self._nuevo_fotograma)
            self.hilo.error.connect(self._error_camara)
            self.hilo.gesto.connect(self._gesto_cabeza)
            self.hilo.calibrando.connect(self._calibrando)
            self.hilo.calibrado.connect(self._calibrado)
            self.hilo.rasgos.connect(self._rasgos)
            self.vistas.setCurrentIndex(3)  # con cámara, arranca calibrando
            self.hilo.start()
            # Esc: omitir las calibraciones (valores por defecto y cruceta sin puntero),
            # p. ej. si otra persona configura la silla
            QShortcut(QKeySequence(Qt.Key_Escape), self, self._omitir)

        # Las flechas del teclado hacen lo mismo que girar la cabeza (pruebas sin cámara o pulsadores)
        for tecla, gesto in ((Qt.Key_Left, "izquierda"), (Qt.Key_Right, "derecha"),
                             (Qt.Key_Up, "arriba"), (Qt.Key_Down, "abajo")):
            QShortcut(QKeySequence(tecla), self, lambda g=gesto: self._gesto(g))

    def _gesto(self, gesto: str):
        """Cruceta: una dirección selecciona el bloque vecino en esa dirección; "pulsar" lo activa."""
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
        boton = _volver(QPushButton("Volver al menú", parent))
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
        for indice, nombre in ((1, "Navegación"), (2, "Activadores")):
            boton = _llenar(QPushButton(nombre, menu))  # bloques grandes: blancos fáciles para la mirada
            boton.setObjectName("primaryBtn")
            boton.setAccessibleName(f"Ir a la vista {nombre}")
            boton.clicked.connect(lambda _, i=indice: self._ir_a(i))
            layout.addWidget(boton, 1)
        return menu

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
        self.fases.addWidget(self._crear_fase_dispositivos())
        for i, nombre in enumerate(MODULOS):
            self.fases.addWidget(self._crear_fase_acciones(i, nombre))
        return self.fases

    def _crear_fase_dispositivos(self) -> QWidget:
        fase = QWidget()
        layout = QVBoxLayout(fase)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(14)

        fila = QHBoxLayout()
        fila.addWidget(self._boton_volver(fase))
        fila.addStretch(1)

        titulo = QLabel("Elige un dispositivo", fase)
        titulo.setObjectName("tituloVista")

        bloques = QHBoxLayout()
        bloques.setSpacing(14)
        for i, nombre in enumerate(MODULOS):
            boton = _llenar(QPushButton(nombre, fase))
            boton.setAccessibleName(f"Elegir dispositivo {i + 1}: {nombre}")
            boton.clicked.connect(lambda _, i=i: self._abrir_dispositivo(i))
            bloques.addWidget(boton)
            self.botones_dispositivo.append(boton)

        fila_estado = QHBoxLayout()
        fila_estado.addWidget(crear_estado_dispositivos())
        fila_estado.addStretch(1)

        layout.addLayout(fila)
        layout.addWidget(titulo)
        layout.addLayout(bloques, 1)
        layout.addLayout(fila_estado)
        return fase

    def _crear_fase_acciones(self, i: int, nombre: str) -> QWidget:
        fase = QWidget()
        layout = QVBoxLayout(fase)
        layout.setContentsMargins(20, 12, 20, 20)

        volver = _volver(QPushButton("Volver a dispositivos", fase))
        volver.setAccessibleName(f"Volver a elegir dispositivo (ahora: {nombre})")
        volver.clicked.connect(lambda: self._volver_a_dispositivos(i))
        fila = QHBoxLayout()
        fila.addWidget(volver)
        fila.addStretch(1)

        # Desplazamiento en vez de aplastar los botones cuando la lista de géneros está abierta
        desplazable = QScrollArea(fase)
        desplazable.setWidget(crear_vista(f"Módulo {i + 1}: {nombre}", FRASES.get(nombre, ()), GENEROS.get(nombre, ())))
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        layout.addLayout(fila)
        layout.addWidget(desplazable, 1)
        return fase

    def _abrir_dispositivo(self, i: int):
        self.fases.setCurrentIndex(1 + i)
        # La selección cae en la primera acción, no en "Volver": es lo que se va a usar
        primer_bloque(self.fases.currentWidget().findChild(QScrollArea)).setFocus()

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
        if not hay_cara and paso != "luz":
            instruccion += "\n(No veo tu cara: colócate frente a la cámara)"
        self.lbl_instruccion.setText(instruccion)
        flecha = paso if paso in ANGULOS else "centro" if paso in ("centro", "volver") else ""
        self.guia_calibracion.set_imagen(None, flecha)
        self.barra_calibracion.setValue(int(progreso * 1000))

    def _calibrado(self, resumen: str, sin_calibrar: tuple):
        print(f"Calibración lista. {resumen}", flush=True)  # para ajustar las perillas de camara.py
        texto = "Calibración lista"
        if sin_calibrar:
            # Importante con movilidad reducida: esa dirección (o la boca) pedirá un movimiento mayor
            texto += f"\nNo detecté movimiento suficiente en: {', '.join(sin_calibrar)}.\nSe usarán los valores por defecto."
        self.lbl_instruccion.setText(texto)
        self.guia_calibracion.set_imagen(None, "")
        self.barra_calibracion.setValue(1000)
        QTimer.singleShot(5000 if sin_calibrar else 1500, lambda: self.vistas.currentIndex() == 3 and self._tras_calibrar())

    def _tras_calibrar(self):
        if self.omitir:
            self._ir_a(0)  # Esc: sin puntero de la mirada; queda la cruceta
            return
        self.puntos, self.i_punto, self.t_punto, self.muestras = puntos_calibracion(), 0, 0.0, []
        self.vistas.setCurrentIndex(4)
        self._mostrar_punto()

    def _omitir(self):
        self.omitir = True
        if self.hilo is not None:
            self.hilo.calibracion.omitida = True
        if self.vistas.currentIndex() == 4:
            self._ir_a(0)

    def _mostrar_punto(self):
        texto = (f"Mira el punto y mueve la cabeza lo que necesites\n"
                 f"Punto {self.i_punto + 1} de {len(self.puntos)} · Esc: omitir")
        self.vista_puntos.mostrar(self.puntos[self.i_punto], max(0.0, self.t_punto - ASENTAR) / MUESTREO, texto)

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
        self.t_punto += dt
        if self.t_punto > ASENTAR:  # el primer tramo es para llevar la mirada al punto: no se mide
            self.muestras.append((rasgos, self.puntos[self.i_punto]))
        if self.t_punto >= ASENTAR + MUESTREO:
            self.i_punto, self.t_punto = self.i_punto + 1, 0.0
            if self.i_punto == len(self.puntos):
                self._terminar_puntos()
                return
        self._mostrar_punto()

    def _terminar_puntos(self):
        rasgos, posiciones = zip(*self.muestras)
        modelo = ModeloMirada(rasgos, posiciones)
        error = modelo.error_medio(rasgos, posiciones)
        print(f"Calibración de pantalla: error medio {error:.3f} de la pantalla", flush=True)
        if error <= ERROR_MAXIMO:
            self.modelo_mirada = modelo
            texto, espera = "Listo: mira un bloque y quédate en él para activarlo", 2000
        else:  # un puntero impreciso activaría cosas al azar: mejor la cruceta
            texto, espera = ("No pude calibrar la mirada con precisión.\n"
                             "Se usará la cabeza como cruceta. Reinicia para intentarlo de nuevo."), 5000
        self.vista_puntos.mostrar(None, 0.0, texto)
        self.i_punto = -1  # la calibración terminó: _rasgos ya no mide aquí
        QTimer.singleShot(espera, lambda: self.vistas.currentIndex() == 4 and self._ir_a(0))

    def _mover_puntero(self, rasgos, dt: float):
        x, y = self.modelo_mirada.predecir(rasgos)
        if self.mirada is None:
            self.mirada = (x, y)
        else:  # suavizado exponencial: quita el temblor de la medida
            self.mirada = (self.mirada[0] + SUAVIZADO * (x - self.mirada[0]), self.mirada[1] + SUAVIZADO * (y - self.mirada[1]))
        punto = QPoint(int(self.mirada[0] * self.width()), int(self.mirada[1] * self.height()))
        global_ = self.mapToGlobal(punto)
        bajo = next((b for b in bloques_visibles(self.vistas.currentWidget()) if caja(b).contains(global_)), None)
        if self.ancla is not None:
            if math.dist(self.mirada, self.ancla) < REARME:
                bajo = None  # recién activado: hasta que la mirada se mueva, no cuenta nada
            else:
                self.ancla = None
        if self.permanencia.bloque is not None and not self.permanencia.bloque.isVisible():
            self.permanencia = Permanencia()  # la pantalla cambió: el bloque anterior ya no está
        activar = self.permanencia.actualizar(bajo, dt)
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
