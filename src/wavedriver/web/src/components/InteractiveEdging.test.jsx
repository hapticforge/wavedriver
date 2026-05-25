import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { InteractiveEdging } from './InteractiveEdging';

describe('InteractiveEdging Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it('triggers cooldown and reduces intensity on clicking ALMOST!', () => {
    const mockIntensityChange = vi.fn();
    render(
      <InteractiveEdging
        isRunning={true}
        intensityPct={80}
        onIntensityChange={mockIntensityChange}
      />
    );

    const button = screen.getByText('ALMOST!');
    fireEvent.click(button);

    // Should immediately change intensity to 10%
    expect(mockIntensityChange).toHaveBeenCalledWith(10);
    expect(screen.getByText(/COOLING DOWN/)).toBeDefined();
  });
});
