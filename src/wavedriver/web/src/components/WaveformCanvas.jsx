import { useEffect, useRef } from 'react';

const CYAN   = '#00f2fe';
const PURPLE = '#c362fc';
const BUFFER = 200;  // 10 s at 20 Hz

/**
 * Scrolling waveform showing shaft position over the last ~10 seconds.
 * Uses a canvas with devicePixelRatio scaling for sharp rendering.
 * Appends a sample each render tick (driven by the 20 Hz telemetry poll).
 */
export function WaveformCanvas({ positionUm, calibratedLength, isRunning, isPaused }) {
  const canvasRef = useRef(null);
  const bufRef    = useRef([]);
  const rafRef    = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!isRunning) {
      // Keep last trace visible but don't append; clear only on a fresh start
      return;
    }

    if (bufRef.current._cleared) {
      bufRef.current._cleared = false;
    }

    if (!isPaused) {
      bufRef.current.push(positionUm);
      if (bufRef.current.length > BUFFER) bufRef.current.shift();
    }

    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      const dpr = window.devicePixelRatio || 1;
      const W   = canvas.clientWidth  * dpr;
      const H   = canvas.clientHeight * dpr;
      if (canvas.width !== W || canvas.height !== H) {
        canvas.width  = W;
        canvas.height = H;
      }

      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, W, H);

      const buf = bufRef.current;
      if (buf.length < 2) return;

      const L = calibratedLength > 0 ? calibratedLength : 150000;
      const PAD = 4 * dpr;

      // Waveform line
      const grad = ctx.createLinearGradient(0, 0, W, 0);
      grad.addColorStop(0, 'rgba(0, 242, 254, 0.15)');
      grad.addColorStop(1, PURPLE);

      ctx.beginPath();
      ctx.strokeStyle = grad;
      ctx.lineWidth   = 2 * dpr;
      ctx.lineJoin    = 'round';

      for (let i = 0; i < buf.length; i++) {
        const x = PAD + (i / (BUFFER - 1)) * (W - PAD * 2);
        const y = (H - PAD * 2) - Math.max(0, Math.min(1, buf[i] / L)) * (H - PAD * 2) + PAD;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Glow dot at current tip
      const lx = PAD + ((buf.length - 1) / (BUFFER - 1)) * (W - PAD * 2);
      const ly = (H - PAD * 2) - Math.max(0, Math.min(1, buf[buf.length - 1] / L)) * (H - PAD * 2) + PAD;
      ctx.beginPath();
      ctx.arc(lx, ly, 4 * dpr, 0, 2 * Math.PI);
      ctx.fillStyle   = CYAN;
      ctx.shadowColor = CYAN;
      ctx.shadowBlur  = 10 * dpr;
      ctx.fill();
      ctx.shadowBlur = 0;
    });

    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [positionUm, calibratedLength, isRunning, isPaused]);

  // Clear buffer when transitioning from stopped → running
  useEffect(() => {
    if (isRunning) {
      bufRef.current = [];
    }
  }, [isRunning]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: '100%',
        height: '72px',
        display: 'block',
        borderRadius: '6px',
        background: 'rgba(8, 9, 13, 0.6)',
      }}
    />
  );
}
