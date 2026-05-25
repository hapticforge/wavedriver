import { useState, useEffect, useRef } from 'react';
import { Video, Upload, Square, ExternalLink } from 'lucide-react';

function formatTime(s) {
  if (s == null) return '--:--';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export function VideoSyncPanel({ isRunning, sendCommand, startPattern }) {
  const [funscriptName, setFunscriptName] = useState('');
  const [actions, setActions] = useState([]);
  const [isLooping, setIsLooping] = useState(true);
  const [videoFilename, setVideoFilename] = useState('');
  const [position, setPosition] = useState(null);
  const [playerAlive, setPlayerAlive] = useState(false);
  const [error, setError] = useState('');

  const pollRef = useRef(null);
  const lastPosRef = useRef(null);
  const lastPausedRef = useRef(true);
  const mpvPausedRef = useRef(true); // live mpv state, updated every poll

  // Poll mpv position when a video is open
  useEffect(() => {
    if (!playerAlive) return;

    pollRef.current = setInterval(async () => {
      if (!window.pywebview?.api?.get_video_position) return;
      const r = await window.pywebview.api.get_video_position();
      if (!r?.success) {
        setPlayerAlive(false);
        setPosition(null);
        clearInterval(pollRef.current);
        return;
      }

      const pos = r.position_s;
      const paused = r.paused;
      mpvPausedRef.current = paused;
      setPosition(pos);

      if (!isRunning || actions.length === 0) return;

      // Sync position to controller
      if (pos != null && pos !== lastPosRef.current) {
        sendCommand('set_pattern_elapsed', { elapsed_s: pos });
        lastPosRef.current = pos;
      }

      // Mirror pause/resume state
      if (paused !== lastPausedRef.current) {
        sendCommand(paused ? 'pause_pattern' : 'resume_pattern');
        lastPausedRef.current = paused;
      }
    }, 200); // 5 Hz

    return () => clearInterval(pollRef.current);
  }, [playerAlive, isRunning, actions, sendCommand]);

  // Send funscript whenever running starts or loop toggle changes while running
  useEffect(() => {
    if (isRunning && actions.length > 0) {
      startPattern({
        patternName: 'Funscript',
        funscript_actions: actions,
        funscript_loop: isLooping,
      });
      // Immediately sync motor pause state with mpv's current state.
      // The polling loop only sends on *changes*, so without this the motor
      // starts at full amplitude even when mpv is still paused.
      if (mpvPausedRef.current) {
        sendCommand('pause_pattern');
        lastPausedRef.current = true;
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning, isLooping]);

  const handleFunscriptUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setFunscriptName(file.name);
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const data = JSON.parse(evt.target.result);
        if (data.actions && Array.isArray(data.actions)) {
          const mapped = data.actions
            .map(act => [act.at / 1000.0, act.pos])
            .sort((a, b) => a[0] - b[0]);
          setActions(mapped);
          if (isRunning) {
            startPattern({ patternName: 'Funscript', funscript_actions: mapped, funscript_loop: isLooping });
          }
        } else {
          setError('Invalid funscript: missing actions array.');
        }
      } catch (err) {
        setError('Failed to parse funscript: ' + err.message);
      }
    };
    reader.readAsText(file);
  };

  const handleOpenVideo = async () => {
    if (!window.pywebview?.api?.pick_and_launch_video) return;
    setError('');
    const r = await window.pywebview.api.pick_and_launch_video();
    if (!r?.success) {
      setError(r?.error || 'Failed to open video.');
      return;
    }
    setVideoFilename(r.filename);
    setPlayerAlive(true);
    lastPosRef.current = null;
    lastPausedRef.current = true;
    mpvPausedRef.current = true;
  };

  const handleCloseVideo = async () => {
    window.pywebview?.api?.close_video?.();
    setPlayerAlive(false);
    setVideoFilename('');
    setPosition(null);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      {/* Funscript loader */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <label className="btn btn-secondary" style={{ flex: 1, padding: '8px', cursor: 'pointer', textAlign: 'center' }}>
          <Upload size={13} style={{ marginRight: '6px' }} />
          Load Funscript
          <input type="file" accept=".funscript" onChange={handleFunscriptUpload} style={{ display: 'none' }} />
        </label>
        <span style={{ flex: 1, fontSize: '0.78rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {funscriptName || 'No script loaded'}
        </span>
      </div>

      {/* Loop toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <input type="checkbox" id="fs-loop" checked={isLooping} onChange={e => setIsLooping(e.target.checked)} />
        <label htmlFor="fs-loop" style={{ fontSize: '0.82rem', cursor: 'pointer', color: 'var(--text-normal)' }}>
          Loop script
        </label>
      </div>

      {/* Video player (mpv) */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {!playerAlive ? (
          <button className="btn btn-secondary" style={{ padding: '10px' }} onClick={handleOpenVideo}>
            <ExternalLink size={14} style={{ marginRight: '6px' }} />
            Open Video in Player
          </button>
        ) : (
          <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '200px' }}>
                <Video size={11} style={{ marginRight: '5px', verticalAlign: 'middle', color: 'var(--accent-cyan)' }} />
                {videoFilename}
              </span>
              <button
                className="btn btn-secondary"
                style={{ padding: '3px 8px', fontSize: '0.72rem', color: 'var(--color-danger)', borderColor: 'rgba(239,68,68,0.2)' }}
                onClick={handleCloseVideo}
              >
                <Square size={10} style={{ marginRight: '4px' }} /> Close
              </button>
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--accent-cyan)', letterSpacing: '0.05em', textAlign: 'center', fontFamily: 'monospace' }}>
              {formatTime(position)}
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textAlign: 'center' }}>
              {actions.length > 0 ? `Script loaded — ${actions.length} keyframes` : 'Load a funscript for motor sync'}
            </div>
          </div>
        )}
      </div>

      {error && (
        <p style={{ fontSize: '0.75rem', color: 'var(--color-danger)', margin: 0 }}>{error}</p>
      )}

      <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>
        mpv opens as a separate window. Play/pause in mpv syncs to the motor.
        {!funscriptName && ' Load a funscript first to enable motor sync.'}
      </p>
    </div>
  );
}
