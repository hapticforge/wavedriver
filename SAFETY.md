# Wavedriver Safety Model

This document describes every safety layer in Wavedriver. It is a living document — any change to the control loop, calibration logic, or safety thresholds must update this file.

Wavedriver controls a powered linear actuator that makes direct body contact. Every safety property documented here has a corresponding code path and, where stated, a test.

---

## Safety layers

### 1 — Software force limit (primary)

**Threshold:** 55 N default (configurable 5–60 N via UI; CLI `--safety-limit`)  
**Mechanism:** Feedback force (`force_mN`) is read at 20 Hz. If the absolute value exceeds the configured limit on **three consecutive** 20 Hz ticks, an e-stop is triggered.  
**Code:** `motor_controller.py` → `_tick_20hz` → `_force_exceed_count >= 3` → `_trigger_estop()`  
**Why debounced:** A single transient spike (e.g. direction reversal, sudden contact) should not cause a false stop. Three consecutive readings at 20 Hz = 150 ms of sustained over-force.  
**Active during:** `RUNNING` and `CALIBRATING_CENTER` states only. `CALIBRATING_RETRACT` / `CALIBRATING_EXTEND` intentionally stall against physical end-stops (force is hardware-clamped at 60 N during homing); checking there would always trip.

### 2 — Hardware force limit

**Threshold:** 60 N (written to actuator register at init via `set_max_force(60000)`)  
**Mechanism:** Enforced by actuator firmware independently of software. Cannot be disabled or overridden by software.  
**Code:** `motor_controller.py` → `_initialize_hardware()`

### 3 — Over-temperature warning

**Threshold:** 65 °C  
**Mechanism:** A warning event is logged and surfaced in telemetry (`temp_warning: true`) when coil temperature reaches 65 °C. The warning clears automatically if temperature drops below the threshold.  
**Code:** `_tick_20hz` → `_temp_warned` flag + `_log_event()`

### 4 — Over-temperature e-stop

**Threshold:** 75 °C  
**Mechanism:** If coil temperature reaches 75 °C, an e-stop is triggered immediately. The hardware limit is 80 °C, giving a 5 °C software margin.  
**Code:** `_tick_20hz` → `temp_C >= _TEMP_ESTOP_C` → `_trigger_estop()`

### 5 — Under-voltage e-stop

**Threshold:** 18 V (on a 24 V nominal supply)  
**Mechanism:** Supply voltage is monitored at 20 Hz. If voltage drops below 18 V while connected, an e-stop fires. The zero-voltage check (`voltage_mV > 0`) prevents false trips during startup before the first telemetry read.  
**Code:** `_tick_20hz` → `voltage_mV > 0 and voltage_mV < _VOLTAGE_LOW_MV` → `_trigger_estop()`

### 6 — Modbus communications watchdog

**Threshold:** 500 ms without a Modbus response  
**Mechanism:** `time_since_last_response_microseconds()` is checked at 20 Hz after a 2-second startup grace period. If the actuator hasn't responded within 500 ms, an e-stop fires.  
**Code:** `_tick_20hz` → `actuator.time_since_last_response_microseconds() > _COMMS_WATCHDOG_US`  
**Note:** The 2-second grace period prevents false trips during the initial connection handshake.

### 7 — Software position limits

**Range:** `software_min_um` to `software_max_um` (set during calibration to ±5 mm inside the physical end-stops)  
**Mechanism:** All position-mode pattern outputs are clamped to `[software_min_um, software_max_um]` before being sent to the actuator. This prevents the motor from commanding travel into the physical end-stop region.  
**Code:** `_drive_running_pattern` → `target_pos_um = max(min_lim, min(max_lim, res_value))`  
**Default before calibration:** `software_min_um = 5000` µm, `software_max_um = 145000` µm (conservative 150 mm range). Pattern execution is not permitted until calibration completes.

### 8 — Pattern output finiteness check

**Mechanism:** After calling the pattern function, the returned value is checked for NaN or infinity before any motor command. A non-finite value triggers an immediate e-stop.  
**Why:** `max/min` comparisons in Python return NaN unchanged when one operand is NaN, so the position-clamp in layer 7 does not protect against NaN.  
**Code:** `_drive_running_pattern` → `if not math.isfinite(res_value): _trigger_estop()`

### 9 — UI deadman (frontend heartbeat)

**Threshold:** 5 seconds without a `get_telemetry()` call from the UI  
**Mechanism:** Every call to `get_telemetry()` updates `_last_ui_poll_time`. If the controller is RUNNING and the UI stops polling for 5 seconds, a soft-stop is initiated (motor ramps to zero, not an abrupt e-stop).  
**Why soft-stop, not e-stop:** A crashed renderer is more recoverable than a hardware e-stop; the user can re-open the app without needing to clear an error state. The motor stops safely either way.  
**Code:** `_tick_20hz` → `(now - last_ui_poll) > _UI_DEADMAN_S` → `_request_soft_stop()`  
**Note:** This watchdog only activates once the UI has polled at least once (`_last_ui_poll_time is not None`). It does not fire during calibration or idle states.

### 10 — Amplitude ramp (soft start / soft stop)

**Mechanism:** Pattern amplitude is interpolated at 0.5/second (2-second full traverse) in both directions. Motor commands are never sent at full amplitude immediately — they ramp up from zero on start.  
**Code:** `_drive_running_pattern` → bidirectional amplitude ramp

### 11 — Rate-limited commanded position

**Mechanism:** The commanded position is stepped toward the target at a rate capped by the pattern's theoretical peak speed (plus 10% headroom). This prevents the motor from commanding an extreme "catch-up" move when transitioning between patterns or resuming from pause.  
**Code:** `_drive_running_pattern` → `_max_pattern_speed_um_s` and `cmd_pos` rate limiting

### 12 — Session auto-shutoff timer

**Mechanism:** If `max_session_s > 0`, the controller initiates a soft-stop when the elapsed session time exceeds the limit. The session timer starts on the first `start_pattern` command.  
**Code:** `_tick_20hz` → session auto-shutoff block

---

## E-stop behavior

When any safety condition triggers `_trigger_estop()`:

1. `state` → `ESTOP`; `error_msg` is set
2. `current_pattern` is cleared (motor stops computing new targets)
3. Motor mode is set to `SleepMode`; streamed force is set to 0
4. `actuator.run()` flushes the command; `disable_stream()` stops data flow
5. `_soft_stopping` and `_paused` are reset

To recover: the UI sends `clear_estop`. The controller re-enables the stream and transitions to `CALIBRATED_IDLE` (if previously calibrated) or `CONNECTED` (if e-stop fired before calibration completed). In the latter case the user must recalibrate before running.

---

## Failure mode analysis (FMEA)

| Failure | Expected behavior | Recovery |
|---|---|---|
| Serial disconnect mid-stroke | Comms watchdog fires within 500 ms → e-stop; motor loses drive signal and coasts to stop | Reconnect, clear e-stop, recalibrate if needed |
| App process crash (Python) | OS terminates the control thread; actuator's own safety limits (hw force + hw temp) remain active; motor coasts | Relaunch app |
| OS freeze / hard reboot | Power to USB is cut; actuator loses drive signal and coasts; hardware force/temp limits remain | Relaunch app |
| USB unplug mid-stroke | Same as serial disconnect → comms watchdog → e-stop within 500 ms | Replug, relaunch app |
| Frontend renderer crash (UI freezes) | UI deadman fires after 5 s → soft-stop (graceful ramp to zero) | Re-open window or relaunch app |
| NaN / inf from pattern function | Finiteness check catches it → e-stop before any motor command | Clear e-stop; patterns are deterministic so this indicates a bug |
| `_update_telemetry()` silent repeated failure | Telemetry values become stale; force/temp/voltage checks use stale values. Comms watchdog (`time_since_last_response_microseconds`) catches the underlying disconnect within 500 ms. **Known gap:** if `run()` succeeds but stream read fails, the watchdog may not fire. | See note below |
| Clock skew in `time.perf_counter()` | Monotonic clock; skew cannot occur on a single machine. Large `dt` values (e.g. after `time.sleep()` overshoot) are not explicitly bounded and could cause a single large step in pattern output, which is then caught by position clamping and rate limiting. | Not a failure mode in practice |
| Calibration never completed (e-stop during homing) | `clear_estop` checks `calibrated_length_um == 0` → drops to `CONNECTED`; user is forced to recalibrate | Re-run calibration |
| Pattern starts from far position | Rate-limited commanded position prevents over-speed catch-up | Normal behavior |

### Known gap: stream read failure without comms failure

If `_update_telemetry()` fails (stream data read returns an exception) but `actuator.run()` continues to succeed, the comms watchdog does not fire because `time_since_last_response_microseconds()` may still show recent communication. In this case stale telemetry values are used for safety checks. The hardware force and temperature limits on the actuator remain active as a backup.

**Mitigation:** A counter for consecutive `_update_telemetry()` failures could trigger an e-stop; this is tracked as a future hardening item (Phase 8).

---

## Lock discipline

See the `MotorController.__init__` docblock comment for the full table. Summary:

- **Shared fields** (read by the UI thread via `get_telemetry`, written by the control thread): protected by `self.lock`.
- **Control-thread-only fields** (`_amplitude_target`, `_soft_stopping`, `_paused` during pattern execution, `_current_phase`, etc.): never touched by the UI thread; no lock needed.
- **UI deadman field** (`_last_ui_poll_time`): written by the UI thread under `self.lock`; read by the control thread under `self.lock`.

---

## Safety-relevant constants (all in `motor_controller.py`)

| Constant | Value | Purpose |
|---|---|---|
| `_TEMP_WARNING_C` | 65 °C | Coil temperature warning threshold |
| `_TEMP_ESTOP_C` | 75 °C | Coil temperature e-stop threshold |
| `_VOLTAGE_LOW_MV` | 18 000 mV | Supply voltage e-stop threshold |
| `_COMMS_WATCHDOG_US` | 500 000 µs | Modbus response timeout |
| `_UI_DEADMAN_S` | 5 s | Frontend heartbeat timeout |
| `max_feedback_force_mN` | 55 000 mN default | Software force e-stop threshold |
| Hardware force limit | 60 000 mN | Set at init; firmware-enforced |
