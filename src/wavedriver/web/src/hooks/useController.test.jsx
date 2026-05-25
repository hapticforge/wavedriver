import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useController } from './useController';

describe('useController', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Reset window
    delete window.pywebview;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initially has default state and waits for pywebview ready', async () => {
    const { result } = renderHook(() => useController());
    expect(result.current.apiReady).toBe(false);
    expect(result.current.telemetry.state_enum).toBe("UNCONNECTED");

    // Mock API arrival
    window.pywebview = {
      api: {
        load_session: vi.fn(),
        get_telemetry: vi.fn().mockResolvedValue({
          state: "Connected",
          state_enum: "CONNECTED",
          calibrated_length_um: 150000,
        }),
      },
    };

    // Trigger interval check
    await act(async () => {
      vi.advanceTimersByTime(50);
    });

    expect(result.current.apiReady).toBe(true);

    // Trigger telemetry poll
    await act(async () => {
      vi.advanceTimersByTime(50);
    });

    expect(result.current.telemetry.state_enum).toBe("CONNECTED");
    expect(result.current.calibratedLength).toBe(150000);
  });

  it('triggers save_session_history on RUNNING -> stopped transition', async () => {
    const saveHistoryMock = vi.fn().mockResolvedValue({ success: true });
    const getTelemetryMock = vi.fn();

    window.pywebview = {
      api: {
        load_session: vi.fn(),
        get_telemetry: getTelemetryMock,
        save_session_history: saveHistoryMock,
      },
    };

    // First, telemetry is RUNNING
    getTelemetryMock.mockResolvedValue({
      state: "Running",
      state_enum: "RUNNING",
      session_elapsed_s: 10,
      current_pattern_name: "Wave",
    });

    const { result } = renderHook(() => useController());

    // Wait for apiReady check
    await act(async () => {
      vi.advanceTimersByTime(50);
    });
    expect(result.current.apiReady).toBe(true);

    // Poll 1 (gets RUNNING)
    await act(async () => {
      vi.advanceTimersByTime(50);
    });
    expect(result.current.telemetry.state_enum).toBe("RUNNING");

    // Change telemetry to CALIBRATED_IDLE
    getTelemetryMock.mockResolvedValue({
      state: "Calibrated Idle",
      state_enum: "CALIBRATED_IDLE",
      session_elapsed_s: 12.4,
      current_pattern_name: "Wave",
    });

    // Poll 2 (gets CALIBRATED_IDLE, should trigger history save)
    await act(async () => {
      vi.advanceTimersByTime(50);
    });

    expect(saveHistoryMock).toHaveBeenCalledWith({
      duration_s: 12,
      pattern_name: "Wave",
      end_state: "CALIBRATED_IDLE",
    });
  });
});
