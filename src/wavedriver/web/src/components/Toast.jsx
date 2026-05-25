import { useEffect } from 'react';
import { X } from 'lucide-react';

export function Toast({ message, onDismiss, durationMs = 4000 }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onDismiss, durationMs);
    return () => clearTimeout(t);
  }, [message, onDismiss, durationMs]);

  if (!message) return null;

  return (
    <div className="toast-notification">
      <span>{message}</span>
      <button className="toast-dismiss" onClick={onDismiss}>
        <X size={12} />
      </button>
    </div>
  );
}
