import { Sliders } from 'lucide-react';
import { WaveformCanvas } from './WaveformCanvas.jsx';

function formatTime(secs) {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

/**
 * Telemetry cards and shaft displacement visualizer.
 *
 * Session card shows a countdown when a session limit is active, otherwise shows elapsed.
 * Force card uses colour-coded percentage of the safety limit.
 * Temperature card flashes a warning colour when approaching the E-stop threshold.
 */
export function TelemetryPanel({ telemetry, calibratedLength, frequencyHz, isRunning, isPaused }) {
  const maxCalMm           = calibratedLength > 0 ? Math.round(calibratedLength / 1000) : 150;
  const currentPosMm       = (telemetry.position_um / 1000).toFixed(1);
  const positionPercentage = calibratedLength > 0
    ? Math.max(0, Math.min(100, (telemetry.position_um / calibratedLength) * 100))
    : 0;

  const limitmN      = telemetry.max_feedback_force_mN || 55000;
  const forceAbs     = Math.abs(telemetry.force_mN);
  const resistancePct = limitmN > 0 ? Math.min(100, Math.round((forceAbs / limitmN) * 100)) : 0;
  const forceN       = (forceAbs / 1000).toFixed(1);
  const forceClass   = resistancePct >= 90 ? 'text-danger'
                     : resistancePct >= 70 ? 'text-warning'
                     : 'text-success';

  const tempClass    = telemetry.temp_warning ? 'text-warning animate-pulse' : '';

  // Session timer: show remaining countdown if a limit is active, else elapsed
  const hasLimit      = telemetry.session_remaining_s !== null && telemetry.session_remaining_s !== undefined;
  const sessionValue  = hasLimit ? telemetry.session_remaining_s : telemetry.session_elapsed_s;
  const sessionLabel  = hasLimit ? "Session Remaining" : "Session Timer";
  const sessionUnit   = hasLimit ? "left" : "m:s";
  const sessionClass  = hasLimit && telemetry.session_remaining_s < 60 ? 'text-warning animate-pulse' : '';

  return (
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
          <span className="card-header-lbl">Feedback Force</span>
          <div className="card-body-row">
            <span className={`card-value ${forceClass}`}>{forceN}</span>
            <span className="card-unit">N</span>
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            {resistancePct}% of {(limitmN / 1000).toFixed(0)} N limit
          </div>
        </div>

        <div className="telemetry-card">
          <span className="card-header-lbl">Pattern Frequency</span>
          <div className="card-body-row">
            <span className="card-value text-purple">{frequencyHz.toFixed(1)}</span>
            <span className="card-unit">Hz</span>
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            {Math.round(frequencyHz * 60)} SPM
          </div>
        </div>

        <div className="telemetry-card">
          <span className="card-header-lbl">{sessionLabel}</span>
          <div className="card-body-row">
            <span className={`card-value ${sessionClass}`}>{formatTime(sessionValue)}</span>
            <span className="card-unit">{sessionUnit}</span>
          </div>
          {hasLimit && (
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              elapsed: {formatTime(telemetry.session_elapsed_s)}
            </div>
          )}
          {hasLimit && telemetry.session_remaining_s < 60 && (
            <div style={{ fontSize: '0.7rem', color: 'var(--color-warning)', marginTop: '4px', fontWeight: 'bold' }}>
              ⚠️ Auto-stopping soon!
            </div>
          )}
        </div>

        <div className="telemetry-card">
          <span className="card-header-lbl">Temperature</span>
          <div className="card-body-row">
            <span className={`card-value ${tempClass || 'text-bright'}`}>
              {telemetry.temperature_C}
            </span>
            <span className="card-unit">°C</span>
          </div>
          {telemetry.temp_warning && (
            <div style={{ fontSize: '0.7rem', color: 'var(--color-warning)', marginTop: '4px' }}>
              High — reduce intensity
            </div>
          )}
        </div>
      </div>

      {/* Shaft visualizer */}
      <div className="visualizer-card" style={{ marginTop: '16px' }}>
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

        {/* Live waveform history */}
        <div className="waveform-container">
          <WaveformCanvas
            positionUm={telemetry.position_um}
            calibratedLength={calibratedLength}
            isRunning={isRunning}
            isPaused={isPaused}
          />
        </div>
      </div>
    </div>
  );
}
