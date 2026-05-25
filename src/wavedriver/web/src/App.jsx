import { useRef, useCallback, useEffect, useState } from 'react';

import { ErrorBoundary }   from './ErrorBoundary.jsx';
import { useController }   from './hooks/useController.js';
import { useSettings }     from './hooks/useSettings.js';
import { useKeyboard }     from './hooks/useKeyboard.js';

import { Banner }          from './components/Banner.jsx';
import { Header }          from './components/Header.jsx';
import { ModeBar }         from './components/ModeBar.jsx';
import { SharedControls }  from './components/SharedControls.jsx';
import { PatternMode }     from './components/PatternMode.jsx';
import { AdvancedDrawer }  from './components/AdvancedDrawer.jsx';
import { StartupModal }    from './components/StartupModal.jsx';
import { HelpModal }       from './components/HelpModal.jsx';
import { ActivityLog }     from './components/ActivityLog.jsx';
import { SessionHistory }  from './components/SessionHistory.jsx';
import { Toast }           from './components/Toast.jsx';
import { Footer }          from './components/Footer.jsx';

import { InteractiveEdging } from './components/InteractiveEdging.jsx';
import { VideoSyncPanel }    from './components/VideoSyncPanel.jsx';
import { AudioSyncPanel }    from './components/AudioSyncPanel.jsx';
import { SequenceBuilder }   from './components/SequenceBuilder.jsx';

const SHUFFLE_PATTERNS = ['Wave', 'Realistic', 'Thrust', 'Pulse', 'Tease', 'Escalate', 'Edge', 'Depth', 'Adaptive'];

function AppInner() {
  const { apiReady, telemetry, calibratedLength, sendCommand, setHistoryEnabled } = useController();

  const {
    patternName,    setPatternName,
    frequencyHz,    setFrequencyHz,
    strokeLengthMm, setStrokeLengthMm,
    intensityPct,   setIntensityPct,
    rodRatio,       setRodRatio,
    escalateDurationS, setEscalateDurationS,
    edgePeriodS,    setEdgePeriodS,
    depthPeriodS,   setDepthPeriodS,
    adaptiveMode,   setAdaptiveMode,
    adaptiveSensitivity, setAdaptiveSensitivity,
    safetyForceN,   setSafetyForceN,
    maxSessionS,    setMaxSessionS,
    presets,
    activePresetSlot, setActivePresetSlot,
    savePreset,
    importPresets,
    defaultPresetSlot, setDefaultPresetSlot,
    historyEnabled, setHistoryEnabled: setHistoryEnabledSetting,
    shuffleEnabled, setShuffleEnabled,
    shuffleDwellS,  setShuffleDwellS,
    shuffleMinFreq, setShuffleMinFreq,
    shuffleMaxFreq, setShuffleMaxFreq,
    shuffleMinStroke, setShuffleMinStroke,
    shuffleMaxStroke, setShuffleMaxStroke,
  } = useSettings({ apiReady, sendCommand, setHistoryEnabled });

  const settingsRef = useRef({});
  useEffect(() => {
    settingsRef.current = {
      patternName, frequencyHz, strokeLengthMm, intensityPct,
      rodRatio, escalateDurationS, edgePeriodS, depthPeriodS, safetyForceN, maxSessionS,
      adaptiveMode, adaptiveSensitivity,
      shuffleMinFreq, shuffleMaxFreq, shuffleMinStroke, shuffleMaxStroke,
    };
  }, [patternName, frequencyHz, strokeLengthMm, intensityPct,
      rodRatio, escalateDurationS, edgePeriodS, depthPeriodS, safetyForceN, maxSessionS,
      adaptiveMode, adaptiveSensitivity,
      shuffleMinFreq, shuffleMaxFreq, shuffleMinStroke, shuffleMaxStroke]);

  const activeModeRef       = useRef('pattern');
  const telemetryRef        = useRef(telemetry);
  const calibratedLengthRef = useRef(calibratedLength);
  useEffect(() => { telemetryRef.current = telemetry; }, [telemetry]);
  useEffect(() => { calibratedLengthRef.current = calibratedLength; }, [calibratedLength]);

  // ── Core actions ──────────────────────────────────────────────────────────
  const startPattern = useCallback((overrides = {}) => {
    const s = { ...settingsRef.current, ...overrides };
    const strokeUm = Math.round(s.strokeLengthMm * 1000);
    const params = { stroke_length_um: strokeUm, frequency_hz: s.frequencyHz };
    if (s.patternName === 'Realistic')  params.rod_ratio           = s.rodRatio;
    if (s.patternName === 'Escalate')   params.escalate_duration_s = s.escalateDurationS;
    if (s.patternName === 'Edge')       params.edge_period_s       = s.edgePeriodS;
    if (s.patternName === 'Depth')      params.depth_period_s      = s.depthPeriodS;
    if (s.patternName === 'Adaptive') {
      params.adaptive_mode = s.adaptiveMode;
      params.sensitivity   = s.adaptiveSensitivity;
    }
    if (s.patternName === 'Funscript' && overrides.funscript_actions) {
      params.funscript_actions = overrides.funscript_actions;
      params.funscript_loop    = overrides.funscript_loop !== undefined ? overrides.funscript_loop : true;
    }
    sendCommand('start_pattern', { pattern_name: s.patternName, params });
  }, [sendCommand]);

  const stopPattern  = useCallback(() => sendCommand('soft_stop'), [sendCommand]);
  const triggerEstop = useCallback(() => sendCommand('estop', { reason: 'Emergency Stop Requested' }), [sendCommand]);
  const clearEstop   = useCallback(() => sendCommand('clear_estop'), [sendCommand]);
  const startCalibration = useCallback(() => sendCommand('start_calibration'), [sendCommand]);
  const quitApplication  = useCallback(() => window.pywebview?.api?.quit_application(), []);

  const changeIntensity = useCallback((val) => {
    const clamped = Math.max(10, Math.min(100, val));
    setIntensityPct(clamped);
    sendCommand('set_intensity', { intensity: clamped / 100.0 });
  }, [sendCommand, setIntensityPct]);

  const changeSafetyLimit = useCallback((val) => {
    const clamped = Math.max(5, Math.min(60, val));
    setSafetyForceN(clamped);
    sendCommand('set_safety_limit', { limit_mN: Math.round(clamped * 1000) });
  }, [sendCommand, setSafetyForceN]);

  const changeMaxSession = useCallback((val) => {
    const clamped = Math.max(0, Math.min(7200, val));
    setMaxSessionS(clamped);
    sendCommand('set_max_session', { max_session_s: clamped });
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
    if (preset.adaptive_mode       != null) setAdaptiveMode(preset.adaptive_mode);
    if (preset.adaptive_sensitivity != null) setAdaptiveSensitivity(preset.adaptive_sensitivity);
    if (telemetryRef.current.state_enum === 'RUNNING') {
      startPattern({
        patternName:         preset.pattern_name         || 'Wave',
        frequencyHz:         preset.frequency_hz         || 1.0,
        strokeLengthMm:      preset.stroke_length_mm     || 50.0,
        rodRatio:            preset.rod_ratio            || 2.5,
        escalateDurationS:   preset.escalate_duration_s || 300.0,
        edgePeriodS:         preset.edge_period_s        || 60.0,
        depthPeriodS:        preset.depth_period_s       || 20.0,
        adaptiveMode:        preset.adaptive_mode        || 'ease',
        adaptiveSensitivity: preset.adaptive_sensitivity || 1.0,
      });
      if (preset.intensity_pct != null)
        sendCommand('set_intensity', { intensity: preset.intensity_pct / 100.0 });
    }
  }, [presets, setActivePresetSlot, setPatternName, setFrequencyHz, setStrokeLengthMm,
      setIntensityPct, setRodRatio, setEscalateDurationS, setEdgePeriodS, setDepthPeriodS,
      setAdaptiveMode, setAdaptiveSensitivity, startPattern, sendCommand]);

  const handlePresetSave = useCallback((slotIdx) => {
    const name = window.prompt(`Name for preset ${slotIdx + 1}:`, presets[slotIdx]?.name || '');
    if (name !== null) savePreset(slotIdx, name);
  }, [presets, savePreset]);

  const defaultAppliedRef = useRef(false);
  useEffect(() => {
    if (!apiReady || defaultAppliedRef.current) return;
    if (defaultPresetSlot != null && presets[defaultPresetSlot]) {
      defaultAppliedRef.current = true;
      handlePresetRecall(defaultPresetSlot);
    }
  }, [apiReady, defaultPresetSlot, presets, handlePresetRecall]);

  // ── Auto-resend pattern when running and settings change ──────────────────
  const isRunning = telemetry.state_enum === 'RUNNING' && !telemetry.soft_stopping;
  useEffect(() => {
    if (apiReady && isRunning && activeModeRef.current !== 'video') startPattern();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiReady, isRunning, patternName, frequencyHz, strokeLengthMm,
      rodRatio, escalateDurationS, edgePeriodS, depthPeriodS, adaptiveMode, adaptiveSensitivity]);

  // ── Shuffle mode ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!shuffleEnabled || !isRunning) return;
    const iv = setInterval(() => {
      const others = SHUFFLE_PATTERNS.filter(p => p !== settingsRef.current.patternName);
      const next   = others[Math.floor(Math.random() * others.length)];
      const minF   = settingsRef.current.shuffleMinFreq || 0.5;
      const maxF   = settingsRef.current.shuffleMaxFreq || 2.0;
      const minS   = settingsRef.current.shuffleMinStroke || 30;
      const maxS   = settingsRef.current.shuffleMaxStroke || 90;
      setPatternName(next);
      setFrequencyHz(Math.round((minF + Math.random() * (maxF - minF)) * 10) / 10);
      setStrokeLengthMm(Math.round((minS + Math.random() * (maxS - minS)) / 5) * 5);
    }, shuffleDwellS * 1000);
    return () => clearInterval(iv);
  }, [shuffleEnabled, isRunning, shuffleDwellS, setPatternName, setFrequencyHz, setStrokeLengthMm]);

  // Spacebar → InteractiveEdging "Almost" button (when in edging mode)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        document.getElementById('btn-almost')?.click();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // ── Calibration-complete toast ────────────────────────────────────────────
  const [toastMessage, setToastMessage] = useState(null);
  const dismissToast = useCallback(() => setToastMessage(null), []);
  const prevStateRef = useRef(null);
  useEffect(() => {
    const cur  = telemetry.state_enum;
    const prev = prevStateRef.current;
    if (cur === 'CALIBRATED_IDLE' &&
        (prev === 'CALIBRATING_CENTER' || prev === 'CALIBRATING_EXTEND' || prev === 'CALIBRATING_RETRACT')) {
      setToastMessage('Calibration complete — select a pattern and press Enter to start');
    }
    prevStateRef.current = cur;
  }, [telemetry.state_enum]);

  // ── UI state ──────────────────────────────────────────────────────────────
  const [activeMode, setActiveMode]       = useState('pattern');
  useEffect(() => { activeModeRef.current = activeMode; }, [activeMode]);
  const [showAdvanced, setShowAdvanced]   = useState(false);
  const [showModal, setShowModal]         = useState(true);
  const [onboardingStep, setOnboardingStep] = useState('WELCOME');
  const [showHelp, setShowHelp]           = useState(false);
  const [showActivityLog, setShowActivityLog] = useState(false);
  const [showHistory, setShowHistory]     = useState(false);
  const [sessionHistory, setSessionHistory] = useState([]);

  const loadHistory = useCallback(async () => {
    try {
      const records = await window.pywebview?.api?.load_session_history();
      if (records) setSessionHistory(records);
    } catch (e) {
      console.error('Failed to load session history:', e);
    }
  }, []);

  const handleToggleHistory = useCallback(() => {
    setShowHistory(v => {
      if (!v) loadHistory();
      return !v;
    });
  }, [loadHistory]);

  const handleClearHistory = useCallback(async () => {
    await window.pywebview?.api?.clear_history();
    setSessionHistory([]);
  }, []);

  const handleConnectAndCalibrate = useCallback(async (port) => {
    if (port && window.pywebview?.api?.connect_port) {
      try { await window.pywebview.api.connect_port(port); } catch (e) {
        console.error('Failed to connect to chosen port:', e);
      }
    }
    startCalibration();
  }, [startCalibration]);

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
    onCalibrate:   startCalibration,
    onStopPattern: stopPattern,
    onEstop:       triggerEstop,
    onClearEstop:  clearEstop,
    onQuit:        quitApplication,
    onToggleHelp:  () => setShowHelp(v => !v),
  });

  return (
    <div className="app-container">
      <Banner telemetry={telemetry} />

      <Header
        telemetry={telemetry}
        onToggleHelp={() => setShowHelp(v => !v)}
        onToggleAdvanced={() => setShowAdvanced(v => !v)}
        onQuit={quitApplication}
      />

      <ModeBar activeMode={activeMode} setActiveMode={setActiveMode} />

      <div className="app-main">
        <SharedControls
          activeMode={activeMode}
          telemetry={telemetry}
          frequencyHz={frequencyHz}       setFrequencyHz={setFrequencyHz}
          strokeLengthMm={strokeLengthMm} setStrokeLengthMm={setStrokeLengthMm}
          calibratedLength={calibratedLength}
          onStart={startPattern}
          onStop={stopPattern}
          onCalibrate={startCalibration}
          onEstop={triggerEstop}
          onClearEstop={clearEstop}
        />

        <div className="mode-panel">
          {activeMode === 'pattern' && (
            <PatternMode
              patternName={patternName}       setPatternName={setPatternName}
              rodRatio={rodRatio}             setRodRatio={setRodRatio}
              depthPeriodS={depthPeriodS}     setDepthPeriodS={setDepthPeriodS}
              adaptiveMode={adaptiveMode}     setAdaptiveMode={setAdaptiveMode}
              adaptiveSensitivity={adaptiveSensitivity} setAdaptiveSensitivity={setAdaptiveSensitivity}
            />
          )}
          {activeMode === 'edging' && (
            <InteractiveEdging
              isRunning={isRunning}
              intensityPct={intensityPct}
              onIntensityChange={changeIntensity}
            />
          )}
          {activeMode === 'sequence' && (
            <SequenceBuilder
              isRunning={isRunning}
              startPattern={startPattern}
              stopPattern={stopPattern}
              setPatternName={setPatternName}
              setFrequencyHz={setFrequencyHz}
              setStrokeLengthMm={setStrokeLengthMm}
              onIntensityChange={changeIntensity}
            />
          )}
          {activeMode === 'video' && (
            <VideoSyncPanel
              isRunning={isRunning}
              sendCommand={sendCommand}
              startPattern={startPattern}
            />
          )}
          {activeMode === 'audio' && (
            <AudioSyncPanel
              isRunning={isRunning}
              intensityPct={intensityPct}
              onIntensityChange={changeIntensity}
              onStart={startPattern}
              onStop={stopPattern}
              frequencyHz={frequencyHz}
              onFrequencyChange={(hz) => {
                setFrequencyHz(hz);
                if (isRunning) startPattern({ frequencyHz: hz });
              }}
            />
          )}
        </div>
      </div>

      <Footer />

      {showAdvanced && (
        <AdvancedDrawer
          onClose={() => setShowAdvanced(false)}
          telemetry={telemetry}
          intensityPct={intensityPct}       onIntensityChange={changeIntensity}
          safetyForceN={safetyForceN}       onSafetyChange={changeSafetyLimit}
          maxSessionS={maxSessionS}         onMaxSessionChange={changeMaxSession}
          presets={presets}
          activePresetSlot={activePresetSlot}
          defaultPresetSlot={defaultPresetSlot} setDefaultPresetSlot={setDefaultPresetSlot}
          onPresetSave={handlePresetSave}   onPresetRecall={handlePresetRecall}
          onImportPresets={importPresets}
          shuffleEnabled={shuffleEnabled}   setShuffleEnabled={setShuffleEnabled}
          shuffleDwellS={shuffleDwellS}     setShuffleDwellS={setShuffleDwellS}
          shuffleMinFreq={shuffleMinFreq}   setShuffleMinFreq={setShuffleMinFreq}
          shuffleMaxFreq={shuffleMaxFreq}   setShuffleMaxFreq={setShuffleMaxFreq}
          historyEnabled={historyEnabled}   onHistoryEnabledChange={setHistoryEnabledSetting}
          sessionHistory={sessionHistory}
          onClearHistory={handleClearHistory}
          onToggleHistory={handleToggleHistory}
          showHistory={showHistory}
          showActivityLog={showActivityLog}
          onToggleActivityLog={() => setShowActivityLog(v => !v)}
        />
      )}

      {showActivityLog && (
        <ActivityLog
          events={telemetry.event_log || []}
          onClose={() => setShowActivityLog(false)}
        />
      )}

      {showHistory && (
        <SessionHistory
          records={sessionHistory}
          historyEnabled={historyEnabled}
          onHistoryEnabledChange={setHistoryEnabledSetting}
          onClearHistory={handleClearHistory}
          onClose={() => setShowHistory(false)}
        />
      )}

      {showModal && (
        <StartupModal
          step={onboardingStep}
          setStep={setOnboardingStep}
          telemetry={onboardingStep === 'CALIBRATING' || onboardingStep === 'COMPLETE' ? telemetry : null}
          onConnectAndCalibrate={handleConnectAndCalibrate}
          onClose={() => setShowModal(false)}
        />
      )}

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}

      <Toast message={toastMessage} onDismiss={dismissToast} />
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
