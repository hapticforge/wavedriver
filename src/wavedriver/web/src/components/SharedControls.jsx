import { Play, Square, RefreshCw, Zap } from 'lucide-react';
import { ArcControl } from './ArcControl.jsx';
import { WaveformCanvas } from './WaveformCanvas.jsx';

function getStateDot(stateEnum, softStopping) {
  if (stateEnum === 'ESTOP' || stateEnum === 'ERROR') return 'danger';
  if (stateEnum === 'RUNNING' && softStopping) return 'warning';
  if (stateEnum === 'RUNNING') return 'running';
  if (stateEnum?.startsWith('CALIBRATING_')) return 'warning';
  return 'idle';
}

export function SharedControls({
  activeMode,
  telemetry,
  frequencyHz, setFrequencyHz,
  strokeLengthMm, setStrokeLengthMm,
  calibratedLength,
  onStart, onStop, onCalibrate,
  onEstop, onClearEstop,
}) {
  const isVideoMode    = activeMode === 'video';
  const isAudioMode    = activeMode === 'audio';
  const stateEnum      = telemetry.state_enum;
  const isRunning      = stateEnum === 'RUNNING';
  const isSoftStopping = isRunning && !!telemetry.soft_stopping;
  const isEstop        = stateEnum === 'ESTOP';
  const isCalib        = stateEnum?.startsWith('CALIBRATING_');
  const dotClass       = getStateDot(stateEnum, isSoftStopping);
  const displayState   = isSoftStopping ? 'Stopping…' : (telemetry.state || '—');
  const maxStrokeMm  = calibratedLength > 0 ? Math.floor(calibratedLength / 1000) - 10 : 140;
  const bpm          = Math.round(frequencyHz * 60);

  return (
    <div className="shared-controls">
      {/* ── Primary action button ── */}
      {isEstop ? (
        <button className="primary-btn primary-btn--resume" onClick={onClearEstop}>
          <Play size={20} fill="currentColor" />
          Clear Emergency Stop
        </button>
      ) : isCalib ? (
        <button className="primary-btn primary-btn--calibrating" disabled>
          Calibrating…
        </button>
      ) : isRunning ? (
        <button
          className={`primary-btn ${isSoftStopping ? 'primary-btn--stopping' : 'primary-btn--stop'}`}
          onClick={onStop}
          disabled={isSoftStopping}
        >
          {isSoftStopping
            ? <><RefreshCw size={15} className="spin" /> Stopping…</>
            : <><Square size={15} fill="currentColor" /> Stop</>}
        </button>
      ) : (
        <div className="primary-btn-row">
          <button className="primary-btn primary-btn--start" style={{ flex: 1 }} onClick={onStart}>
            <Play size={20} fill="currentColor" /> Start
          </button>
          <button
            className="primary-btn primary-btn--calibrate"
            style={{ width: '52px', flex: 'none' }}
            onClick={onCalibrate}
            title="Calibrate (Z)"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      )}

      {/* ── Arc dials ── */}
      <div className="arc-dials-row">
        {!isVideoMode && !isAudioMode && (
          <>
            <ArcControl
              label="Speed"
              value={frequencyHz}
              min={0.1} max={4.0} step={0.1}
              unit="Hz"
              subLabel={`${bpm} BPM`}
              onChange={setFrequencyHz}
            />
            <div className="arc-divider" />
          </>
        )}
        <ArcControl
          label="Stroke"
          value={strokeLengthMm}
          min={10} max={maxStrokeMm} step={5}
          unit="mm"
          accentColor="#c362fc"
          glowColor="rgba(195,98,252,0.45)"
          onChange={v => setStrokeLengthMm(Math.round(v))}
        />
      </div>

      {/* ── Live waveform preview ── */}
      <div style={{ borderRadius: '8px', overflow: 'hidden', background: 'var(--bg-primary)', border: '1px solid var(--border-color)' }}>
        <WaveformCanvas
          positionUm={telemetry.position_um}
          calibratedLength={calibratedLength}
          isRunning={isRunning}
        />
      </div>

      {/* ── E-Stop + status ── */}
      <div className="status-estop-row">
        {isEstop ? (
          <button
            className="btn btn-secondary"
            style={{ padding: '5px 12px', fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-success)', borderColor: 'rgba(16,185,129,0.3)' }}
            onClick={onClearEstop}
          >
            Clear E-Stop (C)
          </button>
        ) : (
          <button className="btn-estop-compact" onClick={onEstop}>
            <Zap size={11} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
            E-Stop [Space]
          </button>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '10px' }}>
          <span className={`status-dot ${dotClass}`} />
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>{displayState}</span>
        </div>
        {telemetry.use_mock && (
          <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--accent-cyan)', fontWeight: 700, opacity: 0.7 }}>SIM</span>
        )}
      </div>
    </div>
  );
}
