import { X, Trash2 } from 'lucide-react';

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatTimestamp(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function SessionHistory({ records, historyEnabled = true, onHistoryEnabledChange, onClearHistory, onClose }) {
  const handleClear = () => {
    if (window.confirm("Clear all session history? This cannot be undone.")) {
      onClearHistory?.();
    }
  };

  return (
    <div className="activity-log-panel">
      <div className="activity-log-header">
        <span className="input-label" style={{ margin: 0 }}>Session History</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', fontSize: '11px', opacity: 0.7 }}>
            <input
              type="checkbox"
              checked={historyEnabled}
              onChange={(e) => onHistoryEnabledChange?.(e.target.checked)}
            />
            Record
          </label>
          <button
            className="btn btn-secondary icon-btn"
            onClick={handleClear}
            title="Clear all history"
            disabled={records.length === 0}
          >
            <Trash2 size={12} />
          </button>
          <button className="btn btn-secondary icon-btn" onClick={onClose}>
            <X size={14} />
          </button>
        </div>
      </div>
      {!historyEnabled && (
        <div style={{ padding: '6px 12px', fontSize: '11px', color: 'var(--accent-yellow, #ffb74d)', background: 'rgba(255,183,77,0.08)' }}>
          History recording is off — sessions will not be saved.
        </div>
      )}
      <div className="activity-log-body">
        {records.length === 0 ? (
          <span className="activity-log-empty">No sessions recorded yet</span>
        ) : (
          records.map((r, i) => (
            <div key={i} className="activity-log-entry">
              <span style={{ opacity: 0.6, marginRight: '8px' }}>
                {formatTimestamp(r.timestamp)}
              </span>
              <span style={{ color: 'var(--accent-cyan)', marginRight: '6px' }}>
                {r.pattern_name || '—'}
              </span>
              <span>{formatDuration(r.duration_s || 0)}</span>
              {r.end_state && r.end_state !== 'CALIBRATED_IDLE' && (
                <span style={{ color: 'var(--accent-red)', marginLeft: '6px', fontSize: '0.75em' }}>
                  {r.end_state}
                </span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
