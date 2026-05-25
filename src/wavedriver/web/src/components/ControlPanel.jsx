import { Play, Pause, Square, RefreshCw, FolderOpen, Save, Star, Download, Upload, Shuffle } from 'lucide-react';

const PATTERN_OPTIONS = [
  { value: "Wave",      label: "Wave",      desc: "Smooth sinusoidal motion, great for warming up" },
  { value: "Realistic", label: "Realistic", desc: "Slider-crank kinematics for a natural asymmetric feel" },
  { value: "Thrust",    label: "Thrust",    desc: "Deep rhythmic strokes with a fast return" },
  { value: "Pulse",     label: "Pulse",     desc: "Rapid burst clusters with rest periods" },
  { value: "Tease",     label: "Tease",     desc: "Playful varied depth and speed changes" },
  { value: "Escalate",  label: "Escalate",  desc: "Gradually builds in speed over the session" },
  { value: "Edge",      label: "Edge",      desc: "Climbs toward peak then drops back repeatedly" },
  { value: "Depth",     label: "Depth",     desc: "Slowly varying penetration depth — shallow to deep on a long cycle" },
];

function exportPresets(presets) {
  const obj = {};
  presets.forEach((p, i) => { if (p) obj[i.toString()] = p; });
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = 'wavedriver-presets.json';
  a.click();
  URL.revokeObjectURL(url);
}

function importPresetsFromFile(onImport) {
  const input    = document.createElement('input');
  input.type     = 'file';
  input.accept   = '.json';
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      onImport(data);
    } catch {
      alert("Invalid preset file.");
    }
  };
  input.click();
}

/**
 * Pattern selector, action buttons, preset slots with names, shuffle mode,
 * and export/import.
 */
export function ControlPanel({
  patternName, setPatternName,
  telemetry,
  presets, activePresetSlot,
  defaultPresetSlot, setDefaultPresetSlot,
  shuffleEnabled, setShuffleEnabled,
  shuffleDwellS, setShuffleDwellS,
  onStart, onStop, onPauseToggle, onCalibrate, onEstop, onClearEstop,
  onPresetSave, onPresetRecall, onImportPresets,
}) {
  const currentPattern = PATTERN_OPTIONS.find(o => o.value === patternName);
  const isRunning = telemetry.state_enum === "RUNNING";
  const isPaused  = !!telemetry.paused;

  return (
    <div className="control-card">
      <div className="input-group">
        <label className="input-label">Active Waveform</label>
        <select
          className="select-widget"
          value={patternName}
          onChange={(e) => setPatternName(e.target.value)}
        >
          {PATTERN_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value} title={opt.desc}>
              {opt.label} — {opt.desc}
            </option>
          ))}
        </select>
        {currentPattern && (
          <p className="pattern-desc">{currentPattern.desc}</p>
        )}
      </div>

      {/* Shuffle mode */}
      <div className="shuffle-row">
        <button
          className={`btn ${shuffleEnabled ? 'btn-primary' : 'btn-secondary'} shuffle-btn`}
          onClick={() => setShuffleEnabled(v => !v)}
          title="Cycle through patterns automatically"
        >
          <Shuffle size={13} />
          {shuffleEnabled ? "Shuffle On" : "Shuffle"}
        </button>
        {shuffleEnabled && isRunning && (
          <span className="shuffle-active-badge" title="Shuffle is cycling patterns">
            <span className="shuffle-active-dot" />
            cycling
          </span>
        )}
        {shuffleEnabled && (
          <select
            className="select-widget shuffle-dwell"
            value={shuffleDwellS}
            onChange={e => setShuffleDwellS(Number(e.target.value))}
          >
            {[30, 60, 120, 180, 300].map(s => (
              <option key={s} value={s}>{s < 60 ? `${s}s` : `${s/60} min`}</option>
            ))}
          </select>
        )}
      </div>

      <div className="button-actions-row">
        {isRunning ? (
          <div className="button-inner-row">
            <button className="btn btn-secondary" onClick={onPauseToggle} title={isPaused ? "Resume (P)" : "Pause (P)"}>
              {isPaused
                ? <><Play size={15} fill="currentColor" /> Resume</>
                : <><Pause size={15} fill="currentColor" /> Pause</>}
            </button>
            <button className="btn btn-secondary" onClick={onStop}>
              <Square size={15} fill="currentColor" /> Stop
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={onStart} title="Start (Enter)">
            <Play size={16} fill="currentColor" /> Start Stimulation
          </button>
        )}

        {!isRunning && (
          <div className="button-inner-row">
            <button className="btn btn-secondary" onClick={onStop}>
              <Square size={16} fill="currentColor" /> Stop
            </button>
            <button className="btn btn-secondary" onClick={onCalibrate}>
              <RefreshCw size={16} /> Calibrate
            </button>
          </div>
        )}

        {isRunning && (
          <button className="btn btn-secondary" onClick={onCalibrate}>
            <RefreshCw size={16} /> Calibrate
          </button>
        )}

        {telemetry.state_enum === "ESTOP" ? (
          <button className="btn btn-primary" onClick={onClearEstop}>
            Resume — Clear Emergency Stop
          </button>
        ) : (
          <button className="btn btn-danger btn-estop" onClick={onEstop}>
            EMERGENCY STOP [Space]
          </button>
        )}
      </div>

      <div className="input-group" style={{ marginTop: 'auto' }}>
        <label className="input-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Preset Slots (1–5)</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              className="btn btn-secondary"
              style={{ padding: '2px 7px', fontSize: '0.7rem', height: '20px' }}
              onClick={() => exportPresets(presets)}
              title="Export presets to JSON"
            >
              <Download size={11} />
            </button>
            <button
              className="btn btn-secondary"
              style={{ padding: '2px 7px', fontSize: '0.7rem', height: '20px' }}
              onClick={() => importPresetsFromFile(onImportPresets)}
              title="Import presets from JSON"
            >
              <Upload size={11} />
            </button>
            <span style={{ fontSize: '0.65rem', textTransform: 'none', opacity: 0.6, lineHeight: '20px' }}>
              Ctrl+Click to Save
            </span>
          </div>
        </label>
        {presets.every(p => !p) && (
          <p className="preset-empty-hint">
            No presets saved yet. Ctrl+Click a slot (or Ctrl+1–5) to save current settings.
          </p>
        )}
        <div className="presets-grid">
          {[0, 1, 2, 3, 4].map(idx => {
            const preset    = presets[idx];
            const isDefault = defaultPresetSlot === idx;
            return (
              <div key={idx} className="preset-slot">
                <button
                  className={`preset-btn ${activePresetSlot === idx ? 'active' : ''}`}
                  onClick={(e) => e.ctrlKey ? onPresetSave(idx) : onPresetRecall(idx)}
                  title={preset
                    ? `${preset.name || `Preset ${idx + 1}`}: ${preset.pattern_name} — ${preset.frequency_hz?.toFixed(1)} Hz, ${preset.stroke_length_mm} mm\nCtrl+Click to overwrite`
                    : `Preset ${idx + 1} (empty) — Ctrl+Click to save current settings`}
                >
                  {preset ? <Save size={14} /> : <FolderOpen size={14} />}
                  <span className="preset-btn-num">{idx + 1}</span>
                  {preset && (
                    <span className="preset-btn-label">
                      {preset.name || preset.pattern_name}
                    </span>
                  )}
                </button>
                {preset && (
                  <button
                    className={`star-btn ${isDefault ? 'star-active' : ''}`}
                    onClick={() => setDefaultPresetSlot(isDefault ? null : idx)}
                    title={isDefault ? "Remove as startup default" : "Set as startup default"}
                  >
                    <Star size={10} fill={isDefault ? 'currentColor' : 'none'} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
