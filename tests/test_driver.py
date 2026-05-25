import json
import math
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from wavedriver.motor_controller import MotorController, ControllerState
from wavedriver import patterns
from wavedriver.main import _pattern_peak_speed_um_s


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wait_for_state(mc: MotorController, target_state: ControllerState, timeout: float) -> bool:
    """Poll until the controller reaches the target state or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if mc.get_telemetry()["state_enum"] == target_state:
            return True
        time.sleep(0.05)
    return False


def _wait_connected(mc: MotorController, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = mc.get_telemetry()["state_enum"]
        if s not in (ControllerState.UNCONNECTED, ControllerState.CONNECTING):
            return True
        time.sleep(0.05)
    return False


# ── Pattern unit tests ────────────────────────────────────────────────────────

class TestPatterns(unittest.TestCase):
    """Verifies pleasure waveform mathematical correctness."""

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
        self.assertGreater(val, self.L / 2.0)

    def test_wave_stays_within_stroke(self):
        C = self.L / 2.0
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
        C = self.L / 2.0
        A = min(100000.0 / 2.0, C - 5000.0)
        for phase in [i * 0.05 for i in range(130)]:
            _, val = self._call(patterns.tease_pattern, phase=phase)
            self.assertGreaterEqual(val, C - A - 1.0, f"tease below floor at phase={phase:.2f}")
            self.assertLessEqual(val, C + A + 1.0, f"tease above ceiling at phase={phase:.2f}")

    def test_soft_start_ramp(self):
        _, val = patterns.wave_pattern(
            0.0, int(self.L / 2), 0.0, self.L,
            stroke_length_um=100000, frequency_hz=1.0,
            _amplitude_scale=0.0, _phase=math.pi / 2,
        )
        self.assertAlmostEqual(val, self.L / 2.0, delta=1.0)

    def test_depth_returns_position(self):
        mode, _ = self._call(patterns.depth_pattern, phase=0.0, depth_period_s=20.0)
        self.assertEqual(mode, "position")

    def test_depth_near_end_fixed(self):
        """Near end (position at sine trough) should be the same across depth_mod variations."""
        L = self.L
        C = L / 2.0
        A = min(100000.0 / 2.0, C - 5000.0)
        near_end = C - A  # expected constant retracted position

        # Sample at trough (phase = -π/2 = 3π/2) across different slow_phase values.
        # depth_period_s=20, frequency_hz=1 → edge_period_cycles=20.
        # Carrier cycles elapsed = _phase / (2π).
        trough_phase = 3.0 * math.pi / 2.0  # sin(phase) = -1
        for slow_cycle_fraction in [0.0, 0.25, 0.5, 0.75]:
            # Choose _phase so slow_phase lands at desired fraction of depth cycle.
            # slow_phase = 2π * carrier_cycles / (depth_period_s * freq) → carrier_cycles = fraction * depth_period_s * freq
            depth_period_s = 20.0
            carrier_cycles_for_slow = slow_cycle_fraction * depth_period_s * 1.0
            base_phase = carrier_cycles_for_slow * 2.0 * math.pi
            # Add trough_phase offset; use modular arithmetic to keep phase reasonable
            phase = base_phase + trough_phase
            _, val = patterns.depth_pattern(
                0.0, int(L / 2), 0.0, L,
                stroke_length_um=100000, frequency_hz=1.0,
                _amplitude_scale=1.0, _phase=phase, depth_period_s=depth_period_s,
            )
            self.assertAlmostEqual(val, near_end, delta=500.0,
                                   msg=f"near end drifted at slow_cycle={slow_cycle_fraction}")

    def test_edge_envelope_freezes_with_phase(self):
        """Edge envelope position must be determined solely by _phase, not t."""
        # Same _phase → same envelope position regardless of what t is.
        phase = 3.5  # arbitrary mid-cycle phase
        _, val1 = patterns.edge_pattern(
            t=0.0, position_um=75000, speed_mm_s=0.0, L=self.L,
            stroke_length_um=100000, frequency_hz=1.0, edge_period_s=60.0,
            _amplitude_scale=1.0, _phase=phase,
        )
        _, val2 = patterns.edge_pattern(
            t=999.0, position_um=75000, speed_mm_s=0.0, L=self.L,
            stroke_length_um=100000, frequency_hz=1.0, edge_period_s=60.0,
            _amplitude_scale=1.0, _phase=phase,
        )
        self.assertAlmostEqual(val1, val2, delta=1.0,
                               msg="edge envelope should depend on _phase, not t")


# ── Peak speed formula tests ──────────────────────────────────────────────────

class TestPatternPeakSpeed(unittest.TestCase):
    """Verifies that _pattern_peak_speed_um_s returns correct per-pattern values."""

    def test_wave_sine_formula(self):
        # π * f * A = π * 1.0 * 50000
        speed = _pattern_peak_speed_um_s("Wave", 100000, 1.0)
        self.assertAlmostEqual(speed, math.pi * 50000.0, delta=1.0)

    def test_thrust_fast_stroke(self):
        # 2A / 0.2 * f = 2*50000 / 0.2 * 1.0 = 500000
        speed = _pattern_peak_speed_um_s("Thrust", 100000, 1.0)
        self.assertAlmostEqual(speed, 500000.0, delta=1.0)

    def test_pulse_faster_than_wave(self):
        wave  = _pattern_peak_speed_um_s("Wave",  100000, 1.0)
        pulse = _pattern_peak_speed_um_s("Pulse", 100000, 1.0)
        self.assertGreater(pulse, wave)

    def test_thrust_faster_than_wave(self):
        wave   = _pattern_peak_speed_um_s("Wave",   100000, 1.0)
        thrust = _pattern_peak_speed_um_s("Thrust", 100000, 1.0)
        self.assertGreater(thrust, wave)

    def test_realistic_faster_than_wave(self):
        wave      = _pattern_peak_speed_um_s("Wave",      100000, 1.0)
        realistic = _pattern_peak_speed_um_s("Realistic", 100000, 1.0)
        self.assertGreater(realistic, wave)

    def test_scales_linearly_with_frequency(self):
        s1 = _pattern_peak_speed_um_s("Wave", 100000, 1.0)
        s2 = _pattern_peak_speed_um_s("Wave", 100000, 2.0)
        self.assertAlmostEqual(s2 / s1, 2.0, places=5)

    def test_scales_linearly_with_stroke(self):
        s1 = _pattern_peak_speed_um_s("Wave", 100000, 1.0)
        s2 = _pattern_peak_speed_um_s("Wave", 200000, 1.0)
        self.assertAlmostEqual(s2 / s1, 2.0, places=5)

    def test_zero_frequency_clamped(self):
        speed = _pattern_peak_speed_um_s("Wave", 100000, 0.0)
        self.assertGreater(speed, 0.0)

    def test_tease_escalate_edge_use_sine_formula(self):
        for name in ("Tease", "Escalate", "Edge"):
            with self.subTest(pattern=name):
                speed = _pattern_peak_speed_um_s(name, 100000, 1.0)
                expected = math.pi * 50000.0
                self.assertAlmostEqual(speed, expected, delta=1.0)


# ── Safety-limit clamping tests ───────────────────────────────────────────────

class TestSafetyLimitClamping(unittest.TestCase):
    """Verifies that the controller enforces safety limit clamps."""

    def setUp(self):
        self.mc = MotorController(use_mock=True)
        self.mc.start(port="mock", baud=115200)

    def tearDown(self):
        self.mc.stop()

    def test_zero_limit_clamped_to_minimum(self):
        _wait_connected(self.mc)
        self.mc.send_command("set_safety_limit", limit_mN=0)
        time.sleep(0.1)
        self.assertGreaterEqual(self.mc.get_telemetry()["max_feedback_force_mN"], 1000)

    def test_negative_limit_clamped_to_minimum(self):
        _wait_connected(self.mc)
        self.mc.send_command("set_safety_limit", limit_mN=-5000)
        time.sleep(0.1)
        self.assertGreaterEqual(self.mc.get_telemetry()["max_feedback_force_mN"], 1000)

    def test_valid_limit_applied(self):
        _wait_connected(self.mc)
        self.mc.send_command("set_safety_limit", limit_mN=30000)
        time.sleep(0.1)
        self.assertEqual(self.mc.get_telemetry()["max_feedback_force_mN"], 30000)

    def test_missing_kwarg_uses_default(self):
        _wait_connected(self.mc)
        self.mc.send_command("set_safety_limit")
        time.sleep(0.1)
        self.assertEqual(self.mc.get_telemetry()["max_feedback_force_mN"], 55000)


# ── Session persistence tests ─────────────────────────────────────────────────

class TestSessionClamping(unittest.TestCase):
    """Verifies session file loading and saving (safety settings only)."""

    def _make_app(self, session_data: dict):
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

    def test_safety_force_loaded_and_clamped(self):
        app = self._make_app({"safety_force_n": 999.0})
        self.assertLessEqual(app.safety_force_n, 60.0)

    def test_safety_force_low_clamped(self):
        app = self._make_app({"safety_force_n": -5.0})
        self.assertGreaterEqual(app.safety_force_n, 5.0)

    def test_max_session_loaded(self):
        app = self._make_app({"max_session_s": 1800})
        self.assertEqual(app.max_session_s, 1800)

    def test_max_session_clamped_high(self):
        app = self._make_app({"max_session_s": 99999})
        self.assertLessEqual(app.max_session_s, 7200)

    def test_max_session_zero_allowed(self):
        app = self._make_app({"max_session_s": 0})
        self.assertEqual(app.max_session_s, 0)

    def test_motion_params_not_in_session(self):
        """pattern_name, frequency_hz, stroke etc. must not be returned by load_session."""
        app = self._make_app({
            "pattern_name": "Thrust", "frequency_hz": 2.0, "stroke_length_mm": 80.0,
            "safety_force_n": 40.0,
        })
        self.assertFalse(hasattr(app, "pattern_name"))
        self.assertFalse(hasattr(app, "frequency_hz"))
        self.assertFalse(hasattr(app, "stroke_length_mm"))

    def test_save_session_only_writes_safety_fields(self):
        from wavedriver import main as main_module
        mc = MotorController(use_mock=True)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            with patch.object(main_module, "SESSION_FILE", tmp_path):
                api = main_module.WebviewAPI(controller=mc, initial_safety_limit_N=55.0)
                api.save_session({
                    "safety_force_n": 40.0,
                    "max_session_s": 600,
                    "pattern_name": "Thrust",
                    "frequency_hz": 2.0,
                    "calibrated_length_um": 120000,
                })
                saved = json.loads(tmp_path.read_text())
                self.assertIn("safety_force_n", saved)
                self.assertIn("max_session_s", saved)
                self.assertNotIn("pattern_name", saved)
                self.assertNotIn("frequency_hz", saved)
                self.assertNotIn("calibrated_length_um", saved)
        finally:
            tmp_path.unlink(missing_ok=True)


# ── Pause / resume tests ──────────────────────────────────────────────────────

class TestPauseResume(unittest.TestCase):
    """Verifies pause and resume behaviour after calibration."""

    @classmethod
    def setUpClass(cls):
        cls.mc = MotorController(use_mock=True)
        cls.mc.start(port="mock", baud=115200)
        cls.mc.send_command("start_calibration")
        ok = _wait_for_state(cls.mc, ControllerState.CALIBRATED_IDLE, timeout=20.0)
        if not ok:
            raise RuntimeError("Calibration did not complete in setUpClass")

    @classmethod
    def tearDownClass(cls):
        cls.mc.stop()

    def _start_wave(self):
        self.mc.send_command(
            "start_pattern",
            pattern_func=patterns.wave_pattern,
            params={"stroke_length_um": 40000, "frequency_hz": 1.0},
        )
        _wait_for_state(self.mc, ControllerState.RUNNING, timeout=2.0)

    def _soft_stop(self):
        self.mc.send_command("soft_stop")
        _wait_for_state(self.mc, ControllerState.CALIBRATED_IDLE, timeout=5.0)

    def test_pause_sets_paused_flag(self):
        self._start_wave()
        self.mc.send_command("pause_pattern")
        time.sleep(0.15)
        self.assertTrue(self.mc.get_telemetry()["paused"])
        self._soft_stop()

    def test_resume_clears_paused_flag(self):
        self._start_wave()
        self.mc.send_command("pause_pattern")
        time.sleep(0.15)
        self.mc.send_command("resume_pattern")
        time.sleep(0.15)
        self.assertFalse(self.mc.get_telemetry()["paused"])
        self._soft_stop()

    def test_soft_stop_returns_to_idle(self):
        self._start_wave()
        self.mc.send_command("soft_stop")
        reached = _wait_for_state(self.mc, ControllerState.CALIBRATED_IDLE, timeout=5.0)
        self.assertTrue(reached, "soft_stop did not return to CALIBRATED_IDLE within 5 s")

    def test_amplitude_ramp_limits_commanded_pos(self):
        """Commanded position must not jump beyond _max_pattern_speed_um_s * dt per tick at startup."""
        self._start_wave()
        # Give the rate limiter one control tick to execute, then read commanded pos from telemetry.
        # We verify indirectly: position must not have jumped from mock's start (75mm) to center
        # instantaneously. After 50 ms at most 500*50 = 25 000 µm movement should have occurred.
        time.sleep(0.05)
        tel = self.mc.get_telemetry()
        # The mock starts at 75 000 µm (mid-stroke). If rate limiting is working, position
        # shouldn't have moved more than a moderate amount from the initial mock position.
        self.assertLessEqual(abs(tel["position_um"] - 75000), 30000,
                             "Motor moved too far in 50 ms — catch-up rate limiter may be broken")
        self._soft_stop()


# ── Integration test (requires mock calibration cycle) ───────────────────────

class TestCalibrationAndSafety(unittest.TestCase):
    """Integration test verifying calibration transitions and E-STOP safety trigger."""

    def test_calibration_and_safety(self):
        mc = MotorController(use_mock=True)
        self.assertEqual(mc.state, ControllerState.UNCONNECTED)

        mc.start(port="mock", baud=115200)

        connected = _wait_for_state(mc, ControllerState.CONNECTED, timeout=3.0)
        self.assertTrue(connected, "Controller did not reach CONNECTED state")

        mc.send_command("start_calibration")

        # Mock runs at 80 mm/s; retract + stall detect + extend + stall detect + centering
        # takes ~8-10 s; allow 20 s to be safe while still failing fast.
        calibrated = _wait_for_state(mc, ControllerState.CALIBRATED_IDLE, timeout=20.0)
        self.assertTrue(calibrated, f"Calibration failed; state is: {mc.state}")

        tel = mc.get_telemetry()
        self.assertEqual(tel["calibrated_length_um"], 150000)

        mc.send_command(
            "start_pattern",
            pattern_func=patterns.wave_pattern,
            params={"stroke_length_um": 40000, "frequency_hz": 1.5},
        )
        running = _wait_for_state(mc, ControllerState.RUNNING, timeout=2.0)
        self.assertTrue(running)

        # Debounce requires 3 consecutive 20 Hz samples over threshold (~150 ms).
        mc.send_command("set_safety_limit", limit_mN=1)
        estop = _wait_for_state(mc, ControllerState.ESTOP, timeout=2.0)
        self.assertTrue(estop, "E-STOP did not trigger after force limit breach")
        self.assertIn("Safety Force", mc.get_telemetry()["error_msg"])

        mc.stop()


if __name__ == "__main__":
    unittest.main()
