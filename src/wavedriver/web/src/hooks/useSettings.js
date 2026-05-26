import { useState, useEffect, useCallback } from 'react';

/**
 * Manages all user-configurable settings, session persistence, and presets.
 *
 * On API ready: loads session from disk, applies safety and session commands.
 * Auto-saves session to disk whenever relevant settings change.
 */
export function useSettings({ apiReady, sendCommand, setHistoryEnabled }) {
  const [patternName, setPatternName]         = useState("Wave");
  const [frequencyHz, setFrequencyHz]         = useState(0.5);
  const [strokeLengthMm, setStrokeLengthMm]   = useState(50.0);
  const [intensityPct, setIntensityPct]       = useState(50.0);
  const [rodRatio, setRodRatio]               = useState(2.5);
  const [escalateDurationS, setEscalateDurationS] = useState(300.0);
  const [edgePeriodS, setEdgePeriodS]         = useState(60.0);
  const [depthPeriodS, setDepthPeriodS]       = useState(20.0);
  const [adaptiveMode, setAdaptiveMode]       = useState("ease");
  const [adaptiveSensitivity, setAdaptiveSensitivity] = useState(1.0);
  const [safetyForceN, setSafetyForceN]       = useState(55.0);
  const [maxSessionS, setMaxSessionS]         = useState(0);
  const [presets, setPresets]                 = useState(Array(5).fill(null));
  const [activePresetSlot, setActivePresetSlot] = useState(null);
  const [defaultPresetSlot, setDefaultPresetSlot] = useState(null);
  
  // Surprise / Shuffle mode config
  const [historyEnabled, setHistoryEnabledState] = useState(true);

  const [shuffleEnabled, setShuffleEnabled]   = useState(false);
  const [shuffleDwellS, setShuffleDwellS]     = useState(60);
  const [shuffleMinFreq, setShuffleMinFreq]   = useState(0.5);
  const [shuffleMaxFreq, setShuffleMaxFreq]   = useState(2.0);
  const [shuffleMinStroke, setShuffleMinStroke] = useState(30.0);
  const [shuffleMaxStroke, setShuffleMaxStroke] = useState(90.0);

  // Load safety settings and presets on startup.
  // Motion parameters (pattern, frequency, stroke, etc.) are intentionally NOT
  // restored — calibration runs each session, so those settings always start fresh.
  useEffect(() => {
    if (!apiReady) return;

    (async () => {
      try {
        const session = await window.pywebview.api.load_session();
        if (session) {
          if (session.safety_force_n != null) {
            setSafetyForceN(session.safety_force_n);
            sendCommand("set_safety_limit", { limit_mN: Math.round(session.safety_force_n * 1000) });
          }
          if (session.max_session_s != null) {
            setMaxSessionS(session.max_session_s);
            sendCommand("set_max_session", { max_session_s: session.max_session_s });
          }
          if (session.history_enabled != null) {
            setHistoryEnabledState(session.history_enabled);
            setHistoryEnabled?.(session.history_enabled);
          }
        }
      } catch (e) {
        console.error("Failed to load session:", e);
      }

      try {
        const loaded = await window.pywebview.api.load_presets();
        if (loaded) {
          const slots = Array(5).fill(null);
          for (let i = 0; i < 5; i++) {
            if (loaded[i.toString()]) slots[i] = loaded[i.toString()];
          }
          setPresets(slots);
        }
      } catch (e) {
        console.error("Failed to load presets:", e);
      }
    })();
  }, [apiReady, sendCommand, setHistoryEnabled]);

  // Keep controller ref in sync with historyEnabled state
  useEffect(() => {
    setHistoryEnabled?.(historyEnabled);
  }, [historyEnabled, setHistoryEnabled]);

  // Auto-save safety settings whenever they change
  useEffect(() => {
    if (!apiReady) return;
    window.pywebview?.api?.save_session({
      safety_force_n:  safetyForceN,
      max_session_s:   maxSessionS,
      history_enabled: historyEnabled,
    });
  }, [apiReady, safetyForceN, maxSessionS, historyEnabled]);

  const savePreset = useCallback((slotIdx, name) => {
    setPresets(prev => {
      const updated = [...prev];
      updated[slotIdx] = {
        name:                name || prev[slotIdx]?.name || "",
        pattern_name:        patternName,
        frequency_hz:        frequencyHz,
        stroke_length_mm:    strokeLengthMm,
        intensity_pct:       intensityPct,
        rod_ratio:           rodRatio,
        escalate_duration_s: escalateDurationS,
        edge_period_s:       edgePeriodS,
        depth_period_s:      depthPeriodS,
        adaptive_mode:       adaptiveMode,
        adaptive_sensitivity: adaptiveSensitivity,
      };
      if (window.pywebview?.api) {
        const obj = {};
        updated.forEach((p, i) => { if (p) obj[i.toString()] = p; });
        window.pywebview.api.save_presets(obj);
      }
      return updated;
    });
    setActivePresetSlot(slotIdx);
  }, [patternName, frequencyHz, strokeLengthMm, intensityPct, rodRatio, escalateDurationS, edgePeriodS, depthPeriodS, adaptiveMode, adaptiveSensitivity]);

  const renamePreset = useCallback((slotIdx, name) => {
    setPresets(prev => {
      if (!prev[slotIdx]) return prev;
      const updated = [...prev];
      updated[slotIdx] = { ...updated[slotIdx], name };
      if (window.pywebview?.api) {
        const obj = {};
        updated.forEach((p, i) => { if (p) obj[i.toString()] = p; });
        window.pywebview.api.save_presets(obj);
      }
      return updated;
    });
  }, []);

  const importPresets = useCallback((presetsData) => {
    const slots = Array(5).fill(null);
    for (let i = 0; i < 5; i++) {
      if (presetsData[i.toString()]) slots[i] = presetsData[i.toString()];
    }
    setPresets(slots);
    if (window.pywebview?.api) {
      window.pywebview.api.save_presets(presetsData);
    }
  }, []);

  return {
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
    renamePreset,
    importPresets,
    defaultPresetSlot, setDefaultPresetSlot,
    historyEnabled, setHistoryEnabled: setHistoryEnabledState,
    shuffleEnabled, setShuffleEnabled,
    shuffleDwellS,  setShuffleDwellS,
    shuffleMinFreq, setShuffleMinFreq,
    shuffleMaxFreq, setShuffleMaxFreq,
    shuffleMinStroke, setShuffleMinStroke,
    shuffleMaxStroke, setShuffleMaxStroke,
  };
}
