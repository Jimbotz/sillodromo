"""
window.py - VentanaPrincipal: la ventana única de Sillódromo (QMainWindow a pantalla completa).
Coordina lo que las pantallas (app/views) no pueden decidir por sí solas: qué vista está activa,
el hilo de la cámara y sus señales, el estado de la calibración (cara, después pantalla) y el
puntero de la mirada (camara.Permanencia). Las pantallas en sí se construyen en app/views/*.py y
solo reciben esta ventana para leer o guardar su estado (p. ej. self.lbl_direccion).

Todo se maneja como bloques con la cruceta de la cabeza (features.tracking.Cruceta): girar mueve la
selección al bloque vecino, que se ilumina, y abrir la boca lo pulsa. Las flechas del teclado hacen
lo mismo que girar la cabeza. Al arrancar con cámara se calibra primero (luz, reposo, rangos de giro
y apertura de la boca; ver features.tracking.Calibracion); Esc la omite. Después se calibra la
pantalla (16 puntos en el borde) y los ojos + la cabeza mueven un puntero: mirar un bloque lo
selecciona y quedarse en él lo activa (features.tracking.Permanencia).
"""

import math
import time
from collections import deque

from PyQt5.QtCore import QPoint, QRect, Qt, QTimer
from PyQt5.QtGui import QImage, QKeySequence
from PyQt5.QtWidgets import QMainWindow, QScrollArea, QShortcut, QStackedWidget

from features import voice as voz
from tools.geometry import caja, distancia
from views import activators, calibration, confirm, menu, navigation
from views import common
from views.common import (NOMBRES_PUNTOS, VISTA_EDITOR, VISTA_NAVEGACION, VISTA_PREVIA, VISTAS_NORMALES,
                          primer_bloque, puntos_calibracion)
from views.editor import EditorComandos
from widgets.calibration_points import VistaPuntos
from widgets.camera_preview import ANGULOS
from widgets.gaze_overlay import CapaMirada

try:
    from features.tracking import (Calibracion, FiltroUnEuro, HiloCamara, ModeloMirada, Permanencia,
                                   borrar_calibracion, cargar_calibracion, dispersion, guardar_calibracion)
    ERROR_CAMARA = None
except ImportError as e:  # p. ej. Mac Intel: MediaPipe no publica paquete para esa plataforma
    HiloCamara = None
    ERROR_CAMARA = f"MediaPipe no está disponible ({e.name})"

# Dirección de cada gesto de la cruceta en pantalla (x hacia la derecha, y hacia abajo)
VECTORES = {"izquierda": (-1, 0), "derecha": (1, 0), "arriba": (0, -1), "abajo": (0, 1)}

# Calibración de pantalla del puntero (ver _mover_puntero y _terminar_puntos)
ASENTAR, MUESTREO = 0.8, 1.2  # por punto: tiempo para llevar la mirada y tiempo midiendo
# Tras activar algo, la pantalla suele cambiar y bajo la mirada queda otro bloque: nada cuenta
# hasta que la mirada se mueva esta distancia (fracción de la pantalla). Evita activar en cadena.
REARME = 0.08
ERROR_MAXIMO = 0.15  # si la calibración de pantalla falla por más que esto, se usa la cruceta
# La barra solo carga con la mirada quieta: si en la última VENTANA_FIJACION (s) el puntero se movió
# más que DISPERSION_MAXIMA (fracción de pantalla), la mirada se está desviando y la carga se pausa
VENTANA_FIJACION = 0.3
DISPERSION_MAXIMA = 0.05


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sillódromo")
        self.resize(1100, 700)
        self.setMinimumSize(900, 560)
        self.HiloCamara = HiloCamara  # leído por views.menu para mostrar u ocultar "Volver a calibrar"

        # Vistas generales: 0 menú, 1 navegación, 2 activadores, 3 calibración, 4 calibración de pantalla,
        # 5 confirmar "Volver a calibrar"
        self.vistas = QStackedWidget(self)
        self.vistas.addWidget(menu.crear(self))
        self.vistas.addWidget(navigation.crear(self))
        self.vistas.addWidget(activators.crear(self))
        self.vistas.addWidget(calibration.crear(self))
        self.vista_puntos = VistaPuntos()
        self.vistas.addWidget(self.vista_puntos)
        self.vistas.addWidget(confirm.crear(self))
        self.editor = EditorComandos()  # 6: para quien acompaña, con teclado y ratón
        self.editor.cambiado.connect(lambda: activators._reconstruir_comandos(self))
        self.editor.cerrar.connect(lambda: activators._cerrar_editor(self))
        self.vistas.addWidget(self.editor)
        # La lista debe existir antes de conectar: setCurrentIndex(3) de la calibración
        # dispara _al_cambiar_vista antes de crear los atajos
        self.atajos_flechas = []
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
        if indice in (VISTA_EDITOR, VISTA_NAVEGACION):  # sin puntero ni barra de carga
            self.capa.mostrar(None, None, 0.0)

    def _gesto(self, gesto: str):
        """Cruceta: una dirección selecciona el bloque vecino en esa dirección; "pulsar" lo activa."""
        if self.vistas.currentIndex() == VISTA_EDITOR:
            return
        bloques = common.bloques_visibles(self.vistas.currentWidget())
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
        print(f"Calibración lista. {resumen}", flush=True)  # para ajustar las perillas de features/tracking.py
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
        if self.vistas.currentIndex() == VISTA_NAVEGACION:
            # En Navegación la cabeza conduce: girar no mueve la selección, así no se sale sin querer.
            # La única salida con la cara es abrir la boca, que vuelve al menú.
            if gesto == "pulsar":
                self._salir_de_navegacion()
            return
        # Con el puntero de la mirada, girar la cabeza mueve el puntero: solo cuenta "pulsar" (boca)
        if self.modelo_mirada is None or gesto == "pulsar":
            self._gesto(gesto)

    def _salir_de_navegacion(self):
        self._ir_a(0)
        if self.permanencia is not None:
            self.permanencia = Permanencia()
        self.ancla = self.mirada  # en el menú, la mirada no activa nada hasta moverse (ver REARME)

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
        # Filtro 1€: quita el temblor con la mirada quieta sin retrasar los saltos (features.tracking.FiltroUnEuro).
        # Se sigue actualizando en todas las vistas, para saber dónde mira al volver al menú.
        self.mirada = self.filtro(self.modelo_mirada.predecir(rasgos), dt)
        if self.vistas.currentIndex() in (VISTA_EDITOR, VISTA_NAVEGACION):
            return  # la mirada no selecciona nada aquí (ver _al_cambiar_vista y _gesto_cabeza)
        punto = QPoint(int(self.mirada[0] * self.width()), int(self.mirada[1] * self.height()))
        global_ = self.mapToGlobal(punto)
        # La mirada está quieta si el puntero casi no se movió en la última VENTANA_FIJACION
        ahora = time.monotonic()
        self.recorrido.append((ahora, *self.mirada))
        while ahora - self.recorrido[0][0] > VENTANA_FIJACION:
            self.recorrido.popleft()
        quieta = dispersion([(x, y) for _, x, y in self.recorrido]) <= DISPERSION_MAXIMA
        # Se selecciona el bloque más cercano al puntero (no hace falta estar encima)
        bloques = common.bloques_visibles(self.vistas.currentWidget())  # vacío mientras una acción está en curso
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
