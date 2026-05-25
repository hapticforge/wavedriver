import { renderHook } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { useKeyboard } from './useKeyboard';

describe('useKeyboard', () => {
  it('binds keyboard events and triggers callbacks', () => {
    const settingsRef = {
      current: {
        patternName: 'Wave',
        frequencyHz: 1.0,
        strokeLengthMm: 50.0,
        intensityPct: 50.0,
      },
    };
    const telemetryRef = {
      current: {
        state_enum: 'CALIBRATED_IDLE',
        paused: false,
      },
    };
    const calibratedLengthRef = { current: 150000 };

    const onEstopMock = vi.fn();
    const onCalibrateMock = vi.fn();
    const startPatternMock = vi.fn();
    const sendCommandMock = vi.fn();

    renderHook(() =>
      useKeyboard({
        settingsRef,
        telemetryRef,
        calibratedLengthRef,
        onEstop: onEstopMock,
        onCalibrate: onCalibrateMock,
        startPattern: startPatternMock,
        sendCommand: sendCommandMock,
      })
    );

    // Trigger Space (Emergency Stop)
    const spaceEvent = new KeyboardEvent('keydown', { code: 'Space' });
    window.dispatchEvent(spaceEvent);
    expect(onEstopMock).toHaveBeenCalled();

    // Trigger Z (Calibrate)
    const zEvent = new KeyboardEvent('keydown', { key: 'z' });
    window.dispatchEvent(zEvent);
    expect(onCalibrateMock).toHaveBeenCalled();

    // Trigger Enter (Start pattern)
    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter' });
    window.dispatchEvent(enterEvent);
    expect(startPatternMock).toHaveBeenCalled();

    // Trigger P when RUNNING (Pause)
    telemetryRef.current.state_enum = 'RUNNING';
    const pEvent = new KeyboardEvent('keydown', { key: 'p' });
    window.dispatchEvent(pEvent);
    expect(sendCommandMock).toHaveBeenCalledWith('pause_pattern');
  });
});
