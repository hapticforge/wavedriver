import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useSettings } from './useSettings';

describe('useSettings', () => {
  let mockSendCommand;

  beforeEach(() => {
    mockSendCommand = vi.fn();
    delete window.pywebview;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads session and presets when apiReady becomes true', async () => {
    const loadSessionMock = vi.fn().mockResolvedValue({
      safety_force_n: 45.0,
      max_session_s: 1200,
    });
    const loadPresetsMock = vi.fn().mockResolvedValue({
      '0': { name: 'Thrust Preset', pattern_name: 'Thrust' },
    });

    window.pywebview = {
      api: {
        load_session: loadSessionMock,
        load_presets: loadPresetsMock,
        save_session: vi.fn(),
      },
    };

    const { result, rerender } = renderHook(
      ({ apiReady }) => useSettings({ apiReady, sendCommand: mockSendCommand }),
      { initialProps: { apiReady: false } }
    );

    expect(result.current.safetyForceN).toBe(55.0);

    // Make apiReady true
    rerender({ apiReady: true });

    // Flush promises
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(loadSessionMock).toHaveBeenCalled();
    expect(loadPresetsMock).toHaveBeenCalled();
    expect(result.current.safetyForceN).toBe(45.0);
    expect(result.current.maxSessionS).toBe(1200);
    expect(mockSendCommand).toHaveBeenCalledWith('set_safety_limit', { limit_mN: 45000 });
    expect(mockSendCommand).toHaveBeenCalledWith('set_max_session', { max_session_s: 1200 });
    expect(result.current.presets[0].name).toBe('Thrust Preset');
  });

  it('saves preset successfully', async () => {
    const savePresetsMock = vi.fn();
    window.pywebview = {
      api: {
        load_session: vi.fn().mockResolvedValue({}),
        load_presets: vi.fn().mockResolvedValue({}),
        save_presets: savePresetsMock,
        save_session: vi.fn(),
      },
    };

    const { result } = renderHook(() =>
      useSettings({ apiReady: true, sendCommand: mockSendCommand })
    );

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await act(async () => {
      result.current.savePreset(1, 'My Custom Wave');
    });

    expect(result.current.presets[1].name).toBe('My Custom Wave');
    expect(savePresetsMock).toHaveBeenCalled();
  });
});
