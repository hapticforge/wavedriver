import { useState } from 'react';
import { X, FolderOpen, Save, Star, Download, Upload, ClipboardCopy, Trash2, Shuffle } from 'lucide-react';

function SliderRow({ title, value, display, min, max, step, onChange, onDecrement, onIncrement }) {
  return (
    <div className="slider-row">
      <div className="slider-header">
        <span className="slider-title">{title}</span>
        <span className="slider-value-display">{display}</span>
      </div>
      <div className="slider-body">
        <button className="slider-btn" onClick={onDecrement}>−</button>
        <input
          type="range"
          className="custom-slider"
          min={min} max={max} step={step}
          value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
        />
        <button className="slider-btn" onClick={onIncrement}>+</button>
      </div>
    </div>
  );
}

function exportPresets(presets) {
  const obj = {};
  presets.forEach((p, i) => { if (p) obj[i.toString()] = p; });
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = 'wavedriver-presets.json'; a.click();
  URL.revokeObjectURL(url);
}

function importPresetsFromFile(onImport) {
  const input = document.createElement('input');
  input.type = 'file'; input.accept = '.json';
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      onImport(JSON.parse(text));
    } catch {
      alert('Invalid preset file.');
    }
  };
  input.click();
}

export function AdvancedDrawer({
  onClose,
  telemetry,
  // Sliders
  intensityPct, onIntensityChange,
  safetyForceN, onSafetyChange,
  maxSessionS,  onMaxSessionChange,
  // Presets
  presets, activePresetSlot,
  defaultPresetSlot, setDefaultPresetSlot,
  onPresetSave, onPresetRecall, onImportPresets,
  // Shuffle
  shuffleEnabled, setShuffleEnabled,
  shuffleDwellS, setShuffleDwellS,
  shuffleMinFreq, setShuffleMinFreq,
  shuffleMaxFreq, setShuffleMaxFreq,
  // History
  historyEnabled, onHistoryEnabledChange,
  onClearHistory,
  onToggleHistory, showHistory,
  // Activity log
  showActivityLog, onToggleActivityLog,
}) {
  const [diagnosticsText, setDiagnosticsText] = useState(null);

  const sessionDisplay = maxSessionS === 0
    ? 'Off'
    : `${Math.floor(maxSessionS / 60)}:${String(maxSessionS % 60).padStart(2, '0')}`;

  const handleExportDiagnostics = async () => {
    if (!window.pywebview?.api?.get_diagnostics) return;
    const data = await window.pywebview.api.get_diagnostics();
    setDiagnosticsText(JSON.stringify(data, null, 2));
  };

  return (
    <div className="advanced-overlay" onClick={onClose}>
      <div className="advanced-drawer" onClick={e => e.stopPropagation()}>
        <div className="advanced-drawer-header">
          <span style={{ fontWeight: 800, fontSize: '0.9rem', color: 'var(--text-bright)' }}>Advanced Settings</span>
          <button className="btn btn-secondary icon-btn" style={{ padding: '4px 8px' }} onClick={onClose}>
            <X size={14} />
          </button>
        </div>

        <div className="advanced-drawer-body">
          {/* ── Levels ────────────────────────────────────────────── */}
          <div className="advanced-section">
            <div className="advanced-section-title">Levels</div>
            <SliderRow
              title="Intensity"
              value={intensityPct}
              display={`${intensityPct}%`}
              min={10} max={100} step={10}
              onChange={v => onIntensityChange(Math.round(v))}
              onDecrement={() => onIntensityChange(intensityPct - 10)}
              onIncrement={() => onIntensityChange(intensityPct + 10)}
            />
            <SliderRow
              title="Safety Force Limit"
              value={safetyForceN}
              display={`${safetyForceN} N`}
              min={5} max={60} step={5}
              onChange={v => onSafetyChange(Math.round(v))}
              onDecrement={() => onSafetyChange(safetyForceN - 5)}
              onIncrement={() => onSafetyChange(safetyForceN + 5)}
            />
            <SliderRow
              title="Session Auto-Stop"
              value={maxSessionS}
              display={sessionDisplay}
              min={0} max={7200} step={300}
              onChange={v => onMaxSessionChange(Math.round(v))}
              onDecrement={() => onMaxSessionChange(Math.max(0, maxSessionS - 300))}
              onIncrement={() => onMaxSessionChange(Math.min(7200, maxSessionS + 300))}
            />
          </div>

          {/* ── Presets ───────────────────────────────────────────── */}
          <div className="advanced-section">
            <div className="advanced-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Presets</span>
              <div style={{ display: 'flex', gap: '6px' }}>
                <button className="btn btn-secondary" style={{ padding: '2px 7px', fontSize: '0.7rem', height: '20px' }}
                  onClick={() => exportPresets(presets)} title="Export presets">
                  <Download size={11} />
                </button>
                <button className="btn btn-secondary" style={{ padding: '2px 7px', fontSize: '0.7rem', height: '20px' }}
                  onClick={() => importPresetsFromFile(onImportPresets)} title="Import presets">
                  <Upload size={11} />
                </button>
              </div>
            </div>
            <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', margin: 0 }}>Click to recall · Ctrl+Click to save</p>
            <div className="presets-grid">
              {[0, 1, 2, 3, 4].map(idx => {
                const preset    = presets[idx];
                const isDefault = defaultPresetSlot === idx;
                return (
                  <div key={idx} className="preset-slot">
                    <button
                      className={`preset-btn ${activePresetSlot === idx ? 'active' : ''}`}
                      onClick={e => e.ctrlKey ? onPresetSave(idx) : onPresetRecall(idx)}
                      title={preset
                        ? `${preset.name || `Preset ${idx + 1}`}: ${preset.pattern_name} — ${preset.frequency_hz?.toFixed(1)} Hz, ${preset.stroke_length_mm} mm\nCtrl+Click to overwrite`
                        : `Preset ${idx + 1} (empty) — Ctrl+Click to save`}
                    >
                      {preset ? <Save size={14} /> : <FolderOpen size={14} />}
                      <span className="preset-btn-num">{idx + 1}</span>
                      {preset && <span className="preset-btn-label">{preset.name || preset.pattern_name}</span>}
                    </button>
                    {preset && (
                      <button
                        className={`star-btn ${isDefault ? 'star-active' : ''}`}
                        onClick={() => setDefaultPresetSlot(isDefault ? null : idx)}
                        title={isDefault ? 'Remove startup default' : 'Set as startup default'}
                      >
                        <Star size={10} fill={isDefault ? 'currentColor' : 'none'} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── Surprise / Shuffle ───────────────────────────────── */}
          <div className="advanced-section">
            <div className="advanced-section-title">Surprise / Shuffle</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                className={`btn ${shuffleEnabled ? 'btn-primary' : 'btn-secondary'} shuffle-btn`}
                style={{ fontSize: '0.82rem', padding: '6px 12px' }}
                onClick={() => setShuffleEnabled(v => !v)}
              >
                <Shuffle size={12} />
                {shuffleEnabled ? 'Shuffle On' : 'Shuffle Off'}
              </button>
              {shuffleEnabled && (
                <select
                  className="select-widget"
                  value={shuffleDwellS}
                  onChange={e => setShuffleDwellS(Number(e.target.value))}
                  style={{ width: 'auto', flex: 1 }}
                >
                  {[30, 60, 120, 180, 300].map(s => (
                    <option key={s} value={s}>{s < 60 ? `${s}s` : `${s / 60} min`}</option>
                  ))}
                </select>
              )}
            </div>
            {shuffleEnabled && (
              <>
                <SliderRow
                  title="Min Speed"
                  value={shuffleMinFreq}
                  display={`${shuffleMinFreq.toFixed(1)} Hz`}
                  min={0.1} max={shuffleMaxFreq} step={0.1}
                  onChange={setShuffleMinFreq}
                  onDecrement={() => setShuffleMinFreq(f => Math.max(0.1, Math.round((f - 0.1) * 10) / 10))}
                  onIncrement={() => setShuffleMinFreq(f => Math.min(shuffleMaxFreq, Math.round((f + 0.1) * 10) / 10))}
                />
                <SliderRow
                  title="Max Speed"
                  value={shuffleMaxFreq}
                  display={`${shuffleMaxFreq.toFixed(1)} Hz`}
                  min={shuffleMinFreq} max={4.0} step={0.1}
                  onChange={setShuffleMaxFreq}
                  onDecrement={() => setShuffleMaxFreq(f => Math.max(shuffleMinFreq, Math.round((f - 0.1) * 10) / 10))}
                  onIncrement={() => setShuffleMaxFreq(f => Math.min(4.0, Math.round((f + 0.1) * 10) / 10))}
                />
              </>
            )}
          </div>

          {/* ── Session & History ─────────────────────────────────── */}
          <div className="advanced-section">
            <div className="advanced-section-title">Privacy & History</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="checkbox"
                id="adv-history-enabled"
                checked={historyEnabled}
                onChange={e => onHistoryEnabledChange(e.target.checked)}
              />
              <label htmlFor="adv-history-enabled" style={{ fontSize: '0.82rem', cursor: 'pointer', color: 'var(--text-normal)' }}>
                Record session history
              </label>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-secondary"
                style={{ flex: 1, fontSize: '0.8rem', padding: '6px' }}
                onClick={onToggleHistory}
              >
                {showHistory ? 'Hide History' : 'View History'}
              </button>
              <button
                className="btn btn-secondary"
                style={{ fontSize: '0.8rem', padding: '6px 10px', color: 'var(--color-danger)', borderColor: 'rgba(239,68,68,0.2)' }}
                onClick={() => {
                  if (window.confirm('Clear all session history? This cannot be undone.')) {
                    onClearHistory();
                  }
                }}
                title="Clear all history"
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>

          {/* ── Telemetry ─────────────────────────────────────────── */}
          <div className="advanced-section">
            <div className="advanced-section-title">Telemetry</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              {[
                { label: 'Force',       value: `${(Math.abs(telemetry.force_mN) / 1000).toFixed(1)} N` },
                { label: 'Temperature', value: `${telemetry.temperature_C} °C` },
                { label: 'Voltage',     value: `${(telemetry.voltage_mV / 1000).toFixed(1)} V` },
                { label: 'Session',     value: (() => {
                  const s = telemetry.session_elapsed_s || 0;
                  return `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
                })() },
              ].map(({ label, value }) => (
                <div key={label} style={{ background: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '10px 12px' }}>
                  <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '4px' }}>{label}</div>
                  <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-bright)' }}>{value}</div>
                </div>
              ))}
            </div>
            <button
              className="btn btn-secondary"
              style={{ fontSize: '0.8rem', padding: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}
              onClick={onToggleActivityLog}
            >
              {showActivityLog ? 'Hide Activity Log' : 'View Activity Log'}
            </button>
          </div>

          {/* ── Diagnostics ───────────────────────────────────────── */}
          <div className="advanced-section">
            <div className="advanced-section-title">Diagnostics</div>
            <button
              className="btn btn-secondary"
              style={{ fontSize: '0.8rem', padding: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}
              onClick={handleExportDiagnostics}
            >
              <ClipboardCopy size={13} />
              Export Diagnostics
            </button>
            {diagnosticsText && (
              <textarea
                readOnly
                value={diagnosticsText}
                style={{
                  width: '100%', height: '140px', resize: 'vertical',
                  background: 'rgba(0,0,0,0.4)', color: '#a0d4e8',
                  border: '1px solid rgba(255,255,255,0.1)', borderRadius: '4px',
                  fontFamily: 'monospace', fontSize: '10px', padding: '8px',
                }}
                onClick={e => e.target.select()}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
