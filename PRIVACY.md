# Privacy

Wavedriver is local-first software. This is a binding commitment, not a marketing claim.

## What is stored and where

All data Wavedriver writes stays on your computer, under `~/.config/wavedriver/`:

| File | Contents | Notes |
|---|---|---|
| `session.json` | Safety force limit, session timer, history on/off | Restored at startup |
| `presets.json` | Your saved pattern profiles | Restored at startup |
| `history.jsonl` | Timestamped log of completed sessions (pattern, duration, end state) | Capped at 500 entries; can be cleared or disabled in the History panel |

## What is never transmitted

- No analytics, telemetry, or crash reports leave your device.
- No network connections are made at any time during normal operation.
- No account, login, or cloud service is required or used.

## Clearing your data

- **Session history**: open the History panel (footer) → trash icon to delete all records, or uncheck "Record" to stop logging new ones.
- **All data**: delete `~/.config/wavedriver/` to reset to factory defaults.

## Log files

Wavedriver logs operational messages to the terminal at `INFO` level. Logs contain device state (connection, calibration, errors) but never record session parameters (pattern names, intensity, duration) at default log level.
