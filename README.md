# Wavedriver

<p align="center">
  <img src="logo.png" alt="Wavedriver Logo" width="200" height="200" />
</p>

Wavedriver is a premium, privacy-first **sex machine controller** for the **Iris Dynamics Orca 6** linear actuator. It transforms the industrial-grade linear motor into a highly responsive, custom-tuned sex machine with an interactive dashboard, 10 motion patterns, microphone-driven beat synchronization, and multiple hardware safety layers.

> 🔒 **Privacy-First**: Your sessions are your business. Wavedriver runs entirely offline—no cloud dependencies, no analytics, and no data leaving your machine. See [PRIVACY.md](PRIVACY.md).

---

## Key Features

*   🛡️ **Safety Watchdogs**: Dedicated local safety layers monitor user-defined force limits, motor temperatures, and connectivity to immediately disarm the machine if boundaries are crossed.
*   🌀 **10 Stimulation Patterns**: From smooth wave oscillations to randomized tease cycles and adaptive push-back force feedback.
*   🎬 **Video Sync & Funscripts**: Load `.funscript` haptic telemetry files to synchronize the machine's thrusts in real-time with video playback.
*   🎵 **Interactive Beat Sync**: Synchronize the stroke frequency automatically to the rhythm of any music, speech, or external audio captured via your microphone.
*   ⌨️ **Quick-Key Play**: Complete keyboard shortcuts let you start, stop, recall presets, and adjust stroke depth or speed mid-session without needing a mouse.

---

## Getting Started

### Requirements
Ensure you have **Python 3.12+**, **Node.js** (for building the app interface), and the task runner **`just`** installed.

### Setup and Launch in 3 Steps
Open a terminal in the project directory and run the following:

```bash
# 1. Install dependencies
uv sync --all-extras
npm install --prefix src/wavedriver/web

# 2. Build the graphical interface (one-time)
just build-web

# 3. Launch the application
# For hardware control:
just run

# Or run in simulation/mock mode (no hardware connected):
just run-mock
```

---

## Experience Patterns

Wavedriver features 10 built-in motion profiles designed for diverse sensations:

| Pattern | Sensation Profile | Tuning Parameter |
| :--- | :--- | :--- |
| **Wave** | Smooth, even, and predictable sinusoidal movement. | Frequency & stroke length |
| **Realistic** | Asymmetric stroke modeling a physical crank mechanism. | Rod ratio (2.5x, 3.5x, 5.0x) |
| **Thrust** | Fast forward stroke, slow retraction, and a brief hold. | Frequency & stroke length |
| **Pulse** | Rapid burst of 4 strokes followed by a rhythmic rest pause. | Frequency & stroke length |
| **Tease** | Playful, irregular frequency shifts using mixed waves. | Frequency & stroke length |
| **Escalate** | Starts at a gentle speed and builds intensity over time. | Duration (minutes) |
| **Edge** | Climbs to a high intensity and drops down in repeating cycles. | Cycle period (seconds) |
| **Depth** | Continuously shifts between shallow and deep strokes. | Depth period (seconds) |
| **Adaptive** | Eases back when physical resistance rises, reacting to force. | Force sensitivity & mode |
| **Funscript** | Keyframe-by-keyframe hardware synchronization with video. | Load via the Video Sync panel |

---

## Desktop Controls & Shortcuts

You can control everything on the screen with these interactive dashboard options or physical hotkeys:

### Parameter Controls
*   **Speed / Frequency** (Disabled in video/audio sync): Adjusts cycles per second (0.1 – 4.0 Hz / 6 – 240 BPM).
*   **Stroke Length**: Sets the physical travel distance of the rod relative to calibrated safety boundaries.
*   **Intensity**: Master amplitude multiplier scaling the overall strength (10 – 100%).
*   **Safety Force Limit**: Restricts maximum force in Newtons (5 – 60 N). E-stops if exceeded.
*   **Session Timer**: Automatically shuts off the pattern after a set time (1 – 120 minutes, 0 = off).

### Hotkey Directory

| Hotkey | Action |
| :--- | :--- |
| `Enter` | Start pattern |
| `Space` | Emergency stop (E-Stop) |
| `Z` | Re-calibrate endpoints |
| `P` | Pause / Resume current motion |
| `C` | Clear active E-Stop status |
| `Q` | Quit Wavedriver |
| `↑` / `↓` | Adjust Speed ± 0.1 Hz |
| `←` / `→` | Adjust Stroke ± 5 mm (or Rod Ratio in Realistic mode) |
| `=` / `−` | Adjust Intensity ± 10% |
| `]` / `[` | Adjust Safety Force ± 5 N |
| `T` | Tap Tempo (Tap 6 times to set manual BPM) |
| `1` – `5` | Recall Preset 1–5 |
| `Ctrl+1` – `5` | Save current settings to Preset slot 1–5 |
| `?` | Toggle keybind overlay |

---

## Built-In Safety Layers

Wavedriver runs 12 software-level safety watchdogs locally on the controller loop:
*   **Force Boundary (E-Stop)**: If the actuator encounters resistance above your Safety Force limit for more than 150 ms, it immediately disarms.
*   **Active Watchdog**: If the frontend crashes or stops responding for 5 seconds while running, the motor instantly shuts down.
*   **Thermal Protection**: Generates an interface warning at 65°C, and triggers a hard E-Stop at 75°C.
*   **Comms Watchdog**: Disarms the motor if connection status over the serial link drops for more than 500 ms.
*   **Endstop Guard**: Soft limits are configured 5 mm inside physical endstops during startup calibration.

*To reset an E-Stop, press **C** in the app to clear it (or press **Z** to run a fresh calibration if requested).*

For detailed technical analysis of the safety architecture, see [SAFETY.md](SAFETY.md).

---

## Technical Resources

If you are a developer looking to build or contribute to the project:
*   **Architecture**: Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand the multi-rate control loops and telemetry engine.
*   **Development Commands**:
    *   **Formatting & Linting**: Run `just lint` and `just typecheck` to analyze styles and types.
    *   **Testing**: Run `just test` to execute backend Python test suites. Frontend unit tests can be run via `npm test --prefix src/wavedriver/web`.
*   **Troubleshooting**: Visit [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for help with installation, hardware communication, and connection issues.
*   **Contributing Guidelines**: Review [CONTRIBUTING.md](CONTRIBUTING.md).
