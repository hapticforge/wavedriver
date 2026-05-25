import json
import math
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from wavedriver.motor_controller import MotorController, ControllerState
from wavedriver import patterns


# ── Pattern unit tests ────────────────────────────────────────────────────────

class TestPatterns(unittest.TestCase):
    """Verifies pleasure waveform mathematical correctness.

    Tests wave centers, peak offsets, stroke bounds, and soft-start scaling without requiring hardware.
    """

    L = 150000.0  # 150 mm stroke

    def _call(self, fn, phase, **extra):
        return fn(0.0, int(self.L / 2), 0.0, self.L,
                  stroke_length_um=100000, frequency_hz=1.0,
                  _amplitude_scale=1.0, _phase=phase, **extra)

    def test_wave_center_at_zero_phase(self):
        mode, val = self._call(patterns.wave_pattern, phase=0.0)
        self.assertEqual(mode, "position")
        self.assertAlmostEqual(val, self.L / 2.0, delta=1.0)

    def test_wave_peak_at_quarter_cycle(self):
        mode, val = self._call(patterns.wave_pattern, phase=math.pi / 2)
        self.assertEqual(mode, "position")
        # Should be near center + half stroke
        self.assertGreater(val, self.L / 2.0)

    def test_wave_stays_within_stroke(self):
        C = self.L / 2.0
        # Pattern radius: min(stroke_length_um/2, C-5000) = min(50000, 70000) = 50000
        A = min(100000.0 / 2.0, C - 5000.0)
        for phase in [i * 0.1 for i in range(63)]:
            _, val = self._call(patterns.wave_pattern, phase=phase)
            self.assertGreaterEqual(val, C - A - 1.0)
            self.assertLessEqual(val, C + A + 1.0)

    def test_realistic_returns_position(self):
        mode, _ = self._call(patterns.realistic_pattern, phase=0.0, rod_ratio=2.5)
        self.assertEqual(mode, "position")

    def test_thrust_returns_position(self):
        mode, _ = self._call(patterns.thrust_pattern, phase=0.0)
        self.assertEqual(mode, "position")

    def test_tease_stays_within_stroke(self):
        """Clamped combined waveform must never exceed stroke bounds."""
        C = self.L / 2.0
        A = min(100000.0 / 2.0, C - 5000.0)  # same formula as the pattern
        for phase in [i * 0.05 for i in range(130)]:
            _, val = self._call(patterns.tease_pattern, phase=phase)
            self.assertGreaterEqual(val, C - A - 1.0, f"tease below floor at phase={phase:.2f}")
            self.assertLessEqual(val, C + A + 1.0, f"tease above ceiling at phase={phase:.2f}")

    def test_soft_start_ramp(self):
        """Pattern output at scale=0.0 must be at center (zero amplitude)."""
        _, val = patterns.wave_pattern(
            0.0, int(self.L / 2), 0.0, self.L,
            stroke_length_um=100000, frequency_hz=1.0,
            _amplitude_scale=0.0, _phase=math.pi / 2,
        )
        self.assertAlmostEqual(val, self.L / 2.0, delta=1.0)


# ── Safety-limit clamping tests ───────────────────────────────────────────────

class TestSafetyLimitClamping(unittest.TestCase):
    """Verifies that the controller enforces safety limit clamps.

    Ensures that safety limits are clamped to at least 1 Newton, even if configured with zero, negative,
    or missing parameters.
    """

    def setUp(self):
        self.mc = MotorController(use_mock=True)
        self.mc.start(port="mock", baud=115200)

    def tearDown(self):
        self.mc.stop()

    def _wait_connected(self, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.mc.get_telemetry()["state_enum"] != ControllerState.CONNECTING:
                return True
            time.sleep(0.05)
        return False

    def test_zero_limit_clamped_to_minimum(self):
        self._wait_connected()
        self.mc.send_command("set_safety_limit", limit_mN=0)
        time.sleep(0.1)
        tel = self.mc.get_telemetry()
        self.assertGreaterEqual(tel["max_feedback_force_mN"], 1000,
                                "Safety limit must be clamped to at least 1 N")

    def test_negative_limit_clamped_to_minimum(self):
        self._wait_connected()
        self.mc.send_command("set_safety_limit", limit_mN=-5000)
        time.sleep(0.1)
        tel = self.mc.get_telemetry()
        self.assertGreaterEqual(tel["max_feedback_force_mN"], 1000)

    def test_valid_limit_applied(self):
        self._wait_connected()
        self.mc.send_command("set_safety_limit", limit_mN=30000)
        time.sleep(0.1)
        tel = self.mc.get_telemetry()
        self.assertEqual(tel["max_feedback_force_mN"], 30000)

    def test_missing_kwarg_uses_default(self):
        """Omitting limit_mN must not silently set limit to an arbitrary value."""
        self._wait_connected()
        original = self.mc.get_telemetry()["max_feedback_force_mN"]
        self.mc.send_command("set_safety_limit")  # no limit_mN kwarg
        time.sleep(0.1)
        tel = self.mc.get_telemetry()
        # Default fallback in _process_command is 55000; must not be 20000
        self.assertEqual(tel["max_feedback_force_mN"], 55000,
                         "Missing limit_mN kwarg must fall back to 55 N, not 20 N")


# ── Session persistence tests ─────────────────────────────────────────────────

class TestSessionClamping(unittest.TestCase):
    """Verifies session file loading and validation.

    Ensures out-of-bounds frequency, stroke, or invalid pattern name inputs are correctly clamped to safe default ranges.
    """

    def _make_app(self, session_data: dict):
        """Create a WebviewAPI pointed at a temp session file, loading and returning session dict as namespace."""
        from wavedriver import main as main_module
        from wavedriver.motor_controller import MotorController
        import types

        mc = MotorController(use_mock=True)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(session_data, f)
            tmp_path = Path(f.name)

        with patch.object(main_module, "SESSION_FILE", tmp_path):
            api = main_module.WebviewAPI(controller=mc, initial_safety_limit_N=55.0)
            session = api.load_session()

        tmp_path.unlink(missing_ok=True)
        return types.SimpleNamespace(**session)

    def test_frequency_clamped_low(self):
        app = self._make_app({"frequency_hz": -10.0})
        self.assertGreaterEqual(app.frequency_hz, 0.1)

    def test_frequency_clamped_high(self):
        app = self._make_app({"frequency_hz": 999.0})
        self.assertLessEqual(app.frequency_hz, 3.0)

    def test_stroke_clamped_low(self):
        app = self._make_app({"stroke_length_mm": 0.0})
        self.assertGreaterEqual(app.stroke_length_mm, 10.0)

    def test_stroke_clamped_high(self):
        app = self._make_app({"stroke_length_mm": 9999.0})
        self.assertLessEqual(app.stroke_length_mm, 150.0)

    def test_invalid_pattern_name_ignored(self):
        app = self._make_app({"pattern_name": "Turbo Laser"})
        self.assertIn(app.pattern_name, {"Wave", "Realistic", "Thrust", "Pulse", "Tease", "Escalate", "Edge"})

    def test_legacy_slider_crank_migrated(self):
        app = self._make_app({"pattern_name": "Slider-Crank"})
        self.assertEqual(app.pattern_name, "Realistic")


# ── Integration test (slow — requires mock calibration cycle) ─────────────────

class TestCalibrationAndSafety(unittest.TestCase):
    """Integration tests verifying calibration transitions and emergency shutdown (E-STOP) triggers.

    Mocks a full startup, calibration homing cycle, pattern playback, and verifies the safety debounce 
    system triggers an E-STOP state when force limits are exceeded.
    """

    def test_calibration_and_safety(self):
        # 1. Initialize controller in mock mode
        mc = MotorController(use_mock=True)
        self.assertEqual(mc.state, ControllerState.UNCONNECTED)

        mc.start(port="mock", baud=115200)

        # After start the controller transitions to CONNECTED (uncalibrated)
        connected = False
        deadline = time.time() + 3.0
        while time.time() < deadline:
            time.sleep(0.05)
            if mc.get_telemetry()["state_enum"] == ControllerState.CONNECTED:
                connected = True
                break
        self.assertTrue(connected, "Controller did not reach CONNECTED state")

        # Calibration does not auto-start; send the command as the TUI would.
        mc.send_command("start_calibration")

        # 2. Wait for calibration to complete.
        # At 80 mm/s: ~1s retract + ~2s extend + stall settle windows + centering.
        # Allow 65s to be safe.
        calibrated = False
        deadline = time.time() + 65.0
        while time.time() < deadline:
            time.sleep(0.5)
            tel = mc.get_telemetry()
            if tel["state_enum"] == ControllerState.CALIBRATED_IDLE:
                calibrated = True
                break

        self.assertTrue(calibrated, f"Calibration failed, current state is: {mc.state}")

        # Check calibrated values
        tel = mc.get_telemetry()
        self.assertEqual(tel["calibrated_length_um"], 150000)

        # 3. Test active pattern start
        mc.send_command("start_pattern",
                        pattern_func=patterns.wave_pattern,
                        params={"stroke_length_um": 40000, "frequency_hz": 1.5})
        time.sleep(0.2)
        tel = mc.get_telemetry()
        self.assertEqual(tel["state_enum"], ControllerState.RUNNING)

        # Test safety trigger: set limit to 0 mN (controller clamps to 1 N minimum,
        # so we use a tiny value that any running force will exceed).
        mc.send_command("set_safety_limit", limit_mN=1)

        # Debounce requires 3 consecutive 20 Hz samples over threshold (~150 ms).
        # Wait 500 ms to give the controller enough time to trip.
        time.sleep(0.5)
        tel = mc.get_telemetry()
        self.assertEqual(tel["state_enum"], ControllerState.ESTOP)
        self.assertIn("Safety Force", tel["error_msg"])

        mc.stop()


if __name__ == "__main__":
    unittest.main()
