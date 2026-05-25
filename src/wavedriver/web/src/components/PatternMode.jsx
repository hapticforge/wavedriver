const PATTERNS = [
  { value: 'Wave',      label: 'Wave',      desc: 'Smooth sinusoidal reciprocating motion.' },
  { value: 'Realistic', label: 'Realistic', desc: 'Slider-crank kinematics — extend is faster than retract.' },
  { value: 'Thrust',    label: 'Thrust',    desc: 'Slow retract, rapid extend, brief hold at full depth.' },
  { value: 'Pulse',     label: 'Pulse',     desc: 'Four quick strokes then a full rest pause.' },
  { value: 'Tease',     label: 'Tease',     desc: 'Four incommensurable frequencies — non-repeating pattern.' },
  { value: 'Depth',     label: 'Depth',     desc: 'Penetration depth oscillates slowly between shallow and full.' },
  { value: 'Adaptive',  label: 'Adaptive',  desc: 'Responds in real time to live force feedback from the actuator.' },
];

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

export function PatternMode({
  patternName, setPatternName,
  rodRatio, setRodRatio,
  depthPeriodS, setDepthPeriodS,
  adaptiveMode, setAdaptiveMode,
  adaptiveSensitivity, setAdaptiveSensitivity,
}) {
  const active = PATTERNS.find(p => p.value === patternName) || PATTERNS[0];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      {/* Pattern pill row */}
      <div className="pattern-pills">
        {PATTERNS.map(p => (
          <button
            key={p.value}
            className={`pattern-pill${patternName === p.value ? ' active' : ''}`}
            onClick={() => setPatternName(p.value)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Pattern description */}
      <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>
        {active.desc}
      </p>

      {/* Pattern-specific parameters — only shown when relevant */}
      {patternName === 'Realistic' && (
        <div className="slider-row">
          <div className="slider-header">
            <span className="slider-title">Rod Ratio</span>
            <span className="slider-value-display">{rodRatio.toFixed(1)}×</span>
          </div>
          <div className="slider-body">
            {[2.5, 3.5, 5.0].map(val => (
              <button
                key={val}
                className={`btn ${rodRatio === val ? 'btn-primary' : 'btn-secondary'}`}
                style={{ flex: 1, padding: '8px' }}
                onClick={() => setRodRatio(val)}
              >
                {val.toFixed(1)}×
              </button>
            ))}
          </div>
        </div>
      )}

      {patternName === 'Depth' && (
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

      {patternName === 'Adaptive' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div className="slider-row">
            <div className="slider-header">
              <span className="slider-title">Adaptive Mode</span>
              <span className="slider-value-display">{adaptiveMode === 'ease' ? 'Auto-Ease' : 'Give & Take'}</span>
            </div>
            <div className="slider-body">
              <button
                className={`btn ${adaptiveMode === 'ease' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ flex: 1, padding: '8px' }}
                onClick={() => setAdaptiveMode('ease')}
              >
                Auto-Ease
              </button>
              <button
                className={`btn ${adaptiveMode === 'give_and_take' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ flex: 1, padding: '8px' }}
                onClick={() => setAdaptiveMode('give_and_take')}
              >
                Give &amp; Take
              </button>
            </div>
          </div>
          <SliderRow
            title="Force Sensitivity"
            value={adaptiveSensitivity}
            display={`${adaptiveSensitivity.toFixed(1)}×`}
            min={0.5} max={3.0} step={0.1}
            onChange={setAdaptiveSensitivity}
            onDecrement={() => setAdaptiveSensitivity(s => Math.max(0.5, Math.round((s - 0.1) * 10) / 10))}
            onIncrement={() => setAdaptiveSensitivity(s => Math.min(3.0, Math.round((s + 0.1) * 10) / 10))}
          />
        </div>
      )}
    </div>
  );
}
