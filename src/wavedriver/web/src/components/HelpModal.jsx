import { X } from 'lucide-react';

const SHORTCUTS = [
  ["Enter",      "Start pattern (when stopped / calibrated)"],
  ["Space",      "Emergency Stop"],
  ["Z",          "Start Calibration"],
  ["P",          "Pause / Resume pattern"],
  ["C",          "Clear E-Stop (resume without calibrating)"],
  ["Q",          "Quit application"],
  ["↑ / ↓",     "Frequency +/− 0.1 Hz"],
  ["← / →",     "Stroke +/− 5 mm (or rod ratio when Realistic)"],
  ["= / −",     "Intensity +/− 10%"],
  ["] / [",     "Safety force +/− 5 N"],
  ["T",          "Tap tempo — set speed by tapping the beat (keep last 6 taps)"],
  ["1 – 5",     "Recall preset slot"],
  ["Ctrl+1–5",  "Save current settings to preset slot"],
  ["?",          "Toggle this help overlay"],
];

export function HelpModal({ onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog help-modal" onClick={e => e.stopPropagation()}>
        <div className="help-modal-header">
          <h2 className="modal-title" style={{ margin: 0 }}>Keyboard Shortcuts</h2>
          <button className="btn btn-secondary icon-btn" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <table className="shortcuts-table">
          <tbody>
            {SHORTCUTS.map(([key, desc]) => (
              <tr key={key}>
                <td><kbd className="kbd">{key}</kbd></td>
                <td>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="help-footer">Press <kbd className="kbd">?</kbd> or click outside to close</p>
      </div>
    </div>
  );
}
