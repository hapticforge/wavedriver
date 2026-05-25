import { useEffect, useRef } from 'react';

/**
 * Registers keyboard shortcuts for the controller.
 *
 * All current values are read from `settingsRef` (always up-to-date) rather
 * than from closed-over React state, fixing the stale-closure bug where arrow
 * key presses sent the previous frequency/stroke to the motor instead of the
 * newly incremented one.
 *
 * When a value changes via keyboard, the new value is passed directly to
 * `startPattern` as an override so the motor command uses the correct number
 * even before the React state update has been committed.
 */
export function useKeyboard({
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
  onCalibrate,
  onStopPattern,
  onEstop,
  onClearEstop,
  onQuit,
  onToggleHelp,
}) {
  const tapTimestampsRef = useRef([]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't intercept shortcuts when typing in an input/textarea
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

      const s      = settingsRef.current;
      const tel    = telemetryRef.current;
      const calLen = calibratedLengthRef.current;
      const isRunning = tel.state_enum === "RUNNING";

      // ── Help modal toggle (?) ─────────────────────────────────────────────
      if (e.key === "?" || (e.key === "/" && e.shiftKey)) {
        e.preventDefault();
        onToggleHelp?.();
        return;
      }

      // ── Start pattern (Enter) ─────────────────────────────────────────────
      if (e.key === "Enter") {
        e.preventDefault();
        if (!isRunning) startPattern();
        return;
      }

      // ── Emergency Stop (Space) ────────────────────────────────────────────
      if (e.code === "Space") {
        e.preventDefault();
        onEstop();
        return;
      }

      // ── Calibrate (Z) ─────────────────────────────────────────────────────
      if (e.key === "z" || e.key === "Z") {
        e.preventDefault();
        onCalibrate();
        return;
      }

      // ── Pause / Resume (P) ────────────────────────────────────────────────
      if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        if (isRunning) {
          sendCommand(tel.paused ? "resume_pattern" : "pause_pattern");
        }
        return;
      }

      // ── Clear E-STOP (C) ──────────────────────────────────────────────────
      if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        onClearEstop();
        return;
      }

      // ── Quit (Q) ──────────────────────────────────────────────────────────
      if (e.key === "q" || e.key === "Q") {
        e.preventDefault();
        onQuit();
        return;
      }

      // ── Tap Tempo (T) ─────────────────────────────────────────────────────
      if (e.key === "t" || e.key === "T") {
        e.preventDefault();
        const now  = Date.now();
        const taps = tapTimestampsRef.current.filter(ts => now - ts < 3000);
        taps.push(now);
        tapTimestampsRef.current = taps.slice(-6);
        if (taps.length >= 2) {
          const intervals = taps.slice(1).map((ts, i) => ts - taps[i]);
          const avgMs  = intervals.reduce((a, b) => a + b) / intervals.length;
          const hz     = Math.round((1000.0 / avgMs) * 10) / 10;
          const next   = Math.max(0.1, Math.min(4.0, hz));
          setFrequencyHz(next);
          if (isRunning) startPattern({ frequencyHz: next });
        }
        return;
      }

      // ── Frequency Up / Down (Arrow Up / Down) ─────────────────────────────
      if (e.key === "ArrowUp") {
        e.preventDefault();
        const next = Math.min(4.0, Math.round((s.frequencyHz + 0.1) * 10) / 10);
        setFrequencyHz(next);
        if (isRunning) startPattern({ frequencyHz: next });
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = Math.max(0.1, Math.round((s.frequencyHz - 0.1) * 10) / 10);
        setFrequencyHz(next);
        if (isRunning) startPattern({ frequencyHz: next });
        return;
      }

      // ── Stroke / Rod-ratio (Arrow Left / Right) ───────────────────────────
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (s.patternName === "Realistic") {
          const ratios = [2.5, 3.5, 5.0];
          const next = ratios[Math.max(0, ratios.indexOf(s.rodRatio) - 1)];
          setRodRatio(next);
          if (isRunning) startPattern({ rodRatio: next });
        } else {
          const next = Math.max(10, s.strokeLengthMm - 5);
          setStrokeLengthMm(next);
          if (isRunning) startPattern({ strokeLengthMm: next });
        }
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        if (s.patternName === "Realistic") {
          const ratios = [2.5, 3.5, 5.0];
          const next = ratios[Math.min(ratios.length - 1, ratios.indexOf(s.rodRatio) + 1)];
          setRodRatio(next);
          if (isRunning) startPattern({ rodRatio: next });
        } else {
          const maxStroke = calLen > 0 ? (calLen / 1000) - 10 : 140.0;
          const next = Math.min(maxStroke, s.strokeLengthMm + 5);
          setStrokeLengthMm(next);
          if (isRunning) startPattern({ strokeLengthMm: next });
        }
        return;
      }

      // ── Intensity +/- (= and -) ───────────────────────────────────────────
      if (e.key === "=" || e.key === "+") {
        e.preventDefault();
        const next = Math.min(100, s.intensityPct + 10);
        setIntensityPct(next);
        sendCommand("set_intensity", { intensity: next / 100.0 });
        return;
      }
      if (e.key === "-" && !e.shiftKey) {
        e.preventDefault();
        const next = Math.max(10, s.intensityPct - 10);
        setIntensityPct(next);
        sendCommand("set_intensity", { intensity: next / 100.0 });
        return;
      }

      // ── Safety Force +/- (] and [) ────────────────────────────────────────
      if (e.key === "]") {
        e.preventDefault();
        const next = Math.min(60, s.safetyForceN + 5);
        setSafetyForceN(next);
        sendCommand("set_safety_limit", { limit_mN: Math.round(next * 1000) });
        return;
      }
      if (e.key === "[") {
        e.preventDefault();
        const next = Math.max(5, s.safetyForceN - 5);
        setSafetyForceN(next);
        sendCommand("set_safety_limit", { limit_mN: Math.round(next * 1000) });
        return;
      }

      // ── Preset Slots 1-5 (Ctrl+1-5 to save, 1-5 to recall) ───────────────
      if (/^[1-5]$/.test(e.key)) {
        e.preventDefault();
        const slotIdx = parseInt(e.key) - 1;
        if (e.ctrlKey) {
          const name = window.prompt(`Name for preset ${slotIdx + 1}:`,
            presets[slotIdx]?.name || "");
          if (name !== null) savePreset(slotIdx, name);
        } else if (presets[slotIdx]) {
          const p = presets[slotIdx];
          setActivePresetSlot(slotIdx);
          const pName   = p.pattern_name     || "Wave";
          const pFreq   = p.frequency_hz     || 1.0;
          const pStroke = p.stroke_length_mm || 50.0;
          const pRatio  = p.rod_ratio        || 2.5;
          const pEsc    = p.escalate_duration_s || 300.0;
          const pEdge   = p.edge_period_s    || 60.0;
          const pInt    = p.intensity_pct    || 50.0;
          setFrequencyHz(pFreq);
          setStrokeLengthMm(pStroke);
          setRodRatio(pRatio);
          setEscalateDurationS(pEsc);
          setEdgePeriodS(pEdge);
          setIntensityPct(pInt);
          if (isRunning) {
            startPattern({
              patternName: pName, frequencyHz: pFreq, strokeLengthMm: pStroke,
              rodRatio: pRatio, escalateDurationS: pEsc, edgePeriodS: pEdge,
            });
            sendCommand("set_intensity", { intensity: pInt / 100.0 });
          }
        }
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presets, savePreset]);
}
