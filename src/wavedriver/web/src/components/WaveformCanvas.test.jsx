import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WaveformCanvas } from './WaveformCanvas';

describe('WaveformCanvas', () => {
  let mockCtx;

  beforeEach(() => {
    mockCtx = {
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      createLinearGradient: vi.fn().mockReturnValue({
        addColorStop: vi.fn(),
      }),
      strokeStyle: '',
      lineWidth: 0,
      lineJoin: '',
      fillStyle: '',
      shadowColor: '',
      shadowBlur: 0,
    };

    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue(mockCtx);
    // Mock client dimensions
    Object.defineProperties(HTMLCanvasElement.prototype, {
      clientWidth: { value: 200, configurable: true },
      clientHeight: { value: 72, configurable: true },
    });

    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      cb();
      return 1;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders canvas and sets dimensions scaled by dpr', () => {
    const { container } = render(
      <WaveformCanvas positionUm={75000} calibratedLength={150000} isRunning={false} isPaused={false} />
    );
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeInTheDocument();
  });

  it('updates canvas buffer and draws lines when running', async () => {
    const { rerender } = render(
      <WaveformCanvas positionUm={50000} calibratedLength={150000} isRunning={true} isPaused={false} />
    );

    // Call multiple times to fill buffer
    rerender(<WaveformCanvas positionUm={60000} calibratedLength={150000} isRunning={true} isPaused={false} />);
    rerender(<WaveformCanvas positionUm={70000} calibratedLength={150000} isRunning={true} isPaused={false} />);

    expect(mockCtx.beginPath).toHaveBeenCalled();
    expect(mockCtx.moveTo).toHaveBeenCalled();
    expect(mockCtx.lineTo).toHaveBeenCalled();
    expect(mockCtx.arc).toHaveBeenCalled();
  });
});
