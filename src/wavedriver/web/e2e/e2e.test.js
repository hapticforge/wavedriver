import { test, expect } from '@playwright/test';

test.describe('Wavedriver E2E flows (Mock Mode)', () => {
  test('should go through calibration, start a pattern, adjust controls, and trigger E-Stop', async ({ page }) => {
    // 1. Load the application
    await page.goto('/');

    // Check that Startup Modal is visible at safety onboarding step
    await expect(page.locator('.modal-title')).toHaveText('Safety Onboarding');
    
    // Check the safety checkboxes
    const checkboxes = page.locator('input[type="checkbox"]');
    await expect(checkboxes).toHaveCount(3);
    for (let i = 0; i < 3; i++) {
      await checkboxes.nth(i).check();
    }

    // Continue to connection step
    await page.locator('button:has-text("Continue to Connection")').click();

    // Verify Connect Device screen is active
    await expect(page.locator('.modal-title')).toHaveText('Connect Device');
    const portPicker = page.locator('#port-picker');
    await expect(portPicker).toBeVisible();
    await portPicker.selectOption('mock');

    // Click Connect & Calibrate
    await page.locator('button:has-text("Connect & Calibrate")').click();

    // The modal should display success screen once calibration completes
    await expect(page.locator('.modal-title')).toHaveText('Calibration Successful', { timeout: 10000 });

    // Click Enter Dashboard to close the modal
    await page.locator('button:has-text("Enter Dashboard")').click();

    // The modal overlay should be gone
    await expect(page.locator('.modal-overlay')).toHaveCount(0);

    // Verify we are now Calibrated Idle (check telemetry panel state)
    const stateBadge = page.locator('.badge-state').last();
    await expect(stateBadge).toContainText('Calibrated & Idle');

    // 2. Select a pattern and start it
    // Select the "Wave" option from the select widget
    await page.locator('.select-widget').first().selectOption('Wave');

    // Click the main start button
    const startBtn = page.locator('button:has-text("Start Stimulation")');
    await startBtn.click();

    // Verify state transition to Running
    await expect(stateBadge).toContainText('Running');

    // 3. Adjust sliders (e.g., Frequency)
    // Find the Frequency slider and change value
    const freqSlider = page.locator('input[type="range"]').first();
    await freqSlider.focus();
    await page.keyboard.press('ArrowRight');
    await freqSlider.blur();
    
    // 4. Trigger E-Stop
    // Press Space bar to E-Stop (use keyboard hook)
    await page.keyboard.press('Space');

    // State should now be Estop
    await expect(stateBadge).toContainText('Estop');

    // Telemetry should display E-STOP error message
    await expect(page.locator('.banner-estop')).toBeVisible();

    // Click Clear E-STOP button to recover
    const recoverBtn = page.locator('button:has-text("Resume — Clear Emergency Stop")');
    await recoverBtn.click();

    // State should go back to Calibrated Idle
    await expect(stateBadge).toContainText('Calibrated & Idle');
  });
});
