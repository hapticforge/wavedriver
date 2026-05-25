import { useState, useEffect, useRef } from 'react';
import { RefreshCw } from 'lucide-react';

export function InteractiveEdging({ isRunning, intensityPct, onIntensityChange }) {
  const [edgingActive, setEdgingActive] = useState(false);
  const [cooldownRemaining, setCooldownRemaining] = useState(0);
  const [surpriseDenial, setSurpriseDenial] = useState(false);
  const [denied, setDenied] = useState(false);

  const savedIntensity = useRef(intensityPct);
  const timerRef = useRef(null);

  const handleAlmost = () => {
    if (!isRunning || edgingActive) return;

    savedIntensity.current = intensityPct;
    setEdgingActive(true);
    setDenied(false);
    onIntensityChange(10);

    const duration = Math.floor(Math.random() * 11) + 5;
    setCooldownRemaining(duration);
  };

  useEffect(() => {
    if (cooldownRemaining > 0 && edgingActive) {
      timerRef.current = setTimeout(() => {
        setCooldownRemaining(prev => prev - 1);
      }, 1000);
    } else if (cooldownRemaining === 0 && edgingActive) {
      if (surpriseDenial && Math.random() < 0.5) {
        setDenied(true);
        onIntensityChange(0);
        setCooldownRemaining(5);
        setSurpriseDenial(false);
        return;
      }

      onIntensityChange(savedIntensity.current);
      setEdgingActive(false);
      setDenied(false);
    }

    return () => clearTimeout(timerRef.current);
  }, [cooldownRemaining, edgingActive, surpriseDenial, onIntensityChange]);

  useEffect(() => {
    if (!isRunning) {
      setEdgingActive(false);
      setCooldownRemaining(0);
      setDenied(false);
    }
  }, [isRunning]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <button
        id="btn-almost"
        className={`almost-btn${edgingActive ? ' almost-btn--active' : ''}`}
        style={{ opacity: isRunning ? 1 : 0.5 }}
        onClick={handleAlmost}
        disabled={!isRunning}
      >
        {edgingActive ? (
          <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}>
            <RefreshCw size={20} className="spin" />
            {denied ? `DENIED — ${cooldownRemaining}s` : `Easing… ${cooldownRemaining}s`}
          </span>
        ) : (
          'ALMOST!'
        )}
      </button>

      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', margin: 0, lineHeight: 1.5 }}>
        {edgingActive
          ? denied
            ? 'Denied. Motor stopped for a moment.'
            : 'Intensity eased — breathe.'
          : 'Press when close. Motor eases back for a random 5–15 s, then resumes.'}
      </p>

      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={surpriseDenial}
          onChange={e => setSurpriseDenial(e.target.checked)}
          disabled={edgingActive}
        />
        <span style={{ fontSize: '0.82rem', color: 'var(--text-normal)' }}>Surprise denial</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>— 50% chance motor stops instead of resuming</span>
      </label>
    </div>
  );
}
