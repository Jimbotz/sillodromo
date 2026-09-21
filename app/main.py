"""Accessible PyQt5 interface for wheelchair control and home interaction."""

from __future__ import annotations

import os
import sys
import time
from statistics import median

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import voz
from control import ControlEvent, ControlStateMachine, fit_gaze_axis

try:
    from camara import CameraFrame, HiloCamara

    CAMERA_IMPORT_ERROR = None
except ImportError as error:
    CameraFrame = object
    HiloCamara = None
    CAMERA_IMPORT_ERROR = f"MediaPipe no esta disponible ({error.name})"


EYE_CALIBRATION, MENU, NAVIGATION, CONFIGURATION, INTERACTION = range(5)
DIRECTION_NAMES = {
    "CENTER": "centro",
    "LEFT": "izquierda",
    "RIGHT": "derecha",
    "UP": "arriba",
    "DOWN": "abajo",
}
DIRECTION_ANGLES = {"arriba": 0, "derecha": 90, "abajo": 180, "izquierda": 270}


class CameraView(QWidget):
    """Circular camera view with an optional stable head-direction marker."""

    def __init__(self, parent=None, show_direction=False):
        super().__init__(parent)
        self.image = None
        self.direction = ""
        self.show_direction = show_direction
        self.setMinimumSize(220, 220)
        self.setAccessibleName("Vista de camara con deteccion facial")

    def set_image(self, image: QImage, direction: str = "") -> None:
        self.image = image
        self.direction = direction
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        side = min(self.width(), self.height()) - 8
        circle = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        path = QPainterPath()
        path.addEllipse(circle)
        painter.fillPath(path, QColor("#2B2D42"))

        if self.image is not None:
            scaled = self.image.scaled(
                int(side),
                int(side),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            painter.setClipPath(path)
            painter.drawImage(
                QPointF(circle.center().x() - scaled.width() / 2, circle.center().y() - scaled.height() / 2),
                scaled,
            )
            painter.setClipping(False)

        painter.setPen(QPen(QColor("#595F85"), 3))
        painter.drawEllipse(circle)
        if self.show_direction and self.direction:
            self._draw_direction(painter, circle, side)

    def _draw_direction(self, painter: QPainter, circle: QRectF, side: int) -> None:
        painter.setPen(QPen(QColor("#1E1E24"), 4))
        painter.setBrush(QColor("#E69F00"))
        painter.translate(circle.center())
        size = side * 0.18
        if self.direction == "centro":
            painter.drawEllipse(QPointF(0, 0), size * 0.4, size * 0.4)
            return
        painter.rotate(DIRECTION_ANGLES[self.direction])
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(0, -size * 1.6),
                    QPointF(size, -size * 0.4),
                    QPointF(size * 0.4, -size * 0.4),
                    QPointF(size * 0.4, size * 1.2),
                    QPointF(-size * 0.4, size * 1.2),
                    QPointF(-size * 0.4, -size * 0.4),
                    QPointF(-size, -size * 0.4),
                ]
            )
        )


class GazeOverlay(QWidget):
    """Shows gaze position and dwell progress without intercepting input."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.position = None
        self.progress = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_gaze(self, position, progress=0.0) -> None:
        self.position = position
        self.progress = progress
        self.update()

    def paintEvent(self, _event) -> None:
        if self.position is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(*self.position)
        painter.setPen(QPen(QColor("#56B4E9"), 3))
        painter.setBrush(QColor("#F4F4F6"))
        painter.drawEllipse(center, 5, 5)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#E69F00"), 5))
        painter.drawArc(QRectF(center.x() - 17, center.y() - 17, 34, 34), 90 * 16, -int(360 * 16 * self.progress))


class EyeCalibrationView(QWidget):
    """Guides the user through center and corner gaze calibration points."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target = (0.5, 0.5)
        self.point_number = 0
        self.point_total = 5
        self.status = "Esperando calibracion facial"
        self.progress = 0.0

    def set_target(self, target, point_number, point_total, status, progress=0.0) -> None:
        self.target = target
        self.point_number = point_number
        self.point_total = point_total
        self.status = status
        self.progress = progress
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#1E1E24"))
        painter.setPen(QColor("#F4F4F6"))
        title_font = painter.font()
        title_font.setPointSize(22)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(0, 28, self.width(), 45), Qt.AlignCenter, "Calibracion de mirada")

        text_font = painter.font()
        text_font.setPointSize(13)
        text_font.setBold(False)
        painter.setFont(text_font)
        painter.drawText(
            QRectF(40, 78, self.width() - 80, 55),
            Qt.AlignCenter | Qt.TextWordWrap,
            f"Punto {self.point_number} de {self.point_total}. {self.status}",
        )

        x = self.target[0] * self.width()
        y = self.target[1] * self.height()
        center = QPointF(x, y)
        painter.setPen(QPen(QColor("#E69F00"), 5))
        painter.setBrush(QColor("#56B4E9"))
        painter.drawEllipse(center, 18, 18)
        painter.setBrush(QColor("#F4F4F6"))
        painter.drawEllipse(center, 5, 5)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#009E73"), 6))
        painter.drawArc(
            QRectF(center.x() - 30, center.y() - 30, 60, 60),
            90 * 16,
            -int(360 * 16 * self.progress),
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sillodromo")
        self.setMinimumSize(900, 560)
        self.fsm = ControlStateMachine()
        self.last_intent = "NO_FACE"
        self.camera_views = []
        self.camera_status_labels = []
        self.gaze_button = None
        self.gaze_since = 0.0
        self.gaze_latched = False
        self.dwell_seconds = 1.2
        self.contrast_auto = True
        self.wide_ranges = False
        self.mouth_enabled = False
        self.eye_calibration_points = (
            (0.5, 0.5),
            (0.12, 0.12),
            (0.88, 0.12),
            (0.88, 0.88),
            (0.12, 0.88),
        )
        self.eye_calibration_index = 0
        self.eye_calibration_started = None
        self.eye_calibration_samples = []
        self.eye_calibration_results = []
        self.eye_calibration_complete = False
        self.eye_calibration_error_until = 0.0

        self.views = QStackedWidget(self)
        self.views.addWidget(self._create_eye_calibration())
        self.views.addWidget(self._create_menu())
        self.views.addWidget(self._create_navigation())
        self.views.addWidget(self._create_configuration())
        self.views.addWidget(self._create_interaction())
        self.setCentralWidget(self.views)
        self.gaze_overlay = GazeOverlay(self.views)
        self.gaze_overlay.setGeometry(self.views.rect())
        self.gaze_overlay.raise_()

        self.camera_thread = None
        if HiloCamara is None:
            self._camera_error(CAMERA_IMPORT_ERROR)
        else:
            self.camera_thread = HiloCamara(self)
            self.camera_thread.frame_ready.connect(self._new_frame)
            self.camera_thread.error.connect(self._camera_error)
            self.camera_thread.start()

        self._start_eye_calibration()

    def _create_eye_calibration(self) -> QWidget:
        self.eye_calibration_view = EyeCalibrationView()
        return self.eye_calibration_view

    def _create_menu(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(56, 48, 56, 48)
        layout.setSpacing(28)
        title = QLabel("Menu principal", view)
        title.setObjectName("tituloVista")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(28)
        entries = (
            ("Navegacion", NAVIGATION, "Control de desplazamiento y estado de la silla"),
            ("Configuracion", CONFIGURATION, "Calibracion, contraste y rangos de gestos"),
            ("Interaccion", INTERACTION, "Dispositivos del hogar mediante TTS para Alexa"),
        )
        for column, (label, index, description) in enumerate(entries):
            button = QPushButton(f"{label}\n\n{description}", view)
            button.setObjectName("menuCard")
            button.setMinimumHeight(220)
            button.setAccessibleName(label)
            button.clicked.connect(lambda _, page=index: self._go_to(page))
            grid.addWidget(button, 0, column)
        layout.addLayout(grid, 1)
        return view

    def _create_navigation(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.addLayout(self._header(view, "Navegacion"))

        split = QSplitter(Qt.Horizontal, view)
        camera_panel, self.navigation_camera = self._camera_panel(view, show_direction=True)
        split.addWidget(camera_panel)

        controls = QFrame(view)
        controls.setObjectName("cardFrame")
        controls_layout = QVBoxLayout(controls)
        self.navigation_status = QLabel("Estado: WAITING\nComando: STOP", controls)
        self.navigation_status.setObjectName("tituloVista")
        self.navigation_status.setAlignment(Qt.AlignCenter)
        controls_layout.addWidget(self.navigation_status)

        self.signal_status = QLabel("Buscando rostro...", controls)
        self.signal_status.setAlignment(Qt.AlignCenter)
        self.signal_status.setWordWrap(True)
        controls_layout.addWidget(self.signal_status)

        buttons = QGridLayout()
        actions = (
            ("Activar desplazamiento", ControlEvent.ENABLE, "primaryBtn"),
            ("En espera", ControlEvent.DISABLE, ""),
            ("Parada de emergencia", ControlEvent.EMERGENCY, "dangerBtn"),
            ("Reset de emergencia", ControlEvent.RESET_EMERGENCY, ""),
        )
        for index, (label, event, object_name) in enumerate(actions):
            button = QPushButton(label, controls)
            if object_name:
                button.setObjectName(object_name)
            button.setMinimumHeight(72)
            button.clicked.connect(lambda _, selected=event: self._control_event(selected))
            if event == ControlEvent.ENABLE:
                self.enable_movement_button = button
                button.setEnabled(False)
            buttons.addWidget(button, index // 2, index % 2)
        controls_layout.addLayout(buttons)
        controls_layout.addStretch(1)
        split.addWidget(controls)
        split.setSizes([520, 520])
        layout.addWidget(split, 1)
        return view

    def _create_configuration(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.addLayout(self._header(view, "Configuracion"))
        split = QSplitter(Qt.Horizontal, view)

        panel = QWidget(view)
        grid = QGridLayout(panel)
        grid.setSpacing(22)
        self.recalibrate_button = self._setting_button("Recalibrar centro facial", panel)
        self.recalibrate_button.clicked.connect(self._recalibrate)
        self.contrast_button = self._setting_button("Contraste automatico: ACTIVADO", panel)
        self.contrast_button.clicked.connect(self._toggle_contrast)
        self.ranges_button = self._setting_button("Rangos de gestos: NORMALES", panel)
        self.ranges_button.clicked.connect(self._toggle_ranges)
        self.mouth_button = self._setting_button("Boca abierta: DESACTIVADA", panel)
        self.mouth_button.clicked.connect(self._toggle_mouth)
        self.eye_calibration_button = self._setting_button("Recalibrar seguimiento de ojos", panel)
        self.eye_calibration_button.clicked.connect(self._start_eye_calibration)
        for index, button in enumerate(
            (
                self.recalibrate_button,
                self.contrast_button,
                self.ranges_button,
                self.mouth_button,
                self.eye_calibration_button,
            )
        ):
            grid.addWidget(button, index // 2, index % 2)
        self.configuration_status = QLabel("Selecciona un ajuste", panel)
        self.configuration_status.setObjectName("statusLabel")
        self.configuration_status.setAlignment(Qt.AlignCenter)
        grid.addWidget(self.configuration_status, 3, 0, 1, 2)
        split.addWidget(panel)

        camera_panel, self.configuration_camera = self._camera_panel(view)
        split.addWidget(camera_panel)
        split.setSizes([650, 400])
        layout.addWidget(split, 1)
        return view

    def _create_interaction(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.addLayout(self._header(view, "Interaccion con el hogar"))
        split = QSplitter(Qt.Horizontal, view)

        devices = QWidget(view)
        device_layout = QGridLayout(devices)
        device_layout.setSpacing(24)
        self.device_buttons = []
        for index, name in enumerate(("Cafetera", "Ventilador", "Secadora", "Lavadora")):
            button = QPushButton(devices)
            button.setProperty("deviceCard", True)
            button.setProperty("deviceActive", False)
            button.setMinimumSize(220, 150)
            button.setAccessibleName(f"Dispositivo {name}")
            self._set_device_text(button, name, False)
            button.clicked.connect(lambda _, selected=button, device=name: self._toggle_device(selected, device))
            self.device_buttons.append(button)
            device_layout.addWidget(button, index // 2, index % 2)
        self.interaction_status = QLabel("Conexion y estado simulados", devices)
        self.interaction_status.setObjectName("statusLabel")
        self.interaction_status.setAlignment(Qt.AlignCenter)
        device_layout.addWidget(self.interaction_status, 2, 0, 1, 2)
        split.addWidget(devices)

        camera_panel, self.interaction_camera = self._camera_panel(view)
        split.addWidget(camera_panel)
        split.setSizes([650, 400])
        layout.addWidget(split, 1)
        return view

    def _header(self, parent, title: str) -> QHBoxLayout:
        row = QHBoxLayout()
        back = QPushButton("Volver al menu", parent)
        back.setMinimumHeight(52)
        back.clicked.connect(lambda: self._go_to(MENU))
        heading = QLabel(title, parent)
        heading.setObjectName("tituloVista")
        heading.setAlignment(Qt.AlignCenter)
        row.addWidget(back)
        row.addStretch(1)
        row.addWidget(heading)
        row.addStretch(1)
        return row

    def _camera_panel(self, parent, show_direction=False):
        panel = QFrame(parent)
        panel.setObjectName("cardFrame")
        layout = QVBoxLayout(panel)
        camera = CameraView(panel, show_direction)
        status = QLabel("Camara: iniciando...", panel)
        status.setAlignment(Qt.AlignCenter)
        status.setWordWrap(True)
        layout.addWidget(camera, 1)
        layout.addWidget(status)
        self.camera_views.append(camera)
        self.camera_status_labels.append(status)
        return panel, camera

    @staticmethod
    def _setting_button(text: str, parent) -> QPushButton:
        button = QPushButton(text, parent)
        button.setMinimumHeight(150)
        button.setObjectName("settingCard")
        return button

    def _go_to(self, index: int) -> None:
        self.views.setCurrentIndex(index)
        self._clear_gaze_target()
        if index == NAVIGATION:
            self._control_event(ControlEvent.DISABLE)
        else:
            self._control_event(ControlEvent.ENTER_MENU)
        current = self.views.currentWidget()
        first_button = current.findChild(QPushButton)
        if first_button:
            first_button.setFocus()
        self.gaze_overlay.raise_()

    def _control_event(self, event: ControlEvent) -> None:
        output = self.fsm.update(self.last_intent, event)
        self._show_control(output)

    def _new_frame(self, frame: CameraFrame) -> None:
        self.last_intent = frame.gesture.intent
        output = self.fsm.update(frame.gesture.intent)
        self._show_control(output)
        direction = DIRECTION_NAMES.get(frame.gesture.intent.value, "")
        for camera in self.camera_views:
            camera.set_image(frame.image, direction)

        if frame.calibration_remaining:
            camera_text = f"Calibrando: faltan {frame.calibration_remaining} muestras"
        else:
            camera_text = (
                f"Camara {self.camera_thread.index} | FPS {frame.fps:.0f} | "
                f"Rostro {'detectado' if frame.face_detected else 'no detectado'} | "
                f"CLAHE {frame.clahe_clip:.2f}"
            )
        self.enable_movement_button.setEnabled(frame.calibration_remaining == 0)
        for label in self.camera_status_labels:
            label.setText(camera_text)

        self.signal_status.setText(
            f"Intent: {frame.gesture.intent.value} | Candidate: {frame.gesture.candidate.value}\n"
            f"yaw={frame.gesture.yaw:.3f} pitch={frame.gesture.pitch:.3f} "
            f"mouth={frame.gesture.mouth_open:.3f}"
        )

        if self.views.currentIndex() == EYE_CALIBRATION:
            self._process_eye_calibration(frame)
            self._clear_gaze_target()
            return

        self._update_gaze(frame.gaze)

    def _show_control(self, output) -> None:
        self.navigation_status.setText(
            f"Estado: {output.state.value}\nComando: {output.command.value}\nRazon: {output.reason}"
        )

    def _update_gaze(self, gaze) -> None:
        if not gaze.detected or not self.isActiveWindow():
            self._clear_gaze_target()
            return

        point = QPoint(int(gaze.x * self.views.width()), int(gaze.y * self.views.height()))
        current = self.views.currentWidget()
        child = current.childAt(current.mapFrom(self.views, point))
        while child is not None and not isinstance(child, QPushButton):
            child = child.parentWidget()
        button = child if isinstance(child, QPushButton) and child.isEnabled() else None
        now = time.monotonic()

        if button is not self.gaze_button:
            self._set_gaze_hover(self.gaze_button, False)
            self.gaze_button = button
            self.gaze_since = now
            self.gaze_latched = False
            self._set_gaze_hover(button, True)

        progress = min(1.0, (now - self.gaze_since) / self.dwell_seconds) if button else 0.0
        self.gaze_overlay.set_gaze((point.x(), point.y()), progress)
        if button is not None and progress >= 1.0 and not self.gaze_latched:
            self.gaze_latched = True
            button.click()

    def _clear_gaze_target(self) -> None:
        self._set_gaze_hover(self.gaze_button, False)
        self.gaze_button = None
        self.gaze_latched = False
        if hasattr(self, "gaze_overlay"):
            self.gaze_overlay.set_gaze(None)

    @staticmethod
    def _set_gaze_hover(button, active: bool) -> None:
        if button is None:
            return
        button.setProperty("gazeHover", active)
        button.style().unpolish(button)
        button.style().polish(button)

    def _recalibrate(self) -> None:
        if self.camera_thread:
            self.camera_thread.request_calibration()
            self.configuration_status.setText("Mira al centro: iniciando recalibracion")

    def _start_eye_calibration(self) -> None:
        self.eye_calibration_index = 0
        self.eye_calibration_started = None
        self.eye_calibration_samples = []
        self.eye_calibration_results = []
        self.eye_calibration_complete = False
        self.eye_calibration_error_until = 0.0
        self.eye_calibration_view.set_target(
            self.eye_calibration_points[0],
            1,
            len(self.eye_calibration_points),
            "Mira al punto sin mover la cabeza",
        )
        self._go_to(EYE_CALIBRATION)

    def _process_eye_calibration(self, frame: CameraFrame) -> None:
        target = self.eye_calibration_points[self.eye_calibration_index]
        point_number = self.eye_calibration_index + 1
        total = len(self.eye_calibration_points)
        now = time.monotonic()

        if now < self.eye_calibration_error_until:
            self.eye_calibration_view.set_target(
                target,
                point_number,
                total,
                "Rango insuficiente. La calibracion se reiniciara.",
            )
            return

        if frame.calibration_remaining:
            self.eye_calibration_started = None
            self.eye_calibration_samples = []
            self.eye_calibration_view.set_target(
                (0.5, 0.5),
                point_number,
                total,
                f"Primero se calibra el rostro: faltan {frame.calibration_remaining} muestras",
            )
            return

        if not frame.gaze.detected:
            self.eye_calibration_view.set_target(
                target,
                point_number,
                total,
                "No se detectan ambos ojos. Mantente frente a la camara.",
            )
            return

        if self.eye_calibration_started is None:
            self.eye_calibration_started = now
            self.eye_calibration_samples = []

        elapsed = now - self.eye_calibration_started
        settle_seconds = 0.8
        sample_seconds = 1.2
        if elapsed >= settle_seconds:
            self.eye_calibration_samples.append((frame.gaze.raw_x, frame.gaze.raw_y))
        progress = max(0.0, min(1.0, (elapsed - settle_seconds) / sample_seconds))
        status = "Ajustando..." if elapsed < settle_seconds else "Mantente mirando el punto"
        self.eye_calibration_view.set_target(target, point_number, total, status, progress)

        if elapsed < settle_seconds + sample_seconds or len(self.eye_calibration_samples) < 12:
            return

        raw_x = median(sample[0] for sample in self.eye_calibration_samples)
        raw_y = median(sample[1] for sample in self.eye_calibration_samples)
        self.eye_calibration_results.append((target[0], target[1], raw_x, raw_y))
        self.eye_calibration_index += 1
        self.eye_calibration_started = None
        self.eye_calibration_samples = []

        if self.eye_calibration_index < total:
            next_target = self.eye_calibration_points[self.eye_calibration_index]
            self.eye_calibration_view.set_target(
                next_target,
                self.eye_calibration_index + 1,
                total,
                "Mueve solo los ojos hacia el nuevo punto",
            )
            return

        try:
            horizontal_start, horizontal_end = fit_gaze_axis(
                [(raw_x, target_x) for target_x, _target_y, raw_x, _raw_y in self.eye_calibration_results]
            )
            vertical_start, vertical_end = fit_gaze_axis(
                [(raw_y, target_y) for _target_x, target_y, _raw_x, raw_y in self.eye_calibration_results]
            )
            self.camera_thread.set_gaze_calibration(
                horizontal_start,
                horizontal_end,
                vertical_start,
                vertical_end,
            )
        except ValueError:
            self.eye_calibration_index = 0
            self.eye_calibration_results = []
            self.eye_calibration_error_until = now + 2.0
            return

        self.eye_calibration_complete = True
        self._go_to(MENU)

    def _toggle_contrast(self) -> None:
        self.contrast_auto = not self.contrast_auto
        self.contrast_button.setText(
            f"Contraste automatico: {'ACTIVADO' if self.contrast_auto else 'DESACTIVADO'}"
        )
        if self.camera_thread:
            self.camera_thread.set_contrast_auto(self.contrast_auto)
        self.configuration_status.setText("Ajuste de contraste actualizado")

    def _toggle_ranges(self) -> None:
        self.wide_ranges = not self.wide_ranges
        self.ranges_button.setText(
            f"Rangos de gestos: {'AMPLIOS' if self.wide_ranges else 'NORMALES'}"
        )
        if self.camera_thread:
            self.camera_thread.set_wide_ranges(self.wide_ranges)
        self.configuration_status.setText("Umbrales de gestos actualizados")

    def _toggle_mouth(self) -> None:
        self.mouth_enabled = not self.mouth_enabled
        self.mouth_button.setText(
            f"Boca abierta: {'ACTIVADA' if self.mouth_enabled else 'DESACTIVADA'}"
        )
        if self.camera_thread:
            self.camera_thread.set_mouth_enabled(self.mouth_enabled)
        self.configuration_status.setText("Deteccion de boca actualizada")

    def _toggle_device(self, button: QPushButton, name: str) -> None:
        enable = not bool(button.property("deviceActive"))
        command = f"Alexa, {'activa' if enable else 'desactiva'} {name}"
        if not voz.hablar(command):
            self.interaction_status.setText("TTS no disponible")
            return
        button.setProperty("deviceActive", enable)
        self._set_device_text(button, name, enable)
        button.style().unpolish(button)
        button.style().polish(button)
        self.interaction_status.setText(f"Orden emitida: {command}")

    @staticmethod
    def _set_device_text(button: QPushButton, name: str, enabled: bool) -> None:
        button.setText(
            f"{name}\n\nCONECTADO (SIMULADO)\n{'ACTIVO' if enabled else 'INACTIVO'}"
        )

    def _camera_error(self, message: str) -> None:
        self.enable_movement_button.setEnabled(False)
        if hasattr(self, "eye_calibration_view"):
            self.eye_calibration_view.set_target(
                (0.5, 0.5),
                0,
                len(self.eye_calibration_points),
                message or "Camara no disponible",
            )
        for label in self.camera_status_labels:
            label.setText(message or "Camara no disponible")
        self.signal_status.setText(message or "Camara no disponible")
        self._clear_gaze_target()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "gaze_overlay"):
            self.gaze_overlay.setGeometry(self.views.rect())
            self.gaze_overlay.raise_()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self.camera_thread is not None:
            self.camera_thread.requestInterruption()
            self.camera_thread.wait()
        super().closeEvent(event)


def main() -> None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Sillodromo")
    stylesheet = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles.qss")
    with open(stylesheet, encoding="utf-8") as file:
        app.setStyleSheet(file.read())
    window = MainWindow()
    window.showFullScreen()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
