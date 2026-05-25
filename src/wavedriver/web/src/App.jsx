import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, Square, RefreshCw, AlertTriangle, Shield, ShieldAlert,
  Zap, Thermometer, Battery, Activity, Sliders, FolderOpen, Save,
  XCircle, ToggleLeft, ToggleRight, LogOut
} from 'lucide-react';

const PATTERN_OPTIONS = [
  { value: "Wave", label: "Wave — smooth & steady" },
  { value: "Realistic", label: "Realistic — natural feel" },
  { value: "Thrust", label: "Thrust — deep & rhythmic" },
  { value: "Pulse", label: "Pulse — intense bursts" },
  { value: "Tease", label: "Tease — playful & varied" },
  { value: "Escalate", label: "Escalate — builds over time" },
  { value: "Edge", label: "Edge — climbs then drops" }
];

function App() {
  // Bridge API Ready State
  const [apiReady, setApiReady] = useState(false);
  
  // Dashboard parameters state
  const [patternName, setPatternName] = useState("Wave");
  const [frequencyHz, setFrequencyHz] = useState(1.0);
  const [strokeLengthMm, setStrokeLengthMm] = useState(50.0);
  const [intensityPct, setIntensityPct] = useState(50.0);
  const [rodRatio, setRodRatio] = useState(2.5);
  const [escalateDurationS, setEscalateDurationS] = useState(300.0);
  const [edgePeriodS, setEdgePeriodS] = useState(60.0);
  const [safetyForceN, setSafetyForceN] = useState(55.0);
  const [maxSessionS, setMaxSessionS] = useState(1800);
  
  // UI states
  const [showStartupModal, setShowStartupModal] = useState(true);
  const [showDebug, setShowDebug] = useState(false);
  const [presets, setPresets] = useState(Array(5).fill(null));
  const [activePresetSlot, setActivePresetSlot] = useState(null);
  const [hasSavedCal, setHasSavedCal] = useState(false);
  const [calibratedLengthUm, setCalibratedLengthUm] = useState(0);

  // Live Telemetry state
  const [telemetry, setTelemetry] = useState({
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
    paused: false,
    use_mock: false
  });

  // Keep state refs for keyboard listeners and intervals to avoid closure issues
  const stateRef = useRef({
    patternName, frequencyHz, strokeLengthMm, intensityPct, rodRatio,
    escalateDurationS, edgePeriodS, safetyForceN, presets, telemetry,
    apiReady, calibratedLengthUm
  });

  useEffect(() => {
    stateRef.current = {
      patternName, frequencyHz, strokeLengthMm, intensityPct, rodRatio,
      escalateDurationS, edgePeriodS, safetyForceN, presets, telemetry,
      apiReady, calibratedLengthUm
    };
  }, [
    patternName, frequencyHz, strokeLengthMm, intensityPct, rodRatio,
    escalateDurationS, edgePeriodS, safetyForceN, presets, telemetry,
    apiReady, calibratedLengthUm
  ]);

  // 1. Establish API Check & Initialize Settings
  useEffect(() => {
    const checkApi = () => {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.load_session) {
        setApiReady(true);
        loadSessionAndPresets();
        return true;
      }
      return false;
    };

    if (!checkApi()) {
      const interval = setInterval(() => {
        if (checkApi()) clearInterval(interval);
      }, 50);
      window.addEventListener('pywebviewready', checkApi);
      return () => {
        clearInterval(interval);
        window.removeEventListener('pywebviewready', checkApi);
      };
    }
  }, []);

  // 2. Load Session and Presets from Python on Startup
  const loadSessionAndPresets = async () => {
    if (!window.pywebview?.api) return;

    try {
      // Load session
      const session = await window.pywebview.api.load_session();
      if (session && Object.keys(session).length > 0) {
        if (session.pattern_name) setPatternName(session.pattern_name);
        if (session.frequency_hz) setFrequencyHz(session.frequency_hz);
        if (session.stroke_length_mm) setStrokeLengthMm(session.stroke_length_mm);
        if (session.intensity_pct) setIntensityPct(session.intensity_pct);
        if (session.rod_ratio) setRodRatio(session.rod_ratio);
        if (session.escalate_duration_s) setEscalateDurationS(session.escalate_duration_s);
        if (session.edge_period_s) setEdgePeriodS(session.edge_period_s);
        if (session.calibrated_length_um) {
          setCalibratedLengthUm(session.calibrated_length_um);
          setHasSavedCal(session.calibrated_length_um > 0);
        }
      }

      // Load presets
      const loadedPresets = await window.pywebview.api.load_presets();
      if (loadedPresets) {
        const slots = Array(5).fill(null);
        for (let i = 0; i < 5; i++) {
          if (loadedPresets[i.toString()]) {
            slots[i] = loadedPresets[i.toString()];
          }
        }
        setPresets(slots);
      }
    } catch (e) {
      console.error("Error loading session/presets:", e);
    }
  };

  // 3. Telemetry Polling Loop (20 Hz / 50ms)
  useEffect(() => {
    if (!apiReady) return;

    const interval = setInterval(async () => {
      try {
        const tel = await window.pywebview.api.get_telemetry();
        if (tel && !tel.error) {
          setTelemetry(tel);
          if (tel.calibrated_length_um > 0 && tel.calibrated_length_um !== calibratedLengthUm) {
            setCalibratedLengthUm(tel.calibrated_length_um);
            setHasSavedCal(true);
          }
        }
      } catch (e) {
        console.error("Failed to poll telemetry:", e);
      }
    }, 50);

    return () => clearInterval(interval);
  }, [apiReady, calibratedLengthUm]);

  // 4. Save Session to Disk on Parameter Changes
  const saveSession = () => {
    if (!window.pywebview?.api) return;
    const data = {
      pattern_name: stateRef.current.patternName,
      frequency_hz: stateRef.current.frequencyHz,
      stroke_length_mm: stateRef.current.strokeLengthMm,
      intensity_pct: stateRef.current.intensityPct,
      rod_ratio: stateRef.current.rodRatio,
      escalate_duration_s: stateRef.current.escalateDurationS,
      edge_period_s: stateRef.current.edgePeriodS,
      calibrated_length_um: stateRef.current.calibratedLengthUm
    };
    window.pywebview.api.save_session(data);
  };

  // Save session when relevant values change
  useEffect(() => {
    if (apiReady) {
      saveSession();
    }
  }, [patternName, frequencyHz, strokeLengthMm, intensityPct, rodRatio, escalateDurationS, edgePeriodS, calibratedLengthUm]);

  // 5. Commands Helper
  const sendCommand = (cmd, args = {}) => {
    if (!window.pywebview?.api) return;
    window.pywebview.api.send_command(cmd, args);
  };

  const startPattern = (force = false) => {
    const strokeUm = Math.round(strokeLengthMm * 1000);
    const params = {
      stroke_length_um: strokeUm,
      frequency_hz: frequencyHz
    };

    if (patternName === "Realistic") params.rod_ratio = rodRatio;
    else if (patternName === "Escalate") params.escalate_duration_s = escalateDurationS;
    else if (patternName === "Edge") params.edge_period_s = edgePeriodS;

    sendCommand("start_pattern", {
      pattern_name: patternName,
      params: params
    });
  };

  // Dynamic parameter updates during active stimulation
  useEffect(() => {
    if (apiReady && telemetry.state_enum === "RUNNING") {
      startPattern();
    }
  }, [patternName, frequencyHz, strokeLengthMm, rodRatio, escalateDurationS, edgePeriodS]);

  const stopPattern = () => {
    sendCommand("soft_stop");
  };

  const triggerEstop = () => {
    sendCommand("estop", { reason: "Emergency Stop Requested" });
  };

  const clearEstop = () => {
    sendCommand("clear_estop");
  };

  const startCalibration = () => {
    setShowStartupModal(false);
    sendCommand("start_calibration");
  };

  const resumeSession = () => {
    setShowStartupModal(false);
    if (calibratedLengthUm > 0) {
      sendCommand("load_calibration", { calibrated_length_um: calibratedLengthUm });
    }
  };

  const quitApplication = () => {
    if (window.pywebview?.api?.quit_application) {
      window.pywebview.api.quit_application();
    }
  };

  const changeIntensity = (newVal) => {
    const val = Math.max(10, Math.min(100, newVal));
    setIntensityPct(val);
    sendCommand("set_intensity", { intensity: val / 100.0 });
  };

  const changeSafetyLimit = (newVal) => {
    const val = Math.max(5, Math.min(60, newVal));
    setSafetyForceN(val);
    sendCommand("set_safety_limit", { limit_mN: Math.round(val * 1000) });
  };

  // Presets Handlers
  const handlePresetClick = (slotIdx) => {
    const preset = presets[slotIdx];
    if (!preset) return;
    
    setPatternName(preset.pattern_name || "Wave");
    setFrequencyHz(preset.frequency_hz || 1.0);
    setStrokeLengthMm(preset.stroke_length_mm || 50.0);
    setIntensityPct(preset.intensity_pct || 50.0);
    setRodRatio(preset.rod_ratio || 2.5);
    setEscalateDurationS(preset.escalate_duration_s || 300.0);
    setEdgePeriodS(preset.edge_period_s || 60.0);
    setActivePresetSlot(slotIdx);
    
    // If already running, automatically update pattern
    if (telemetry.state_enum === "RUNNING") {
      // Small timeout to let state update, or construct payload directly
      const strokeUm = Math.round((preset.stroke_length_mm || 50.0) * 1000);
      const params = {
        stroke_length_um: strokeUm,
        frequency_hz: preset.frequency_hz || 1.0
      };
      if (preset.pattern_name === "Realistic") params.rod_ratio = preset.rod_ratio || 2.5;
      else if (preset.pattern_name === "Escalate") params.escalate_duration_s = preset.escalate_duration_s || 300.0;
      else if (preset.pattern_name === "Edge") params.edge_period_s = preset.edge_period_s || 60.0;

      sendCommand("start_pattern", {
        pattern_name: preset.pattern_name || "Wave",
        params: params
      });
      sendCommand("set_intensity", { intensity: (preset.intensity_pct || 50.0) / 100.0 });
    }
  };

  const handlePresetSave = (slotIdx) => {
    const updated = [...presets];
    updated[slotIdx] = {
      pattern_name: patternName,
      frequency_hz: frequencyHz,
      stroke_length_mm: strokeLengthMm,
      intensity_pct: intensityPct,
      rod_ratio: rodRatio,
      escalate_duration_s: escalateDurationS,
      edge_period_s: edgePeriodS
    };
    setPresets(updated);
    setActivePresetSlot(slotIdx);

    // Save presets back to file
    if (window.pywebview?.api) {
      const presetsObj = {};
      updated.forEach((preset, idx) => {
        if (preset) presetsObj[idx.toString()] = preset;
      });
      window.pywebview.api.save_presets(presetsObj);
    }
  };

  // 6. Keyboard Shortcuts Event Listener
  useEffect(() => {
    const handleKeyDown = (e) => {
      const { 
        patternName: curPattern, 
        frequencyHz: curFreq, 
        strokeLengthMm: curStroke, 
        intensityPct: curInt, 
        safetyForceN: curSafety,
        presets: curPresets,
        calibratedLengthUm: calLen
      } = stateRef.current;
      
      // Emergency Stop (Space) - Global priority
      if (e.code === "Space") {
        e.preventDefault();
        triggerEstop();
        return;
      }

      // Calibration (Z)
      if (e.key === "z" || e.key === "Z") {
        e.preventDefault();
        sendCommand("start_calibration");
        return;
      }

      // Play/Pause (P)
      if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        if (stateRef.current.telemetry.state_enum === "RUNNING") {
          if (stateRef.current.telemetry.paused) {
            sendCommand("resume_pattern");
          } else {
            sendCommand("pause_pattern");
          }
        }
        return;
      }

      // Clear E-STOP (C)
      if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        clearEstop();
        return;
      }

      // Quit Application (Q)
      if (e.key === "q" || e.key === "Q") {
        e.preventDefault();
        quitApplication();
        return;
      }

      // Speed Up / Down (Arrows Up/Down)
      if (e.key === "ArrowUp") {
        e.preventDefault();
        const nextFreq = Math.min(3.0, Math.round((curFreq + 0.1) * 10) / 10);
        setFrequencyHz(nextFreq);
        // Dispatch update if running
        if (stateRef.current.telemetry.state_enum === "RUNNING") {
          startPattern();
        }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const nextFreq = Math.max(0.1, Math.round((curFreq - 0.1) * 10) / 10);
        setFrequencyHz(nextFreq);
        if (stateRef.current.telemetry.state_enum === "RUNNING") {
          startPattern();
        }
        return;
      }

      // Stroke Up / Down or Rod Ratio (Arrows Left/Right)
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (curPattern === "Realistic") {
          const ratios = [2.5, 3.5, 5.0];
          const curIdx = ratios.indexOf(rodRatio);
          const nextIdx = Math.max(0, curIdx - 1);
          setRodRatio(ratios[nextIdx]);
        } else {
          setStrokeLengthMm(prev => Math.max(10, prev - 5));
        }
        if (stateRef.current.telemetry.state_enum === "RUNNING") {
          startPattern();
        }
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        if (curPattern === "Realistic") {
          const ratios = [2.5, 3.5, 5.0];
          const curIdx = ratios.indexOf(rodRatio);
          const nextIdx = Math.min(ratios.length - 1, curIdx + 1);
          setRodRatio(ratios[nextIdx]);
        } else {
          const maxStroke = calLen > 0 ? (calLen / 1000) - 10 : 140.0;
          setStrokeLengthMm(prev => Math.min(maxStroke, prev + 5));
        }
        if (stateRef.current.telemetry.state_enum === "RUNNING") {
          startPattern();
        }
        return;
      }

      // Intensity + / - (Keys = and -)
      if (e.key === "=" || e.key === "+") {
        e.preventDefault();
        changeIntensity(curInt + 10);
        return;
      }
      if (e.key === "-") {
        e.preventDefault();
        changeIntensity(curInt - 10);
        return;
      }

      // Safety Force Limit + / - (Keys [ and ])
      if (e.key === "]") {
        e.preventDefault();
        changeSafetyLimit(curSafety + 5);
        return;
      }
      if (e.key === "[") {
        e.preventDefault();
        changeSafetyLimit(curSafety - 5);
        return;
      }

      // Presets Slots 1-5 (Keys 1-5, Ctrl+1-5 to save)
      if (/^[1-5]$/.test(e.key)) {
        e.preventDefault();
        const slotIdx = parseInt(e.key) - 1;
        if (e.ctrlKey) {
          handlePresetSave(slotIdx);
        } else {
          handlePresetClick(slotIdx);
        }
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [rodRatio]);

  // State Formatting Handlers
  const maxCalMm = calibratedLengthUm > 0 ? Math.round(calibratedLengthUm / 1000) : 150;
  const currentPosMm = (telemetry.position_um / 1000).toFixed(1);
  const positionPercentage = calibratedLengthUm > 0 
    ? Math.max(0, Math.min(100, (telemetry.position_um / calibratedLengthUm) * 100)) 
    : 0;

  // Formatting session time
  const formatSessionTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  // Get active display state
  const getDisplayState = () => {
    if (telemetry.state_enum === "RUNNING" && telemetry.paused) {
      return "Paused";
    }
    return telemetry.state;
  };

  const getDisplayStateClass = () => {
    switch (telemetry.state_enum) {
      case "RUNNING":
        return telemetry.paused ? "badge-state calibrating" : "badge-state running";
      case "CALIBRATING_RETRACT":
      case "CALIBRATING_EXTEND":
      case "CALIBRATING_CENTER":
        return "badge-state calibrating";
      case "ESTOP":
      case "ERROR":
        return "badge-state estop";
      default:
        return "badge-state";
    }
  };

  // Resistance % (force vs limit)
  const limitmN = telemetry.max_feedback_force_mN || 55000;
  const forceAbs = Math.abs(telemetry.force_mN);
  const resistancePct = limitmN > 0 ? Math.min(100, Math.round((forceAbs / limitmN) * 100)) : 0;

  return (
    <div className="app-container">
      {/* 1. Global Banner warnings */}
      {telemetry.state_enum === "ESTOP" && (
        <div className="banner banner-estop">
          <ShieldAlert size={20} />
          EMERGENCY STOP TRIGGERED: FORCE SAFETY THRESHOLD EXCEEDED
        </div>
      )}

      {telemetry.state_enum === "ERROR" && (
        <div className="banner banner-error">
          <AlertTriangle size={20} />
          DEVICE SYSTEM ERROR: {telemetry.error_msg}
        </div>
      )}

      {/* 2. Top Header Navigation */}
      <header className="app-header">
        <div className="logo-container">
          <Activity className="text-cyan animate-pulse" size={24} />
          <h1 className="logo-title">WAVEDRIVER</h1>
        </div>

        <div className="header-badges">
          {telemetry.use_mock && (
            <span className="badge badge-mock">
              <Zap size={14} />
              Simulation Mode
            </span>
          )}
          <span className="badge badge-state">
            Baud: {telemetry.use_mock ? 'Mock' : '19200'}
          </span>
          <span className={getDisplayStateClass()}>
            {getDisplayState()}
          </span>
          <button 
            className="btn btn-secondary" 
            style={{ 
              padding: '6px 12px', 
              display: 'flex', 
              alignItems: 'center', 
              gap: '6px', 
              fontSize: '0.8rem',
              height: '28px',
              borderRadius: '6px'
            }}
            onClick={quitApplication}
          >
            <LogOut size={12} />
            Exit
          </button>
        </div>
      </header>

      {/* 3. Main content dashboard */}
      <main className="dashboard-grid">
        {/* Telemetry tiles */}
        <div>
          <h2 className="section-title">
            <Sliders size={14} /> Telemetry Dashboard
          </h2>
          
          <div className="telemetry-row">
            <div className="telemetry-card">
              <span className="card-header-lbl">Current Position</span>
              <div className="card-body-row">
                <span className="card-value text-cyan">{currentPosMm}</span>
                <span className="card-unit">mm</span>
              </div>
            </div>

            <div className="telemetry-card">
              <span className="card-header-lbl">Feedback Resistance</span>
              <div className="card-body-row">
                <span className={`card-value ${resistancePct >= 90 ? 'text-danger' : resistancePct >= 70 ? 'text-warning' : 'text-success'}`}>
                  {resistancePct}
                </span>
                <span className="card-unit">%</span>
              </div>
            </div>

            <div className="telemetry-card">
              <span className="card-header-lbl">Pattern Frequency</span>
              <div className="card-body-row">
                <span className="card-value text-purple">{frequencyHz.toFixed(1)}</span>
                <span className="card-unit">Hz</span>
              </div>
            </div>

            <div className="telemetry-card">
              <span className="card-header-lbl">Session Timer</span>
              <div className="card-body-row">
                <span className="card-value">{formatSessionTime(telemetry.session_elapsed_s)}</span>
                <span className="card-unit">min</span>
              </div>
            </div>
          </div>
        </div>

        {/* Shaft visual track */}
        <div className="visualizer-card">
          <div className="visualizer-header">
            <span className="input-label">Shaft Displacement Visualizer</span>
            <span className="visualizer-info">{currentPosMm} mm / {maxCalMm} mm</span>
          </div>

          <div className="shaft-rail-container">
            <div className="shaft-rail">
              <div className="shaft-fill-progress" style={{ width: `${positionPercentage}%` }} />
              <div className="shaft-indicator" style={{ left: `${positionPercentage}%` }} />
            </div>
            
            <div className="shaft-ticks">
              <span className="tick">0 mm</span>
              <span className="tick">{Math.round(maxCalMm / 4)} mm</span>
              <span className="tick">{Math.round(maxCalMm / 2)} mm</span>
              <span className="tick">{Math.round(maxCalMm * 3 / 4)} mm</span>
              <span className="tick">{maxCalMm} mm</span>
            </div>
          </div>
        </div>

        {/* Controls Layout */}
        <div className="control-grid">
          {/* Action buttons & Presets */}
          <div className="control-card">
            <div className="input-group">
              <label className="input-label">Active Waveform</label>
              <select 
                className="select-widget"
                value={patternName}
                onChange={(e) => {
                  setPatternName(e.target.value);
                  if (telemetry.state_enum === "RUNNING") {
                    // Small delay to ensure state updates
                    setTimeout(() => startPattern(), 0);
                  }
                }}
              >
                {PATTERN_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="button-actions-row">
              <button className="btn btn-primary" onClick={() => startPattern(true)}>
                <Play size={16} fill="currentColor" /> Start Stimulation
              </button>
              
              <div className="button-inner-row">
                <button className="btn btn-secondary" onClick={stopPattern}>
                  <Square size={16} fill="currentColor" /> Stop
                </button>
                <button 
                  className="btn btn-secondary" 
                  onClick={() => sendCommand("start_calibration")}
                >
                  <RefreshCw size={16} /> Calibrate
                </button>
              </div>

              {telemetry.state_enum === "ESTOP" ? (
                <button className="btn btn-primary" onClick={clearEstop}>
                  Clear Emergency Stop
                </button>
              ) : (
                <button className="btn btn-danger btn-estop" onClick={triggerEstop}>
                  EMERGENCY STOP [Space]
                </button>
              )}
            </div>

            <div className="input-group" style={{ marginTop: 'auto' }}>
              <label className="input-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Presets Slots (1-5)</span>
                <span style={{ fontSize: '0.65rem', textTransform: 'none', opacity: 0.6 }}>Ctrl+Click to Save</span>
              </label>
              <div className="presets-grid">
                {[0, 1, 2, 3, 4].map(idx => (
                  <button 
                    key={idx}
                    className={`preset-btn ${activePresetSlot === idx ? 'active' : ''}`}
                    onClick={(e) => {
                      if (e.ctrlKey) {
                        handlePresetSave(idx);
                      } else {
                        handlePresetClick(idx);
                      }
                    }}
                    title={presets[idx] ? `Preset ${idx+1}: ${presets[idx].pattern_name}` : `Preset ${idx+1} (Empty)`}
                  >
                    <FolderOpen size={16} />
                    <span className="preset-btn-num">{idx + 1}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Sliders adjustments */}
          <div className="control-card">
            <h3 className="section-title" style={{ marginBottom: 0 }}>
              <Sliders size={14} /> Parameter Scaling
            </h3>
            
            <div className="parameter-sliders">
              {/* Slider 1: Speed Frequency */}
              <div className="slider-row">
                <div className="slider-header">
                  <span className="slider-title">Stimulation Speed</span>
                  <span className="slider-value-display">{frequencyHz.toFixed(1)} Hz ({Math.round(frequencyHz * 60)} SPM)</span>
                </div>
                <div className="slider-body">
                  <button className="slider-btn" onClick={() => {
                    const next = Math.max(0.1, Math.round((frequencyHz - 0.1) * 10) / 10);
                    setFrequencyHz(next);
                  }}>-</button>
                  <input 
                    type="range" 
                    className="custom-slider" 
                    min="0.1" 
                    max="3.0" 
                    step="0.1" 
                    value={frequencyHz}
                    onChange={(e) => setFrequencyHz(parseFloat(e.target.value))}
                  />
                  <button className="slider-btn" onClick={() => {
                    const next = Math.min(3.0, Math.round((frequencyHz + 0.1) * 10) / 10);
                    setFrequencyHz(next);
                  }}>+</button>
                </div>
              </div>

              {/* Slider 2: Stroke Length */}
              <div className="slider-row">
                <div className="slider-header">
                  <span className="slider-title">Stroke Amplitude</span>
                  <span className="slider-value-display">{strokeLengthMm} mm</span>
                </div>
                <div className="slider-body">
                  <button className="slider-btn" onClick={() => setStrokeLengthMm(prev => Math.max(10, prev - 5))}>-</button>
                  <input 
                    type="range" 
                    className="custom-slider" 
                    min="10" 
                    max={maxCalMm - 10} 
                    step="5" 
                    value={strokeLengthMm}
                    onChange={(e) => setStrokeLengthMm(parseInt(e.target.value))}
                  />
                  <button className="slider-btn" onClick={() => setStrokeLengthMm(prev => Math.min(maxCalMm - 10, prev + 5))}>+</button>
                </div>
              </div>

              {/* Slider 3: Intensity Scaling */}
              <div className="slider-row">
                <div className="slider-header">
                  <span className="slider-title">Overall Scale Intensity</span>
                  <span className="slider-value-display">{intensityPct}%</span>
                </div>
                <div className="slider-body">
                  <button className="slider-btn" onClick={() => changeIntensity(intensityPct - 10)}>-</button>
                  <input 
                    type="range" 
                    className="custom-slider" 
                    min="10" 
                    max="100" 
                    step="10" 
                    value={intensityPct}
                    onChange={(e) => changeIntensity(parseInt(e.target.value))}
                  />
                  <button className="slider-btn" onClick={() => changeIntensity(intensityPct + 10)}>+</button>
                </div>
              </div>

              {/* Slider 4: Safety Force threshold */}
              <div className="slider-row">
                <div className="slider-header">
                  <span className="slider-title">Feedback Safety Clamps</span>
                  <span className="slider-value-display">{safetyForceN} N</span>
                </div>
                <div className="slider-body">
                  <button className="slider-btn" onClick={() => changeSafetyLimit(safetyForceN - 5)}>-</button>
                  <input 
                    type="range" 
                    className="custom-slider" 
                    min="5" 
                    max="60" 
                    step="5" 
                    value={safetyForceN}
                    onChange={(e) => changeSafetyLimit(parseInt(e.target.value))}
                  />
                  <button className="slider-btn" onClick={() => changeSafetyLimit(safetyForceN + 5)}>+</button>
                </div>
              </div>

              {/* Additional options based on selected pattern */}
              {patternName === "Realistic" && (
                <div className="slider-row">
                  <div className="slider-header">
                    <span className="slider-title">Realistic Rod Ratio</span>
                    <span className="slider-value-display">{rodRatio.toFixed(1)}x</span>
                  </div>
                  <div className="slider-body">
                    {[2.5, 3.5, 5.0].map(val => (
                      <button 
                        key={val} 
                        className={`btn ${rodRatio === val ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ padding: '6px 12px', flex: 1 }}
                        onClick={() => setRodRatio(val)}
                      >
                        {val.toFixed(1)}x
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {patternName === "Escalate" && (
                <div className="slider-row">
                  <div className="slider-header">
                    <span className="slider-title">Escalation Duration</span>
                    <span className="slider-value-display">{escalateDurationS} seconds</span>
                  </div>
                  <div className="slider-body">
                    <button className="slider-btn" onClick={() => setEscalateDurationS(prev => Math.max(30, prev - 30))}>-</button>
                    <input 
                      type="range" 
                      className="custom-slider" 
                      min="30" 
                      max="600" 
                      step="30" 
                      value={escalateDurationS}
                      onChange={(e) => setEscalateDurationS(parseInt(e.target.value))}
                    />
                    <button className="slider-btn" onClick={() => setEscalateDurationS(prev => Math.min(600, prev + 30))}>+</button>
                  </div>
                </div>
              )}

              {patternName === "Edge" && (
                <div className="slider-row">
                  <div className="slider-header">
                    <span className="slider-title">Edging Reciprocating Cycle</span>
                    <span className="slider-value-display">{edgePeriodS} seconds</span>
                  </div>
                  <div className="slider-body">
                    <button className="slider-btn" onClick={() => setEdgePeriodS(prev => Math.max(10, prev - 10))}>-</button>
                    <input 
                      type="range" 
                      className="custom-slider" 
                      min="10" 
                      max="180" 
                      step="10" 
                      value={edgePeriodS}
                      onChange={(e) => setEdgePeriodS(parseInt(e.target.value))}
                    />
                    <button className="slider-btn" onClick={() => setEdgePeriodS(prev => Math.min(180, prev + 10))}>+</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* 4. Bottom Debug display and telemetry */}
      <footer className="app-footer">
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <span>© 2026 Wavedriver Controller System</span>
          <span 
            style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}
            onClick={() => setShowDebug(!showDebug)}
          >
            {showDebug ? <ToggleRight className="text-cyan" size={18} /> : <ToggleLeft size={18} />}
            <span>Show Advanced Diagnostic Logs</span>
          </span>
        </div>

        {showDebug && (
          <div className="footer-links" style={{ gap: '12px' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Zap size={12} className="text-purple" />
              Power: <strong className="text-bright">{telemetry.power_W} W</strong>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Thermometer size={12} className="text-warning" />
              Temp: <strong className="text-bright">{telemetry.temperature_C} °C</strong>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Battery size={12} className="text-cyan" />
              Voltage: <strong className="text-bright">{(telemetry.voltage_mV / 1000).toFixed(1)} V</strong>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Activity size={12} className="text-success" />
              Speed: <strong className="text-bright">{(telemetry.speed_mm_s || 0).toFixed(0)} mm/s</strong>
            </span>
          </div>
        )}
      </footer>

      {/* 5. Startup Welcome screen */}
      {showStartupModal && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <h2 className="modal-title">Wavedriver Workspace Setup</h2>
            {hasSavedCal ? (
              <>
                <p className="modal-body">
                  A cached physical device calibration is saved and ready to load.
                  <br /><br />
                  Choose <strong>Resume Session</strong> to restore settings, or <strong>Recalibrate</strong> if you have remounted the Orca 6 motor.
                </p>
                <div className="modal-buttons">
                  <button className="btn btn-primary" onClick={resumeSession}>
                    Resume Session
                  </button>
                  <button className="btn btn-secondary" onClick={startCalibration}>
                    Recalibrate Device
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="modal-body">
                  Before starting stimulation patterns, Wavedriver must calibrate the physical workspace of the Orca 6 linear motor.
                  <br /><br />
                  The shaft will move slowly to both endpoints to determine the safe stroke length. Ensure the path is completely clear.
                </p>
                <div className="modal-buttons">
                  <button className="btn btn-primary" onClick={startCalibration}>
                    Set Up Device (Calibrate)
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
