# Wavedriver development tasks — run with `just <target>`

lint:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

typecheck:
    uv run mypy src/wavedriver/

test:
    uv run --with pytest pytest tests/

build-web:
    npm run build --prefix src/wavedriver/web

run:
    uv run wavedriver

run-mock:
    uv run wavedriver --mock
