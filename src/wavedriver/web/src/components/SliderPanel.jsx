import { useState } from 'react';
import { Sliders, ChevronDown, ChevronRight, ShieldAlert, Sparkles } from 'lucide-react';

function SliderRow({ title, value, display, min, max, step, onChange, onDecrement, onIncrement, extra }) {
  return (
    <div className="slider-row">
      <div className="slider-header">
        <span className="slider-title">{title}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {extra}
          <span className="slider-value-display">{display}</span>
        </div>
      </div>
      <div className="slider-body">
        <button className="slider-btn" onClick={onDecrement}>−</button>
        <input
          type="range"
          className="custom-slider"
          min={min} max={max} step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
        />
        <button className="slider-btn" onClick={onIncrement}>+</button>
      </div>
    </div>
  );
}

function BpmInput({ frequencyHz, onFrequencyChange }) {
  const [editing, setEditing] = useState(false);
  const [bpmStr, setBpmStr]   = useState("");
  const bpm = Math.round(frequencyHz * 60);

  if (editing) {
    return (
      <input
        className="bpm-input"
        type="number"
        autoFocus
        value={bpmStr}
        placeholder={bpm}
        min={6} max={240}
        onChange={e => setBpmStr(e.target.value)}
        onBlur={() => {
          const v = parseInt(bpmStr, 10);
          if (!isNaN(v) && v >= 6 && v <= 240) {
            onFrequencyChange(Math.round((v / 60) * 10) / 10);
          }
          setEditing(false);
          setBpmStr("");
        }}
        onKeyDown={e => {
          if (e.key === "Enter") e.target.blur();
          if (e.key === "Escape") { setEditing(false); setBpmStr(""); }
        }}
      />
    );
  }
  return (
    <span
      className="bpm-badge"
      onClick={() => { setBpmStr(String(bpm)); setEditing(true); }}
      title="Click to enter BPM, or press T to tap the beat"
    >
      {bpm} BPM
    </span>
  );
}

/**
 * Parameter adjustment sliders.
 */
export function SliderPanel({
  patternName,
  frequencyHz, setFrequencyHz,
  strokeLengthMm, setStrokeLengthMm,
  intensityPct,
  rodRatio, setRodRatio,
  escalateDurationS, setEscalateDurationS,
  edgePeriodS, setEdgePeriodS,
  depthPeriodS, setDepthPeriodS,
  adaptiveMode, setAdaptiveMode,
  adaptiveSensitivity, setAdaptiveSensitivity,
  shuffleEnabled, setShuffleEnabled,
  shuffleDwellS, setShuffleDwellS,
  shuffleMinFreq, setShuffleMinFreq,
  shuffleMaxFreq, setShuffleMaxFreq,
  shuffleMinStroke, setShuffleMinStroke,
  shuffleMaxStroke, setShuffleMaxStroke,
  safetyForceN,
  maxSessionS, setMaxSessionS,
  calibratedLength,
  onIntensityChange,
  onSafetyChange,
  onMaxSessionChange,
}) {
  const [safetyOpen, setSafetyOpen] = useState(false);
  const [shuffleOpen, setShuffleOpen] = useState(false);
  const maxStrokeMm = calibratedLength > 0 ? Math.floor(calibratedLength / 1000) - 10 : 140;
  const sessionDisplay = maxSessionS === 0
    ? "Off"
    : `${Math.floor(maxSessionS / 60)}:${String(maxSessionS % 60).padStart(2, '0')}`;

  return (
    <div className="control-card">
      <h3 className="section-title" style={{ marginBottom: 0 }}>
        <Sliders size={14} /> Parameter Scaling
      </h3>

      <div className="parameter-sliders">
        <SliderRow
          title="Stimulation Speed"
          value={frequencyHz}
          display={`${frequencyHz.toFixed(1)} Hz`}
          min={0.1} max={4.0} step={0.1}
          onChange={setFrequencyHz}
          onDecrement={() => setFrequencyHz(f => Math.max(0.1, Math.round((f - 0.1) * 10) / 10))}
          onIncrement={() => setFrequencyHz(f => Math.min(4.0, Math.round((f + 0.1) * 10) / 10))}
          extra={<BpmInput frequencyHz={frequencyHz} onFrequencyChange={setFrequencyHz} />}
        />

        <SliderRow
          title="Stroke Amplitude"
          value={strokeLengthMm}
          display={`${strokeLengthMm} mm`}
          min={10} max={maxStrokeMm} step={5}
          onChange={v => setStrokeLengthMm(Math.round(v))}
          onDecrement={() => setStrokeLengthMm(s => Math.max(10, s - 5))}
          onIncrement={() => setStrokeLengthMm(s => Math.min(maxStrokeMm, s + 5))}
        />

        <SliderRow
          title="Intensity Scale"
          value={intensityPct}
          display={`${intensityPct}%`}
          min={10} max={100} step={10}
          onChange={v => onIntensityChange(Math.round(v))}
          onDecrement={() => onIntensityChange(intensityPct - 10)}
          onIncrement={() => onIntensityChange(intensityPct + 10)}
        />

        {/* Collapsible safety section */}
        <div className="safety-section">
          <button
            className="safety-section-toggle"
            onClick={() => setSafetyOpen(v => !v)}
          >
            <ShieldAlert size={13} />
            <span>Safety &amp; Session</span>
            <span className="safety-section-summary">
              {safetyForceN} N · {sessionDisplay === "Off" ? "no timer" : sessionDisplay}
            </span>
            {safetyOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
          {safetyOpen && (
            <div className="safety-section-body">
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
          )}
        </div>

        {/* Surprise / Shuffle bounds section */}
        <div className="safety-section">
          <button
            className="safety-section-toggle"
            onClick={() => setShuffleOpen(v => !v)}
          >
            <Sparkles size={13} />
            <span>Surprise / Shuffle bounds</span>
            <span className="safety-section-summary">
              {shuffleEnabled ? "Active" : "Disabled"}
            </span>
            {shuffleOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
          {shuffleOpen && (
            <div className="safety-section-body">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <input
                  type="checkbox"
                  id="surprise-active"
                  checked={shuffleEnabled}
                  onChange={(e) => setShuffleEnabled(e.target.checked)}
                />
                <label htmlFor="surprise-active" className="slider-title" style={{ cursor: 'pointer' }}>Enable Surprise Mode</label>
              </div>
              <SliderRow
                title="Shuffle Dwell Time"
                value={shuffleDwellS}
                display={`${shuffleDwellS} s`}
                min={10} max={300} step={10}
                onChange={v => setShuffleDwellS(Math.round(v))}
                onDecrement={() => setShuffleDwellS(s => Math.max(10, s - 10))}
                onIncrement={() => setShuffleDwellS(s => Math.min(300, s + 10))}
              />
              <SliderRow
                title="Min Speed Bounds"
                value={shuffleMinFreq}
                display={`${shuffleMinFreq.toFixed(1)} Hz`}
                min={0.1} max={shuffleMaxFreq} step={0.1}
                onChange={setShuffleMinFreq}
                onDecrement={() => setShuffleMinFreq(f => Math.max(0.1, Math.round((f - 0.1) * 10) / 10))}
                onIncrement={() => setShuffleMinFreq(f => Math.min(shuffleMaxFreq, Math.round((f + 0.1) * 10) / 10))}
              />
              <SliderRow
                title="Max Speed Bounds"
                value={shuffleMaxFreq}
                display={`${shuffleMaxFreq.toFixed(1)} Hz`}
                min={shuffleMinFreq} max={4.0} step={0.1}
                onChange={setShuffleMaxFreq}
                onDecrement={() => setShuffleMaxFreq(f => Math.max(shuffleMinFreq, Math.round((f - 0.1) * 10) / 10))}
                onIncrement={() => setShuffleMaxFreq(f => Math.min(4.0, Math.round((f + 0.1) * 10) / 10))}
              />
            </div>
          )}
        </div>

        {/* Pattern-specific extra controls */}
        {patternName === "Realistic" && (
          <div className="slider-row">
            <div className="slider-header">
              <span className="slider-title">Realistic Rod Ratio</span>
              <span className="slider-value-display">{rodRatio.toFixed(1)}×</span>
            </div>
            <div className="slider-body">
              {[2.5, 3.5, 5.0].map(val => (
                <button
                  key={val}
                  className={`btn ${rodRatio === val ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ padding: '6px 12px', flex: 1 }}
                  onClick={() => setRodRatio(val)}
                >
                  {val.toFixed(1)}×
                </button>
              ))}
            </div>
          </div>
        )}

        {patternName === "Adaptive" && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div className="slider-row">
              <div className="slider-header">
                <span className="slider-title">Adaptive Mode</span>
                <span className="slider-value-display">{adaptiveMode === "ease" ? "Auto-Ease" : "Give & Take"}</span>
              </div>
              <div className="slider-body">
                <button
                  className={`btn ${adaptiveMode === 'ease' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ padding: '6px 12px', flex: 1 }}
                  onClick={() => setAdaptiveMode('ease')}
                >
                  Auto-Ease
                </button>
                <button
                  className={`btn ${adaptiveMode === 'give_and_take' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ padding: '6px 12px', flex: 1 }}
                  onClick={() => setAdaptiveMode('give_and_take')}
                >
                  Give &amp; Take
                </button>
              </div>
            </div>
            <SliderRow
              title="Force Sensitivity"
              value={adaptiveSensitivity}
              display={`${adaptiveSensitivity.toFixed(1)}x`}
              min={0.5} max={3.0} step={0.1}
              onChange={setAdaptiveSensitivity}
              onDecrement={() => setAdaptiveSensitivity(s => Math.max(0.5, Math.round((s - 0.1) * 10) / 10))}
              onIncrement={() => setAdaptiveSensitivity(s => Math.min(3.0, Math.round((s + 0.1) * 10) / 10))}
            />
          </div>
        )}

        {patternName === "Escalate" && (
          <SliderRow
            title="Escalation Duration"
            value={escalateDurationS}
            display={`${Math.round(escalateDurationS / 60)} min`}
            min={30} max={3600} step={30}
            onChange={v => setEscalateDurationS(Math.round(v))}
            onDecrement={() => setEscalateDurationS(s => Math.max(30, s - 30))}
            onIncrement={() => setEscalateDurationS(s => Math.min(3600, s + 30))}
          />
        )}

        {patternName === "Edge" && (
          <SliderRow
            title="Edging Cycle Period"
            value={edgePeriodS}
            display={`${edgePeriodS} s`}
            min={10} max={600} step={10}
            onChange={v => setEdgePeriodS(Math.round(v))}
            onDecrement={() => setEdgePeriodS(s => Math.max(10, s - 10))}
            onIncrement={() => setEdgePeriodS(s => Math.min(600, s + 10))}
          />
        )}

        {patternName === "Depth" && (
          <SliderRow
            title="Depth Cycle Period"
            value={depthPeriodS}
            display={`${depthPeriodS} s`}
            min={5} max={120} step={5}
            onChange={v => setDepthPeriodS(Math.round(v))}
            onDecrement={() => setDepthPeriodS(s => Math.max(5, s - 5))}
            onIncrement={() => setDepthPeriodS(s => Math.min(120, s + 5))}
          />
        )}
      </div>
    </div>
  );
}
