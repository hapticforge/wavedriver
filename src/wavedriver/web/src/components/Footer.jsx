import { useState } from 'react';
import { Zap, Thermometer, Battery, Activity, ToggleLeft, ToggleRight, List, History } from 'lucide-react';

export function Footer({ telemetry, showActivityLog, onToggleActivityLog, showHistory, onToggleHistory }) {
  const [showDebug, setShowDebug] = useState(false);

  return (
    <footer className="app-footer">
      <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
        <span>© 2026 Wavedriver Controller System</span>
        <span
          style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}
          onClick={() => setShowDebug(d => !d)}
        >
          {showDebug
            ? <ToggleRight className="text-cyan" size={18} />
            : <ToggleLeft size={18} />}
          <span>Advanced Diagnostics</span>
        </span>
        <span
          style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer',
                   color: showActivityLog ? 'var(--accent-cyan)' : undefined }}
          onClick={onToggleActivityLog}
        >
          <List size={16} />
          <span>Activity Log</span>
        </span>
        <span
          style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer',
                   color: showHistory ? 'var(--accent-cyan)' : undefined }}
          onClick={onToggleHistory}
        >
          <History size={16} />
          <span>Session History</span>
        </span>
      </div>

      {showDebug && (
        <div className="footer-links" style={{ gap: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Zap size={12} className="text-purple" />
            Power: <strong className="text-bright">{telemetry.power_W} W</strong>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Thermometer size={12} className={telemetry.temp_warning ? 'text-warning' : 'text-warning'} />
            Temp: <strong className={telemetry.temp_warning ? 'text-warning' : 'text-bright'}>
              {telemetry.temperature_C} °C
            </strong>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Battery size={12} className="text-cyan" />
            Voltage: <strong className="text-bright">{(telemetry.voltage_mV / 1000).toFixed(1)} V</strong>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Activity size={12} className="text-success" />
            Speed: <strong className="text-bright">{Math.abs(telemetry.speed_mm_s || 0).toFixed(0)} mm/s</strong>
          </span>
        </div>
      )}
    </footer>
  );
}
