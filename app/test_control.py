import unittest

from control import (
    ControlEvent,
    ControlState,
    ControlStateMachine,
    EyeGazeTracker,
    FaceSignalExtractor,
    GestureIntent,
    GestureInterpreter,
    MotionCommand,
    fit_gaze_axis,
)


class Landmark:
    def __init__(self, x=0.5, y=0.5):
        self.x = x
        self.y = y


class ControlTest(unittest.TestCase):
    def test_state_machine_stops_when_face_is_lost(self):
        fsm = ControlStateMachine()
        fsm.update("CENTER", ControlEvent.ENABLE)
        self.assertEqual(fsm.update("UP").command, MotionCommand.FORWARD)

        lost = fsm.update("NO_FACE")
        self.assertEqual(lost.state, ControlState.WAITING)
        self.assertEqual(lost.command, MotionCommand.STOP)

    def test_emergency_is_latched(self):
        fsm = ControlStateMachine()
        fsm.update("CENTER", ControlEvent.EMERGENCY)
        self.assertEqual(fsm.update("CENTER", ControlEvent.ENABLE).state, ControlState.EMERGENCY)
        self.assertEqual(fsm.update("CENTER", ControlEvent.RESET_EMERGENCY).state, ControlState.WAITING)

    def test_calibration_and_stable_gesture(self):
        landmarks = self._face()
        extractor = FaceSignalExtractor()
        extractor.reset_calibration()
        for _ in range(10):
            self.assertTrue(extractor.add_calibration_sample(landmarks))
        self.assertTrue(extractor.finish_calibration())

        interpreter = GestureInterpreter()
        signals = extractor.extract(landmarks)
        result = interpreter.update(signals, 1000)
        result = interpreter.update(signals, 1200)
        self.assertEqual(result.intent, GestureIntent.CENTER)

    def test_gaze_tracks_down_and_rejects_blink(self):
        landmarks = [Landmark() for _ in range(478)]
        self._eye(landmarks, 468, 33, 133, 159, 145, 0.40, 0.50)
        self._eye(landmarks, 473, 362, 263, 386, 374, 0.50, 0.60)
        tracker = EyeGazeTracker()
        self.assertTrue(tracker.extract(landmarks).detected)

        landmarks[468].y = landmarks[473].y = 0.51
        down = None
        for _ in range(12):
            down = tracker.extract(landmarks)
        self.assertGreater(down.y, 0.70)

        landmarks[145].y = landmarks[159].y
        self.assertFalse(tracker.extract(landmarks).detected)

    def test_full_screen_gaze_calibration(self):
        horizontal_start, horizontal_end = fit_gaze_axis(
            [(0.60, 0.1), (0.50, 0.5), (0.40, 0.9)]
        )
        self.assertAlmostEqual(horizontal_start, 0.625, places=3)
        self.assertAlmostEqual(horizontal_end, 0.375, places=3)

        landmarks = [Landmark() for _ in range(478)]
        self._eye(landmarks, 468, 33, 133, 159, 145, 0.40, 0.50)
        self._eye(landmarks, 473, 362, 263, 386, 374, 0.50, 0.60)
        landmarks[468].x = 0.46
        landmarks[473].x = 0.56
        tracker = EyeGazeTracker()
        tracker.set_calibration(0.60, 0.40, -0.10, 0.10)
        self.assertAlmostEqual(tracker.extract(landmarks).x, 0.0, places=2)

        tracker.reset()
        landmarks[468].x = 0.44
        landmarks[473].x = 0.54
        self.assertAlmostEqual(tracker.extract(landmarks).x, 1.0, places=2)

    @staticmethod
    def _face():
        landmarks = [Landmark() for _ in range(478)]
        landmarks[33] = Landmark(0.4, 0.4)
        landmarks[263] = Landmark(0.6, 0.4)
        landmarks[1] = Landmark(0.5, 0.5)
        landmarks[13] = Landmark(0.48, 0.6)
        landmarks[14] = Landmark(0.48, 0.61)
        return landmarks

    @staticmethod
    def _eye(landmarks, iris, corner_a, corner_b, upper, lower, left, right):
        center = (left + right) / 2
        landmarks[corner_a] = Landmark(left, 0.5)
        landmarks[corner_b] = Landmark(right, 0.5)
        landmarks[upper] = Landmark(center, 0.48)
        landmarks[lower] = Landmark(center, 0.52)
        landmarks[iris] = Landmark(center, 0.5)


if __name__ == "__main__":
    unittest.main()
