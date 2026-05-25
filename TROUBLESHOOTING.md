# Troubleshooting

## Device not detected / port not found

**Symptom**: "No device found" in the startup screen, or connecting produces no telemetry.

1. Run `uv run wavedriver --list-ports` and check whether your adapter appears. If nothing shows, the OS hasn't recognised the USB-serial adapter — check the cable and try a different USB port.
2. On Linux, your user may not be in the `dialout` group: `sudo usermod -aG dialout $USER`, then log out and back in.
3. Make sure no other application (e.g. another terminal session, RealTerm) has the port open. Only one process can hold a serial port at a time.
4. The default port is `/dev/ttyUSB0`. If your adapter appears as `/dev/ttyACM0` or `COM3`, pass `--port /dev/ttyACM0` or select it in the startup screen.
5. The default baud rate is 19200. If your Orca 6 firmware uses a different rate, pass `--baud <rate>`.

---

## Calibration fails or gets stuck

**Symptom**: Calibration starts but never completes, the motor stalls, or "Calibration failed" appears.

1. **Stand clear during calibration.** The motor moves to both physical end-stops at low force (60 N hardware limit) to measure the stroke. Any obstruction causes it to stall and fail.
2. If the motor stalls partway, press **Space** (e-stop), then **Z** to retry. Make sure the travel path is unobstructed.
3. If calibration completes but the measured stroke looks wrong (e.g. 5 mm instead of 150 mm), the end-stop detection may have tripped early — reduce any external load and retry.
4. A fresh power cycle of the Orca 6 before calibrating usually resolves intermittent issues.

---

## Force limit trips unexpectedly

**Symptom**: The motor stops frequently with "Force limit reached" even at low stroke or speed.

1. Lower the frequency or stroke — the peak force scales with speed squared. Small reductions have a large effect.
2. Increase the Safety Force slider (up to 60 N maximum). The default 55 N is conservative; 60 N is the hardware limit.
3. Check that the device is not experiencing abnormal resistance. Friction from a dry coupling or mechanical binding will increase the apparent force.
4. In mock/simulation mode, force readings are approximate — the simulated model is calibrated for typical use, not precise force reproduction.

---

## Motor stops after a few seconds without touching anything

**Symptom**: Motor starts then stops on its own.

1. The **deadman watchdog** stops the motor if the app stops calling `get_telemetry()` for 5 seconds. This can happen if the computer goes to sleep, the process is paused (e.g. debugger), or the UI is frozen. Keep the app in the foreground.
2. The **session timer** may have expired. Check the session remaining counter in the telemetry panel. Increase or disable it via the Session Timer slider.
3. A **communications watchdog** e-stop fires if the serial link drops for 500 ms. Check the USB cable is secure.

---

## App window is grey / blank on launch

**Symptom**: The desktop window opens but shows a blank or grey page.

1. The frontend bundle may be missing or stale. Run:
   ```bash
   cd src/wavedriver/web && npm run build && cd ../../..
   uv run wavedriver --mock
   ```
2. If the build succeeds but the window is still blank, try `uv run wavedriver --dev` to use the Vite dev server and check the browser console for errors.
3. On some Linux systems, `PYWEBVIEW_GUI` must be set to `qt` — this is done automatically, but check that PyQt6 is installed: `uv run python -c "import PyQt6"`.

---

## Video sync / MP4 playback not working

**Symptom**: Video player shows a black/blank box after loading a file.

1. H.264 MP4 decoding depends on the system's QtWebEngine build. On most Arch Linux systems with `qt6-webengine`, H.264 is supported.
2. If your file still won't play, convert it to WebM:
   ```bash
   ffmpeg -i input.mp4 -c:v libvpx-vp9 -b:v 0 -crf 33 -c:a libopus output.webm
   ```
3. The video is served via a local HTTP server on a random port — make sure no local firewall blocks loopback connections.

---

## Resetting all data

To wipe all saved settings, presets, and session history:

```bash
rm -rf ~/.config/wavedriver/
```

The app will recreate defaults on next launch.
