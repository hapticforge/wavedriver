# Wavedriver

Desktop controller for the **Iris Dynamics Orca 6** linear actuator. Wavedriver provides a live graphical dashboard with 10 motion patterns, real-time force/position telemetry, session management, and multiple safety layers — all running locally with no cloud dependency.

> **Privacy**: nothing leaves your device. See [PRIVACY.md](PRIVACY.md).

---

## Quick start

**Requirements**: Python 3.12+, `uv`, Node.js (for the initial build only).

```bash
# 1. Install dependencies
uv sync --all-extras

# 2. Build the frontend (one-time)
cd src/wavedriver/web && npm install && npm run build && cd ../../..

# 3. Run — hardware mode
uv run wavedriver --port /dev/ttyUSB0

# 3. Run — mock/simulation mode (no hardware needed)
uv run wavedriver --mock
```

Don't know your port? `uv run wavedriver --list-ports` will enumerate available serial ports. You can also select the port from the startup screen inside the app.

---

## Patterns

| Pattern | What it feels like | Key parameter |
|---|---|---|
| **Wave** | Smooth, even, predictable | Frequency, stroke |
| **Realistic** | Asymmetric — like a physical crank mechanism | Rod ratio (2.5 × / 3.5 × / 5.0 ×) |
| **Thrust** | Slow pull, fast push, brief hold | Frequency, stroke |
| **Pulse** | Rapid burst of 4 strokes, then a rest pause | Frequency, stroke |
| **Tease** | Irregular — four incommensurable frequencies mixed | Frequency, stroke |
| **Escalate** | Starts very slow, builds to full intensity over time | Duration (minutes) |
| **Edge** | Climbs to peak then drops suddenly — repeating cycle | Cycle period |
| **Depth** | Slowly oscillates between shallow and full depth | Depth period |
| **Adaptive** | Reacts to live force feedback — eases when resistance rises | Sensitivity, mode |
| **Funscript** | Follows a `.funscript` keyframe file in sync with video | Load via Video Sync panel |

---

## Controls

### Sliders

- **Frequency** — cycles per second (0.1 – 3.0 Hz)
- **Stroke** — travel distance relative to calibrated range
- **Intensity** — master amplitude scale (10 – 100%)
- **Safety Force** — e-stop threshold in Newtons (5 – 60 N)
- **Session Timer** — auto-shutoff after N minutes (0 = off)

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Enter` | Start pattern |
| `Space` | Emergency stop |
| `Z` | Calibrate |
| `P` | Pause / Resume |
| `C` | Clear e-stop |
| `Q` | Quit |
| `↑ / ↓` | Frequency ± 0.1 Hz |
| `← / →` | Stroke ± 5 mm (or rod ratio in Realistic mode) |
| `= / −` | Intensity ± 10% |
| `] / [` | Safety force ± 5 N |
| `T` | Tap tempo |
| `1 – 5` | Recall preset |
| `Ctrl+1 – 5` | Save preset |
| `?` | Help overlay |

### Presets

Five save slots store pattern, frequency, stroke, intensity, and all pattern-specific parameters. Save with `Ctrl+[1-5]`, recall with `[1-5]` or by clicking the slot.

---

## Safety

Wavedriver implements layered safety in software. The most important ones for day-to-day use:

- **Force limit** (default 55 N): if the actuator encounters sustained resistance above the threshold for 150 ms, it stops. Adjust the Safety Force slider to suit your use.
- **Deadman watchdog**: if the app freezes or the UI stops polling for 5 seconds while running, the motor stops automatically.
- **Thermal cutoff**: warning at 65 °C, e-stop at 75 °C.
- **Comms watchdog**: e-stop if the serial connection drops for more than 500 ms.
- **Position limits**: soft limits set 5 mm inside the physical end-stops during calibration.

After any e-stop, press **C** to clear it (and re-calibrate if prompted), or press **Z** to run a fresh calibration.

See [SAFETY.md](SAFETY.md) for the full list of all 12 safety layers with code references and FMEA notes.

---

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## For developers

### Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a description of the multi-rate control loop, state machine, and key design decisions.

### Running tests

```bash
uv run pytest          # backend (74 tests, no hardware required)

cd src/wavedriver/web
npm test -- --run      # frontend (Vitest)
```

### Linting and type-checking

```bash
uv run ruff check src/
uv run ruff format src/
uv run mypy src/wavedriver/
```

Or via the justfile: `just lint`, `just typecheck`, `just test`.

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Pre-commit hooks enforce ruff format, ruff check, and mypy on every commit.
