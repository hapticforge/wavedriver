import { useState } from 'react';
import { X } from 'lucide-react';

const SHORTCUTS = [
  ["Enter",       "Start pattern (when calibrated / stopped)"],
  ["Space",       "Emergency stop"],
  ["Z",           "Start calibration"],
  ["P",           "Pause / Resume pattern"],
  ["C",           "Clear e-stop"],
  ["Q",           "Quit application"],
  ["↑ / ↓",      "Frequency ± 0.1 Hz"],
  ["← / →",      "Stroke ± 5 mm (rod ratio in Realistic mode)"],
  ["= / −",      "Intensity ± 10%"],
  ["] / [",      "Safety force ± 5 N"],
  ["T",           "Tap tempo — set speed by tapping (last 6 taps)"],
  ["1 – 5",      "Recall preset slot"],
  ["Ctrl+1 – 5", "Save current settings to preset slot"],
  ["?",           "Toggle this help overlay"],
];

const PATTERNS = [
  {
    name: "Wave",
    desc: "Smooth, even sine-wave reciprocating motion. The most predictable pattern — a good starting point.",
    params: "Frequency, Stroke, Intensity",
  },
  {
    name: "Realistic",
    desc: "Slider-crank kinematics: the extend stroke is faster than the retract, mimicking a physical crank mechanism. Rod Ratio controls the asymmetry (higher = more pronounced difference).",
    params: "Frequency, Stroke, Rod Ratio (2.5 × / 3.5 × / 5.0 ×)",
  },
  {
    name: "Thrust",
    desc: "Slow, gradual retraction followed by a rapid high-acceleration extend and a brief hold at full depth. Emphasises the forward stroke.",
    params: "Frequency, Stroke",
  },
  {
    name: "Pulse",
    desc: "A rapid burst of four quick strokes followed by a full rest pause at center. Rhythmic and interval-based.",
    params: "Frequency, Stroke",
  },
  {
    name: "Tease",
    desc: "Four incommensurable frequencies mixed together produce an irregular, non-repeating pattern. Each cycle is subtly different.",
    params: "Frequency, Stroke",
  },
  {
    name: "Escalate",
    desc: "Sine-wave motion whose amplitude builds from zero to full intensity over a set duration — for a slow, gradual build-up. After the duration elapses, it holds at full intensity.",
    params: "Frequency, Stroke, Duration (minutes)",
  },
  {
    name: "Edge",
    desc: "Intensity climbs steadily to peak over a set period, then drops sharply back to zero before repeating. Designed for edging — the sudden drop provides the denial.",
    params: "Frequency, Stroke, Cycle Period",
  },
  {
    name: "Depth",
    desc: "A sine carrier whose penetration depth slowly oscillates between shallow and full, creating a breathing quality. The Depth Period controls how long each full oscillation takes.",
    params: "Frequency, Stroke, Depth Period",
  },
  {
    name: "Adaptive",
    desc: "Uses live force feedback from the actuator to respond in real time. In Ease mode, rising resistance eases the stroke back. In Yield mode, it shifts the center of motion in the direction of applied force.",
    params: "Frequency, Stroke, Mode (Ease / Yield), Sensitivity",
  },
  {
    name: "Funscript",
    desc: "Follows keyframe position data from a .funscript file. Use the Video Sync panel to load a script and pair it with a local video file — the motor tracks the video position.",
    params: "Load via the Video Sync panel",
  },
];

const SAFETY = [
  {
    event: "Force limit reached",
    what: "The actuator sensed sustained resistance above the safety force threshold for 150 ms.",
    action: "Press C to clear, or Z to recalibrate. Lower frequency or stroke, or raise the Safety Force slider if the limit is too sensitive for your use.",
  },
  {
    event: "Temperature warning",
    what: "Motor coil temperature reached 65 °C. This is a warning only — motion continues.",
    action: "The warning clears automatically when temperature drops. Allow a rest period between long sessions.",
  },
  {
    event: "Over-temperature stop",
    what: "Motor coil temperature reached 75 °C. Emergency stop triggered to protect the hardware.",
    action: "Allow the motor to cool before restarting. Reduce session length or lower intensity.",
  },
  {
    event: "Under-voltage stop",
    what: "Supply voltage dropped below 18 V (nominal 24 V supply). Usually indicates a power supply issue.",
    action: "Check the power supply and cabling. Press C once voltage is stable.",
  },
  {
    event: "Communications lost",
    what: "The serial connection to the actuator was interrupted for more than 500 ms.",
    action: "Check the USB cable. The app will attempt to reconnect; recalibrate after reconnecting.",
  },
  {
    event: "UI watchdog",
    what: "The app stopped receiving telemetry updates for 5 seconds while running — the UI may have frozen or the computer went to sleep.",
    action: "Bring the app window to the foreground. Recalibrate if prompted.",
  },
  {
    event: "Session timer expired",
    what: "The session ran for the configured maximum duration and stopped automatically.",
    action: "Extend or disable the Session Timer slider if you want longer sessions.",
  },
];

const TABS = ["Keyboard Shortcuts", "Patterns", "Safety Events"];

export function HelpModal({ onClose }) {
  const [tab, setTab] = useState(0);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog help-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '600px', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
        <div className="help-modal-header">
          <h2 className="modal-title" style={{ margin: 0 }}>Help</h2>
          <button className="btn btn-secondary icon-btn" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        {/* Tab bar */}
        <div style={{ display: 'flex', gap: '2px', padding: '0 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          {TABS.map((t, i) => (
            <button
              key={t}
              onClick={() => setTab(i)}
              className="btn"
              style={{
                padding: '8px 14px',
                fontSize: '12px',
                borderRadius: '4px 4px 0 0',
                background: tab === i ? 'rgba(255,255,255,0.08)' : 'transparent',
                color: tab === i ? '#fff' : 'rgba(255,255,255,0.5)',
                border: 'none',
              }}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '16px' }}>
          {tab === 0 && (
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
          )}

          {tab === 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {PATTERNS.map(p => (
                <div key={p.name} style={{ borderLeft: '2px solid rgba(0,242,254,0.4)', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600, color: 'var(--accent-cyan, #00f2fe)', marginBottom: '4px' }}>{p.name}</div>
                  <div style={{ fontSize: '13px', lineHeight: 1.5, marginBottom: '4px', opacity: 0.85 }}>{p.desc}</div>
                  <div style={{ fontSize: '11px', opacity: 0.5 }}>Parameters: {p.params}</div>
                </div>
              ))}
            </div>
          )}

          {tab === 2 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {SAFETY.map(s => (
                <div key={s.event} style={{ borderLeft: '2px solid rgba(255,107,107,0.4)', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600, color: '#ff6b6b', marginBottom: '4px' }}>{s.event}</div>
                  <div style={{ fontSize: '13px', lineHeight: 1.5, marginBottom: '4px', opacity: 0.85 }}>{s.what}</div>
                  <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.6)' }}>
                    <span style={{ fontWeight: 600, color: 'rgba(255,255,255,0.4)', marginRight: '4px' }}>What to do:</span>
                    {s.action}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <p className="help-footer" style={{ margin: 0, padding: '10px 16px', borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: '11px' }}>
          Press <kbd className="kbd">?</kbd> or click outside to close
        </p>
      </div>
    </div>
  );
}
