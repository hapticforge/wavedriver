#!/bin/bash
# Run Wavedriver TUI in simulation mode (offline demo)
export PYTHONPATH="src"
exec .venv/bin/python src/wavedriver/main.py --mock "$@"
