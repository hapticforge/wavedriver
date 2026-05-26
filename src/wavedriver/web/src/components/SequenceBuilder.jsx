import { useState, useEffect, useRef, useCallback } from 'react';
import { Layers, Plus, Trash2, Play, Square, FastForward, Clock } from 'lucide-react';

const PATTERNS = ["Wave", "Realistic", "Thrust", "Pulse", "Tease", "Escalate", "Edge", "Depth", "Adaptive"];

export function SequenceBuilder({
  isRunning,
  startPattern,
  stopPattern,
  setPatternName,
  setFrequencyHz,
  setStrokeLengthMm,
  onIntensityChange,
}) {
  const [steps, setSteps] = useState([
    { pattern: 'Wave', freq: 1.0, stroke: 40, intensity: 50, duration: 60 },
    { pattern: 'Realistic', freq: 1.5, stroke: 50, intensity: 60, duration: 90 },
  ]);
  const [activeStepIdx, setActiveStepIdx] = useState(null);
  const [stepTimeRemaining, setStepTimeRemaining] = useState(0);
  const [isSequencePlaying, setIsSequencePlaying] = useState(false);

  const timerRef = useRef(null);

  const addStep = () => {
    setSteps(prev => [
      ...prev,
      { pattern: 'Wave', freq: 1.0, stroke: 40, intensity: 50, duration: 60 }
    ]);
  };

  const removeStep = (idx) => {
    setSteps(prev => prev.filter((_, i) => i !== idx));
  };

  const updateStep = (idx, field, val) => {
    setSteps(prev => prev.map((step, i) => {
      if (i === idx) {
        return { ...step, [field]: val };
      }
      return step;
    }));
  };

  const startSequence = () => {
    if (steps.length === 0) return;
    setIsSequencePlaying(true);
    setActiveStepIdx(0);
    setStepTimeRemaining(steps[0].duration);
    executeStep(steps[0]);
  };

  const executeStep = useCallback((step) => {
    // Set UI states so sliders align
    setPatternName(step.pattern);
    setFrequencyHz(step.freq);
    setStrokeLengthMm(step.stroke);
    onIntensityChange(step.intensity);

    // Call start pattern on backend
    startPattern({
      patternName: step.pattern,
      frequencyHz: step.freq,
      strokeLengthMm: step.stroke,
      intensityPct: step.intensity,
    });
  }, [setPatternName, setFrequencyHz, setStrokeLengthMm, onIntensityChange, startPattern]);

  const stopSequence = useCallback(() => {
    setIsSequencePlaying(false);
    setActiveStepIdx(null);
    setStepTimeRemaining(0);
    stopPattern();
  }, [stopPattern]);

  const nextStep = useCallback(() => {
    const nextIdx = activeStepIdx + 1;
    if (nextIdx < steps.length) {
      setActiveStepIdx(nextIdx);
      setStepTimeRemaining(steps[nextIdx].duration);
      executeStep(steps[nextIdx]);
    } else {
      stopSequence();
    }
  }, [activeStepIdx, steps, executeStep, stopSequence]);

  // Timer loop for sequence playback
  useEffect(() => {
    if (isSequencePlaying && activeStepIdx !== null && isRunning) {
      if (stepTimeRemaining > 0) {
        timerRef.current = setTimeout(() => {
          setStepTimeRemaining(prev => prev - 1);
        }, 1000);
      } else {
        setTimeout(() => {
          nextStep();
        }, 0);
      }
    } else if (!isRunning && isSequencePlaying) {
      setTimeout(() => {
        stopSequence();
      }, 0);
    }

    return () => clearTimeout(timerRef.current);
  }, [isSequencePlaying, activeStepIdx, stepTimeRemaining, isRunning, nextStep, stopSequence]);

  return (
    <div className="control-card glass">
      <h3 className="section-title">
        <Layers size={14} className="accent-glow" /> Ramp / Session sequencing
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {/* Playback Control Bar */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {isSequencePlaying ? (
            <button className="btn btn-danger" style={{ flex: 1 }} onClick={stopSequence}>
              <Square size={14} style={{ marginRight: '6px' }} /> Stop Sequence
            </button>
          ) : (
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={startSequence} disabled={steps.length === 0}>
              <Play size={14} style={{ marginRight: '6px' }} /> Start Sequence
            </button>
          )}

          {isSequencePlaying && (
            <button className="btn btn-secondary" title="Skip to next step" onClick={nextStep}>
              <FastForward size={14} />
            </button>
          )}

          {isSequencePlaying && activeStepIdx !== null && (
            <div className="badge" style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'rgba(255,255,255,0.05)', padding: '6px 10px', borderRadius: '4px' }}>
              <Clock size={12} />
              <span>Step {activeStepIdx + 1}: {stepTimeRemaining}s</span>
            </div>
          )}
        </div>

        {/* Steps List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto', paddingRight: '4px' }}>
          {steps.map((step, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px',
                borderRadius: '6px',
                border: activeStepIdx === idx ? '1px solid #00f2fe' : '1px solid rgba(255,255,255,0.05)',
                background: activeStepIdx === idx ? 'rgba(0, 242, 254, 0.05)' : 'rgba(8, 9, 13, 0.4)',
              }}
            >
              {/* Pattern Selector */}
              <select
                className="custom-input"
                style={{ flex: 1, padding: '4px', fontSize: '12px' }}
                value={step.pattern}
                onChange={(e) => updateStep(idx, 'pattern', e.target.value)}
                disabled={isSequencePlaying}
              >
                {PATTERNS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>

              {/* Freq input */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                <input
                  type="number"
                  className="custom-input"
                  style={{ width: '40px', padding: '4px', fontSize: '12px', textAlign: 'center' }}
                  value={step.freq}
                  step="0.1"
                  min="0.1"
                  max="4.0"
                  onChange={(e) => updateStep(idx, 'freq', parseFloat(e.target.value) || 0.1)}
                  disabled={isSequencePlaying}
                />
                <span className="slider-desc" style={{ fontSize: '10px' }}>Hz</span>
              </div>

              {/* Stroke input */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                <input
                  type="number"
                  className="custom-input"
                  style={{ width: '40px', padding: '4px', fontSize: '12px', textAlign: 'center' }}
                  value={step.stroke}
                  step="5"
                  min="10"
                  max="140"
                  onChange={(e) => updateStep(idx, 'stroke', parseInt(e.target.value, 10) || 10)}
                  disabled={isSequencePlaying}
                />
                <span className="slider-desc" style={{ fontSize: '10px' }}>mm</span>
              </div>

              {/* Duration input */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                <input
                  type="number"
                  className="custom-input"
                  style={{ width: '45px', padding: '4px', fontSize: '12px', textAlign: 'center' }}
                  value={step.duration}
                  step="10"
                  min="5"
                  onChange={(e) => updateStep(idx, 'duration', parseInt(e.target.value, 10) || 5)}
                  disabled={isSequencePlaying}
                />
                <span className="slider-desc" style={{ fontSize: '10px' }}>s</span>
              </div>

              {/* Delete Button */}
              <button
                className="btn btn-danger"
                style={{ padding: '4px 8px' }}
                onClick={() => removeStep(idx)}
                disabled={isSequencePlaying}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>

        {/* Add Step Button */}
        {!isSequencePlaying && (
          <button className="btn btn-secondary" onClick={addStep} style={{ width: '100%' }}>
            <Plus size={14} style={{ marginRight: '6px' }} /> Add Sequence Step
          </button>
        )}
      </div>
    </div>
  );
}
