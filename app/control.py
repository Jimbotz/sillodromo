from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from math import sqrt
from statistics import mean, median
from typing import Any, Optional


class ControlState(str, Enum):
    WAITING = "WAITING"
    MOVEMENT = "MOVEMENT"
    MENU = "MENU"
    EMERGENCY = "EMERGENCY"


class MotionCommand(str, Enum):
    STOP = "STOP"
    FORWARD = "FORWARD"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class ControlEvent(str, Enum):
    NONE = "NONE"
    ENABLE = "ENABLE"
    DISABLE = "DISABLE"
    ENTER_MENU = "ENTER_MENU"
    EXIT_MENU = "EXIT_MENU"
    EMERGENCY = "EMERGENCY"
    RESET_EMERGENCY = "RESET_EMERGENCY"


@dataclass(frozen=True)
class ControlOutput:
    state: ControlState
    command: MotionCommand
    reason: str


class ControlStateMachine:
    def __init__(self):
        self.state = ControlState.WAITING
        self.last_command = MotionCommand.STOP

    def update(self, gesture: Any, event: ControlEvent = ControlEvent.NONE) -> ControlOutput:
        intent = str(gesture.value) if hasattr(gesture, "value") else str(gesture)

        if event == ControlEvent.EMERGENCY:
            self.state = ControlState.EMERGENCY
            command, reason = MotionCommand.EMERGENCY_STOP, "external_emergency"
        elif self.state == ControlState.EMERGENCY:
            if event == ControlEvent.RESET_EMERGENCY:
                self.state = ControlState.WAITING
                command, reason = MotionCommand.STOP, "emergency_reset"
            else:
                command, reason = MotionCommand.EMERGENCY_STOP, "emergency_latched"
        elif intent == "NO_FACE":
            if self.state == ControlState.MOVEMENT:
                self.state = ControlState.WAITING
            command, reason = MotionCommand.STOP, "no_face"
        elif event == ControlEvent.DISABLE:
            self.state = ControlState.WAITING
            command, reason = MotionCommand.STOP, "disabled"
        elif event == ControlEvent.ENABLE:
            self.state = ControlState.MOVEMENT
            command, reason = self._command(intent), "enabled"
        elif event == ControlEvent.ENTER_MENU:
            self.state = ControlState.MENU
            command, reason = MotionCommand.STOP, "menu"
        elif event == ControlEvent.EXIT_MENU and self.state == ControlState.MENU:
            self.state = ControlState.WAITING
            command, reason = MotionCommand.STOP, "menu_exit"
        elif self.state != ControlState.MOVEMENT:
            command = MotionCommand.EMERGENCY_STOP if self.state == ControlState.EMERGENCY else MotionCommand.STOP
            reason = self.state.value.lower()
        else:
            command, reason = self._command(intent), "gesture"

        self.last_command = command
        return ControlOutput(self.state, command, reason)

    @staticmethod
    def _command(intent: str) -> MotionCommand:
        return {
            "UP": MotionCommand.FORWARD,
            "LEFT": MotionCommand.TURN_LEFT,
            "RIGHT": MotionCommand.TURN_RIGHT,
        }.get(intent, MotionCommand.STOP)


@dataclass(frozen=True)
class FaceSignals:
    face_detected: bool
    yaw: float = 0.0
    pitch: float = 0.0
    mouth_open: float = 0.0


class FaceSignalExtractor:
    def __init__(self, smoothing_alpha: float = 0.25):
        self.smoothing_alpha = smoothing_alpha
        self.neutral: Optional[tuple[float, float, float]] = None
        self._smoothed: Optional[FaceSignals] = None
        self._calibration_samples: list[tuple[float, float, float]] = []

    def reset_calibration(self) -> None:
        self.neutral = None
        self._smoothed = None
        self._calibration_samples.clear()

    def add_calibration_sample(self, landmarks: Optional[list[Any]]) -> bool:
        raw = self._raw(landmarks)
        if raw is None:
            return False
        self._calibration_samples.append(raw)
        return True

    def finish_calibration(self) -> bool:
        if not self._calibration_samples:
            return False
        self.neutral = tuple(mean(values) for values in zip(*self._calibration_samples))
        self._calibration_samples.clear()
        self._smoothed = None
        return True

    def extract(self, landmarks: Optional[list[Any]]) -> FaceSignals:
        raw = self._raw(landmarks)
        if raw is None:
            self._smoothed = None
            return FaceSignals(False)

        neutral = self.neutral or (0.0, 0.0, 0.0)
        current = FaceSignals(
            True,
            yaw=raw[0] - neutral[0],
            pitch=raw[1] - neutral[1],
            mouth_open=raw[2] - neutral[2],
        )
        if self._smoothed is None:
            self._smoothed = current
            return current

        alpha = self.smoothing_alpha
        previous = self._smoothed
        self._smoothed = FaceSignals(
            True,
            yaw=alpha * current.yaw + (1.0 - alpha) * previous.yaw,
            pitch=alpha * current.pitch + (1.0 - alpha) * previous.pitch,
            mouth_open=alpha * current.mouth_open + (1.0 - alpha) * previous.mouth_open,
        )
        return self._smoothed

    @staticmethod
    def _raw(landmarks: Optional[list[Any]]) -> Optional[tuple[float, float, float]]:
        if not landmarks or len(landmarks) <= 291:
            return None
        left_eye, right_eye = landmarks[33], landmarks[263]
        nose, upper_lip, lower_lip = landmarks[1], landmarks[13], landmarks[14]
        eye_distance = sqrt((left_eye.x - right_eye.x) ** 2 + (left_eye.y - right_eye.y) ** 2)
        if eye_distance < 0.03:
            return None
        eye_x = (left_eye.x + right_eye.x) / 2.0
        eye_y = (left_eye.y + right_eye.y) / 2.0
        mouth = sqrt((upper_lip.x - lower_lip.x) ** 2 + (upper_lip.y - lower_lip.y) ** 2)
        return (
            (nose.x - eye_x) / eye_distance,
            (nose.y - eye_y) / eye_distance,
            mouth / eye_distance,
        )


class GestureIntent(str, Enum):
    NO_FACE = "NO_FACE"
    CENTER = "CENTER"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP = "UP"
    DOWN = "DOWN"
    MOUTH_OPEN = "MOUTH_OPEN"


@dataclass(frozen=True)
class GestureConfig:
    yaw_enter: float = 0.12
    yaw_exit: float = 0.07
    pitch_enter: float = 0.20
    pitch_exit: float = 0.12
    mouth_enter: float = 0.08
    mouth_exit: float = 0.04
    min_activation_ms: int = 300
    center_activation_ms: int = 150
    stop_activation_ms: int = 100
    invert_yaw: bool = True
    enable_mouth: bool = False


@dataclass(frozen=True)
class GestureResult:
    intent: GestureIntent
    candidate: GestureIntent
    stable_ms: int
    changed: bool
    yaw: float
    pitch: float
    mouth_open: float


class GestureInterpreter:
    def __init__(self, config: Optional[GestureConfig] = None):
        self.config = config or GestureConfig()
        self.reset()

    def reset(self) -> None:
        self.active = GestureIntent.CENTER
        self.candidate = GestureIntent.CENTER
        self.candidate_since = self._now_ms()

    def update(self, signals: FaceSignals, timestamp_ms: Optional[int] = None) -> GestureResult:
        now = timestamp_ms if timestamp_ms is not None else self._now_ms()
        yaw = -signals.yaw if self.config.invert_yaw else signals.yaw

        if not signals.face_detected:
            changed = self.active != GestureIntent.NO_FACE
            self.active = self.candidate = GestureIntent.NO_FACE
            self.candidate_since = now
            return GestureResult(self.active, self.candidate, 0, changed, yaw, signals.pitch, signals.mouth_open)

        candidate = self._candidate(yaw, signals.pitch, signals.mouth_open)
        if candidate != self.candidate:
            self.candidate = candidate
            self.candidate_since = now
        stable_ms = now - self.candidate_since
        required = self.config.center_activation_ms if candidate == GestureIntent.CENTER else self.config.min_activation_ms
        if candidate == GestureIntent.MOUTH_OPEN:
            required = self.config.stop_activation_ms
        changed = candidate != self.active and stable_ms >= required
        if changed:
            self.active = candidate
        return GestureResult(self.active, candidate, stable_ms, changed, yaw, signals.pitch, signals.mouth_open)

    def _candidate(self, yaw: float, pitch: float, mouth: float) -> GestureIntent:
        if self.config.enable_mouth and mouth >= self.config.mouth_enter:
            return GestureIntent.MOUTH_OPEN
        if self.active == GestureIntent.MOUTH_OPEN and self.config.enable_mouth and mouth >= self.config.mouth_exit:
            return GestureIntent.MOUTH_OPEN
        if self.active == GestureIntent.LEFT and yaw <= -self.config.yaw_exit:
            return GestureIntent.LEFT
        if self.active == GestureIntent.RIGHT and yaw >= self.config.yaw_exit:
            return GestureIntent.RIGHT
        if self.active == GestureIntent.UP and pitch <= -self.config.pitch_exit:
            return GestureIntent.UP
        if self.active == GestureIntent.DOWN and pitch >= self.config.pitch_exit:
            return GestureIntent.DOWN
        if yaw <= -self.config.yaw_enter:
            return GestureIntent.LEFT
        if yaw >= self.config.yaw_enter:
            return GestureIntent.RIGHT
        if pitch <= -self.config.pitch_enter:
            return GestureIntent.UP
        if pitch >= self.config.pitch_enter:
            return GestureIntent.DOWN
        return GestureIntent.CENTER

    @staticmethod
    def _now_ms() -> int:
        return int(time.monotonic() * 1000)


@dataclass(frozen=True)
class EyeGazeResult:
    detected: bool
    x: float = 0.5
    y: float = 0.5
    raw_x: float = 0.5
    raw_y: float = 0.0


def fit_gaze_axis(samples: list[tuple[float, float]]) -> tuple[float, float]:
    """Returns raw values that correspond to screen coordinates 0 and 1."""
    if len(samples) < 2:
        raise ValueError("Se necesitan al menos dos puntos de calibracion")
    raw_mean = mean(raw for raw, _target in samples)
    target_mean = mean(target for _raw, target in samples)
    denominator = sum((raw - raw_mean) ** 2 for raw, _target in samples)
    if denominator < 1e-6:
        raise ValueError("La mirada no cambio lo suficiente durante la calibracion")
    slope = sum(
        (raw - raw_mean) * (target - target_mean)
        for raw, target in samples
    ) / denominator
    if abs(slope) < 1e-6:
        raise ValueError("No se pudo calcular el rango de mirada")
    intercept = target_mean - slope * raw_mean
    return -intercept / slope, (1.0 - intercept) / slope


class EyeGazeTracker:
    EYES = ((468, 33, 133, 159, 145), (473, 362, 263, 386, 374))

    def __init__(self):
        self._smoothed: Optional[tuple[float, float]] = None
        self._horizontal: deque[float] = deque(maxlen=5)
        self._vertical: deque[float] = deque(maxlen=5)
        self._missing = 0
        self._horizontal_start = 0.65
        self._horizontal_end = 0.35
        self._vertical_start = -0.12
        self._vertical_end = 0.12

    def set_calibration(
        self,
        horizontal_start: float,
        horizontal_end: float,
        vertical_start: float,
        vertical_end: float,
    ) -> None:
        if abs(horizontal_end - horizontal_start) < 1e-4:
            raise ValueError("Rango horizontal de mirada insuficiente")
        if abs(vertical_end - vertical_start) < 1e-4:
            raise ValueError("Rango vertical de mirada insuficiente")
        self._horizontal_start = horizontal_start
        self._horizontal_end = horizontal_end
        self._vertical_start = vertical_start
        self._vertical_end = vertical_end
        self.reset()

    def reset(self) -> None:
        self._smoothed = None
        self._horizontal.clear()
        self._vertical.clear()
        self._missing = 0

    def extract(self, landmarks: Optional[list[Any]]) -> EyeGazeResult:
        if not landmarks or len(landmarks) <= 473:
            return self._not_detected()
        horizontal, vertical = [], []
        for iris_i, corner_a_i, corner_b_i, upper_i, lower_i in self.EYES:
            iris = landmarks[iris_i]
            a, b = landmarks[corner_a_i], landmarks[corner_b_i]
            upper, lower = landmarks[upper_i], landmarks[lower_i]
            width = sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)
            height = sqrt((upper.x - lower.x) ** 2 + (upper.y - lower.y) ** 2)
            if width <= 0.0 or height / width < 0.045:
                return self._not_detected()
            min_x, max_x = sorted((a.x, b.x))
            horizontal.append((iris.x - min_x) / max(max_x - min_x, 1e-6))
            position = (iris.x - a.x) / (b.x - a.x) if b.x != a.x else 0.5
            eye_line_y = a.y + position * (b.y - a.y)
            vertical.append((iris.y - eye_line_y) / width)

        raw_x = mean(horizontal)
        raw_y = mean(vertical)
        x = self._map(raw_x, self._horizontal_start, self._horizontal_end)
        y = self._map(raw_y, self._vertical_start, self._vertical_end)
        self._missing = 0
        self._horizontal.append(x)
        self._vertical.append(y)
        target_x, target_y = median(self._horizontal), median(self._vertical)
        if self._smoothed is None:
            current_x, current_y = target_x, target_y
        else:
            previous_x, previous_y = self._smoothed
            current_x = previous_x if abs(target_x - previous_x) < 0.01 else 0.18 * target_x + 0.82 * previous_x
            current_y = previous_y if abs(target_y - previous_y) < 0.01 else 0.18 * target_y + 0.82 * previous_y
        self._smoothed = current_x, current_y
        return EyeGazeResult(True, current_x, current_y, raw_x, raw_y)

    def _not_detected(self) -> EyeGazeResult:
        self._missing += 1
        position = self._smoothed or (0.5, 0.5)
        if self._missing >= 15:
            self.reset()
        return EyeGazeResult(False, *position)

    @staticmethod
    def _map(value: float, start: float, end: float) -> float:
        return max(0.0, min(1.0, (value - start) / (end - start)))
