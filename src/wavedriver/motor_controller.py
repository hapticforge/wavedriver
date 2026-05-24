import gc
import time
import math
import threading
import queue
import collections
from enum import Enum

_TEMP_ESTOP_C   = 75      # Software over-temperature threshold (°C), below 80 °C hardware limit
_VOLTAGE_LOW_MV = 18000   # Minimum acceptable supply voltage (mV); 18 V for a nominal 24 V supply


class ControllerState(Enum):
    """Defines the operational and calibration states of the pleasure controller."""
    UNCONNECTED         = "Unconnected"
    CONNECTING          = "Connecting"
    CONNECTED           = "Connected (Uncalibrated)"
    CALIBRATING_RETRACT = "Calibrating (Retracting)"
    CALIBRATING_EXTEND  = "Calibrating (Extending)"
    CALIBRATING_CENTER  = "Calibrating (Centering)"
    CALIBRATED_IDLE     = "Calibrated & Idle"
    RUNNING             = "Running"
    ESTOP               = "EMERGENCY STOP (Force Exceeded)"
    ERROR               = "Error"


class MotorController:
    """High-performance controller coordinating the pleasure device and the Orca 6 motor.

    Uses a decoupled multi-rate timing loop:
    - High-frequency updates (500 Hz) for smooth position ramping and pleasure waveform calculations.
    - Low-frequency updates (20 Hz) for Modbus register reads, safety threshold checks,
      and connection watchdogs to prevent bus saturation.
    """

    def __init__(self, use_mock=False):
        """Initializes the controller state, communication fields, and pattern buffers.

        Args:
            use_mock (bool): If True, forces offline simulation mode utilizing the mock actuator.
        """
        self.use_mock = use_mock

        if self.use_mock:
            from wavedriver import mock_actuator as sdk
        else:
            try:
                import pyorcasdk as sdk
            except ImportError:
                from wavedriver import mock_actuator as sdk
                self.use_mock = True

        self.sdk      = sdk
        self.actuator = None
        self.port     = "/dev/ttyUSB0"
        self.baud     = 19200

        # Telemetry & State (thread-safe via lock)
        self.lock             = threading.Lock()
        self.state            = ControllerState.UNCONNECTED
        self.error_msg        = ""
        self.position_um      = 0
        self.force_mN         = 0
        self.speed_mm_s       = 0.0
        self.temperature_C    = 0
        self.voltage_mV       = 0
        self.power_W          = 0
        self.errors_bitmask   = 0
        self.calibrated_length_um = 0
        self.software_min_um  = 5000
        self.software_max_um  = 145000

        # Safety Configuration
        self.max_feedback_force_mN = 55000  # Default 55 N (under 60 N hardware limit)

        # Control inputs
        self.current_pattern          = None
        self.pattern_params           = {}
        self.pattern_start_time       = 0.0
        self._pattern_amplitude_scale = 0.0   # current interpolated scale (0 → 1)
        self._amplitude_target        = 1.0   # desired scale; bidirectional ramp converges here
        self._pre_pause_amplitude     = 1.0   # saved target before pause, restored on resume

        # Pause / soft-stop flags (written only in control thread)
        self._paused       = False
        self._soft_stopping = False

        # Session timer
        self._session_start_time = None   # set when first start_pattern received
        self._max_session_s      = 0      # 0 = no limit

        # Interpolated pattern parameters (smoothly blend to new targets at 500 Hz)
        self._stroke_um_current = 50000.0
        self._stroke_um_target  = 50000.0
        self._freq_hz_current   = 1.0
        self._freq_hz_target    = 1.0

        # Accumulated phase (integrated as φ += 2π·f·dt so frequency changes
        # never cause a back-calculated ω·t phase jump).
        self._current_phase = 0.0

        # Extra (non-interpolated) pattern params cached at command time
        self._extra_params = {}

        # Thread management
        self.cmd_queue  = queue.Queue()
        self.thread     = None
        self.stop_event = threading.Event()

        # Calibration state
        self._position_history        = collections.deque(maxlen=10)
        self._calibration_target      = None
        self._calibration_stage_ticks = 0
        self._last_set_mode           = None
        self._force_exceed_count      = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, port="/dev/ttyUSB0", baud=19200):
        """Starts the background execution control thread.

        Args:
            port (str): The serial device port path (e.g. '/dev/ttyUSB0').
            baud (int): Modbus communication speed (e.g. 19200).
        """
        self.port = port
        self.baud = baud
        self.stop_event.clear()
        self.state = ControllerState.CONNECTING
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Safely stops the background thread, placing the motor in Sleep Mode."""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.5)
        self.state = ControllerState.UNCONNECTED

    def send_command(self, cmd_type, **kwargs):
        """Enqueues a command (e.g., 'start_pattern', 'estop') for processing by the thread.

        Args:
            cmd_type (str): Command identifier.
            **kwargs: Arguments specific to the command.
        """
        self.cmd_queue.put((cmd_type, kwargs))

    def get_telemetry(self):
        """Returns a thread-safe snapshot dictionary of live device telemetry.

        Includes state representation, current physical position, feedback resistance force, 
        running speed SPM, temperature readings, input voltage, power usage, errors, 
        and session elapsed timer.
        """
        with self.lock:
            session_start = self._session_start_time
            paused        = self._paused
            return {
                "state":                  self.state.value,
                "state_enum":             self.state,
                "error_msg":              self.error_msg,
                "position_um":            self.position_um,
                "force_mN":               self.force_mN,
                "speed_mm_s":             self.speed_mm_s,
                "temperature_C":          self.temperature_C,
                "voltage_mV":             self.voltage_mV,
                "power_W":                self.power_W,
                "errors_bitmask":         self.errors_bitmask,
                "calibrated_length_um":   self.calibrated_length_um,
                "max_feedback_force_mN":  self.max_feedback_force_mN,
                "use_mock":               self.use_mock,
                "session_elapsed_s":      (time.perf_counter() - session_start)
                                          if session_start is not None else 0.0,
                "paused":                 paused,
            }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _set_motor_mode(self, mode):
        """Sends a motor mode change command to the actuator, caching the state to avoid redundant calls."""
        if self._last_set_mode != mode:
            self.actuator.set_mode(mode)
            self._last_set_mode = mode

    def _update_telemetry(self):
        """Fetches the latest data stream block from the actuator and updates telemetry fields.

        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.actuator:
            return False
        try:
            stream_data = self.actuator.get_stream_data()
            with self.lock:
                self.position_um    = stream_data.position
                self.force_mN       = stream_data.force
                self.power_W        = stream_data.power
                self.temperature_C  = stream_data.temperature
                self.voltage_mV     = stream_data.voltage
                self.errors_bitmask = stream_data.errors
            return True
        except Exception:
            return False

    def _initialize_hardware(self):
        """Configure hardware registers, safety limits, PID gains, and disable GC for the control thread.

        Disabling garbage collection prevents periodic latency spikes that could disrupt
        the high-frequency (500 Hz) control loop timing.
        """
        self.actuator.set_max_force(60000)
        self.actuator.write_register_blocking(176, 0)    # MB_POS_FILTER   → no filter
        self.actuator.write_register_blocking(175, 0)    # MB_FORCE_FILTER → no filter
        # POS_MAX_VEL 500 mm/s / POS_MAX_ACCEL 8000 mm/s² / POS_MAX_DECEL 8000 mm/s²
        # (well above peak for 1 Hz sine, 150 mm stroke: v≈236 mm/s, a≈2960 mm/s²)
        self.actuator.write_register_blocking(153, 500)
        self.actuator.write_register_blocking(154, 8000)
        self.actuator.write_register_blocking(155, 8000)
        self.actuator.write_register_blocking(150, 200)  # PC_SOFTSTART_PERIOD 200 ms
        # pgain 200 mN/µm · igain 0 · dvgain 400 mN·s/m · sat 60000 mN
        self.actuator.tune_position_controller(pgain=200, igain=0, dvgain=400, sat=60000)
        gc.collect()
        gc.disable()

    def _drive_running_pattern(self, now, dt, pos_um):
        """Generates and sends the target command for the active pattern at 500 Hz.

        Manages:
        - Bidirectional amplitude scaling ramps (soft start/stop).
        - Gradual parameter interpolation (stroke and frequency shifts).
        - Integrated phase tracking to avoid sudden position jumps when frequency changes. Clamps
          target output to the software safety margins.
        """
        if not self.current_pattern:
            self._set_motor_mode(self.sdk.MotorMode.PositionMode)
            self.actuator.set_streamed_position_um(int(pos_um))
            return

        elapsed = now - self.pattern_start_time
        with self.lock:
            speed     = self.speed_mm_s
            cal_len   = self.calibrated_length_um
            min_lim   = self.software_min_um
            max_lim   = self.software_max_um
            amp_scale = self._pattern_amplitude_scale
            max_force = self.max_feedback_force_mN

        # ── Bidirectional amplitude ramp ──────────────────────────────────────
        # _amplitude_target is the desired scale (1.0 = full, 0.0 = paused/stopping).
        # Ramp at 0.5/second (2-second full traverse) in both directions.
        amp_target = self._amplitude_target
        step       = dt / 2.0
        if amp_scale < amp_target:
            amp_scale = min(amp_target, amp_scale + step)
        elif amp_scale > amp_target:
            amp_scale = max(amp_target, amp_scale - step)
        with self.lock:
            self._pattern_amplitude_scale = amp_scale

        # ── Soft-stop completion ──────────────────────────────────────────────
        if self._soft_stopping and amp_scale <= 0.001:
            with self.lock:
                self.state           = ControllerState.CALIBRATED_IDLE
                self.current_pattern = None
            self._soft_stopping    = False
            self._amplitude_target = 1.0
            with self.lock:
                self._pattern_amplitude_scale = 0.0
            self._set_motor_mode(self.sdk.MotorMode.SleepMode)
            self.actuator.set_streamed_force_mN(0)
            gc.collect()
            return

        # ── Smooth parameter interpolation at 500 Hz ──────────────────────────
        stroke_rate = 50000.0 * dt
        freq_rate   = 1.0 * dt

        s_curr = self._stroke_um_current
        s_tgt  = self._stroke_um_target
        diff_s = s_tgt - s_curr
        s_curr = s_tgt if abs(diff_s) <= stroke_rate else s_curr + math.copysign(stroke_rate, diff_s)
        self._stroke_um_current = s_curr

        f_curr = self._freq_hz_current
        f_tgt  = self._freq_hz_target
        diff_f = f_tgt - f_curr
        f_curr = f_tgt if abs(diff_f) <= freq_rate else f_curr + math.copysign(freq_rate, diff_f)
        self._freq_hz_current = f_curr

        # ── Phase integration ─────────────────────────────────────────────────
        # Freeze phase while fully paused so the waveform resumes from the same
        # point in its cycle rather than having drifted during the pause.
        fully_paused = (amp_target <= 0.001 and amp_scale <= 0.001)
        if not fully_paused:
            self._current_phase += 2.0 * math.pi * f_curr * dt

        # ── Call pattern and send motor command ───────────────────────────────
        L = cal_len if cal_len > 0 else 150000.0
        res_mode, res_value = self.current_pattern(
            elapsed, pos_um, speed, L,
            stroke_length_um=s_curr, frequency_hz=f_curr,
            _amplitude_scale=amp_scale, _phase=self._current_phase,
            **self._extra_params
        )

        if res_mode == "position":
            target_pos_um = max(min_lim, min(max_lim, res_value))
            self._set_motor_mode(self.sdk.MotorMode.PositionMode)
            self.actuator.set_streamed_position_um(int(target_pos_um))
        elif res_mode == "force":
            clamped = max(-float(max_force), min(float(max_force), res_value))
            self._set_motor_mode(self.sdk.MotorMode.ForceMode)
            self.actuator.set_streamed_force_mN(int(clamped))

    def _drive_calibration(self, dt, current_state):
        """Advances the target position ramp during homing calibration stages at 500 Hz.

        Slowly moves the shaft outward or inward until a physical end-stop stall is detected by the 20 Hz loop.
        """
        with self.lock:
            pos_um = self.position_um

        if self._calibration_target is None:
            self._calibration_target = float(pos_um)

        if current_state == ControllerState.CALIBRATING_RETRACT:
            self._calibration_target -= 80000.0 * dt
        elif current_state == ControllerState.CALIBRATING_EXTEND:
            self._calibration_target += 80000.0 * dt
        else:  # CALIBRATING_CENTER
            with self.lock:
                center_target = self.calibrated_length_um / 2.0
            step = 80000.0 * dt
            diff = center_target - self._calibration_target
            if abs(diff) <= step:
                self._calibration_target = center_target
            else:
                self._calibration_target += math.copysign(step, diff)

        self._set_motor_mode(self.sdk.MotorMode.PositionMode)
        self.actuator.set_streamed_position_um(int(self._calibration_target))

    def _tick_500hz_controls(self, now, dt, current_state, is_estop, pos_um):
        """Executes the high-frequency control loop tasks at 500 Hz.

        Triggers pattern movement calculation or advances calibration target ramps.
        """
        if is_estop:
            return
        if current_state == ControllerState.RUNNING:
            self._drive_running_pattern(now, dt, pos_um)
        elif current_state in (ControllerState.CALIBRATING_RETRACT,
                               ControllerState.CALIBRATING_EXTEND,
                               ControllerState.CALIBRATING_CENTER):
            self._drive_calibration(dt, current_state)

    def _drain_command_queue(self):
        """Drains and processes all pending commands from the command queue in the control thread context."""
        try:
            while True:
                cmd_type, kwargs = self.cmd_queue.get_nowait()
                self._process_command(cmd_type, kwargs)
                self.cmd_queue.task_done()
        except queue.Empty:
            pass

    def _request_soft_stop(self):
        """Initiate a graceful ramp-to-zero stop (callable from the control thread)."""
        self._amplitude_target = 0.0
        self._soft_stopping    = True
        self._paused           = False

    def _tick_20hz(self, now, startup_time, current_state, is_estop, prev_pos):
        """20 Hz block: safety monitoring, auto-shutoff, calibration state machine, GC.

        Returns the updated prev_pos for the next speed calculation.
        """
        telemetry_interval = 0.050

        # ── Session auto-shutoff ──────────────────────────────────────────────
        with self.lock:
            session_start = self._session_start_time
        if (self._max_session_s > 0 and
                session_start is not None and
                not self._soft_stopping and
                current_state == ControllerState.RUNNING and
                (now - session_start) >= self._max_session_s):
            self._request_soft_stop()

        # ── Connection health check ───────────────────────────────────────────
        if now - startup_time > 2.0:
            try:
                if self.actuator.time_since_last_response_microseconds() > 500000:
                    self._trigger_estop("Motor Connection Link Lost")
                    return prev_pos
            except Exception:
                pass

        # ── Speed calculation ─────────────────────────────────────────────────
        with self.lock:
            self.speed_mm_s = ((self.position_um - prev_pos) / 1000.0) / telemetry_interval
            new_prev_pos    = self.position_um

        # ── Safety monitors ───────────────────────────────────────────────────
        with self.lock:
            current_force = abs(self.force_mN)
            max_force     = self.max_feedback_force_mN
            temp_C        = self.temperature_C
            voltage_mV    = self.voltage_mV

        if not is_estop:
            # Force check: RUNNING and CALIBRATING_CENTER only.
            # RETRACT/EXTEND intentionally stall against end-stops (hardware-clamped 60 N);
            # checking there would always false-trip.
            if current_state in (ControllerState.RUNNING, ControllerState.CALIBRATING_CENTER):
                if current_force > max_force:
                    self._force_exceed_count += 1
                    if self._force_exceed_count >= 3:
                        self._trigger_estop(
                            f"Safety Force Threshold Exceeded "
                            f"({current_force / 1000.0:.1f} N > {max_force / 1000.0:.1f} N limit)"
                        )
                        self._force_exceed_count = 0
                        return new_prev_pos
                else:
                    self._force_exceed_count = 0
            else:
                self._force_exceed_count = 0

            if temp_C >= _TEMP_ESTOP_C:
                self._trigger_estop(
                    f"Overtemperature Shutdown ({temp_C} °C ≥ {_TEMP_ESTOP_C} °C)"
                )
                return new_prev_pos

            if voltage_mV > 0 and voltage_mV < _VOLTAGE_LOW_MV:
                self._trigger_estop(
                    f"Low Supply Voltage "
                    f"({voltage_mV / 1000.0:.1f} V < {_VOLTAGE_LOW_MV / 1000.0:.1f} V)"
                )
                return new_prev_pos

        if is_estop:
            self._set_motor_mode(self.sdk.MotorMode.SleepMode)
            self.actuator.set_streamed_force_mN(0)
            return new_prev_pos

        # ── Calibration state machine ─────────────────────────────────────────
        if current_state in (ControllerState.CALIBRATING_RETRACT,
                             ControllerState.CALIBRATING_EXTEND):
            self._handle_calibration(telemetry_interval)

        elif current_state == ControllerState.CALIBRATING_CENTER:
            with self.lock:
                cal_len_snap = self.calibrated_length_um
            center_done = cal_len_snap / 2.0
            if (self._calibration_target is not None and
                    abs(self._calibration_target - center_done) < 1.0):
                self._calibration_target = None
                self.actuator.write_register_blocking(153, 500)
                self.actuator.write_register_blocking(154, 8000)
                self.actuator.write_register_blocking(155, 8000)
                with self.lock:
                    self.state = ControllerState.CALIBRATED_IDLE

        elif current_state in (ControllerState.CONNECTED, ControllerState.CALIBRATED_IDLE):
            self._set_motor_mode(self.sdk.MotorMode.SleepMode)
            self.actuator.set_streamed_force_mN(0)
            gc.collect()

        return new_prev_pos

    def _cleanup_on_stop(self):
        """Performs teardown of communications, resets the motor to Sleep Mode, and re-enables garbage collection."""
        gc.enable()
        gc.collect()
        if self.actuator:
            self._set_motor_mode(self.sdk.MotorMode.SleepMode)
            self.actuator.set_streamed_force_mN(0)
            self.actuator.run()
            self.actuator.disable_stream()
            self.actuator.close_serial_port()

    def _run_loop(self):
        """The main thread execution loop running at 500 Hz.

        Manages connection startup, calls high-frequency controls, drains the command queue,
        and periodically calls the 20 Hz telemetry/safety check tick.
        """
        self.actuator = self.sdk.Actuator()
        err = self.actuator.open_serial_port(self.port, self.baud)
        if err:
            with self.lock:
                self.state     = ControllerState.ERROR
                self.error_msg = f"Failed to open port {self.port}: {err.what()}"
            return

        self.actuator.enable_stream()
        self._initialize_hardware()
        self._last_set_mode = None

        with self.lock:
            self.state = ControllerState.CONNECTED

        tick_interval       = 0.002
        telemetry_interval  = 0.050
        last_tick           = time.perf_counter()
        startup_time        = time.perf_counter()
        last_telemetry_time = 0.0
        prev_pos            = 0

        while not self.stop_event.is_set():
            now = time.perf_counter()
            dt  = now - last_tick
            last_tick = now

            self.actuator.run()
            self._update_telemetry()

            with self.lock:
                current_state = self.state
                is_estop      = (self.state == ControllerState.ESTOP)
                pos_um        = self.position_um

            self._tick_500hz_controls(now, dt, current_state, is_estop, pos_um)
            self._drain_command_queue()

            if now - last_telemetry_time >= telemetry_interval:
                last_telemetry_time = now
                prev_pos = self._tick_20hz(
                    now, startup_time, current_state, is_estop, prev_pos
                )

            elapsed_tick = time.perf_counter() - now
            sleep_time   = tick_interval - elapsed_tick
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._cleanup_on_stop()

    def _process_command(self, cmd_type, kwargs):
        """Processes enqueued commands within the control thread.

        Handles commands for E-STOP triggers, safety limits, presets, pause/resume, and starting/stopping patterns.
        """
        with self.lock:
            is_estop = (self.state == ControllerState.ESTOP)

        if cmd_type == "estop":
            self._trigger_estop(kwargs.get("reason", "Emergency Stop Requested"))
            return

        if cmd_type == "clear_estop":
            if self.actuator:
                self.actuator.clear_errors()
            with self.lock:
                self.state     = ControllerState.CALIBRATED_IDLE
                self.error_msg = ""
            return

        if is_estop:
            return

        if cmd_type == "set_safety_limit":
            with self.lock:
                self.max_feedback_force_mN = max(1000, kwargs.get("limit_mN", 55000))

        elif cmd_type == "set_max_session":
            self._max_session_s = max(0, int(kwargs.get("max_session_s", 0)))

        elif cmd_type == "start_calibration":
            self._position_history.clear()
            self._calibration_stage_ticks = 0
            self._calibration_target      = None
            self._amplitude_target        = 1.0
            self._soft_stopping           = False
            self._paused                  = False
            with self.lock:
                self._session_start_time = None   # new calibration = new session
                self.state               = ControllerState.CALIBRATING_RETRACT

        elif cmd_type == "load_calibration":
            length_um = int(kwargs.get("calibrated_length_um", 0))
            if length_um > 20000:
                with self.lock:
                    self.calibrated_length_um = length_um
                    self.software_min_um      = 5000
                    self.software_max_um      = length_um - 5000
                    self.state                = ControllerState.CALIBRATED_IDLE

        elif cmd_type == "pause_pattern":
            with self.lock:
                if self.state == ControllerState.RUNNING:
                    self._pre_pause_amplitude = self._amplitude_target
                    self._paused              = True
            self._amplitude_target = 0.0

        elif cmd_type == "resume_pattern":
            with self.lock:
                if self.state == ControllerState.RUNNING:
                    self._paused = False
            self._amplitude_target = self._pre_pause_amplitude
            self._soft_stopping    = False

        elif cmd_type == "set_intensity":
            # Directly set the amplitude target (0.0–1.0) without affecting pause state.
            intensity = max(0.0, min(1.0, float(kwargs.get("intensity", 1.0))))
            self._amplitude_target    = intensity
            self._pre_pause_amplitude = intensity
            if intensity > 0.0:
                with self.lock:
                    self._paused = False
                self._soft_stopping = False

        elif cmd_type == "soft_stop":
            with self.lock:
                running = (self.state == ControllerState.RUNNING)
            if running:
                self._request_soft_stop()

        elif cmd_type == "start_pattern":
            pattern_func = kwargs.get("pattern_func")
            params       = kwargs.get("params", {})
            with self.lock:
                already_running = (self.state == ControllerState.RUNNING and
                                   self.current_pattern is not None)
                if self.state in (ControllerState.CALIBRATED_IDLE, ControllerState.RUNNING):
                    if already_running:
                        self.current_pattern   = pattern_func
                        self.pattern_params    = params
                        self._stroke_um_target = params.get('stroke_length_um', self._stroke_um_target)
                        self._freq_hz_target   = params.get('frequency_hz', self._freq_hz_target)
                        self._extra_params     = {k: v for k, v in params.items()
                                                  if k not in ('stroke_length_um', 'frequency_hz')}
                        self.state             = ControllerState.RUNNING
                    else:
                        self.current_pattern        = pattern_func
                        self.pattern_params         = params
                        new_stroke = params.get('stroke_length_um', 50000.0)
                        new_freq   = params.get('frequency_hz', 1.0)
                        self._stroke_um_target      = new_stroke
                        self._stroke_um_current     = new_stroke
                        self._freq_hz_target        = new_freq
                        self._freq_hz_current       = new_freq
                        self._extra_params          = {k: v for k, v in params.items()
                                                       if k not in ('stroke_length_um', 'frequency_hz')}
                        self.pattern_start_time       = time.perf_counter()
                        self._pattern_amplitude_scale = 0.0
                        self._current_phase           = 0.0
                        self.state                    = ControllerState.RUNNING
                    # Reset pause/stop state and set full amplitude for fresh/resumed play
                    self._amplitude_target    = 1.0
                    self._pre_pause_amplitude = 1.0
                    self._soft_stopping       = False
                    self._paused              = False
                    if self._session_start_time is None:
                        self._session_start_time = time.perf_counter()

        elif cmd_type == "stop_pattern":
            with self.lock:
                if self.state == ControllerState.RUNNING:
                    self.current_pattern = None
                    self.state           = ControllerState.CALIBRATED_IDLE
            self._amplitude_target    = 1.0
            self._pre_pause_amplitude = 1.0
            self._soft_stopping       = False
            self._paused              = False
            gc.collect()

    def _trigger_estop(self, reason):
        """Triggers an immediate Emergency Stop (E-STOP).

        Sets the controller state to ESTOP, clears active patterns, and places the motor in Sleep Mode.
        """
        with self.lock:
            self.state           = ControllerState.ESTOP
            self.error_msg       = reason
            self.current_pattern = None
        self._soft_stopping    = False
        self._paused           = False
        self._amplitude_target = 1.0
        if self.actuator:
            self._set_motor_mode(self.sdk.MotorMode.SleepMode)
            self.actuator.set_streamed_force_mN(0)
            self.actuator.run()

    def _handle_calibration(self, dt):
        """Stall detection and stage transitions for the calibration state machine (20 Hz)."""
        with self.lock:
            current_pos   = self.position_um
            current_state = self.state

        self._calibration_stage_ticks += 1
        self._position_history.append(current_pos)

        stalled = (
            self._calibration_stage_ticks > 30 and
            len(self._position_history) == self._position_history.maxlen and
            max(self._position_history) - min(self._position_history) < 150.0
        )

        if current_state == ControllerState.CALIBRATING_RETRACT:
            if stalled:
                self.actuator.zero_position()
                self._calibration_target = None
                self._position_history.clear()
                self._calibration_stage_ticks = 0
                with self.lock:
                    self.state = ControllerState.CALIBRATING_EXTEND

        elif current_state == ControllerState.CALIBRATING_EXTEND:
            if stalled:
                if current_pos < 20000:
                    self._trigger_estop("Calibration failed: measured stroke too short")
                    return
                self._calibration_target = None
                self._calibration_stage_ticks = 0
                with self.lock:
                    self.calibrated_length_um = current_pos
                    self.software_min_um      = 5000
                    self.software_max_um      = current_pos - 5000
                    self.state                = ControllerState.CALIBRATING_CENTER
