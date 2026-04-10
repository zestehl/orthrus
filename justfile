# Justfile for Orthrus — ML Data Capture for Hermes Agent

# Install just: https://github.com/casey/just

# Default recipe — show available commands
default:
    @just --list

# Setup project (create venv and install)
setup:
    uv venv
    uv pip install -e ".[dev]"

# Install in development mode with all dev dependencies
dev:
    uv pip install -e ".[dev]"

# Run linting
lint:
    uv run ruff check src/orthrus
    uv run ruff format --check src/orthrus

# Run linting with auto-fix
lint-fix:
    uv run ruff check --fix src/orthrus
    uv run ruff format src/orthrus

# Run type checking
typecheck:
    uv run mypy src/orthrus

# Run tests
test:
    uv run pytest tests/ -v

# Run all checks
check: lint typecheck test
    @echo "All checks passed"

# Clean build artifacts
clean:
    rm -rf build/
    rm -rf dist/
    rm -rf .eggs/
    rm -rf src/*.egg-info
    rm -rf .pytest_cache
    rm -rf .mypy_cache
    rm -rf .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete

# Update lock files
lock:
    uv pip compile pyproject.toml -o requirements.lock
    uv pip compile pyproject.toml --extra dev -o requirements-dev.lock

# Sync dependencies from lock files
sync:
    uv pip sync requirements-dev.lock
    uv pip install -e .
