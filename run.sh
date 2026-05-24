#!/bin/bash
# Run Wavedriver TUI connected to actual Orca 6 hardware
export PYTHONPATH="src"
exec .venv/bin/python src/wavedriver/main.py "$@"
