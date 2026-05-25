import bisect
import dataclasses
import math
from collections.abc import Callable
from typing import Any, Protocol


class PatternFunc(Protocol):
    """Interface satisfied by every pattern function.

    Returns a tuple (mode, value) where:
    - mode (str): The control mode, either "position" (target in micrometers, µm) or "force" (target in milli-Newtons, mN).
    - value (float): The target value for the motor controller in the selected mode.

    The motor controller clamps force-mode output to the configured safety limit
    to protect the user.
    """

    def __call__(
        self,
        t: float,
        position_um: int,
        speed_mm_s: float,
        L: float,
        **kwargs: Any,
    ) -> tuple[str, float]: ...


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


def wave_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 1.0,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
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
    C, A = _base(L, stroke_length_um, scale)
    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    return "position", C + A * math.sin(phase)


def realistic_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 1.0,
    rod_ratio: float = 2.5,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
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
    C, A = _base(L, stroke_length_um, scale)
    theta = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    lam = 1.0 / rod_ratio
    y = math.cos(theta) + math.sqrt((1.0 / lam) ** 2 - math.sin(theta) ** 2)
    return "position", C + A * (y - 1.0 / lam)


def thrust_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 1.0,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
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
    C, A = _base(L, stroke_length_um, scale)
    TWO_PI = 2.0 * math.pi
    phase = _phase if _phase is not None else TWO_PI * frequency_hz * t
    u = (phase % TWO_PI) / TWO_PI  # [0, 1) within current cycle
    if u < 0.6:
        val = C + A - (2.0 * A * (u / 0.6))
    elif u < 0.8:
        frac = (u - 0.6) / 0.2
        val = C - A + A * (1.0 - math.cos(math.pi * frac))
    else:
        val = C + A
    return "position", val


def pulse_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 0.5,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
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
    scale = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A = _base(L, stroke_length_um, scale)
    TWO_PI = 2.0 * math.pi
    phase = _phase if _phase is not None else TWO_PI * frequency_hz * t
    u = (phase % TWO_PI) / TWO_PI  # [0, 1)
    BURST_FRAC = 0.70
    STROKES = 4
    if u < BURST_FRAC:
        # Compress STROKES full sine cycles into the burst window
        val = C + A * math.sin(u / BURST_FRAC * STROKES * TWO_PI)
    else:
        val = C + A * 0.25  # rest slightly extended — less mechanical than dead center
    return "position", val


def tease_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 1.0,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
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
    C, A = _base(L, stroke_length_um, scale)
    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    combined = (
        0.55 * math.sin(phase)
        + 0.25 * math.sin(1.41421 * phase + 0.5)
        + 0.12 * math.sin(2.71828 * phase + 2.3)
        + 0.08 * math.sin(0.61803 * phase + 1.2)
    )
    # Clamp combined to [-1, 1] before scaling: irrational ratios can briefly
    # push the sum slightly outside this range, which would exceed stroke bounds.
    combined = max(-1.0, min(1.0, combined))
    return "position", C + A * combined


def escalate_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 1.0,
    escalate_duration_s: float = 300.0,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
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
    soft_start = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A = _base(L, stroke_length_um, soft_start * time_progress)
    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    return "position", C + A * math.sin(phase)


def depth_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 1.0,
    depth_period_s: float = 20.0,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
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
    C, A = _base(L, stroke_length_um, scale)

    # Depth envelope: slowly oscillates amplitude between 35% and 100% of A.
    # Derived from carrier cycles so the envelope respects pause/resume phase freezing.
    if _phase is not None:
        carrier_cycles = _phase / (2.0 * math.pi)
        slow_phase = (
            2.0 * math.pi * carrier_cycles / (max(1.0, depth_period_s) * max(0.01, frequency_hz))
        )
    else:
        slow_phase = 2.0 * math.pi * t / max(1.0, depth_period_s)

    depth_mod = 0.675 + 0.325 * math.sin(slow_phase)  # oscillates [0.35, 1.00]
    effective_A = A * depth_mod

    # Fix the near end (retracted position) so only the far end changes depth.
    # near_end = C - A  (constant),  center shifts so center - effective_A = near_end.
    center = (C - A) + effective_A

    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    return "position", center + effective_A * math.sin(phase)


def edge_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 1.0,
    edge_period_s: float = 60.0,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
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
    scale = _amplitude_scale if _amplitude_scale is not None else 1.0
    period = max(1.0, edge_period_s)
    PEAK_FRAC = 0.75

    if _phase is not None:
        # Express the edge period in carrier cycles so the envelope follows _phase.
        # edge_period_cycles = edge_period_s * frequency_hz (number of carrier cycles per edge cycle).
        edge_period_cycles = period * max(0.01, frequency_hz)
        carrier_cycles = _phase / (2.0 * math.pi)
        pos_in_cycle = math.fmod(carrier_cycles, edge_period_cycles) / edge_period_cycles
    else:
        pos_in_cycle = (t % period) / period

    if pos_in_cycle < PEAK_FRAC:
        envelope = pos_in_cycle / PEAK_FRAC  # linear ramp 0 → 1
    else:
        envelope = 0.0  # instant drop back to zero

    C, A = _base(L, stroke_length_um, scale * envelope)
    phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
    return "position", C + A * math.sin(phase)


def adaptive_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    frequency_hz: float = 1.0,
    force_mN: float = 0.0,
    adaptive_mode: str = "ease",
    sensitivity: float = 1.0,
    _amplitude_scale: float | None = None,
    _phase: float | None = None,
    **kwargs: Any,
) -> tuple[str, float]:
    """Motion that dynamically adapts to external resistance (forces) on the shaft.

    Supports two modes:
    - "ease": As resistance rises, the stroke is scaled down (up to 75%) to ease off.
    - "give_and_take": Yields by shifting the center position and softening stroke.
    """
    scale = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)

    # 25 N (25000 mN) is the reference threshold for high force
    force_ratio = min(1.0, abs(force_mN) / 25000.0) * sensitivity

    if adaptive_mode == "ease":
        stroke_scale = 1.0 - 0.75 * force_ratio
        C, A = _base(L, stroke_length_um * stroke_scale, scale)
        phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
        return "position", C + A * math.sin(phase)
    else:  # give_and_take
        # Yield to push/pull by moving the center back/forward
        yield_um = -math.copysign(25000.0 * force_ratio, force_mN)
        effective_stroke = stroke_length_um * (1.0 - 0.5 * force_ratio)
        C, A = _base(L, effective_stroke, scale)
        C_shifted = max(5000.0 + A, min(L - 5000.0 - A, C + yield_um))
        phase = _phase if _phase is not None else 2.0 * math.pi * frequency_hz * t
        return "position", C_shifted + A * math.sin(phase)


def funscript_pattern(
    t: float,
    position_um: int,
    speed_mm_s: float,
    L: float,
    stroke_length_um: float = 100000,
    _amplitude_scale: float | None = None,
    funscript_actions: list[list[float]] | None = None,
    funscript_loop: bool = True,
    **kwargs: Any,
) -> tuple[str, float]:
    """Follows a list of action keyframes parsed from a .funscript file.

    Interpolates between keyframes and scales targets to the configured stroke limits.
    """
    scale = _amplitude_scale if _amplitude_scale is not None else min(1.0, t / 2.0)
    C, A = _base(L, stroke_length_um, scale)

    if not funscript_actions:
        return "position", C

    # Each action is a list/tuple: [time_s, pos_pct]
    duration = funscript_actions[-1][0]
    if duration <= 0:
        return "position", C

    lookup_time = t
    if funscript_loop:
        lookup_time = t % duration
    else:
        lookup_time = min(t, duration)

    times = [a[0] for a in funscript_actions]
    idx = bisect.bisect_right(times, lookup_time)

    if idx == 0:
        pos_pct = funscript_actions[0][1]
    elif idx >= len(funscript_actions):
        pos_pct = funscript_actions[-1][1]
    else:
        t0, p0 = funscript_actions[idx - 1]
        t1, p1 = funscript_actions[idx]
        if t1 == t0:
            pos_pct = p0
        else:
            frac = (lookup_time - t0) / (t1 - t0)
            pos_pct = p0 + (p1 - p0) * frac

    # Map pos_pct (0 to 100) to actual stroke range [C - A, C + A]
    target_pos = (C - A) + (pos_pct / 100.0) * (2.0 * A)
    return "position", target_pos


# ── Pattern registry ──────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class PatternDef:
    """Metadata and peak-speed formula for a single motion pattern.

    ``peak_speed_um_s(stroke_um, freq_hz)`` returns the pattern's theoretical peak
    velocity (µm/s) at the given parameters.  MotorController uses this to cap the
    catch-up speed so the motor never repositions faster than normal playback.
    """

    name: str
    func: PatternFunc
    label: str
    description: str
    peak_speed_um_s: Callable[[float, float], float]


def _peak_sine(stroke_um: float, freq_hz: float) -> float:
    return math.pi * max(freq_hz, 0.01) * stroke_um / 2.0


def _peak_realistic(stroke_um: float, freq_hz: float) -> float:
    # Slider-crank is asymmetric; peak is ~50% higher than a pure sine at the same params.
    return 1.5 * math.pi * max(freq_hz, 0.01) * stroke_um / 2.0


def _peak_thrust(stroke_um: float, freq_hz: float) -> float:
    # Fast stroke traverses the full 2A in 20% of the period.
    return 2.0 * (stroke_um / 2.0) * max(freq_hz, 0.01) / 0.20


def _peak_pulse(stroke_um: float, freq_hz: float) -> float:
    # Four sine cycles compressed into 70% of the period.
    return (4.0 / 0.70) * math.pi * max(freq_hz, 0.01) * stroke_um / 2.0


PATTERN_REGISTRY: dict[str, PatternDef] = {
    "Wave": PatternDef(
        name="Wave",
        func=wave_pattern,
        label="Wave",
        description="Smooth sine-wave reciprocating motion",
        peak_speed_um_s=_peak_sine,
    ),
    "Realistic": PatternDef(
        name="Realistic",
        func=realistic_pattern,
        label="Realistic",
        description="Slider-crank kinematics — asymmetric like a physical mechanism",
        peak_speed_um_s=_peak_realistic,
    ),
    "Thrust": PatternDef(
        name="Thrust",
        func=thrust_pattern,
        label="Thrust",
        description="Slow retract, rapid thrust, brief hold — accented extend stroke",
        peak_speed_um_s=_peak_thrust,
    ),
    "Pulse": PatternDef(
        name="Pulse",
        func=pulse_pattern,
        label="Pulse",
        description="Rapid burst of 4 strokes followed by a rest pause at center",
        peak_speed_um_s=_peak_pulse,
    ),
    "Tease": PatternDef(
        name="Tease",
        func=tease_pattern,
        label="Tease",
        description="Irregular motion from four incommensurable frequencies — unpredictable and varied",
        peak_speed_um_s=_peak_sine,
    ),
    "Escalate": PatternDef(
        name="Escalate",
        func=escalate_pattern,
        label="Escalate",
        description="Sine wave whose amplitude builds from zero to full over time",
        peak_speed_um_s=_peak_sine,
    ),
    "Edge": PatternDef(
        name="Edge",
        func=edge_pattern,
        label="Edge",
        description="Ramps intensity to peak then drops sharply — repeating edging cycles",
        peak_speed_um_s=_peak_sine,
    ),
    "Depth": PatternDef(
        name="Depth",
        func=depth_pattern,
        label="Depth",
        description="Sine carrier whose penetration depth slowly oscillates between shallow and full",
        peak_speed_um_s=_peak_sine,
    ),
    "Adaptive": PatternDef(
        name="Adaptive",
        func=adaptive_pattern,
        label="Adaptive",
        description="Responsive motion that shifts center or stroke based on force feedback",
        peak_speed_um_s=_peak_sine,
    ),
    "Funscript": PatternDef(
        name="Funscript",
        func=funscript_pattern,
        label="Funscript",
        description="Follows custom keyframe motion profiles imported from .funscript files",
        peak_speed_um_s=_peak_sine,
    ),
}
