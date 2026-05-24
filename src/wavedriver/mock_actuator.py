import time
import math
from enum import IntEnum

# Mirror the enums of pyorcasdk
class MotorMode(IntEnum):
    SleepMode = 1
    ForceMode = 2
    PositionMode = 3
    HapticMode = 4
    KinematicMode = 5

class MessagePriority(IntEnum):
    important = 0
    not_important = 1

class SpringCoupling(IntEnum):
    both = 0
    positive = 1
    negative = 2

class OrcaError:
    def __init__(self, failure_type, error_message=""):
        self._failure = failure_type
        self._message = error_message

    def __bool__(self):
        return bool(self._failure)

    def what(self):
        return self._message

    def __repr__(self):
        return f"<OrcaError failure={self._failure}, message='{self._message}'>"

class OrcaResult:
    def __init__(self, value, error):
        self.value = value
        self.error = error

# Aliases for the specific types
OrcaResultInt32 = OrcaResult
OrcaResultUInt16 = OrcaResult
OrcaResultInt16 = OrcaResult
OrcaResultMotorMode = OrcaResult
OrcaResultList = OrcaResult

class StreamData:
    def __init__(self, position=75000, force=0, power=5, temperature=35, voltage=24000, errors=0):
        self.position = position
        self.force = force
        self.power = power
        self.temperature = temperature
        self.voltage = voltage
        self.errors = errors

class Actuator:
    """Simulated actuator mocking the pyorcasdk interface.

    Models a 0.5 kg physical shaft moving along a 150 mm axis, affected by dry friction (1.5 N),
    viscous damping, hardware end-stop collisions, PID control algorithms, and S-curve kinematic limitations.
    """

    def __init__(self):
        """Initializes the physical state, limits, and Modbus registers of the simulated actuator."""
        self.port_path = None
        self.is_open = False
        self.stream_enabled = False
        self.stream_cache = StreamData()

        
        # Physical model state
        self._position_um = 75000.0  # start at mid-stroke (75mm)
        self._velocity_um_s = 0.0
        self._force_mN = 0
        self._errors_bitmask = 0
        self._mode = MotorMode.SleepMode

        # Limits and parameters
        self._max_force_mN  = 50000  # Default 50 N hardware limit
        self._max_power_W   = 100    # Hardware power limit (W)
        self._current_power_W = 0.0  # Live computed power reading (W)
        self._max_temp_C    = 80
        self._board_temp_C = 35
        self._coil_temp_C = 38
        self._voltage_mV = 24000
        
        # Targets
        self._target_force_mN = 0
        self._target_position_um = 75000
        self._constant_force_mN = 0
        
        # Homing limits (initialized during calibration)
        # Standard Orca 6 physical end stops
        self._physical_min_um = 0.0
        self._physical_max_um = 150000.0 # 150mm

        # Hardware velocity/acceleration cursor (mirrors POS_MAX_VEL/ACCEL/DECEL registers)
        # The motor advances an internal cursor toward the target at bounded kinematics.
        # 0 = unlimited (simulated as a very large number)
        self._pos_cursor_um = 75000.0       # cursor starts at same place as shaft
        self._cursor_vel_um_s = 0.0          # cursor velocity (for S-curve simulation)
        self._max_vel_um_s = 0.0             # 0 → unlimited
        self._max_accel_um_s2 = 0.0          # 0 → unlimited
        self._max_decel_um_s2 = 0.0          # 0 → unlimited

        # Time keeping
        self._last_run_time = None
        
        # Kinematic motions storage (0 to 15 slots)
        self._kinematic_motions = {}

    def open_serial_port(self, port_path, baud_rate=19200, interframe_delay=2000):
        self.port_path = port_path
        self.is_open = True
        self._last_run_time = time.perf_counter()
        return OrcaError(0, "")

    def close_serial_port(self):
        self.is_open = False
        self.stream_enabled = False

    def enable_stream(self):
        if not self.is_open:
            raise RuntimeError("Serial port not open.")
        self.stream_enabled = True

    def disable_stream(self):
        self.stream_enabled = False

    def get_errors(self):
        if not self.is_open:
            return OrcaResultUInt16(0, OrcaError(1, "There is no opened serial port. "))
        return OrcaResultUInt16(self._errors_bitmask, OrcaError(0))

    def get_latched_errors(self):
        return self.get_errors()

    def get_mode(self):
        if not self.is_open:
            return OrcaResultMotorMode(MotorMode.SleepMode, OrcaError(1, "There is no opened serial port. "))
        return OrcaResultMotorMode(self._mode, OrcaError(0))

    def set_mode(self, motor_mode):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        self._mode = motor_mode
        return OrcaError(0)

    def zero_position(self):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        # In real actuator, zero_position resets current position as 0
        # In our simulation, we offset the position coordinate system
        # Set physical min to current position
        offset = self._position_um
        self._physical_min_um = 0.0
        self._physical_max_um -= offset
        self._position_um = 0.0
        return OrcaError(0)

    def get_position_um(self):
        if not self.is_open:
            return OrcaResultInt32(0, OrcaError(1, "There is no opened serial port. "))
        return OrcaResultInt32(int(self._position_um), OrcaError(0))

    def get_force_mN(self):
        if not self.is_open:
            return OrcaResultInt32(0, OrcaError(1, "There is no opened serial port. "))
        return OrcaResultInt32(int(self._force_mN), OrcaError(0))

    def get_power_W(self):
        if not self.is_open:
            return OrcaResultUInt16(0, OrcaError(1, "There is no opened serial port. "))
        return OrcaResultUInt16(int(self._current_power_W), OrcaError(0))

    def get_temperature_C(self):
        if not self.is_open:
            return OrcaResultInt16(0, OrcaError(1, "There is no opened serial port. "))
        # Slowly heat up if force is high
        heating = (abs(self._force_mN) / self._max_force_mN) ** 2 * 0.05
        cooling = (self._coil_temp_C - 25.0) * 0.001
        self._coil_temp_C += heating - cooling
        self._board_temp_C = self._coil_temp_C - 3.0
        return OrcaResultInt16(int(self._coil_temp_C), OrcaError(0))

    def get_voltage_mV(self):
        if not self.is_open:
            return OrcaResultUInt16(0, OrcaError(1, "There is no opened serial port. "))
        # Simulated sag under high force
        sag = (abs(self._force_mN) / self._max_force_mN) * 1000
        return OrcaResultUInt16(int(self._voltage_mV - sag), OrcaError(0))

    def clear_errors(self):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        self._errors_bitmask = 0
        return OrcaError(0)

    def set_max_force(self, max_force):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        self._max_force_mN = max_force
        return OrcaError(0)

    def set_max_power(self, max_power):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        self._max_power_W = max_power
        return OrcaError(0)

    def set_max_temp(self, max_temp):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        self._max_temp_C = max_temp
        return OrcaError(0)

    def set_safety_damping(self, max_safety_damping):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        return OrcaError(0)

    def set_constant_force(self, force):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        self._constant_force_mN = force
        return OrcaError(0)

    def set_streamed_force_mN(self, force):
        self._target_force_mN = force

    def set_streamed_position_um(self, position):
        """Set the commanded target. The cursor will move toward this target."""
        self._target_position_um = position

    def run(self):
        """Advances the physical model simulation by a timestep (dt).

        Updates velocity, position, friction forces, power draw, temperature, and coordinates 
        collision responses when hitting physical end-stops.
        """
        if not self.is_open:
            return

        now = time.perf_counter()
        dt = now - self._last_run_time if self._last_run_time else 0.005
        self._last_run_time = now

        # Prevent absurdly large dt if run() was paused
        if dt > 0.1:
            dt = 0.005

        # Physics simulation:
        # Shaft mass = 0.5 kg
        # Acceleration a (m/s^2) = Force (N) / Mass (kg)
        # Acceleration a (um/s^2) = Force (mN) * 2000
        # Friction = dry friction (e.g. 2 N) + viscous damping (e.g. 5 N per m/s)
        
        applied_force_mN = 0.0

        if self._mode == MotorMode.SleepMode:
            # Electromechanical braking: acts as a damper
            applied_force_mN = 0.0
            damping_coeff = 25.0  # high damping
        elif self._mode == MotorMode.ForceMode:
            applied_force_mN = self._target_force_mN
            # Hard limit check
            if abs(applied_force_mN) > self._max_force_mN:
                applied_force_mN = math.copysign(self._max_force_mN, applied_force_mN)
            damping_coeff = 2.0  # low friction
        elif self._mode == MotorMode.PositionMode:
            # ── Hardware Velocity/Acceleration Cursor ────────────────────────
            # Advance internal cursor toward commanded target, respecting
            # POS_MAX_VEL and POS_MAX_ACCEL limits (set via write_register_blocking).
            # 0 means unlimited (use a large sentinel).
            max_v = self._max_vel_um_s   if self._max_vel_um_s   > 0 else 1e9
            max_a = self._max_accel_um_s2 if self._max_accel_um_s2 > 0 else 1e9
            max_d = self._max_decel_um_s2 if self._max_decel_um_s2 > 0 else 1e9

            dist = self._target_position_um - self._pos_cursor_um
            direction = math.copysign(1.0, dist) if dist != 0 else 0.0

            # Deceleration lookahead: how much distance do we need to stop?
            # d_stop = v² / (2 * max_d)
            d_stop = (self._cursor_vel_um_s ** 2) / (2.0 * max_d) if max_d > 0 else 0.0

            if abs(dist) <= 1.0:  # arrived
                self._pos_cursor_um = self._target_position_um
                self._cursor_vel_um_s = 0.0
            elif abs(dist) <= d_stop + 1.0:  # need to decelerate
                decel = min(max_d, abs(self._cursor_vel_um_s) / dt if dt > 0 else max_d)
                self._cursor_vel_um_s -= math.copysign(decel * dt, self._cursor_vel_um_s)
            else:  # can still accelerate
                desired_v = direction * max_v
                delta_v = desired_v - self._cursor_vel_um_s
                accel_step = math.copysign(min(max_a * dt, abs(delta_v)), delta_v)
                self._cursor_vel_um_s += accel_step

            # Clamp cursor velocity
            if abs(self._cursor_vel_um_s) > max_v:
                self._cursor_vel_um_s = math.copysign(max_v, self._cursor_vel_um_s)

            self._pos_cursor_um += self._cursor_vel_um_s * dt

            # ── PID loop: shaft follows cursor (not raw target) ───────────────
            error_um = self._pos_cursor_um - self._position_um
            kp = 1.2  # mN per um (equivalent to 1200 N/m)
            kd = 0.08 # mN per (um/s) (equivalent to 80 Ns/m)
            
            pid_force = error_um * kp - self._velocity_um_s * kd
            applied_force_mN = pid_force
            
            # Hardware saturation
            if abs(applied_force_mN) > self._max_force_mN:
                applied_force_mN = math.copysign(self._max_force_mN, applied_force_mN)
            damping_coeff = 2.0
        else:
            damping_coeff = 5.0

        # Sum of forces: Applied - Damping - Dry Friction
        v_m_s = self._velocity_um_s / 1000000.0
        viscous_friction_mN = v_m_s * damping_coeff * 1000.0
        dry_friction_mN = math.copysign(1500.0, self._velocity_um_s) if abs(self._velocity_um_s) > 10.0 else 0.0
        
        total_force_mN = applied_force_mN - viscous_friction_mN - dry_friction_mN

        # Limit acceleration for physical realism
        # a (um/s^2) = total_force_mN * 2000
        accel_um_s2 = total_force_mN * 2000.0
        
        # Integrate
        self._velocity_um_s += accel_um_s2 * dt
        self._position_um   += self._velocity_um_s * dt
        self._force_mN       = int(applied_force_mN)

        # Live power reading: mechanical output + idle draw + resistive coil losses
        mech_power = abs(self._force_mN / 1000.0 * self._velocity_um_s / 1_000_000.0)
        self._current_power_W = min(mech_power + 5.0 + (self._force_mN / 10000.0) ** 2, 150.0)

        # End-stop collisions
        if self._position_um <= self._physical_min_um:
            self._position_um = self._physical_min_um
            self._velocity_um_s = 0.0
            # Collision reaction force
            self._force_mN = int(applied_force_mN)
        elif self._position_um >= self._physical_max_um:
            self._position_um = self._physical_max_um
            self._velocity_um_s = 0.0
            self._force_mN = int(applied_force_mN)

        # Update stream cache
        self.stream_cache.position    = int(self._position_um)
        self.stream_cache.force       = int(self._force_mN)
        self.stream_cache.power       = int(self._current_power_W)
        self.stream_cache.temperature = int(self._coil_temp_C)
        self.stream_cache.voltage     = int(self._voltage_mV)
        self.stream_cache.errors      = int(self._errors_bitmask)

    def get_stream_data(self):
        return self.stream_cache

    def write_register_blocking(self, reg_address, write_data, priority=None):
        """Simulates writing to Modbus registers, capturing velocity and acceleration constraints for the PID cursor.

        Args:
            reg_address (int): Modbus register address.
            write_data (int): Numeric value to write.
            priority (MessagePriority, optional): Message priority flag.
        """
        UNLIMITED = 0.0
        if reg_address == 153:  # POS_MAX_VEL (mm/s → µm/s)
            self._max_vel_um_s = write_data * 1000.0 if write_data > 0 else UNLIMITED
        elif reg_address == 154:  # POS_MAX_ACCEL (mm/s² → µm/s²)
            self._max_accel_um_s2 = write_data * 1000.0 if write_data > 0 else UNLIMITED
        elif reg_address == 155:  # POS_MAX_DECEL (mm/s² → µm/s²)
            self._max_decel_um_s2 = write_data * 1000.0 if write_data > 0 else UNLIMITED
        return OrcaError(0)

    def read_register_blocking(self, reg_address, priority=None):
        return OrcaResultUInt16(0, OrcaError(0))

    def write_wide_register_blocking(self, reg_address, write_data, priority=None):
        return OrcaError(0)

    def read_wide_register_blocking(self, reg_address, priority=None):
        return OrcaResultInt32(0, OrcaError(0))

    def time_since_last_response_microseconds(self):
        return 1000

    def trigger_kinematic_motion(self, id):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        if id in self._kinematic_motions:
            motion = self._kinematic_motions[id]
            # Transition to Kinematic Mode and configure target
            self._mode = MotorMode.KinematicMode
            self._target_position_um = motion['position']
            # Simplify transition to position mode for our physics
            self._mode = MotorMode.PositionMode
            return OrcaError(0)
        return OrcaError(2, "Invalid kinematic motion ID")

    def set_kinematic_motion(self, id, position, time, delay, type, auto_next, next_id=-1):
        if not self.is_open:
            return OrcaError(1, "There is no opened serial port. ")
        self._kinematic_motions[id] = {
            'position': position,
            'time': time,
            'delay': delay,
            'type': type,
            'auto_next': auto_next,
            'next_id': next_id
        }
        return OrcaError(0)

    def tune_position_controller(self, pgain, igain, dvgain, sat, dgain=0):
        pass

    def name(self):
        return "Simulated Orca 6"
