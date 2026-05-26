import { useState, useEffect, useRef, useCallback } from 'react';
import { Music, Mic } from 'lucide-react';

export function AudioSyncPanel({
  isRunning,
  intensityPct,
  onIntensityChange,
  onFrequencyChange,
}) {
  const [isActive, setIsActive] = useState(false);
  const [volumeLevel, setVolumeLevel] = useState(0);
  const [sensitivity, setSensitivity] = useState(1.5);
  const [isFlashing, setIsFlashing] = useState(false);
  const [detectedBpm, setDetectedBpm] = useState(null);

  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRefNode = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);
  const lastIntensity = useRef(intensityPct);

  const energyHistory = useRef([]);
  const lastBeatTime = useRef(0);
  const beatTimestamps = useRef([]);

  const stopAudioSync = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (sourceRefNode.current) {
      try {
        sourceRefNode.current.disconnect();
      } catch {
        // Silently ignore
      }
      sourceRefNode.current = null;
    }
    if (streamRef.current) {
      try {
        streamRef.current.getTracks().forEach(track => track.stop());
      } catch {
        // Silently ignore
      }
      streamRef.current = null;
    }
    if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
      try {
        audioCtxRef.current.close();
      } catch {
        // Silently ignore
      }
      audioCtxRef.current = null;
    }
    setTimeout(() => {
      setIsActive(false);
      setVolumeLevel(0);
      setDetectedBpm(null);
    }, 0);
    beatTimestamps.current = [];
  }, []);

  const startAudioSync = useCallback(async () => {
    try {
      // Clean up any existing instances first
      stopAudioSync();

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
      analyserRef.current = audioCtxRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      
      sourceRefNode.current = audioCtxRef.current.createMediaStreamSource(stream);
      sourceRefNode.current.connect(analyserRef.current);
      
      setTimeout(() => {
        setIsActive(true);
      }, 0);
    } catch (err) {
      alert("Failed to access microphone: " + err.message);
    }
  }, [stopAudioSync]);

  // Sync mic activity with global running state
  useEffect(() => {
    if (isRunning) {
      startAudioSync();
    } else {
      stopAudioSync();
    }
    return () => {
      stopAudioSync();
    };
  }, [isRunning, startAudioSync, stopAudioSync]);

  useEffect(() => {
    if (!isActive) return;

    const bufferLength = analyserRef.current.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    
    let lastCommandTime = 0;

    const tick = () => {
      if (!analyserRef.current) return;
      analyserRef.current.getByteFrequencyData(dataArray);
      
      // Calculate root-mean-square volume of low-mid frequencies (beats/drums)
      let sum = 0;
      const beatFreqMaxBin = Math.floor(bufferLength * 0.4); // Focus on lower frequencies
      for (let i = 0; i < beatFreqMaxBin; i++) {
        sum += dataArray[i] * dataArray[i];
      }
      const rms = Math.sqrt(sum / beatFreqMaxBin);
      
      // Normalize to 0-100
      const normVolume = Math.min(100, (rms / 255.0) * 100 * sensitivity);
      setVolumeLevel(normVolume);

      // Low frequency energy for beat detection
      let lowEnergy = 0;
      const bassBinEnd = Math.max(1, Math.floor(bufferLength * 0.15));
      for (let i = 0; i < bassBinEnd; i++) {
        lowEnergy += dataArray[i];
      }
      lowEnergy = lowEnergy / bassBinEnd;

      // Keep energy history for running average
      energyHistory.current.push(lowEnergy);
      if (energyHistory.current.length > 40) {
        energyHistory.current.shift();
      }

      const avgEnergy = energyHistory.current.reduce((a, b) => a + b, 0) / (energyHistory.current.length || 1);
      const thresholdFactor = Math.max(1.05, 1.6 - (sensitivity * 0.15));
      const now = Date.now();

      // Trigger beat detection
      if (lowEnergy > avgEnergy * thresholdFactor && now - lastBeatTime.current > 300 && lowEnergy > 10) {
        lastBeatTime.current = now;
        setIsFlashing(true);
        setTimeout(() => setIsFlashing(false), 150);

        const beats = beatTimestamps.current.filter(ts => now - ts < 4000);
        beats.push(now);
        beatTimestamps.current = beats.slice(-6);

        if (beats.length >= 2) {
          const intervals = beats.slice(1).map((ts, idx) => ts - beats[idx]);
          const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length;
          const calculatedBpm = Math.round(60000.0 / avgInterval);
          setDetectedBpm(calculatedBpm);

          const hz = Math.round((calculatedBpm / 60.0) * 10) / 10;
          const nextHz = Math.max(0.5, Math.min(4.0, hz));
          onFrequencyChange(nextHz);
        }
      }

      // Clear BPM if no beats detected for 4 seconds
      if (now - lastBeatTime.current > 4000) {
        setDetectedBpm(null);
        beatTimestamps.current = [];
      }

      // Send update to device at most every 100ms to prevent buffer overflow
      if (now - lastCommandTime > 100) {
        lastCommandTime = now;
        if (isRunning) {
          // Map normVolume to intensity range
          const newIntensity = Math.max(10, Math.min(100, Math.round(normVolume)));
          if (Math.abs(newIntensity - lastIntensity.current) >= 5) {
            lastIntensity.current = newIntensity;
            onIntensityChange(newIntensity);
          }
        }
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    tick();

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isActive, sensitivity, isRunning, onIntensityChange, onFrequencyChange]);

  return (
    <div className="control-card glass">
      <h3 className="section-title">
        <Music size={14} className="accent-glow" /> Audio &amp; Music Sync
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {!isRunning ? (
          <div style={{ textAlign: 'center', padding: '24px 16px', color: 'var(--text-secondary)' }}>
            <Mic size={24} style={{ marginBottom: '8px', opacity: 0.5, color: '#00f2fe' }} />
            <p style={{ margin: 0, fontSize: '14px' }}>Click <strong>Start</strong> above to activate microphone beat-sync.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Visualizer Bar & Beat Indicator */}
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <div style={{ flex: 1, background: 'rgba(255,255,255,0.05)', borderRadius: '4px', height: '20px', overflow: 'hidden', position: 'relative' }}>
                <div
                  style={{
                    background: 'linear-gradient(90deg, #00f2fe 0%, #c362fc 100%)',
                    width: `${volumeLevel}%`,
                    height: '100%',
                    transition: 'width 0.1s ease',
                    boxShadow: '0 0 10px rgba(0, 242, 254, 0.5)',
                  }}
                />
                <span className="slider-desc" style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', fontWeight: 'bold' }}>
                  Volume Level: {Math.round(volumeLevel)}%
                </span>
              </div>
              <div
                style={{
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  backgroundColor: isFlashing ? '#00f2fe' : 'rgba(255, 255, 255, 0.1)',
                  boxShadow: isFlashing ? '0 0 12px #00f2fe' : 'none',
                  transition: 'background-color 0.05s ease, box-shadow 0.05s ease',
                  flexShrink: 0,
                }}
                title="Beat Indicator"
              />
            </div>

            {/* BPM Display */}
            {detectedBpm && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.03)', padding: '6px 12px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <span className="slider-title" style={{ fontSize: '13px' }}>Detected Tempo:</span>
                <span className="slider-value-display" style={{ fontSize: '14px', fontWeight: 'bold', color: '#00f2fe', textShadow: '0 0 8px rgba(0, 242, 254, 0.4)' }}>
                  {detectedBpm} BPM ({ (detectedBpm / 60.0).toFixed(1) } Hz)
                </span>
              </div>
            )}

            {/* Sensitivity Control */}
            <div>
              <div className="slider-header">
                <span className="slider-title">Sensitivity</span>
                <span className="slider-value-display">{sensitivity.toFixed(1)}x</span>
              </div>
              <input
                type="range"
                className="custom-slider"
                min="0.5" max="3.0" step="0.1"
                value={sensitivity}
                onChange={(e) => setSensitivity(parseFloat(e.target.value))}
              />
            </div>
          </div>
        )}

        <p className="slider-desc" style={{ margin: 0, textAlign: 'center' }}>
          The pattern speed adjusts automatically to the beat of the music, and the pattern intensity reacts to volume.
        </p>
      </div>
    </div>
  );
}
