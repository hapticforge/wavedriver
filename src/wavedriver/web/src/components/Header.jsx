import { Activity, Zap, LogOut, HelpCircle, Settings } from 'lucide-react';

function getStateClass(stateEnum, paused) {
  switch (stateEnum) {
    case 'RUNNING':
      return paused ? 'badge-state calibrating' : 'badge-state running';
    case 'CALIBRATING_RETRACT':
    case 'CALIBRATING_EXTEND':
    case 'CALIBRATING_CENTER':
      return 'badge-state calibrating';
    case 'ESTOP':
    case 'ERROR':
      return 'badge-state estop';
    default:
      return 'badge-state';
  }
}

function getDisplayState(telemetry) {
  if (telemetry.state_enum === 'RUNNING' && telemetry.paused) return 'Paused';
  return telemetry.state;
}

export function Header({ telemetry, onToggleHelp, onToggleAdvanced, onQuit }) {
  const stateClass   = getStateClass(telemetry.state_enum, telemetry.paused);
  const displayState = getDisplayState(telemetry);
  const simTitle     = telemetry.use_mock && telemetry.simulation_reason
    ? telemetry.simulation_reason : undefined;

  return (
    <header className="app-header">
      <div className="logo-container" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <img src="/logo.png" alt="Wavedriver Logo" style={{ width: '24px', height: '24px', borderRadius: '4px' }} />
        <h1 className="logo-title">WAVEDRIVER</h1>
      </div>

      <div className="header-badges">
        {telemetry.use_mock && (
          <span className="badge badge-mock" title={simTitle}>
            <Zap size={13} />
            Simulation
          </span>
        )}
        <span className={stateClass}>{displayState}</span>
        <button
          className="btn btn-secondary"
          style={{ padding: '5px 10px', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', height: '28px' }}
          onClick={onToggleHelp}
          title="Help (?)"
        >
          <HelpCircle size={13} />
        </button>
        <button
          className="btn btn-secondary"
          style={{ padding: '5px 10px', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', height: '28px' }}
          onClick={onToggleAdvanced}
          title="Advanced settings"
        >
          <Settings size={13} />
        </button>
        <button
          className="btn btn-secondary"
          style={{ padding: '5px 12px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', height: '28px' }}
          onClick={onQuit}
        >
          <LogOut size={12} />
          Exit
        </button>
      </div>
    </header>
  );
}
