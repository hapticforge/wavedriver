# Wavedriver

Wavedriver is a high-performance, Textual-based Terminal User Interface (TUI) controller designed for reciprocating adult novelty and pleasure devices powered by the **Iris Dynamics Orca 6 Linear Motor**. 

By leveraging the high-speed capability and direct force/position feedback of the Orca 6, Wavedriver provides a responsive interface to design, trigger, and dynamically tune motion profiles (strokes, frequency, and safety limits) in real time.

---

## Key Features

- **Pleasure Waveform Kinematics**: Seven built-in movement profiles tailored for varying sensory and tactile stimulation.
- **Decoupled Multi-Rate Architecture**: 
  - **High-Frequency Control Loop (500 Hz)**: Ensures ultra-smooth, jitter-free position and force transitions.
  - **Low-Frequency Monitoring Loop (20 Hz)**: Monitors telemetry, temperature, and supply voltage, preventing bus saturation and enforcing software safety boundaries.
- **Full Preset System**: Five distinct slot directories to instantly save and recall custom speed, stroke, and pattern configurations.
- **Offline Simulation Mode**: A built-in physical model simulator featuring mass physics, dry/viscous friction, and physical end-stop collisions for testing and demonstrations without requiring physical hardware.
- **Auto-Shutoff Timer**: Enforces session limits to protect hardware against extended unattended runs.

---

## Pleasure Patterns

Wavedriver defines seven unique motion patterns in `src/wavedriver/patterns.py`:

| Pattern | Description | Application |
|---|---|---|
| **Wave** | Smooth, steady, and predictable reciprocating motion. | Classic, uniform stimulation. |
| **Realistic** | Simulates slider-crank kinematics to mimic natural reciprocating machinery movements. | Asymmetric, lifelike thrust feel. Customizable rod ratio (2.5x, 3.5x, 5.0x). |
| **Thrust** | Features a slow, gradual retraction followed by a rapid, high-acceleration thrust. | Deep, rhythmic, and impact-oriented profiles. |
| **Pulse** | Rapid bursts of four consecutive strokes followed by a rest pause at the center. | Rhythmic, high-intensity intervals followed by anticipation. |
| **Tease** | Uses three incommensurable frequencies to produce highly irregular, unpredictable motions. | Varied, non-repetitive sensory stimulation. |
| **Escalate** | Gradually ramps the movement amplitude from zero to full intensity over a custom duration (e.g. 5 minutes). | Long, gradual sensory build-up. |
| **Edge** | Climbs steadily to peak intensity over a custom period, then drops sharply back to zero before repeating. | Designed specifically for edging training and endurance cycles. |

---

## Getting Started

### Prerequisites
Wavedriver requires Python 3.12+ and uses the `uv` tool for fast dependency and environment management.

### Installation
Clone the repository and install dependencies in a virtual environment:
```bash
# Install package dependencies (textual, pyserial, etc.)
uv sync
```

### Running the Application

#### 1. Hardware Mode (Real Device)
Ensure your Orca 6 linear motor is connected via your RS-485 USB serial adapter (defaults to `/dev/ttyUSB0` at 19200 baud).
```bash
./run.sh --port /dev/ttyUSB0 --baud 19200
```

#### 2. Mock Mode (Hardware-Free Simulation)
To run and test the application offline using the integrated physics simulator:
```bash
./run_mock.sh
```

#### 3. Listing Serial Ports
To check available ports on your system:
```bash
./run.sh --list-ports
```

---

## User Interface & Control Reference

The interface is divided into a live **Telemetry Dashboard** (monitoring device state, position, safety resistance, speed SPM, voltage, temperature, and session time), a **Visual Shaft Position Progress Bar**, and a **Control Command Section**.

### Key Bindings

| Key | Action | Description |
|---|---|---|
| **`Space`** | **EMERGENCY STOP** | Instantly drops the motor into Sleep Mode and commands 0 mN force. |
| **`Z`** | **Calibrate / Zero** | Initiates homing calibration. Moves the shaft to both endpoints to determine stroke length. |
| **`P`** | **Pause / Resume** | Pauses the active pattern using a smooth ramp-down to center, or resumes play. |
| **`Up` / `Down`** | **Speed +/-** | Adjusts pattern cycle frequency between 0.1 Hz and 3.0 Hz in 0.1 Hz steps. |
| **`Left` / `Right`** | **Stroke / Ratio +/-** | Adjusts stroke length (or changes the rod-ratio geometry if in *Realistic* mode). |
| **`=` / `-`** | **Intensity +/-** | Changes overall movement amplitude scale by +/- 10% (from 10% to 100%). |
| **`[` / `]`** | **Safety Force +/-** | Adjusts the feedback force threshold in Newtons (clamps hardware behavior). |
| **`D`** | **Toggle Debug** | Displays real-time motor electrical power (W), voltage (V), temperature (°C), and internal parameters. |
| **`C`** | **Clear E-STOP** | Clears the error state (requires homing calibration before resuming). |
| **`1` – `5`** | **Recall Preset** | Recalls saved speed, stroke, and pattern configuration from slots 1-5. |
| **`Ctrl+1` – `Ctrl+5`** | **Save Preset** | Saves current settings into slot 1-5. Saved to disk automatically. |
| **`Q`** | **Quit** | Exits the TUI app gracefully. |

---

## Safety Systems

To ensure safe personal use and prevent motor damage, Wavedriver implements software-level safety constraints:
1. **Force Clamping**: The motor controller continuously monitors feedback resistance. If the force exceeds the configured safety limit (default 55 N, configurable down to 5 N) for more than three consecutive telemetry cycles, an emergency stop is triggered.
2. **Thermal Cutoff**: If the motor coil temperature reaches or exceeds **75°C**, the software commands an immediate thermal shutdown.
3. **Under-Voltage Stop**: Triggers shutdown if supply voltage sags below **18V** to protect driver electronics.
4. **Endpoint Protection**: Stroke limits are automatically set to exclude the absolute end-zones (5 mm margin at each side) to prevent harsh metal-on-metal collisions during regular pattern operations.
5. **Connection Watchdog**: Triggers an E-STOP if serial communications drop for more than 500 milliseconds.

---

## Technical Architecture

- **`src/wavedriver/main.py`**: Handles CLI arguments parsing, configures initial safety bounds, and coordinates the startup/shutdown sequence.
- **`src/wavedriver/motor_controller.py`**: Establishes serial connection, schedules background control loop ticks, manages state transitions, and streams position/force targets.
- **`src/wavedriver/ui.py`**: Built on the Textual framework, implements custom widgets, handles screen rendering, key events dispatch, and manages JSON-based persistent states.
- **`src/wavedriver/patterns.py`**: Contains the mathematical generators for reciprocating position and force outputs.
- **`src/wavedriver/mock_actuator.py`**: Simulates mass, friction, endpoint collisions, and PID position tracking.

---

## Testing
To run the mathematical verification and driver simulation tests:
```bash
./test.sh
```
All unit tests are located in `tests/test_driver.py` and run offline without hardware dependencies.
