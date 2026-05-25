import math
from typing import Protocol


class PatternFunc(Protocol):
    """Interface satisfied by every pattern function.

    Returns a tuple (mode, value) where:
    - mode (str): The control mode, either "position" (target in micrometers, µm) or "force" (target in milli-Newtons, mN).
    - value (float): The target value for the motor controller in the selected mode.

    The motor controller clamps force-mode output to the configured safety limit
    to protect the user.
    """
    def __call__(self, t: float, position_um: int, speed_mm_s: float,
                 L: float, **kwargs) -> tuple[str, float]: ...


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base(L: float, stroke_length_um: float, amplitude_scale: float) -> tuple[float, float]:
    """Helper to calculate the center position and scale amplitude.

    Returns (center, amplitude) clamped to 5 mm (5000 µm) margins on either end
    of the calibrated length to prevent the motor from hitting physical end-stops.
    """
    C = L / 2.0
    A = min(stroke_length_um / 2.0, C - 5000.0) * amplitude_scale
    return C, A


# ── Patterns ──────────────────────────────────────────────────────────────────

def wave_pattern(t, position_um, speed_mm_s, L, stroke_length_um=100000, frequency_hz=1.0,
                 _amplitude_scale=None, _phase=None, **kwargs):
    """Smooth sine-wave reciprocating motion with a 2-second soft-start ramp.

    Provides a classic, steady, and predictable back-and-forth movement.

    Args:
        t (float): Elapsed time in seconds.
        position_um (int): Current motor position in micrometers.
        speed_mm_s (float): Current motor speed in millimeters per second.
        L (float): Calibrated total shaft stroke length in micrometers.
        stroke_length_um (float): Desired stroke length in micrometers.
        frequency_hz (float): Wave frequency in Hertz (cycles per second).
        _amplitude_scale (float, optional): Dynamic scaling factor (0.0 to 1.0) for soft-start/stop.
        _phase (float, optional): Integrated phase angle to prevent jump-discontinuities on frequency changes.

    Returns:
        tuple[str, float]: Control mode ("position") and target position (µm).
    """
    scale = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A  = _base(L, stroke_length_um, scale)
    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    return "position", C + A * math.sin(phase)


def realistic_pattern(t, position_um, speed_mm_s, L, stroke_length_um=100000, frequency_hz=1.0,
                      rod_ratio=2.5, _amplitude_scale=None, _phase=None, **kwargs):
    """Slider-crank kinematics — mimics the asymmetric motion profile of physical reciprocating mechanisms.

    Produces a highly lifelike thrust feel. The asymmetric speed curve means the forward and
    backward strokes differ in acceleration.

    Args:
        t (float): Elapsed time in seconds.
        position_um (int): Current motor position in micrometers.
        speed_mm_s (float): Current motor speed in millimeters per second.
        L (float): Calibrated total shaft stroke length in micrometers.
        stroke_length_um (float): Desired stroke length in micrometers.
        frequency_hz (float): Cycle frequency in Hertz (cycles per second).
        rod_ratio (float): Rod-to-crank length ratio (typically 2.5 to 5.0). Lower values produce 
            greater velocity/acceleration asymmetry, resulting in a more distinct and realistic thrust.
        _amplitude_scale (float, optional): Dynamic scaling factor (0.0 to 1.0).
        _phase (float, optional): Integrated phase angle.

    Returns:
        tuple[str, float]: Control mode ("position") and target position (µm).
    """
    scale = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A  = _base(L, stroke_length_um, scale)
    theta  = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    lam    = 1.0 / rod_ratio
    y      = math.cos(theta) + math.sqrt((1.0 / lam) ** 2 - math.sin(theta) ** 2)
    return "position", C + A * (y - 1.0 / lam)


def thrust_pattern(t, position_um, speed_mm_s, L, stroke_length_um=100000, frequency_hz=1.0,
                   _amplitude_scale=None, _phase=None, **kwargs):
    """Slow retract, rapid thrust, brief hold — accented extend stroke.

    Mimics a highly dynamic thrusting motion by allocating 60% of the cycle to a slow
    retraction, 20% to a high-speed forward stroke, and 20% to a stationary hold at the 
    fully extended position before repeating.

    Args:
        t (float): Elapsed time in seconds.
        position_um (int): Current motor position in micrometers.
        speed_mm_s (float): Current motor speed in millimeters per second.
        L (float): Calibrated total shaft stroke length in micrometers.
        stroke_length_um (float): Desired stroke length in micrometers.
        frequency_hz (float): Thrust cycle frequency in Hertz.
        _amplitude_scale (float, optional): Dynamic scaling factor (0.0 to 1.0).
        _phase (float, optional): Integrated phase angle.

    Returns:
        tuple[str, float]: Control mode ("position") and target position (µm).
    """
    scale = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A  = _base(L, stroke_length_um, scale)
    TWO_PI = 2.0 * math.pi
    phase  = _phase if _phase is not None else TWO_PI * frequency_hz * t
    u      = (phase % TWO_PI) / TWO_PI  # [0, 1) within current cycle
    if u < 0.6:
        val = C + A - (2.0 * A * (u / 0.6))
    elif u < 0.8:
        frac = (u - 0.6) / 0.2
        val  = C - A + A * (1.0 - math.cos(math.pi * frac))
    else:
        val = C + A
    return "position", val


def pulse_pattern(t, position_um, speed_mm_s, L, stroke_length_um=100000, frequency_hz=0.5,
                  _amplitude_scale=None, _phase=None, **kwargs):
    """Rapid burst of 4 strokes followed by a rest pause at center.

    Delivers high-intensity stimulation bursts followed by periods of anticipated rest.

    Args:
        t (float): Elapsed time in seconds.
        position_um (int): Current motor position in micrometers.
        speed_mm_s (float): Current motor speed in millimeters per second.
        L (float): Calibrated total shaft stroke length in micrometers.
        stroke_length_um (float): Desired stroke length in micrometers.
        frequency_hz (float): Burst repetition rate (bursts per second).
        _amplitude_scale (float, optional): Dynamic scaling factor (0.0 to 1.0).
        _phase (float, optional): Integrated phase angle.

    Returns:
        tuple[str, float]: Control mode ("position") and target position (µm).
    """
    scale  = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A   = _base(L, stroke_length_um, scale)
    TWO_PI = 2.0 * math.pi
    phase  = _phase if _phase is not None else TWO_PI * frequency_hz * t
    u      = (phase % TWO_PI) / TWO_PI  # [0, 1)
    BURST_FRAC = 0.70
    STROKES    = 4
    if u < BURST_FRAC:
        # Compress STROKES full sine cycles into the burst window
        val = C + A * math.sin(u / BURST_FRAC * STROKES * TWO_PI)
    else:
        val = C + A * 0.25  # rest slightly extended — less mechanical than dead center
    return "position", val


def tease_pattern(t, position_um, speed_mm_s, L, stroke_length_um=100000, frequency_hz=1.0,
                  _amplitude_scale=None, _phase=None, **kwargs):
    """Irregular motion from four incommensurable frequencies — unpredictable and varied.

    Combines four out-of-phase sine wave generators (scaled by √2, e, and φ−1) to create a
    continuous, non-repetitive sensory pattern that remains fresh well past the 60-second mark.

    Args:
        t (float): Elapsed time in seconds.
        position_um (int): Current motor position in micrometers.
        speed_mm_s (float): Current motor speed in millimeters per second.
        L (float): Calibrated total shaft stroke length in micrometers.
        stroke_length_um (float): Desired stroke length in micrometers.
        frequency_hz (float): Base frequency in Hertz.
        _amplitude_scale (float, optional): Dynamic scaling factor (0.0 to 1.0).
        _phase (float, optional): Integrated phase angle.

    Returns:
        tuple[str, float]: Control mode ("position") and target position (µm).
    """
    scale = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A  = _base(L, stroke_length_um, scale)
    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    combined = (0.55 * math.sin(phase) +
                0.25 * math.sin(1.41421 * phase + 0.5) +
                0.12 * math.sin(2.71828 * phase + 2.3) +
                0.08 * math.sin(0.61803 * phase + 1.2))
    # Clamp combined to [-1, 1] before scaling: irrational ratios can briefly
    # push the sum slightly outside this range, which would exceed stroke bounds.
    combined = max(-1.0, min(1.0, combined))
    return "position", C + A * combined


def escalate_pattern(t, position_um, speed_mm_s, L, stroke_length_um=100000, frequency_hz=1.0,
                     escalate_duration_s=300.0, _amplitude_scale=None, _phase=None, **kwargs):
    """Sine wave whose amplitude builds from zero to full over escalate_duration_s seconds.

    Designed for gradual build-up play, ramping intensity slowly from silent movement 
    up to full capacity over a prolonged period.

    Args:
        t (float): Elapsed time in seconds.
        position_um (int): Current motor position in micrometers.
        speed_mm_s (float): Current motor speed in millimeters per second.
        L (float): Calibrated total shaft stroke length in micrometers.
        stroke_length_um (float): Desired stroke length in micrometers.
        frequency_hz (float): Sine frequency in Hertz.
        escalate_duration_s (float): Escalation duration in seconds.
        _amplitude_scale (float, optional): Dynamic scaling factor (0.0 to 1.0).
        _phase (float, optional): Integrated phase angle.

    Returns:
        tuple[str, float]: Control mode ("position") and target position (µm).
    """
    time_progress = min(1.0, t / escalate_duration_s) if escalate_duration_s > 0 else 1.0
    soft_start    = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A  = _base(L, stroke_length_um, soft_start * time_progress)
    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    return "position", C + A * math.sin(phase)


def depth_pattern(t, position_um, speed_mm_s, L, stroke_length_um=100000, frequency_hz=1.0,
                  depth_period_s=20.0, _amplitude_scale=None, _phase=None, **kwargs):
    """Sine carrier whose penetration depth slowly oscillates between shallow and full stroke.

    The retracted (near) end stays fixed while the extended (far) end drifts between 35%
    and 100% of the configured stroke over depth_period_s seconds, giving a continuous
    sense of varying depth without any abrupt transitions.

    The depth envelope is derived from the accumulated carrier phase (_phase) so it freezes
    correctly on pause and advances smoothly across frequency changes.

    Args:
        t (float): Elapsed time in seconds.
        position_um (int): Current motor position in micrometers.
        speed_mm_s (float): Current motor speed in millimeters per second.
        L (float): Calibrated total shaft stroke length in micrometers.
        stroke_length_um (float): Maximum stroke length in micrometers.
        frequency_hz (float): Carrier sine frequency in Hertz.
        depth_period_s (float): Duration of one full shallow→deep→shallow cycle in seconds.
        _amplitude_scale (float, optional): Dynamic scaling factor (0.0 to 1.0).
        _phase (float, optional): Integrated phase angle.

    Returns:
        tuple[str, float]: Control mode ("position") and target position (µm).
    """
    scale = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A  = _base(L, stroke_length_um, scale)

    # Depth envelope: slowly oscillates amplitude between 35% and 100% of A.
    # Derived from carrier cycles so the envelope respects pause/resume phase freezing.
    if _phase is not None:
        carrier_cycles = _phase / (2.0 * math.pi)
        slow_phase = 2.0 * math.pi * carrier_cycles / (max(1.0, depth_period_s) * max(0.01, frequency_hz))
    else:
        slow_phase = 2.0 * math.pi * t / max(1.0, depth_period_s)

    depth_mod  = 0.675 + 0.325 * math.sin(slow_phase)   # oscillates [0.35, 1.00]
    effective_A = A * depth_mod

    # Fix the near end (retracted position) so only the far end changes depth.
    # near_end = C - A  (constant),  center shifts so center - effective_A = near_end.
    center = (C - A) + effective_A

    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    return "position", center + effective_A * math.sin(phase)


def edge_pattern(t, position_um, speed_mm_s, L, stroke_length_um=100000, frequency_hz=1.0,
                 edge_period_s=60.0, _amplitude_scale=None, _phase=None, **kwargs):
    """Ramps intensity to peak over 75% of edge_period_s, then drops sharply back to zero.

    Designed for edging routines, providing repeating cycles of building intensity
    followed by a sudden drop to complete rest.

    The edging envelope is derived from the accumulated carrier phase (_phase) rather than
    wall-clock time, so the envelope position freezes correctly when the pattern is paused
    and resumes exactly where it left off.

    Args:
        t (float): Elapsed time in seconds.
        position_um (int): Current motor position in micrometers.
        speed_mm_s (float): Current motor speed in millimeters per second.
        L (float): Calibrated total shaft stroke length in micrometers.
        stroke_length_um (float): Desired stroke length in micrometers.
        frequency_hz (float): Sine frequency in Hertz.
        edge_period_s (float): Total period of one edging loop in seconds.
        _amplitude_scale (float, optional): Dynamic scaling factor (0.0 to 1.0).
        _phase (float, optional): Integrated phase angle.

    Returns:
        tuple[str, float]: Control mode ("position") and target position (µm).
    """
    scale  = _amplitude_scale if _amplitude_scale is not None else 1.0
    period = max(1.0, edge_period_s)
    PEAK_FRAC = 0.75

    if _phase is not None:
        # Express the edge period in carrier cycles so the envelope follows _phase.
        # edge_period_cycles = edge_period_s * frequency_hz (number of carrier cycles per edge cycle).
        edge_period_cycles = period * max(0.01, frequency_hz)
        carrier_cycles     = _phase / (2.0 * math.pi)
        pos_in_cycle       = math.fmod(carrier_cycles, edge_period_cycles) / edge_period_cycles
    else:
        pos_in_cycle = (t % period) / period

    if pos_in_cycle < PEAK_FRAC:
        envelope = pos_in_cycle / PEAK_FRAC   # linear ramp 0 → 1
    else:
        envelope = 0.0                         # instant drop back to zero

    C, A  = _base(L, stroke_length_um, scale * envelope)
    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    return "position", C + A * math.sin(phase)
