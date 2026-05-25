# Contributing to Wavedriver

## Setup

**Prerequisites:** Python 3.12+, [uv](https://github.com/astral-sh/uv), Node.js 20+, [just](https://github.com/casey/just)

```bash
# Install Python dependencies
uv sync --dev

# Install frontend dependencies
npm ci --prefix src/wavedriver/web

# Install pre-commit hooks
uv run pre-commit install
```

## Development workflow

All common tasks are in the `justfile`:

| Command | What it does |
|---|---|
| `just lint` | Run ruff lint + format check |
| `just typecheck` | Run mypy strict |
| `just test` | Run the test suite |
| `just build-web` | Build the frontend bundle |
| `just run` | Launch the app (requires hardware) |
| `just run-mock` | Launch in mock/simulation mode |

Run all checks before opening a PR:
```bash
just lint && just typecheck && just test
```

## Code standards

- **Formatting:** ruff (line length 100, double quotes). Run `uv run ruff format src/ tests/` to fix.
- **Linting:** ruff with E/F/I/UP/W rules. Run `uv run ruff check --fix src/ tests/` to fix.
- **Types:** mypy strict. Every function needs type annotations. Use `Any` sparingly and document why.
- **Tests:** pytest. New backend features need tests. Run `just test` to verify.
- **Comments:** Only when the *why* is non-obvious — a constraint, workaround, or safety invariant.

## Safety

This is a powered device in contact with the body. Any change to the control loop, safety limits, or calibration logic requires:

1. A description of the failure mode the change addresses or creates.
2. A test that demonstrates the safety property holds.
3. An update to `SAFETY.md` if the change affects documented safety layers.

Never weaken a safety check without a documented, reviewed justification.

## Project structure

```
src/wavedriver/
  main.py             # PyWebView bridge and app entry point
  motor_controller.py # Multi-rate control loop (500 Hz / 20 Hz)
  patterns.py         # Motion pattern library
  mock_actuator.py    # Physics simulation for development
  web/                # React frontend (Vite)
tests/
  test_driver.py      # Backend test suite
```

## Commit messages

Use the imperative mood, keep the subject line under 72 characters, and explain *why* in the body when the change isn't obvious from the diff.

## Pull requests

- One logical change per PR.
- Include a brief description of what changed and why.
- All CI checks must pass.
