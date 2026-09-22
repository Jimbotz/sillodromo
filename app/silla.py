"""
silla.py - Conecta la vista de Navegación de la interfaz con el Arduino que mueve la silla de
ruedas, usando las flechas del teclado.

La lógica serial está extraída de movement.py y silla_de_ruedas.py (que quedan tal cual): mismo
protocolo de dos bytes [vertical, horizontal] por el puerto serie, con 128 como posición neutra.
La placa va en PUERTO_SERIAL (COM6 por defecto, igual que en movement.py).

Al abrir la vista de Navegación, las flechas del teclado mueven la silla igual que w-a-s-d en
movement.py: la silla se mueve mientras la flecha está apretada (ControladorSilla.presionar) y
frena sola al soltarla (soltar), sin pulso ni temporizador de por medio. Abrir la boca ("pulsar",
por giro de cabeza) frena y es la única forma de pulsar "Volver al menú"; también se frena al
salir de la vista, si la ventana pierde el foco (alt+tab con una flecha apretada) o al cerrar la app.

Ejecutar con:  python app/silla.py
"""

import os
import sys
import time

import serial
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtWidgets import QPushButton, QWidget

from tools import scale
from views import common as vistas_comunes
from window import VentanaPrincipal

PUERTO_SERIAL = 'COM6'
BAUD_RATE = 9600
POSICION_NEUTRA = 128
VALOR_MAXIMO = 255
VALOR_MINIMO = 0
PASO_MOVIMIENTO = 15
VISTA_NAVEGACION = 1  # índice de la vista de Navegación en VentanaPrincipal
TECLA_A_DIRECCION = {Qt.Key_Up: "arriba", Qt.Key_Down: "abajo", Qt.Key_Left: "izquierda", Qt.Key_Right: "derecha"}

# "Volver al menú" solo se activa con la boca: en Navegación no existe ni para la
# cruceta de la cabeza ni para el puntero de la mirada. window.py lo busca con la
# función views.common.bloques_visibles (cruceta, _gesto) y también _mover_puntero (mirada y
# permanencia), así que filtramos esa función en el propio módulo de las vistas.
_ventana = None
_bloques_originales = vistas_comunes.bloques_visibles


def _bloques_sin_volver(contenedor: QWidget) -> list:
    bloques = _bloques_originales(contenedor)
    if _ventana is not None and _ventana.vistas.currentIndex() == VISTA_NAVEGACION:
        bloques = [b for b in bloques if b.objectName() != "volverBtn"]
    return bloques


vistas_comunes.bloques_visibles = _bloques_sin_volver


def duty_por_teclas(direcciones_activas: set) -> tuple:
    """(vertical, horizontal) a partir de las flechas sostenidas ahora mismo: igual que
    ControladorArduino.actualizar_movimiento en movement.py (cada dirección suma o resta por su
    lado, así que arriba+derecha da diagonal y arriba+abajo se cancelan), con las flechas del
    teclado en lugar de w-a-s-d."""
    mov_vertical = ("arriba" in direcciones_activas) - ("abajo" in direcciones_activas)
    mov_horizontal = ("derecha" in direcciones_activas) - ("izquierda" in direcciones_activas)
    return (POSICION_NEUTRA + mov_vertical * PASO_MOVIMIENTO * 8,
            POSICION_NEUTRA + mov_horizontal * PASO_MOVIMIENTO * 8)


assert duty_por_teclas(set()) == (POSICION_NEUTRA, POSICION_NEUTRA)
assert duty_por_teclas({"arriba"}) == (POSICION_NEUTRA + PASO_MOVIMIENTO * 8, POSICION_NEUTRA)
assert duty_por_teclas({"abajo"}) == (POSICION_NEUTRA - PASO_MOVIMIENTO * 8, POSICION_NEUTRA)
assert duty_por_teclas({"derecha"}) == (POSICION_NEUTRA, POSICION_NEUTRA + PASO_MOVIMIENTO * 8)
assert duty_por_teclas({"izquierda"}) == (POSICION_NEUTRA, POSICION_NEUTRA - PASO_MOVIMIENTO * 8)
assert duty_por_teclas({"arriba", "derecha"}) == (POSICION_NEUTRA + PASO_MOVIMIENTO * 8, POSICION_NEUTRA + PASO_MOVIMIENTO * 8)
assert duty_por_teclas({"arriba", "abajo"}) == (POSICION_NEUTRA, POSICION_NEUTRA)  # opuestas: se cancelan, como w+s


class ControladorSilla:
    """Comunicación serial con el Arduino: protocolo de dos bytes [vertical, horizontal].

    Igual que ControladorArduino de movement.py (se mueve mientras la tecla está apretada y
    frena sola al soltarla), pero con las flechas del teclado en vez de w-a-s-d.
    """

    def __init__(self, puerto, baudrate):
        self.ver_duty = POSICION_NEUTRA
        self.hor_duty = POSICION_NEUTRA
        self.direcciones_activas = set()  # flechas apretadas ahora mismo
        self.arduino = None
        self.conectado = False
        try:
            self.arduino = serial.Serial(puerto, baudrate, timeout=1)
            self.conectado = True
            print(f"Arduino conectado en {puerto}")
            time.sleep(2)  # esperar el reinicio del Arduino al abrir el puerto
            self.enviar_datos()  # posición neutra inicial
        except serial.SerialException as e:
            print(f"Error: No se pudo abrir el puerto {puerto}. Detalles: {e}")

    def enviar_datos(self):
        """Envía el duty cycle actual al Arduino, acotado al rango 0-255."""
        if self.conectado and self.arduino.is_open:
            try:
                ver_enviar = max(VALOR_MINIMO, min(VALOR_MAXIMO, int(self.ver_duty)))
                hor_enviar = max(VALOR_MINIMO, min(VALOR_MAXIMO, int(self.hor_duty)))
                self.arduino.write(bytes([ver_enviar, hor_enviar]))
                print(f"Enviando -> Vertical: {ver_enviar}, Horizontal: {hor_enviar}")
            except serial.SerialException as e:
                print(f"Error al escribir al puerto serial: {e}")

    def presionar(self, direccion: str):
        """Al apretar una flecha, se mueve en esa dirección (y sigue mientras siga apretada)."""
        self.direcciones_activas.add(direccion)
        self._actualizar()

    def soltar(self, direccion: str):
        """Al soltar una flecha, deja de moverse en esa dirección (frena si no queda ninguna)."""
        self.direcciones_activas.discard(direccion)
        self._actualizar()

    def _actualizar(self):
        self.ver_duty, self.hor_duty = duty_por_teclas(self.direcciones_activas)
        self.enviar_datos()

    def detener(self):
        """Suelta todas las flechas y regresa los dos ejes a la posición neutra."""
        self.direcciones_activas.clear()
        self._actualizar()

    def cerrar_conexion(self):
        """Cierra la conexión serial dejando la silla en neutro."""
        if self.conectado and self.arduino and self.arduino.is_open:
            try:
                self.arduino.write(bytes([POSICION_NEUTRA, POSICION_NEUTRA]))
                time.sleep(0.1)
                self.arduino.close()
                print("Conexión con Arduino cerrada.")
            except serial.SerialException as e:
                print(f"Error al cerrar la conexión serial: {e}")


class VentanaConSilla(VentanaPrincipal):
    """VentanaPrincipal cuyas flechas del teclado mueven la silla, mientras estén apretadas, en
    la vista de Navegación (fuera de ahí la interfaz funciona tal cual)."""

    def __init__(self):
        global _ventana
        super().__init__()
        _ventana = self
        self.silla = ControladorSilla(PUERTO_SERIAL, BAUD_RATE)

    def _al_cambiar_vista(self, indice: int):
        super()._al_cambiar_vista(indice)
        # En Navegación las flechas mueven la silla directamente: se desactivan como atajos de
        # bloque para que el evento llegue tal cual a keyPressEvent/keyReleaseEvent (más abajo).
        if indice == VISTA_NAVEGACION:
            for atajo in self.atajos_flechas:
                atajo.setEnabled(False)

    def keyPressEvent(self, evento):
        direccion = TECLA_A_DIRECCION.get(evento.key())
        if direccion and self.vistas.currentIndex() == VISTA_NAVEGACION and not evento.isAutoRepeat():
            self.silla.presionar(direccion)
            evento.accept()
            return
        super().keyPressEvent(evento)

    def keyReleaseEvent(self, evento):
        direccion = TECLA_A_DIRECCION.get(evento.key())
        if direccion and self.vistas.currentIndex() == VISTA_NAVEGACION and not evento.isAutoRepeat():
            self.silla.soltar(direccion)
            evento.accept()
            return
        super().keyReleaseEvent(evento)

    def _gesto(self, gesto: str):
        if self.vistas.currentIndex() != VISTA_NAVEGACION:
            # Fuera de Navegación la interfaz funciona tal cual
            super()._gesto(gesto)
            return
        # En Navegación, "pulsar" (abrir la boca) frena y es la única forma de pulsar "Volver al
        # menú"; las direcciones ya no pasan por aquí (ver keyPressEvent/keyReleaseEvent).
        if gesto == "pulsar":
            self.silla.detener()
            volver = self.vistas.widget(VISTA_NAVEGACION).findChild(QPushButton, "volverBtn")
            if volver is not None:
                volver.animateClick()

    def _ir_a(self, indice: int):
        # Al salir de Navegación (o entrar a otra vista), la silla se detiene
        if self.vistas.currentIndex() == VISTA_NAVEGACION and indice != VISTA_NAVEGACION:
            self.silla.detener()
        super()._ir_a(indice)

    def changeEvent(self, evento):
        super().changeEvent(evento)
        # Si la ventana pierde el foco con una flecha apretada (alt+tab, otra ventana), Qt no
        # entrega el "soltar": frenar es más seguro que dejarla moviéndose sola.
        if evento.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.silla.detener()

    def closeEvent(self, evento):
        self.silla.cerrar_conexion()
        super().closeEvent(evento)


if __name__ == "__main__":
    # Copia de main.main() de main.py, pero levantando VentanaConSilla
    from PyQt5.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Sillódromo")

    pantalla = app.primaryScreen().availableGeometry()
    scale.establecer_escala(min(pantalla.width() / scale.ANCHO_DISENO, pantalla.height() / scale.ALTO_DISENO))

    qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles.qss")
    with open(qss_path, encoding="utf-8") as f:
        app.setStyleSheet(scale.escalar_qss(f.read(), scale.ESCALA))

    ventana = VentanaConSilla()
    ventana.showFullScreen()
    sys.exit(app.exec_())
