"""Camera thread with MediaPipe, calibrated gestures, gaze and automatic contrast."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, replace

import cv2
import mediapipe as mp
import numpy as np

os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)

from mediapipe.tasks.python import BaseOptions, vision
from mediapipe.tasks.python.vision import drawing_styles, drawing_utils
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

from control import (
    EyeGazeResult,
    EyeGazeTracker,
    FaceSignalExtractor,
    FaceSignals,
    GestureConfig,
    GestureInterpreter,
    GestureResult,
)


MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos", "face_landmarker.task")
DELEGATE = BaseOptions.Delegate.GPU if sys.platform == "darwin" else BaseOptions.Delegate.CPU
CAMERA_INDEX = 1
CALIBRATION_SAMPLES = 90


@dataclass(frozen=True)
class CameraFrame:
    image: QImage
    face_detected: bool
    fps: float
    signals: FaceSignals
    gesture: GestureResult
    gaze: EyeGazeResult
    clahe_clip: float
    calibration_remaining: int


class HiloCamara(QThread):
    """Reads camera index 1 and runs all vision processing outside the UI thread."""

    frame_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.index = CAMERA_INDEX
        self.cap = cv2.VideoCapture(self.index)
        self.extractor = FaceSignalExtractor()
        self.interpreter = GestureInterpreter(GestureConfig())
        self.gaze_tracker = EyeGazeTracker()
        self.calibration_remaining = CALIBRATION_SAMPLES
        self.extractor.reset_calibration()
        self.contrast_auto = True
        self.current_clahe_clip = 0.0
        self.target_clahe_clip = 0.0
        self._last_light_analysis = 0.0
        self._recalibration_requested = False

    def request_calibration(self) -> None:
        self._recalibration_requested = True

    def set_contrast_auto(self, enabled: bool) -> None:
        self.contrast_auto = enabled
        if not enabled:
            self.target_clahe_clip = 0.0

    def set_wide_ranges(self, enabled: bool) -> None:
        if enabled:
            self.interpreter.config = replace(
                self.interpreter.config,
                yaw_enter=0.17,
                yaw_exit=0.10,
                pitch_enter=0.27,
                pitch_exit=0.16,
                mouth_enter=0.12,
                mouth_exit=0.07,
            )
        else:
            self.interpreter.config = replace(
                self.interpreter.config,
                yaw_enter=0.12,
                yaw_exit=0.07,
                pitch_enter=0.20,
                pitch_exit=0.12,
                mouth_enter=0.08,
                mouth_exit=0.04,
            )
        self.interpreter.reset()

    def set_mouth_enabled(self, enabled: bool) -> None:
        self.interpreter.config = replace(self.interpreter.config, enable_mouth=enabled)
        self.interpreter.reset()

    def set_gaze_calibration(
        self,
        horizontal_start: float,
        horizontal_end: float,
        vertical_start: float,
        vertical_end: float,
    ) -> None:
        self.gaze_tracker.set_calibration(
            horizontal_start,
            horizontal_end,
            vertical_start,
            vertical_end,
        )

    def run(self) -> None:
        if not self.cap.isOpened():
            self.error.emit(f"No se pudo abrir la camara {self.index}.")
            return
        try:
            self._process()
        except Exception as error:
            self.error.emit(f"Error de vision: {error}")
        finally:
            self.cap.release()

    def _process(self) -> None:
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH, delegate=DELEGATE),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        with vision.FaceLandmarker.create_from_options(options) as detector:
            timestamp_ms = 0
            previous = time.monotonic()

            while not self.isInterruptionRequested():
                ok, bgr = self.cap.read()
                if not ok:
                    self.error.emit("La camara dejo de enviar imagen")
                    break

                if self._recalibration_requested:
                    self.extractor.reset_calibration()
                    self.interpreter.reset()
                    self.gaze_tracker.reset()
                    self.calibration_remaining = CALIBRATION_SAMPLES
                    self._recalibration_requested = False

                processed = self._apply_automatic_contrast(bgr)
                rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
                timestamp_ms = max(timestamp_ms + 1, int(time.monotonic() * 1000))
                image = mp.Image(
                    image_format=mp.ImageFormat.SRGBA,
                    data=cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA),
                )
                result = detector.detect_for_video(image, timestamp_ms)
                landmarks = result.face_landmarks[0] if result.face_landmarks else None

                if self.calibration_remaining > 0 and self.extractor.add_calibration_sample(landmarks):
                    self.calibration_remaining -= 1
                    if self.calibration_remaining == 0:
                        self.extractor.finish_calibration()
                        self.interpreter.reset()
                        self.gaze_tracker.reset()

                signals = self.extractor.extract(landmarks)
                gesture = self.interpreter.update(signals, timestamp_ms)
                gaze = self.gaze_tracker.extract(landmarks)

                if landmarks:
                    drawing_utils.draw_landmarks(
                        rgb,
                        landmarks,
                        vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=drawing_styles.get_default_face_mesh_tesselation_style(),
                    )

                display_rgb = cv2.flip(rgb, 1)
                now = time.monotonic()
                fps = 1.0 / max(now - previous, 1e-6)
                previous = now
                height, width, _ = display_rgb.shape
                qt_image = QImage(
                    display_rgb.data,
                    width,
                    height,
                    3 * width,
                    QImage.Format_RGB888,
                ).copy()
                self.frame_ready.emit(
                    CameraFrame(
                        qt_image,
                        landmarks is not None,
                        fps,
                        signals,
                        gesture,
                        gaze,
                        self.current_clahe_clip,
                        self.calibration_remaining,
                    )
                )

    def _apply_automatic_contrast(self, frame: np.ndarray) -> np.ndarray:
        now = time.monotonic()
        if now - self._last_light_analysis >= 2.0:
            self.target_clahe_clip = self._select_clahe_clip(frame) if self.contrast_auto else 0.0
            self._last_light_analysis = now

        self.current_clahe_clip = self._approach(
            self.current_clahe_clip,
            self.target_clahe_clip,
            0.05,
        )
        if self.current_clahe_clip <= 0.01:
            return frame

        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        y, cr, cb = cv2.split(ycrcb)
        y = cv2.createCLAHE(clipLimit=self.current_clahe_clip, tileGridSize=(8, 8)).apply(y)
        return cv2.cvtColor(cv2.merge((y, cr, cb)), cv2.COLOR_YCrCb2BGR)

    @staticmethod
    def _select_clahe_clip(frame: np.ndarray) -> float:
        luminance = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)[:, :, 0]
        mean_luma = float(np.mean(luminance))
        contrast = float(np.std(luminance))
        bright_ratio = float(np.mean(luminance > 230))
        if bright_ratio > 0.25:
            return 0.0
        if contrast < 25.0:
            return 2.5
        if contrast < 35.0:
            return 1.8
        if mean_luma < 75.0:
            return 1.5
        return 0.0

    @staticmethod
    def _approach(current: float, target: float, step: float) -> float:
        if abs(target - current) <= step:
            return target
        return current + step if target > current else current - step
