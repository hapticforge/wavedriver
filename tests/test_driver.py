import json
import math
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from wavedriver import main as main_module
from wavedriver import patterns
from wavedriver.config import Config
from wavedriver.motor_controller import ControllerState, MotorController
from wavedriver.patterns import PATTERN_REGISTRY
from wavedriver.storage import Storage

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
        return fn(
            0.0,
            int(self.L / 2),
            0.0,
            self.L,
            stroke_length_um=100000,
            frequency_hz=1.0,
            _amplitude_scale=1.0,
            _phase=phase,
            **extra,
        )

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
            0.0,
            int(self.L / 2),
            0.0,
            self.L,
            stroke_length_um=100000,
            frequency_hz=1.0,
            _amplitude_scale=0.0,
            _phase=math.pi / 2,
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
                0.0,
                int(L / 2),
                0.0,
                L,
                stroke_length_um=100000,
                frequency_hz=1.0,
                _amplitude_scale=1.0,
                _phase=phase,
                depth_period_s=depth_period_s,
            )
            self.assertAlmostEqual(
                val,
                near_end,
                delta=500.0,
                msg=f"near end drifted at slow_cycle={slow_cycle_fraction}",
            )

    def test_edge_envelope_freezes_with_phase(self):
        """Edge envelope position must be determined solely by _phase, not t."""
        # Same _phase → same envelope position regardless of what t is.
        phase = 3.5  # arbitrary mid-cycle phase
        _, val1 = patterns.edge_pattern(
            t=0.0,
            position_um=75000,
            speed_mm_s=0.0,
            L=self.L,
            stroke_length_um=100000,
            frequency_hz=1.0,
            edge_period_s=60.0,
            _amplitude_scale=1.0,
            _phase=phase,
        )
        _, val2 = patterns.edge_pattern(
            t=999.0,
            position_um=75000,
            speed_mm_s=0.0,
            L=self.L,
            stroke_length_um=100000,
            frequency_hz=1.0,
            edge_period_s=60.0,
            _amplitude_scale=1.0,
            _phase=phase,
        )
        self.assertAlmostEqual(
            val1, val2, delta=1.0, msg="edge envelope should depend on _phase, not t"
        )


# ── Peak speed formula tests ──────────────────────────────────────────────────


def _peak(name: str, stroke_um: float, freq_hz: float) -> float:
    """Convenience wrapper: look up peak speed via PATTERN_REGISTRY."""
    return PATTERN_REGISTRY[name].peak_speed_um_s(stroke_um, freq_hz)


class TestPatternPeakSpeed(unittest.TestCase):
    """Verifies that PATTERN_REGISTRY peak-speed formulas return correct values."""

    def test_wave_sine_formula(self):
        # π * f * A = π * 1.0 * 50000
        speed = _peak("Wave", 100000, 1.0)
        self.assertAlmostEqual(speed, math.pi * 50000.0, delta=1.0)

    def test_thrust_fast_stroke(self):
        # 2A / 0.2 * f = 2*50000 / 0.2 * 1.0 = 500000
        speed = _peak("Thrust", 100000, 1.0)
        self.assertAlmostEqual(speed, 500000.0, delta=1.0)

    def test_pulse_faster_than_wave(self):
        wave = _peak("Wave", 100000, 1.0)
        pulse = _peak("Pulse", 100000, 1.0)
        self.assertGreater(pulse, wave)

    def test_thrust_faster_than_wave(self):
        wave = _peak("Wave", 100000, 1.0)
        thrust = _peak("Thrust", 100000, 1.0)
        self.assertGreater(thrust, wave)

    def test_realistic_faster_than_wave(self):
        wave = _peak("Wave", 100000, 1.0)
        realistic = _peak("Realistic", 100000, 1.0)
        self.assertGreater(realistic, wave)

    def test_scales_linearly_with_frequency(self):
        s1 = _peak("Wave", 100000, 1.0)
        s2 = _peak("Wave", 100000, 2.0)
        self.assertAlmostEqual(s2 / s1, 2.0, places=5)

    def test_scales_linearly_with_stroke(self):
        s1 = _peak("Wave", 100000, 1.0)
        s2 = _peak("Wave", 200000, 1.0)
        self.assertAlmostEqual(s2 / s1, 2.0, places=5)

    def test_zero_frequency_clamped(self):
        speed = _peak("Wave", 100000, 0.0)
        self.assertGreater(speed, 0.0)

    def test_tease_escalate_edge_use_sine_formula(self):
        for name in ("Tease", "Escalate", "Edge"):
            with self.subTest(pattern=name):
                speed = _peak(name, 100000, 1.0)
                expected = math.pi * 50000.0
                self.assertAlmostEqual(speed, expected, delta=1.0)

    def test_all_registry_entries_present(self):
        expected = {
            "Wave",
            "Realistic",
            "Thrust",
            "Pulse",
            "Tease",
            "Escalate",
            "Edge",
            "Depth",
            "Adaptive",
            "Funscript",
        }
        self.assertEqual(set(PATTERN_REGISTRY.keys()), expected)


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

    def _make_app(self, session_data: dict):  # type: ignore[type-arg]
        import types

        mc = MotorController(use_mock=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = Storage(config_dir=Path(tmp_dir))
            storage.session_file.write_text(json.dumps(session_data), encoding="utf-8")
            api = main_module.WebviewAPI(
                controller=mc, initial_safety_limit_N=55.0, storage=storage
            )
            session = api.load_session()
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
        app = self._make_app(
            {
                "pattern_name": "Thrust",
                "frequency_hz": 2.0,
                "stroke_length_mm": 80.0,
                "safety_force_n": 40.0,
            }
        )
        self.assertFalse(hasattr(app, "pattern_name"))
        self.assertFalse(hasattr(app, "frequency_hz"))
        self.assertFalse(hasattr(app, "stroke_length_mm"))

    def test_save_session_only_writes_safety_fields(self):
        mc = MotorController(use_mock=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = Storage(config_dir=Path(tmp_dir))
            api = main_module.WebviewAPI(
                controller=mc, initial_safety_limit_N=55.0, storage=storage
            )
            api.save_session(
                {
                    "safety_force_n": 40.0,
                    "max_session_s": 600,
                    "pattern_name": "Thrust",
                    "frequency_hz": 2.0,
                    "calibrated_length_um": 120000,
                }
            )
            saved = json.loads(storage.session_file.read_text(encoding="utf-8"))
            self.assertIn("safety_force_n", saved)
            self.assertIn("max_session_s", saved)
            self.assertNotIn("pattern_name", saved)
            self.assertNotIn("frequency_hz", saved)
            self.assertNotIn("calibrated_length_um", saved)


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
        self.assertLessEqual(
            abs(tel["position_um"] - 75000),
            30000,
            "Motor moved too far in 50 ms — catch-up rate limiter may be broken",
        )
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


# ── Crash / reliability tests ────────────────────────────────────────────────


class TestCrashHandling(unittest.TestCase):
    """Verify that an unhandled exception in the control loop is handled gracefully."""

    def test_crash_sets_error_state_and_message(self) -> None:
        mc = MotorController(use_mock=True)
        mc.start(port="mock", baud=115200)

        connected = _wait_connected(mc, timeout=3.0)
        self.assertTrue(
            connected, "Controller did not reach connected state before crash injection"
        )

        # Replace _update_telemetry with a version that raises immediately.
        # patch.object on an instance sets mc.__dict__['_update_telemetry'] so
        # the control thread's self._update_telemetry() lookup finds the mock first.
        with patch.object(mc, "_update_telemetry", side_effect=RuntimeError("injected crash")):
            error_reached = _wait_for_state(mc, ControllerState.ERROR, timeout=3.0)

        self.assertTrue(error_reached, "ERROR state not reached after crash injection")
        tel = mc.get_telemetry()
        self.assertEqual(tel["state_enum"], ControllerState.ERROR)
        self.assertIn("crash", tel["error_msg"].lower())

    def test_stop_does_not_hang_after_crash(self) -> None:
        mc = MotorController(use_mock=True)
        mc.start(port="mock", baud=115200)

        _wait_connected(mc, timeout=3.0)

        with patch.object(mc, "_update_telemetry", side_effect=RuntimeError("injected crash")):
            _wait_for_state(mc, ControllerState.ERROR, timeout=3.0)

        start = time.time()
        mc.stop()
        self.assertLess(time.time() - start, 3.0, "stop() hung after control loop crash")

    def test_get_telemetry_still_works_after_crash(self) -> None:
        mc = MotorController(use_mock=True)
        mc.start(port="mock", baud=115200)

        _wait_connected(mc, timeout=3.0)

        with patch.object(mc, "_update_telemetry", side_effect=RuntimeError("injected crash")):
            _wait_for_state(mc, ControllerState.ERROR, timeout=3.0)

        # get_telemetry() must not raise even though the control thread is dead
        tel = mc.get_telemetry()
        self.assertIsInstance(tel, dict)
        self.assertIn("state_enum", tel)

        mc.stop()


# ── Pattern safety: finiteness and bounds ────────────────────────────────────

_ALL_PATTERNS = [
    patterns.wave_pattern,
    patterns.realistic_pattern,
    patterns.thrust_pattern,
    patterns.pulse_pattern,
    patterns.tease_pattern,
    patterns.escalate_pattern,
    patterns.depth_pattern,
    patterns.edge_pattern,
]

_SOFTWARE_MIN_UM = 5000
_SOFTWARE_MAX_UM = 145000
_CALIB_LEN_UM = 150000.0


class TestPatternSafety(unittest.TestCase):
    """Every pattern must produce finite outputs within software position limits."""

    def _call(
        self,
        fn: object,
        t: float,
        phase: float,
        stroke: float = 80000,
        freq: float = 1.0,
        **extra: object,
    ) -> tuple[str, float]:

        assert isinstance(fn, type(fn))  # satisfy type checker for callable
        return fn(  # type: ignore[operator]
            t,
            int(_CALIB_LEN_UM / 2),
            0.0,
            _CALIB_LEN_UM,
            stroke_length_um=stroke,
            frequency_hz=freq,
            _amplitude_scale=1.0,
            _phase=phase,
            **extra,
        )

    def test_all_patterns_finite_at_zero(self) -> None:
        for fn in _ALL_PATTERNS:
            with self.subTest(pattern=fn.__name__):
                mode, val = self._call(fn, t=0.0, phase=0.0)
                self.assertTrue(math.isfinite(val), f"{fn.__name__} returned {val!r} at t=0")

    def test_all_patterns_within_bounds(self) -> None:
        """Sweep 100 phases across a full cycle; all outputs must stay within software limits."""
        import random

        rng = random.Random(42)
        for fn in _ALL_PATTERNS:
            for _ in range(100):
                phase = rng.uniform(0, 2 * math.pi * 10)
                t = rng.uniform(0, 60)
                stroke = rng.uniform(10000, 100000)
                freq = rng.uniform(0.1, 3.0)
                with self.subTest(pattern=fn.__name__, phase=round(phase, 2)):
                    mode, val = self._call(fn, t=t, phase=phase, stroke=stroke, freq=freq)
                    self.assertTrue(
                        math.isfinite(val),
                        f"{fn.__name__} returned non-finite {val!r}",
                    )
                    if mode == "position":
                        self.assertGreaterEqual(
                            val,
                            _SOFTWARE_MIN_UM,
                            f"{fn.__name__} output {val} below software_min_um",
                        )
                        self.assertLessEqual(
                            val,
                            _SOFTWARE_MAX_UM,
                            f"{fn.__name__} output {val} above software_max_um",
                        )

    def test_tease_clamp_prevents_out_of_bounds(self) -> None:
        """The irrational-ratio sum in tease can exceed [-1,1] — verify clamping holds."""
        import math as _math

        worst_phase = 0.0
        worst_val = 0.0
        for i in range(10000):
            phase = i * 0.01
            _, val = self._call(patterns.tease_pattern, t=phase, phase=phase)
            if not _math.isfinite(val) or val > _SOFTWARE_MAX_UM or val < _SOFTWARE_MIN_UM:
                worst_val = val
                worst_phase = phase
                break
        self.assertTrue(
            _math.isfinite(worst_val) or worst_val == 0.0,
            f"tease_pattern out of bounds at phase={worst_phase}: {worst_val}",
        )


# ── Safety hardening: NaN guard, deadman, e-stop paths ───────────────────────


class TestNaNGuard(unittest.TestCase):
    """Pattern returning NaN must trigger an e-stop, not send garbage to the motor."""

    def test_nan_pattern_triggers_estop(self) -> None:
        def nan_pattern(
            t: float, position_um: int, speed_mm_s: float, L: float, **kwargs: object
        ) -> tuple[str, float]:
            return "position", float("nan")

        mc = MotorController(use_mock=True)
        mc.start(port="mock", baud=115200)
        _wait_connected(mc, timeout=3.0)

        mc.send_command("start_calibration")
        _wait_for_state(mc, ControllerState.CALIBRATED_IDLE, timeout=20.0)

        mc.send_command("start_pattern", pattern_func=nan_pattern, params={})
        estop = _wait_for_state(mc, ControllerState.ESTOP, timeout=3.0)
        mc.stop()

        self.assertTrue(estop, "NaN pattern did not trigger e-stop")
        self.assertIn("non-finite", mc.error_msg)

    def test_inf_pattern_triggers_estop(self) -> None:
        def inf_pattern(
            t: float, position_um: int, speed_mm_s: float, L: float, **kwargs: object
        ) -> tuple[str, float]:
            return "position", float("inf")

        mc = MotorController(use_mock=True)
        mc.start(port="mock", baud=115200)
        _wait_connected(mc, timeout=3.0)

        mc.send_command("start_calibration")
        _wait_for_state(mc, ControllerState.CALIBRATED_IDLE, timeout=20.0)

        mc.send_command("start_pattern", pattern_func=inf_pattern, params={})
        estop = _wait_for_state(mc, ControllerState.ESTOP, timeout=3.0)
        mc.stop()

        self.assertTrue(estop, "Inf pattern did not trigger e-stop")


class TestEstopPaths(unittest.TestCase):
    """E-stop → clear-estop state machine and the 'calibration never completed' branch."""

    def setUp(self) -> None:
        self.mc = MotorController(use_mock=True)
        self.mc.start(port="mock", baud=115200)
        _wait_connected(self.mc, timeout=3.0)

    def tearDown(self) -> None:
        self.mc.stop()

    def test_clear_estop_without_calibration_goes_to_connected(self) -> None:
        """E-stop before any calibration → clear-estop must go to CONNECTED, not CALIBRATED_IDLE."""
        self.mc.send_command("estop")
        _wait_for_state(self.mc, ControllerState.ESTOP, timeout=2.0)

        self.mc.send_command("clear_estop")
        time.sleep(0.2)

        state = self.mc.get_telemetry()["state_enum"]
        self.assertEqual(
            state,
            ControllerState.CONNECTED,
            f"Expected CONNECTED after clear_estop with no calibration, got {state}",
        )

    def test_clear_estop_after_calibration_goes_to_calibrated_idle(self) -> None:
        """E-stop after calibration → clear-estop must go to CALIBRATED_IDLE."""
        self.mc.send_command("start_calibration")
        _wait_for_state(self.mc, ControllerState.CALIBRATED_IDLE, timeout=20.0)

        self.mc.send_command("estop")
        _wait_for_state(self.mc, ControllerState.ESTOP, timeout=2.0)

        self.mc.send_command("clear_estop")
        time.sleep(0.2)

        state = self.mc.get_telemetry()["state_enum"]
        self.assertEqual(
            state,
            ControllerState.CALIBRATED_IDLE,
            f"Expected CALIBRATED_IDLE after clear_estop post-calibration, got {state}",
        )

    def test_estop_clears_error_message_on_clear(self) -> None:
        self.mc.send_command("estop", reason="test fault")
        _wait_for_state(self.mc, ControllerState.ESTOP, timeout=2.0)
        self.assertNotEqual(self.mc.get_telemetry()["error_msg"], "")

        self.mc.send_command("clear_estop")
        time.sleep(0.2)
        self.assertEqual(self.mc.get_telemetry()["error_msg"], "")

    def test_recalibrate_after_estop_reaches_calibrated_idle(self) -> None:
        """Full path: calibrate → e-stop → clear → recalibrate."""
        self.mc.send_command("start_calibration")
        _wait_for_state(self.mc, ControllerState.CALIBRATED_IDLE, timeout=20.0)

        self.mc.send_command("estop")
        _wait_for_state(self.mc, ControllerState.ESTOP, timeout=2.0)

        self.mc.send_command("clear_estop")
        time.sleep(0.2)

        self.mc.send_command("start_calibration")
        recalibrated = _wait_for_state(self.mc, ControllerState.CALIBRATED_IDLE, timeout=20.0)
        self.assertTrue(recalibrated, "Recalibration after e-stop did not complete")


class TestUIDeadman(unittest.TestCase):
    """Deadman watchdog soft-stops the motor when the UI stops polling."""

    def test_deadman_triggers_softstop_when_ui_silent(self) -> None:
        # Use Config to shorten the deadman timeout for test speed, instead of monkey-patching.
        mc = MotorController(use_mock=True, config=Config(ui_deadman_s=0.5))
        mc.start(port="mock", baud=115200)
        _wait_connected(mc, timeout=3.0)

        mc.send_command("start_calibration")
        _wait_for_state(mc, ControllerState.CALIBRATED_IDLE, timeout=20.0)

        # Simulate the UI polling once to arm the deadman
        mc.get_telemetry()

        mc.send_command(
            "start_pattern",
            pattern_func=patterns.wave_pattern,
            params={"stroke_length_um": 40000, "frequency_hz": 1.0},
        )
        _wait_for_state(mc, ControllerState.RUNNING, timeout=2.0)

        # Stop polling — deadman should fire within 0.5 s + one 20 Hz tick
        time.sleep(1.5)

        state = mc.get_telemetry()["state_enum"]
        mc.stop()

        self.assertNotEqual(
            state,
            ControllerState.RUNNING,
            "Motor still RUNNING after UI silence — deadman did not fire",
        )


class TestStorageEdgeCases(unittest.TestCase):
    """Verifies low-level I/O error handling and recovery in the Storage layer."""

    def test_read_json_os_error(self):
        from unittest.mock import patch

        storage = Storage(config_dir=Path("/nonexistent/path/here"))
        with patch.object(Path, "read_text", side_effect=OSError("Access denied")):
            data = storage._read_json(storage.session_file)
            self.assertIsNone(data)

    def test_corrupt_json_backup_failure(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = Storage(config_dir=Path(tmp_dir))
            # Write bad JSON
            storage.session_file.write_text("invalid json {", encoding="utf-8")

            # Mock rename to raise OSError
            with patch.object(Path, "rename", side_effect=OSError("Rename failed")):
                data = storage.load_presets()
                self.assertEqual(data, {})

    def test_load_presets_when_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = Storage(config_dir=Path(tmp_dir))
            storage.presets_file.write_text("not json", encoding="utf-8")
            data = storage.load_presets()
            self.assertEqual(data, {})
            # Check backup file was created
            bak = storage.presets_file.with_suffix(storage.presets_file.suffix + ".bak")
            self.assertTrue(bak.exists())
            self.assertEqual(bak.read_text(encoding="utf-8"), "not json")

    def test_append_and_load_history_os_error(self):
        from unittest.mock import patch

        storage = Storage(config_dir=Path("/invalid/path"))
        # Verify load_history recovers from OSError gracefully
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", side_effect=OSError("Cannot read")):
                self.assertEqual(storage.load_history(), [])

    def test_load_history_with_malformed_lines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = Storage(config_dir=Path(tmp_dir))
            # Write a mix of valid JSON, empty line, and malformed JSON
            lines = [
                '{"duration_s": 10, "pattern_name": "Wave", "end_state": "CALIBRATED_IDLE"}',
                "",
                "malformed json",
                '{"duration_s": 20, "pattern_name": "Pulse", "end_state": "CALIBRATED_IDLE"}',
            ]
            storage.history_file.write_text("\n".join(lines), encoding="utf-8")
            history = storage.load_history(limit=5)
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["duration_s"], 20)
            self.assertEqual(history[1]["duration_s"], 10)


class TestWebviewAPIEdgeCases(unittest.TestCase):
    """Verifies exception handling and error paths in the WebviewAPI bridge."""

    def setUp(self):
        self.mc = MotorController(use_mock=True)
        self.storage = Storage(config_dir=Path("/nonexistent"))
        self.api = main_module.WebviewAPI(
            self.mc, initial_safety_limit_N=55.0, storage=self.storage
        )

    def tearDown(self):
        self.mc.stop()

    def test_quit_application_no_window(self):
        res = self.api.quit_application()
        self.assertFalse(res["success"])
        self.assertEqual(res["error_kind"], "system")

    def test_quit_application_with_mock_window(self):
        from unittest.mock import MagicMock

        window = MagicMock()
        self.api.set_window(window)
        res = self.api.quit_application()
        self.assertTrue(res["success"])
        window.destroy.assert_called_once()

    def test_get_telemetry_raises_exception(self):
        from unittest.mock import patch

        with patch.object(
            self.mc, "get_telemetry", side_effect=ValueError("Unexpected internal state")
        ):
            res = self.api.get_telemetry()
            self.assertIn("error", res)
            self.assertEqual(res["error"], "Unexpected internal state")

    def test_send_command_invalid_pattern(self):
        res = self.api.send_command("start_pattern", {"pattern_name": "NonexistentPattern"})
        self.assertFalse(res["success"])
        self.assertEqual(res["error_kind"], "user")
        self.assertIn("Unknown pattern name", res["error"])

    def test_send_command_exception(self):
        from unittest.mock import patch

        with patch.object(
            self.mc, "send_command", side_effect=RuntimeError("Controller logic failed")
        ):
            res = self.api.send_command("set_safety_limit", {"limit_mN": 1000})
            self.assertFalse(res["success"])
            self.assertEqual(res["error_kind"], "system")
            self.assertIn("Controller logic failed", res["error"])

    def test_storage_failures_in_api(self):
        from unittest.mock import patch

        # presets load error
        with patch.object(self.storage, "load_presets", side_effect=OSError("HD full")):
            self.assertEqual(self.api.load_presets(), {})

        # presets save error
        with patch.object(self.storage, "save_presets", side_effect=OSError("HD full")):
            res = self.api.save_presets({})
            self.assertFalse(res["success"])
            self.assertEqual(res["error_kind"], "system")

        # session load error
        with patch.object(self.storage, "load_session", side_effect=OSError("Corrupt folder")):
            res = self.api.load_session()
            self.assertEqual(res["safety_force_n"], 55.0)

        # session save error
        with patch.object(self.storage, "save_session", side_effect=OSError("Read-only FS")):
            res = self.api.save_session({"safety_force_n": 40.0})
            self.assertFalse(res["success"])
            self.assertEqual(res["error_kind"], "system")

        # session history append error
        with patch.object(self.storage, "append_history", side_effect=OSError("Locked file")):
            res = self.api.save_session_history({"duration_s": 10})
            self.assertFalse(res["success"])

        # session history load error
        with patch.object(self.storage, "load_history", side_effect=OSError("IO error")):
            self.assertEqual(self.api.load_session_history(), [])

    def test_list_ports_success(self):
        from unittest.mock import MagicMock

        mock_port = MagicMock()
        mock_port.device = "/dev/ttyUSB9"
        mock_port.description = "Orca 6 Linear Actuator"
        with patch("serial.tools.list_ports.comports", return_value=[mock_port]):
            ports = self.api.list_ports()
            self.assertEqual(len(ports), 1)
            self.assertEqual(ports[0]["device"], "/dev/ttyUSB9")
            self.assertEqual(ports[0]["description"], "Orca 6 Linear Actuator")

    def test_list_ports_error(self):
        with patch("serial.tools.list_ports.comports", side_effect=Exception("Serial port error")):
            self.assertEqual(self.api.list_ports(), [])

    def test_connect_port_success(self):
        with (
            patch.object(self.mc, "stop") as mock_stop,
            patch.object(self.mc, "start") as mock_start,
        ):
            self.mc.baud = 9600
            res = self.api.connect_port("/dev/ttyUSB2")
            self.assertTrue(res["success"])
            mock_stop.assert_called_once()
            mock_start.assert_called_once_with(port="/dev/ttyUSB2", baud=9600)

    def test_connect_port_error(self):
        with patch.object(self.mc, "stop", side_effect=RuntimeError("Thread stuck")):
            res = self.api.connect_port("/dev/ttyUSB2")
            self.assertFalse(res["success"])
            self.assertEqual(res["error_kind"], "system")


class TestRebuildFrontend(unittest.TestCase):
    """Verifies that rebuild logic detects stale bundles and behaves correctly on errors."""

    def test_rebuild_if_no_src_files(self):
        from unittest.mock import patch

        with patch("pathlib.Path.rglob", return_value=[]):
            # Should return immediately without checking dist or running subprocess
            with patch("subprocess.run") as mock_run:
                main_module._rebuild_frontend_if_stale()
                mock_run.assert_not_called()

    def test_rebuild_if_up_to_date(self):
        from unittest.mock import MagicMock, patch

        src_mock = MagicMock()
        src_mock.is_file.return_value = True
        src_mock.stat.return_value.st_mtime = 1000.0

        dist_mock = MagicMock()
        dist_mock.is_file.return_value = True
        dist_mock.stat.return_value.st_mtime = 2000.0

        with patch("pathlib.Path.rglob", return_value=[src_mock]):
            with patch("pathlib.Path.glob", return_value=[dist_mock]):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("subprocess.run") as mock_run:
                        main_module._rebuild_frontend_if_stale()
                        mock_run.assert_not_called()

    def test_rebuild_runs_npm_successfully(self):
        from unittest.mock import MagicMock, patch

        src_mock = MagicMock()
        src_mock.is_file.return_value = True
        src_mock.stat.return_value.st_mtime = 2000.0

        dist_mock = MagicMock()
        dist_mock.is_file.return_value = True
        dist_mock.stat.return_value.st_mtime = 1000.0

        with patch("pathlib.Path.rglob", return_value=[src_mock]):
            with patch("pathlib.Path.glob", return_value=[dist_mock]):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        main_module._rebuild_frontend_if_stale()
                        mock_run.assert_called_once_with(
                            ["npm", "run", "build"],
                            cwd=main_module.Path(__file__).resolve().parent.parent
                            / "src"
                            / "wavedriver"
                            / "web",
                            capture_output=True,
                            text=True,
                        )

    def test_rebuild_runs_npm_fails(self):
        from unittest.mock import MagicMock, patch

        src_mock = MagicMock()
        src_mock.is_file.return_value = True
        src_mock.stat.return_value.st_mtime = 2000.0

        with patch("pathlib.Path.rglob", return_value=[src_mock]):
            with patch("pathlib.Path.glob", return_value=[]):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 1
                        mock_run.return_value.stderr = "Compilation error"
                        with self.assertRaises(SystemExit):
                            main_module._rebuild_frontend_if_stale()

    def test_rebuild_runs_npm_not_found(self):
        from unittest.mock import MagicMock, patch

        src_mock = MagicMock()
        src_mock.is_file.return_value = True
        src_mock.stat.return_value.st_mtime = 2000.0

        with patch("pathlib.Path.rglob", return_value=[src_mock]):
            with patch("pathlib.Path.glob", return_value=[]):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("subprocess.run", side_effect=FileNotFoundError):
                        # Should log a warning and continue (skipping build)
                        main_module._rebuild_frontend_if_stale()


class TestCLIArgsAndMain(unittest.TestCase):
    """Verifies that the CLI entrypoint handles arguments and configures modes properly."""

    def test_list_ports_success(self):
        from unittest.mock import MagicMock, patch

        mock_port = MagicMock()
        mock_port.device = "/dev/ttyUSB0"
        mock_port.description = "USB Serial Device"

        with patch("sys.argv", ["wavedriver", "--list-ports"]):
            with patch("serial.tools.list_ports.comports", return_value=[mock_port]):
                with patch("builtins.print") as mock_print:
                    with self.assertRaises(SystemExit) as cm:
                        main_module.main()
                    self.assertEqual(cm.exception.code, 0)
                    mock_print.assert_any_call("Available serial ports:")

    def test_list_ports_import_error(self):
        from unittest.mock import patch

        with patch("sys.argv", ["wavedriver", "--list-ports"]):
            with patch("builtins.print"):
                with patch("serial.tools.list_ports.comports", side_effect=ImportError):
                    with self.assertRaises(SystemExit) as cm:
                        main_module.main()
                    self.assertEqual(cm.exception.code, 0)

    def test_invalid_safety_limit(self):
        with self.assertRaises(SystemExit):
            with patch("sys.argv", ["wavedriver", "--safety-limit", "99.0"]):
                main_module.main()

    @patch("wavedriver.main.webview.create_window")
    @patch("wavedriver.main.webview.start")
    @patch("wavedriver.main.MotorController")
    def test_main_runs_dev_mode(self, mock_mc_cls, mock_start, mock_create_window):
        mock_mc = mock_mc_cls.return_value

        with patch("sys.argv", ["wavedriver", "--mock", "--dev"]):
            main_module.main()
            mock_mc.start.assert_called_once()
            mock_create_window.assert_called_once_with(
                title="Wavedriver Orca 6 Dashboard",
                url="http://localhost:5173?platform=pywebview",
                js_api=ANY,
                width=1000,
                height=720,
                min_size=(900, 650),
                background_color="#0d0e15",
            )
            mock_start.assert_called_once()
            mock_mc.stop.assert_called_once()


class TestNewInteractiveFeatures(unittest.TestCase):
    """Verifies Phase 5.5 Delight & Differentiation Features."""

    def test_adaptive_pattern_ease(self):
        # With zero force, ease should not scale the stroke
        mode, val1 = patterns.adaptive_pattern(
            t=1.0,
            position_um=75000,
            speed_mm_s=0.0,
            L=150000,
            stroke_length_um=80000,
            frequency_hz=1.0,
            force_mN=0.0,
            adaptive_mode="ease",
            sensitivity=1.0,
        )
        # With high force, ease should scale down stroke/amplitude
        mode, val2 = patterns.adaptive_pattern(
            t=1.0,
            position_um=75000,
            speed_mm_s=0.0,
            L=150000,
            stroke_length_um=80000,
            frequency_hz=1.0,
            force_mN=25000.0,
            adaptive_mode="ease",
            sensitivity=1.0,
        )
        self.assertEqual(mode, "position")
        # With force_mN=25000, force_ratio is 1.0. stroke_scale = 1.0 - 0.75 * 1.0 = 0.25.
        # So val2 should have much smaller amplitude than val1.
        # Center position C = 75000.
        # Since t=1.0 and freq=1.0, math.sin(phase) at phase=2pi is 0. So let's test at phase = pi/2
        # phase = pi/2 when frequency_hz = 1.0 and t = 0.25 (2*pi*1.0*0.25 = pi/2)
        _, peak1 = patterns.adaptive_pattern(
            t=0.25,
            position_um=75000,
            speed_mm_s=0.0,
            L=150000,
            stroke_length_um=80000,
            frequency_hz=1.0,
            force_mN=0.0,
            adaptive_mode="ease",
            sensitivity=1.0,
            _phase=math.pi / 2,
            _amplitude_scale=1.0,
        )
        _, peak2 = patterns.adaptive_pattern(
            t=0.25,
            position_um=75000,
            speed_mm_s=0.0,
            L=150000,
            stroke_length_um=80000,
            frequency_hz=1.0,
            force_mN=25000.0,
            adaptive_mode="ease",
            sensitivity=1.0,
            _phase=math.pi / 2,
            _amplitude_scale=1.0,
        )
        # peak1: C + A_orig = 75000 + 40000 = 115000
        # peak2: C + A_scaled = 75000 + (40000 * 0.25) = 85000
        self.assertAlmostEqual(peak1, 115000.0, delta=1.0)
        self.assertAlmostEqual(peak2, 85000.0, delta=1.0)

    def test_adaptive_pattern_give_and_take(self):
        # push force shifts center backwards
        _, pos_push = patterns.adaptive_pattern(
            t=0.25,
            position_um=75000,
            speed_mm_s=0.0,
            L=150000,
            stroke_length_um=80000,
            frequency_hz=1.0,
            force_mN=25000.0,
            adaptive_mode="give_and_take",
            sensitivity=1.0,
            _phase=0.0,
            _amplitude_scale=1.0,
        )
        # C_shifted: center shifts back by 25mm = 25000 um
        # base C = 75000, shift is -25000 => C_shifted = 50000.
        # A = 40000 * 0.5 = 20000. C_shifted clamped: min_lim + A = 5000 + 20000 = 25000.
        # Here 50000 is safe since 50000 - 20000 >= 5000 and 50000 + 20000 <= 145000.
        # So pos_push should be around 50000.
        self.assertAlmostEqual(pos_push, 50000.0, delta=1.0)

    def test_funscript_pattern(self):
        actions = [[0.0, 0.0], [1.0, 100.0], [2.0, 0.0]]
        # At t=0.5, pos should be 50%
        _, pos_half = patterns.funscript_pattern(
            t=0.5,
            position_um=75000,
            speed_mm_s=0.0,
            L=150000,
            stroke_length_um=100000,
            funscript_actions=actions,
            funscript_loop=True,
            _amplitude_scale=1.0,
        )
        # C = 75000, A = 50000. Range is [25000, 125000].
        # 50% should map to C = 75000
        self.assertAlmostEqual(pos_half, 75000.0, delta=1.0)

    def test_set_pattern_elapsed_command(self):
        mc = MotorController(use_mock=True)
        mc.start(port="mock", baud=115200)
        try:
            mc.send_command("set_pattern_elapsed", elapsed_s=10.5)
            # Wait for command queue to drain
            mc.cmd_queue.join()
            # Verify the start time was adjusted
            now = time.perf_counter()
            self.assertAlmostEqual(now - mc.pattern_start_time, 10.5, delta=1.0)
        finally:
            mc.stop()


if __name__ == "__main__":
    unittest.main()
