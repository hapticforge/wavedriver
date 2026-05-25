# Architecture

## Overview

Wavedriver is a desktop application with a Python backend and a React frontend, bridged by [pywebview](https://pywebview.app/). The backend runs a multi-rate control loop that drives the Orca 6 actuator; the frontend polls telemetry and sends commands via a JSON API.

```
┌─────────────────────────────────────────┐
│  React (Vite SPA)                       │
│  ├── useController  — telemetry at 20Hz │
│  ├── useSettings    — persist to disk   │
│  └── Components                         │
└────────────┬───────────────┬────────────┘
             │ pywebview API │
┌────────────▼───────────────▼────────────┐
│  WebviewAPI (main.py)                   │
│  ├── send_command / get_telemetry       │
│  ├── Storage  — presets / session / log │
│  └── _VideoHTTPServer                  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│  MotorController (motor_controller.py)  │
│  ├── 500 Hz control thread             │
│  └── 20 Hz monitoring thread           │
└────────────────┬────────────────────────┘
                 │ Modbus RS-485
┌────────────────▼────────────────────────┐
│  Orca 6 actuator  (or MockActuator)    │
└─────────────────────────────────────────┘
```

---

## Multi-rate control loop

`MotorController` runs two background threads:

### 500 Hz control thread (`_run_loop`)

Fires every 2 ms. Responsible for:

1. **Reading telemetry** (`_update_telemetry`): reads position, force, speed, temperature, voltage, errors from the actuator via Modbus. Updates `_telemetry_lock`-protected shared state.
2. **Driving the pattern** (`_drive_running_pattern`): calls the active pattern function to get a target position, clamps it to software limits, checks it is finite (NaN/inf → e-stop), then sends a position command to the actuator.
3. **Soft-start/stop ramping**: position commands are passed through `_position_ramp` which interpolates from the current position when starting or stopping, preventing abrupt jumps.

The 500 Hz thread does **not** perform safety checks — that is deliberately delegated to the 20 Hz thread to avoid adding latency to the control path.

### 20 Hz monitoring thread (`_tick_20hz`)

Fires every 50 ms via a `threading.Timer` chain. Responsible for:

1. **Force limit check** (`_force_exceed_count`): if force exceeds the configured limit for 3 consecutive ticks (150 ms), e-stop fires.
2. **Temperature monitoring**: warning event at 65 °C, e-stop at 75 °C.
3. **Under-voltage check**: e-stop if supply < 18 V.
4. **Comms watchdog**: e-stop if no Modbus response for 500 ms (after a 2-second startup grace).
5. **UI deadman**: soft-stop if `get_telemetry()` has not been called for 5 seconds while RUNNING (the React polling loop calls it at 20 Hz; if the UI freezes, this fires).

---

## State machine

```
UNCONNECTED
    │  serial open + actuator found
    ▼
CONNECTED
    │  start_calibration command
    ▼
CALIBRATING_CENTER → CALIBRATING_EXTEND → CALIBRATING_RETRACT
    │  end-stop found at both limits
    ▼
CALIBRATED_IDLE
    │  start_pattern command
    ▼
RUNNING ──pause_pattern──► PAUSED
    │                           │ resume_pattern
    │ ◄─────────────────────────┘
    │  soft_stop / e-stop / session timeout / watchdog
    ▼
CALIBRATED_IDLE  (or ERROR on e-stop)
    │  clear_estop
    ▼
CALIBRATED_IDLE  (or CONNECTED if not calibrated)
```

State transitions are serialized through `_command_queue` (a `queue.Queue`). The 500 Hz loop dequeues one command per tick and calls `_process_command`, which contains the full state machine logic.

---

## Pattern system (`patterns.py`)

Each pattern is a Python generator function with this signature:

```python
def my_pattern(
    t: float,           # time elapsed since pattern start (seconds)
    stroke_length_um: float,  # calibrated stroke in micrometres
    **kwargs,           # pattern-specific params
) -> Generator[tuple[str, float], None, None]:
    while True:
        yield "position", <target_um>
```

Patterns are registered in `PATTERN_REGISTRY` as `PatternDef` frozen dataclasses that also carry:
- `label` / `description` — shown in the UI
- `peak_speed_um_s(stroke_um, freq_hz)` — used to compute the safe catch-up speed limit for position ramps

The 500 Hz loop calls `next()` on the active generator each tick.

---

## Storage layer (`storage.py`)

Three files under `~/.config/wavedriver/`:

| File | Format | Written by |
|---|---|---|
| `session.json` | JSON | On any safety/session setting change |
| `presets.json` | JSON | On preset save |
| `history.jsonl` | Newline-delimited JSON | On session end (when `history_enabled`) |

All writes are atomic: data is written to a `.tmp` sibling, then `os.replace()` swaps it in. Corrupt files are renamed to `.bak` and defaults are used — the app never crashes on a bad config file. History is capped at 500 entries.

---

## Configuration (`config.py`)

All safety thresholds and timing constants live in the `Config` frozen dataclass:

```python
Config(
    force_limit_mN=55000,
    temp_warn_C=65.0,
    temp_estop_C=75.0,
    voltage_low_mV=18000,
    comms_watchdog_us=500_000,
    ui_deadman_s=5.0,
    ...
)
```

`MotorController(config=Config(...))` makes every threshold injectable for tests — no monkey-patching of module globals.

---

## Mock actuator (`mock_actuator.py`)

`MockActuator` implements the same `ActuatorProtocol` as the real SDK, simulating:
- Second-order mass dynamics with dry + viscous friction
- Physical end-stop collisions (stiff spring + damping)
- PID position tracking
- Call-rate-dependent temperature model

Known divergences from real hardware are documented in the module docstring.

---

## Key files

| File | Role |
|---|---|
| `main.py` | CLI entry point, pywebview bridge (`WebviewAPI`), video HTTP server |
| `motor_controller.py` | Multi-rate control loop, state machine, safety enforcement |
| `patterns.py` | Pattern generators + `PATTERN_REGISTRY` |
| `storage.py` | Atomic persistence — session, presets, history |
| `config.py` | All tuneable thresholds in one place |
| `actuator_protocol.py` | `ActuatorProtocol` / `StreamDataProtocol` structural types |
| `mock_actuator.py` | Physics simulation for `--mock` mode |
| `web/src/` | React SPA — hooks, components, CSS |
