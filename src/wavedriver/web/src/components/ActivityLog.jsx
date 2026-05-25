import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export function ActivityLog({ events, onClose }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  return (
    <div className="activity-log-panel">
      <div className="activity-log-header">
        <span className="input-label" style={{ margin: 0 }}>Activity Log</span>
        <button className="btn btn-secondary icon-btn" onClick={onClose}>
          <X size={14} />
        </button>
      </div>
      <div className="activity-log-body">
        {events.length === 0 ? (
          <span className="activity-log-empty">No events yet</span>
        ) : (
          events.map((entry, i) => (
            <div key={i} className="activity-log-entry">{entry}</div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
