import { useRef, useCallback, useEffect, useState } from 'react';

import { ErrorBoundary }   from './ErrorBoundary.jsx';
import { useController }   from './hooks/useController.js';
import { useSettings }     from './hooks/useSettings.js';
import { useKeyboard }     from './hooks/useKeyboard.js';

import { Banner }          from './components/Banner.jsx';
import { Header }          from './components/Header.jsx';
import { StartupModal }    from './components/StartupModal.jsx';
import { TelemetryPanel }  from './components/TelemetryPanel.jsx';
import { ControlPanel }    from './components/ControlPanel.jsx';
import { SliderPanel }     from './components/SliderPanel.jsx';
import { Footer }          from './components/Footer.jsx';
import { HelpModal }       from './components/HelpModal.jsx';
import { ActivityLog }     from './components/ActivityLog.jsx';
import { SessionHistory }  from './components/SessionHistory.jsx';
import { Toast }           from './components/Toast.jsx';

const SHUFFLE_PATTERNS = ["Wave", "Realistic", "Thrust", "Pulse", "Tease", "Escalate", "Edge", "Depth"];

function AppInner() {
  const { apiReady, telemetry, calibratedLength, sendCommand } = useController();

  const {
    patternName,    setPatternName,
    frequencyHz,    setFrequencyHz,
    strokeLengthMm, setStrokeLengthMm,
    intensityPct,   setIntensityPct,
    rodRatio,       setRodRatio,
    escalateDurationS, setEscalateDurationS,
    edgePeriodS,    setEdgePeriodS,
    depthPeriodS,   setDepthPeriodS,
    safetyForceN,   setSafetyForceN,
    maxSessionS,    setMaxSessionS,
    presets,
    activePresetSlot, setActivePresetSlot,
    savePreset,
    renamePreset,
    importPresets,
    defaultPresetSlot, setDefaultPresetSlot,
    shuffleEnabled, setShuffleEnabled,
    shuffleDwellS,  setShuffleDwellS,
  } = useSettings({ apiReady, sendCommand });

  // Refs that always hold the latest values — used by keyboard handler and
  // startPattern so they never capture stale React state.
  const settingsRef = useRef({});
  useEffect(() => {
    settingsRef.current = {
      patternName, frequencyHz, strokeLengthMm, intensityPct,
      rodRatio, escalateDurationS, edgePeriodS, depthPeriodS, safetyForceN, maxSessionS,
    };
  }, [patternName, frequencyHz, strokeLengthMm, intensityPct,
      rodRatio, escalateDurationS, edgePeriodS, depthPeriodS, safetyForceN, maxSessionS]);

  const telemetryRef        = useRef(telemetry);
  const calibratedLengthRef = useRef(calibratedLength);
  useEffect(() => { telemetryRef.current = telemetry; }, [telemetry]);
  useEffect(() => { calibratedLengthRef.current = calibratedLength; }, [calibratedLength]);

  // ── Core action: build and send a start_pattern command ──────────────────
  const startPattern = useCallback((overrides = {}) => {
    const s = { ...settingsRef.current, ...overrides };
    const strokeUm = Math.round(s.strokeLengthMm * 1000);
    const params = { stroke_length_um: strokeUm, frequency_hz: s.frequencyHz };
    if (s.patternName === "Realistic")  params.rod_ratio           = s.rodRatio;
    if (s.patternName === "Escalate")   params.escalate_duration_s = s.escalateDurationS;
    if (s.patternName === "Edge")       params.edge_period_s       = s.edgePeriodS;
    if (s.patternName === "Depth")      params.depth_period_s      = s.depthPeriodS;
    sendCommand("start_pattern", { pattern_name: s.patternName, params });
  }, [sendCommand]);

  // ── Derived command helpers ────────────────────────────────────────────────
  const stopPattern = useCallback(() => sendCommand("soft_stop"), [sendCommand]);

  const pauseToggle = useCallback(() => {
    sendCommand(telemetryRef.current.paused ? "resume_pattern" : "pause_pattern");
  }, [sendCommand]);

  const triggerEstop = useCallback(
    () => sendCommand("estop", { reason: "Emergency Stop Requested" }), [sendCommand]);

  const clearEstop = useCallback(
    () => sendCommand("clear_estop"), [sendCommand]);

  const startCalibration = useCallback(
    () => sendCommand("start_calibration"), [sendCommand]);

  const quitApplication = useCallback(
    () => window.pywebview?.api?.quit_application(), []);

  const changeIntensity = useCallback((val) => {
    const clamped = Math.max(10, Math.min(100, val));
    setIntensityPct(clamped);
    sendCommand("set_intensity", { intensity: clamped / 100.0 });
  }, [sendCommand, setIntensityPct]);

  const changeSafetyLimit = useCallback((val) => {
    const clamped = Math.max(5, Math.min(60, val));
    setSafetyForceN(clamped);
    sendCommand("set_safety_limit", { limit_mN: Math.round(clamped * 1000) });
  }, [sendCommand, setSafetyForceN]);

  const changeMaxSession = useCallback((val) => {
    const clamped = Math.max(0, Math.min(7200, val));
    setMaxSessionS(clamped);
    sendCommand("set_max_session", { max_session_s: clamped });
  }, [sendCommand, setMaxSessionS]);

  // ── Preset handlers ───────────────────────────────────────────────────────
  const handlePresetRecall = useCallback((slotIdx) => {
    const preset = presets[slotIdx];
    if (!preset) return;
    setActivePresetSlot(slotIdx);
    if (preset.pattern_name        != null) setPatternName(preset.pattern_name);
    if (preset.frequency_hz        != null) setFrequencyHz(preset.frequency_hz);
    if (preset.stroke_length_mm    != null) setStrokeLengthMm(preset.stroke_length_mm);
    if (preset.intensity_pct       != null) setIntensityPct(preset.intensity_pct);
    if (preset.rod_ratio           != null) setRodRatio(preset.rod_ratio);
    if (preset.escalate_duration_s != null) setEscalateDurationS(preset.escalate_duration_s);
    if (preset.edge_period_s       != null) setEdgePeriodS(preset.edge_period_s);
    if (preset.depth_period_s      != null) setDepthPeriodS(preset.depth_period_s);
    if (telemetryRef.current.state_enum === "RUNNING") {
      startPattern({
        patternName:      preset.pattern_name        || "Wave",
        frequencyHz:      preset.frequency_hz        || 1.0,
        strokeLengthMm:   preset.stroke_length_mm    || 50.0,
        rodRatio:         preset.rod_ratio           || 2.5,
        escalateDurationS: preset.escalate_duration_s || 300.0,
        edgePeriodS:      preset.edge_period_s       || 60.0,
        depthPeriodS:     preset.depth_period_s      || 20.0,
      });
      if (preset.intensity_pct != null) {
        sendCommand("set_intensity", { intensity: preset.intensity_pct / 100.0 });
      }
    }
  }, [presets, setActivePresetSlot, setPatternName, setFrequencyHz, setStrokeLengthMm,
      setIntensityPct, setRodRatio, setEscalateDurationS, setEdgePeriodS, setDepthPeriodS,
      startPattern, sendCommand]);

  const handlePresetSave = useCallback((slotIdx) => {
    const name = window.prompt(
      `Name for preset ${slotIdx + 1}:`,
      presets[slotIdx]?.name || ""
    );
    if (name !== null) savePreset(slotIdx, name);
  }, [presets, savePreset]);

  // ── Auto-load default preset once presets are available ──────────────────
  const defaultAppliedRef = useRef(false);
  useEffect(() => {
    if (!apiReady || defaultAppliedRef.current) return;
    if (defaultPresetSlot != null && presets[defaultPresetSlot]) {
      defaultAppliedRef.current = true;
      handlePresetRecall(defaultPresetSlot);
    }
  }, [apiReady, defaultPresetSlot, presets, handlePresetRecall]);

  // ── Auto-resend pattern when running and relevant settings change ─────────
  const isRunning = telemetry.state_enum === "RUNNING";
  useEffect(() => {
    if (apiReady && isRunning) startPattern();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiReady, isRunning, patternName, frequencyHz, strokeLengthMm,
      rodRatio, escalateDurationS, edgePeriodS, depthPeriodS]);

  // ── Shuffle mode: cycle patterns on a timer ───────────────────────────────
  useEffect(() => {
    if (!shuffleEnabled || !isRunning) return;
    const iv = setInterval(() => {
      const others = SHUFFLE_PATTERNS.filter(p => p !== settingsRef.current.patternName);
      const next   = others[Math.floor(Math.random() * others.length)];
      setPatternName(next);
    }, shuffleDwellS * 1000);
    return () => clearInterval(iv);
  }, [shuffleEnabled, isRunning, shuffleDwellS, setPatternName]);

  // ── Calibration-complete toast ────────────────────────────────────────────
  const [toastMessage, setToastMessage]       = useState(null);
  const prevStateRef = useRef(null);
  useEffect(() => {
    const cur  = telemetry.state_enum;
    const prev = prevStateRef.current;
    if (cur === "CALIBRATED_IDLE" &&
        (prev === "CALIBRATING_CENTER" || prev === "CALIBRATING_EXTEND" || prev === "CALIBRATING_RETRACT")) {
      setToastMessage("Calibration complete — select a pattern and press Enter to start");
    }
    prevStateRef.current = cur;
  }, [telemetry.state_enum]);

  // ── UI state ──────────────────────────────────────────────────────────────
  const [showModal, setShowModal]             = useState(true);
  const [showHelp, setShowHelp]               = useState(false);
  const [showActivityLog, setShowActivityLog] = useState(false);
  const [showHistory, setShowHistory]         = useState(false);
  const [sessionHistory, setSessionHistory]   = useState([]);

  const loadHistory = useCallback(async () => {
    try {
      const records = await window.pywebview?.api?.load_session_history();
      if (records) setSessionHistory(records);
    } catch (e) {
      console.error("Failed to load session history:", e);
    }
  }, []);

  const handleToggleHistory = useCallback(() => {
    setShowHistory(v => {
      if (!v) loadHistory();
      return !v;
    });
  }, [loadHistory]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  useKeyboard({
    settingsRef,
    setFrequencyHz,
    setStrokeLengthMm,
    setRodRatio,
    setEscalateDurationS,
    setEdgePeriodS,
    setDepthPeriodS,
    setIntensityPct,
    setSafetyForceN,
    sendCommand,
    startPattern,
    telemetryRef,
    calibratedLengthRef,
    presets,
    activePresetSlot,
    savePreset,
    setActivePresetSlot,
    onCalibrate:    startCalibration,
    onStopPattern:  stopPattern,
    onEstop:        triggerEstop,
    onClearEstop:   clearEstop,
    onQuit:         quitApplication,
    onToggleHelp:   () => setShowHelp(v => !v),
  });

  return (
    <div className="app-container">
      <Banner telemetry={telemetry} />

      <Header
        telemetry={telemetry}
        onQuit={quitApplication}
        onToggleHelp={() => setShowHelp(v => !v)}
      />

      <main className="dashboard-grid">
        <TelemetryPanel
          telemetry={telemetry}
          calibratedLength={calibratedLength}
          frequencyHz={frequencyHz}
          isRunning={isRunning}
          isPaused={!!telemetry.paused}
        />

        <div className="control-grid">
          <ControlPanel
            patternName={patternName}
            setPatternName={setPatternName}
            telemetry={telemetry}
            presets={presets}
            activePresetSlot={activePresetSlot}
            defaultPresetSlot={defaultPresetSlot}
            setDefaultPresetSlot={setDefaultPresetSlot}
            shuffleEnabled={shuffleEnabled}
            setShuffleEnabled={setShuffleEnabled}
            shuffleDwellS={shuffleDwellS}
            setShuffleDwellS={setShuffleDwellS}
            onStart={startPattern}
            onStop={stopPattern}
            onPauseToggle={pauseToggle}
            onCalibrate={startCalibration}
            onEstop={triggerEstop}
            onClearEstop={clearEstop}
            onPresetSave={handlePresetSave}
            onPresetRecall={handlePresetRecall}
            onImportPresets={importPresets}
          />

          <SliderPanel
            patternName={patternName}
            frequencyHz={frequencyHz}       setFrequencyHz={setFrequencyHz}
            strokeLengthMm={strokeLengthMm} setStrokeLengthMm={setStrokeLengthMm}
            intensityPct={intensityPct}
            rodRatio={rodRatio}             setRodRatio={setRodRatio}
            escalateDurationS={escalateDurationS} setEscalateDurationS={setEscalateDurationS}
            edgePeriodS={edgePeriodS}       setEdgePeriodS={setEdgePeriodS}
            depthPeriodS={depthPeriodS}     setDepthPeriodS={setDepthPeriodS}
            safetyForceN={safetyForceN}
            maxSessionS={maxSessionS}       setMaxSessionS={setMaxSessionS}
            calibratedLength={calibratedLength}
            onIntensityChange={changeIntensity}
            onSafetyChange={changeSafetyLimit}
            onMaxSessionChange={changeMaxSession}
          />
        </div>
      </main>

      <Footer
        telemetry={telemetry}
        showActivityLog={showActivityLog}
        onToggleActivityLog={() => setShowActivityLog(v => !v)}
        showHistory={showHistory}
        onToggleHistory={handleToggleHistory}
      />

      {showActivityLog && (
        <ActivityLog
          events={telemetry.event_log || []}
          onClose={() => setShowActivityLog(false)}
        />
      )}

      {showHistory && (
        <SessionHistory
          records={sessionHistory}
          onClose={() => setShowHistory(false)}
        />
      )}

      {showModal && (
        <StartupModal
          onCalibrate={() => { setShowModal(false); startCalibration(); }}
        />
      )}

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}

      <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppInner />
    </ErrorBoundary>
  );
}
