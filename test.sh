#!/bin/bash
# Run driver unit tests
export PYTHONPATH="src"
exec .venv/bin/python -m unittest tests/test_driver.py "$@"
