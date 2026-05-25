from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Typed configuration for MotorController tunables.

    Pass a custom instance to MotorController() to override defaults — useful in tests
    (e.g. shorten ``ui_deadman_s`` for speed) without monkey-patching module constants.
    """

    # Safety thresholds
    temp_warning_c: int = 65
    temp_estop_c: int = 75
    voltage_low_mv: int = 18_000
    comms_watchdog_us: int = 500_000
    ui_deadman_s: float = 5.0

    # Hardware motion limits written at init and after calibration
    init_max_vel_mm_s: int = 500
    init_max_accel_mm_s2: int = 8_000
    init_softstart_ms: int = 200
    calib_vel_um_s: float = 80_000.0

    # Control loop timing
    telemetry_interval_s: float = 0.050
