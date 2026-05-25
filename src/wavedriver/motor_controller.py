import gc
import time
import math
import datetime
import threading
import queue
import collections
from enum import Enum

# ── Modbus register addresses ─────────────────────────────────────────────────
_REG_FORCE_FILTER   = 175   # MB_FORCE_FILTER  (0 = no filter)
_REG_POS_FILTER     = 176   # MB_POS_FILTER    (0 = no filter)
_REG_SOFTSTART_MS   = 150   # PC_SOFTSTART_PERIOD (ms)
_REG_POS_MAX_VEL    = 153   # position-mode velocity cap (mm/s)
_REG_POS_MAX_ACCEL  = 154   # position-mode acceleration cap (mm/s²)
_REG_POS_MAX_DECEL  = 155   # position-mode deceleration cap (mm/s²)

# ── Hardware motion limits ────────────────────────────────────────────────────
_INIT_MAX_VEL_MM_S    = 500    # velocity limit written at init and after calibration
_INIT_MAX_ACCEL_MM_S2 = 8000   # accel/decel limits written at init and after calibration
_INIT_SOFTSTART_MS    = 200    # position controller soft-start period
_CALIB_VEL_UM_S       = 80000.0  # homing traverse speed (µm/s = 80 mm/s)

# ── Safety thresholds ─────────────────────────────────────────────────────────
_TEMP_WARNING_C = 65      # temperature at which a warning banner is shown
_TEMP_ESTOP_C   = 75      # software over-temperature threshold (°C), below 80 °C hardware limit
_VOLTAGE_LOW_MV = 18000   # minimum acceptable supply voltage (mV); 18 V for a nominal 24 V supply

# ── Timing constants ──────────────────────────────────────────────────────────
_TELEMETRY_INTERVAL_S = 0.050   # 20 Hz low-frequency loop period

# ── Internal param filter ─────────────────────────────────────────────────────
_EXTRA_PARAMS_EXCLUDE = frozenset(('stroke_length_um', 'frequency_hz', '_max_catch_up_speed_um_s', '_pattern_name'))


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

    def __init__(self, use_mock: bool = False) -> None:
        """Initializes the controller state, communication fields, and pattern buffers.

        Args:
            use_mock: If True, forces offline simulation mode utilizing the mock actuator.
        """
        self.use_mock = use_mock
        self._simulation_reason = ""

        if self.use_mock:
            from wavedriver import mock_actuator as sdk
            self._simulation_reason = "Mock mode enabled (--mock flag)"
        else:
            try:
                import pyorcasdk as sdk
            except ImportError:
                from wavedriver import mock_actuator as sdk
                self.use_mock = True
                self._simulation_reason = "pyorcasdk not installed — hardware unavailable"

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
        self._paused        = False
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

        # Rate-limited commanded position: smooths approach from far-away positions.
        # None means "reinitialize from current position on next tick".
        self._commanded_pos_um       = None
        self._max_pattern_speed_um_s = 500000.0  # µm/s; updated from pattern params

        # Extra (non-interpolated) pattern params cached at command time
        self._extra_params = {}

        # Activity event log: ring buffer of formatted strings
        self._event_log      = collections.deque(maxlen=100)
        self._temp_warned    = False       # prevents duplicate warning log entries
        self._current_pattern_name = ""   # for telemetry display

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

    def start(self, port: str = "/dev/ttyUSB0", baud: int = 19200) -> None:
        """Starts the background execution control thread.

        Args:
            port: The serial device port path (e.g. '/dev/ttyUSB0').
            baud: Modbus communication speed (e.g. 19200).
        """
        self.port = port
        self.baud = baud
        self.stop_event.clear()
        self.state = ControllerState.CONNECTING
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Safely stops the background thread, placing the motor in Sleep Mode."""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.5)
        self.state = ControllerState.UNCONNECTED

    def send_command(self, cmd_type: str, **kwargs) -> None:
        """Enqueues a command (e.g., 'start_pattern', 'estop') for processing by the thread.

        Args:
            cmd_type: Command identifier.
            **kwargs: Arguments specific to the command.
        """
        self.cmd_queue.put((cmd_type, kwargs))

    def get_telemetry(self) -> dict:
        """Returns a thread-safe snapshot dictionary of live device telemetry.

        Includes state representation, current physical position, feedback resistance force,
        running speed SPM, temperature readings, input voltage, power usage, errors,
        and session elapsed timer.
        """
        now = time.perf_counter()
        with self.lock:
            session_start = self._session_start_time
            max_sess      = self._max_session_s
            elapsed_s     = (now - session_start) if session_start is not None else 0.0
            remaining_s: float | None = (
                max(0.0, max_sess - elapsed_s)
                if max_sess > 0 and session_start is not None else None
            )
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
                "simulation_reason":      self._simulation_reason,
                "session_elapsed_s":      elapsed_s,
                "session_remaining_s":    remaining_s,
                "paused":                 self._paused,
                "temp_warning":           _TEMP_WARNING_C <= self.temperature_C < _TEMP_ESTOP_C,
                "current_pattern_name":   self._current_pattern_name,
                "event_log":              list(self._event_log)[-30:],
            }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _log_event(self, msg: str) -> None:
        """Appends a timestamped event string to the ring-buffer activity log."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._event_log.append(f"[{ts}] {msg}")

    def _set_motor_mode(self, mode) -> None:
        """Sends a motor mode change command to the actuator, caching the state to avoid redundant calls."""
        if self._last_set_mode != mode:
            self.actuator.set_mode(mode)
            self._last_set_mode = mode

    def _update_telemetry(self) -> bool:
        """Fetches the latest data stream block from the actuator and updates telemetry fields.

        Returns:
            True if successful, False otherwise.
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

    def _initialize_hardware(self) -> None:
        """Configure hardware registers, safety limits, PID gains, and disable GC for the control thread.

        Disabling garbage collection prevents periodic latency spikes that could disrupt
        the high-frequency (500 Hz) control loop timing.
        """
        self.actuator.set_max_force(60000)
        self.actuator.write_register_blocking(_REG_POS_FILTER, 0)
        self.actuator.write_register_blocking(_REG_FORCE_FILTER, 0)
        self.actuator.write_register_blocking(_REG_POS_MAX_VEL,   _INIT_MAX_VEL_MM_S)
        self.actuator.write_register_blocking(_REG_POS_MAX_ACCEL, _INIT_MAX_ACCEL_MM_S2)
        self.actuator.write_register_blocking(_REG_POS_MAX_DECEL, _INIT_MAX_ACCEL_MM_S2)
        self.actuator.write_register_blocking(_REG_SOFTSTART_MS,  _INIT_SOFTSTART_MS)
        # pgain 200 mN/µm · igain 0 · dvgain 400 mN·s/m · sat 60000 mN
        self.actuator.tune_position_controller(pgain=200, igain=0, dvgain=400, sat=60000)
        gc.collect()
        gc.disable()

    def _drive_running_pattern(self, now: float, dt: float, pos_um: int) -> None:
        """Generates and sends the target command for the active pattern at 500 Hz.

        Manages:
        - Bidirectional amplitude scaling ramps (soft start/stop).
        - Gradual parameter interpolation (stroke and frequency shifts).
        - Integrated phase tracking to avoid sudden position jumps when frequency changes.
        - Rate-limited commanded position to prevent over-speed catch-up from far positions.
        - Clamps target output to the software safety margins.
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
            # Rate-limit the commanded position so the motor never exceeds the
            # pattern's natural peak speed when approaching from a far position.
            if self._commanded_pos_um is None:
                self._commanded_pos_um = float(pos_um)
            max_step = self._max_pattern_speed_um_s * dt
            diff = target_pos_um - self._commanded_pos_um
            if abs(diff) <= max_step:
                self._commanded_pos_um = target_pos_um
            else:
                self._commanded_pos_um += math.copysign(max_step, diff)
            self._set_motor_mode(self.sdk.MotorMode.PositionMode)
            self.actuator.set_streamed_position_um(int(self._commanded_pos_um))
        elif res_mode == "force":
            clamped = max(-float(max_force), min(float(max_force), res_value))
            self._set_motor_mode(self.sdk.MotorMode.ForceMode)
            self.actuator.set_streamed_force_mN(int(clamped))

    def _drive_calibration(self, dt: float, current_state: ControllerState) -> None:
        """Advances the target position ramp during homing calibration stages at 500 Hz.

        Slowly moves the shaft outward or inward until a physical end-stop stall is detected by the 20 Hz loop.
        """
        with self.lock:
            pos_um = self.position_um

        if self._calibration_target is None:
            self._calibration_target = float(pos_um)

        if current_state == ControllerState.CALIBRATING_RETRACT:
            self._calibration_target -= _CALIB_VEL_UM_S * dt
        elif current_state == ControllerState.CALIBRATING_EXTEND:
            self._calibration_target += _CALIB_VEL_UM_S * dt
        else:  # CALIBRATING_CENTER
            with self.lock:
                center_target = self.calibrated_length_um / 2.0
            step = _CALIB_VEL_UM_S * dt
            diff = center_target - self._calibration_target
            if abs(diff) <= step:
                self._calibration_target = center_target
            else:
                self._calibration_target += math.copysign(step, diff)

        self._set_motor_mode(self.sdk.MotorMode.PositionMode)
        self.actuator.set_streamed_position_um(int(self._calibration_target))

    def _tick_500hz_controls(self, now: float, dt: float, current_state: ControllerState,
                              is_estop: bool, pos_um: int) -> None:
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

    def _drain_command_queue(self) -> None:
        """Drains and processes all pending commands from the command queue in the control thread context."""
        try:
            while True:
                cmd_type, kwargs = self.cmd_queue.get_nowait()
                self._process_command(cmd_type, kwargs)
                self.cmd_queue.task_done()
        except queue.Empty:
            pass

    def _request_soft_stop(self) -> None:
        """Initiate a graceful ramp-to-zero stop (callable from the control thread)."""
        self._amplitude_target = 0.0
        self._soft_stopping    = True
        self._paused           = False

    def _tick_20hz(self, now: float, dt_20hz: float, startup_time: float,
                   current_state: ControllerState, is_estop: bool, prev_pos: int) -> int:
        """20 Hz block: safety monitoring, auto-shutoff, calibration state machine, GC.

        Returns the updated prev_pos for the next speed calculation.
        """
        # ── Session auto-shutoff ──────────────────────────────────────────────
        with self.lock:
            session_start = self._session_start_time
        if (self._max_session_s > 0 and
                session_start is not None and
                not self._soft_stopping and
                current_state == ControllerState.RUNNING and
                (now - session_start) >= self._max_session_s):
            mins = self._max_session_s // 60
            self._log_event(f"Session auto-stop ({mins} min limit reached)")
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
            self.speed_mm_s = ((self.position_um - prev_pos) / 1000.0) / dt_20hz
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

            if temp_C >= _TEMP_WARNING_C:
                if not self._temp_warned:
                    self._temp_warned = True
                    self._log_event(f"Temperature warning: {temp_C} °C (limit: {_TEMP_ESTOP_C} °C)")
            else:
                self._temp_warned = False

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
            self._handle_calibration()

        elif current_state == ControllerState.CALIBRATING_CENTER:
            with self.lock:
                cal_len_snap = self.calibrated_length_um
            center_done = cal_len_snap / 2.0
            if (self._calibration_target is not None and
                    abs(self._calibration_target - center_done) < 1.0):
                self._calibration_target = None
                self.actuator.write_register_blocking(_REG_POS_MAX_VEL,   _INIT_MAX_VEL_MM_S)
                self.actuator.write_register_blocking(_REG_POS_MAX_ACCEL, _INIT_MAX_ACCEL_MM_S2)
                self.actuator.write_register_blocking(_REG_POS_MAX_DECEL, _INIT_MAX_ACCEL_MM_S2)
                with self.lock:
                    self.state = ControllerState.CALIBRATED_IDLE

        elif current_state in (ControllerState.CONNECTED, ControllerState.CALIBRATED_IDLE):
            self._set_motor_mode(self.sdk.MotorMode.SleepMode)
            self.actuator.set_streamed_force_mN(0)
            gc.collect()

        return new_prev_pos

    def _cleanup_on_stop(self) -> None:
        """Performs teardown of communications, resets the motor to Sleep Mode, and re-enables garbage collection."""
        gc.enable()
        gc.collect()
        if self.actuator:
            self._set_motor_mode(self.sdk.MotorMode.SleepMode)
            self.actuator.set_streamed_force_mN(0)
            self.actuator.run()
            self.actuator.disable_stream()
            self.actuator.close_serial_port()

    def _run_loop(self) -> None:
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

            if now - last_telemetry_time >= _TELEMETRY_INTERVAL_S:
                dt_20hz             = now - last_telemetry_time
                last_telemetry_time = now
                prev_pos = self._tick_20hz(
                    now, dt_20hz, startup_time, current_state, is_estop, prev_pos
                )

            elapsed_tick = time.perf_counter() - now
            sleep_time   = tick_interval - elapsed_tick
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._cleanup_on_stop()

    def _process_command(self, cmd_type: str, kwargs: dict) -> None:
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
            self._log_event("E-stop cleared — ready to run")
            return

        if is_estop:
            return

        if cmd_type == "set_safety_limit":
            with self.lock:
                self.max_feedback_force_mN = max(1000, kwargs.get("limit_mN", 55000))

        elif cmd_type == "set_max_session":
            self._max_session_s = max(0, int(kwargs.get("max_session_s", 0)))

        elif cmd_type == "start_calibration":
            self._log_event("Calibration started")
            self._position_history.clear()
            self._calibration_stage_ticks = 0
            self._calibration_target      = None
            self._amplitude_target        = 1.0
            self._soft_stopping           = False
            self._paused                  = False
            with self.lock:
                self._session_start_time   = None   # new calibration = new session
                self._current_pattern_name = ""
                self.state                 = ControllerState.CALIBRATING_RETRACT

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
                self._log_event("Pattern stopped")
                self._request_soft_stop()

        elif cmd_type == "start_pattern":
            pattern_func = kwargs.get("pattern_func")
            params       = kwargs.get("params", {})
            pname        = params.get("_pattern_name", "Unknown")
            with self.lock:
                already_running = (self.state == ControllerState.RUNNING and
                                   self.current_pattern is not None)
                if self.state in (ControllerState.CALIBRATED_IDLE, ControllerState.RUNNING):
                    # Update speed limit from caller-supplied peak velocity (with 10% headroom).
                    raw_speed = params.get('_max_catch_up_speed_um_s', None)
                    if raw_speed is None:
                        s = params.get('stroke_length_um', self._stroke_um_target)
                        f = params.get('frequency_hz', self._freq_hz_target)
                        raw_speed = math.pi * f * (s / 2.0)
                    self._max_pattern_speed_um_s = max(5000.0, raw_speed * 1.10)

                    self._current_pattern_name = pname
                    if already_running:
                        self.current_pattern   = pattern_func
                        self.pattern_params    = params
                        self._stroke_um_target = params.get('stroke_length_um', self._stroke_um_target)
                        self._freq_hz_target   = params.get('frequency_hz', self._freq_hz_target)
                        self._extra_params     = {k: v for k, v in params.items()
                                                  if k not in _EXTRA_PARAMS_EXCLUDE}
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
                                                       if k not in _EXTRA_PARAMS_EXCLUDE}
                        self.pattern_start_time       = time.perf_counter()
                        self._pattern_amplitude_scale = 0.0
                        self._current_phase           = 0.0
                        self._commanded_pos_um        = None   # reinit from current position on next tick
                        self.state                    = ControllerState.RUNNING
                    # Reset pause/stop state and set full amplitude for fresh/resumed play
                    self._amplitude_target    = 1.0
                    self._pre_pause_amplitude = 1.0
                    self._soft_stopping       = False
                    self._paused              = False
                    if self._session_start_time is None:
                        self._session_start_time = time.perf_counter()
                    freq  = params.get('frequency_hz', 1.0)
                    smm   = params.get('stroke_length_um', 50000.0) / 1000.0
                    action = "resumed" if already_running else "started"
                    self._log_event(f"Pattern {action}: {pname} @ {freq:.1f} Hz, {smm:.0f} mm")

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

    def _trigger_estop(self, reason: str) -> None:
        """Triggers an immediate Emergency Stop (E-STOP).

        Sets the controller state to ESTOP, clears active patterns, and places the motor in Sleep Mode.
        """
        self._log_event(f"E-STOP: {reason}")
        with self.lock:
            self.state                = ControllerState.ESTOP
            self.error_msg            = reason
            self.current_pattern      = None
            self._current_pattern_name = ""
        self._soft_stopping    = False
        self._paused           = False
        self._amplitude_target = 1.0
        if self.actuator:
            self._set_motor_mode(self.sdk.MotorMode.SleepMode)
            self.actuator.set_streamed_force_mN(0)
            self.actuator.run()

    def _handle_calibration(self) -> None:
        """Stall detection and stage transitions for the calibration state machine (20 Hz)."""
        with self.lock:
            current_pos   = self.position_um
            current_state = self.state

        self._calibration_stage_ticks += 1
        self._position_history.append(current_pos)

        stalled = (
            self._calibration_stage_ticks > 30 and
            len(self._position_history) == self._position_history.maxlen and
            max(self._position_history) - min(self._position_history) < 400.0
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
                self._log_event(f"Calibration complete: {current_pos // 1000} mm range")
                with self.lock:
                    self.calibrated_length_um = current_pos
                    self.software_min_um      = 5000
                    self.software_max_um      = current_pos - 5000
                    self.state                = ControllerState.CALIBRATING_CENTER
