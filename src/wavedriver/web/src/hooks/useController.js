import { useState, useEffect, useRef, useCallback } from 'react';

const DEFAULT_TELEMETRY = {
  state: "Unconnected",
  state_enum: "UNCONNECTED",
  error_msg: "",
  position_um: 0,
  force_mN: 0,
  speed_mm_s: 0,
  temperature_C: 0,
  voltage_mV: 0,
  power_W: 0,
  errors_bitmask: 0,
  calibrated_length_um: 0,
  max_feedback_force_mN: 55000,
  session_elapsed_s: 0,
  session_remaining_s: null,
  paused: false,
  use_mock: false,
  simulation_reason: "",
  temp_warning: false,
  current_pattern_name: "",
  event_log: [],
};

/**
 * Manages pywebview API detection, telemetry polling, and motor command dispatch.
 *
 * The calibratedLength is tracked via a ref internally so updating it does NOT
 * tear down and recreate the telemetry polling interval (which would cause a
 * brief gap in telemetry right after calibration completes).
 */
export function useController() {
  const [apiReady, setApiReady] = useState(false);
  const [telemetry, setTelemetry] = useState(DEFAULT_TELEMETRY);
  const [calibratedLength, setCalibratedLength] = useState(0);
  const calibratedLengthRef = useRef(0);
  const historyEnabledRef = useRef(true);

  // Detect pywebview API availability
  useEffect(() => {
    const check = () => {
      if (window.pywebview?.api?.load_session) {
        setApiReady(true);
        return true;
      }
      return false;
    };

    if (!check()) {
      const iv = setInterval(() => { if (check()) clearInterval(iv); }, 50);
      window.addEventListener('pywebviewready', check);
      return () => {
        clearInterval(iv);
        window.removeEventListener('pywebviewready', check);
      };
    }
  }, []);

  // Telemetry polling at 20 Hz — only depends on apiReady so calibration
  // completion never causes the interval to restart.
  const prevStateRef = useRef(null);

  useEffect(() => {
    if (!apiReady) return;

    const iv = setInterval(async () => {
      try {
        const tel = await window.pywebview.api.get_telemetry();
        if (tel && !tel.error) {
          // Session history: detect RUNNING → stopped transition
          const prevState = prevStateRef.current;
          prevStateRef.current = tel.state_enum;
          if (prevState === "RUNNING" &&
              tel.state_enum !== "RUNNING" &&
              tel.session_elapsed_s > 5 &&
              historyEnabledRef.current) {
            window.pywebview?.api?.save_session_history({
              duration_s:      Math.round(tel.session_elapsed_s),
              pattern_name:    tel.current_pattern_name || "",
              end_state:       tel.state_enum,
            });
          }

          setTelemetry(tel);
          if (tel.calibrated_length_um > 0 &&
              tel.calibrated_length_um !== calibratedLengthRef.current) {
            calibratedLengthRef.current = tel.calibrated_length_um;
            setCalibratedLength(tel.calibrated_length_um);
          }
        }
      } catch (e) {
        console.error("Telemetry poll failed:", e);
      }
    }, 50);

    return () => clearInterval(iv);
  }, [apiReady]);

  const sendCommand = useCallback((cmd, args = {}) => {
    window.pywebview?.api?.send_command(cmd, args);
  }, []);

  const setHistoryEnabled = useCallback((enabled) => {
    historyEnabledRef.current = enabled;
  }, []);

  return { apiReady, telemetry, calibratedLength, sendCommand, setHistoryEnabled };
}
