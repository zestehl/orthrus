# Justfile for Agathos — Agent Guardian & Health Oversight System
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
    uv run ruff check src/agathos
    uv run ruff format --check src/agathos

# Run linting with auto-fix
lint-fix:
    uv run ruff check --fix src/agathos
    uv run ruff format src/agathos

# Run type checking
typecheck:
    uv run mypy src/agathos

# Run tests
test:
    uv run pytest tests/ -v

# Run POSIX compliance checks
test-posix:
    uv run python tests/run_posix_compliance_check.py

# Run audit for stale references
audit:
    uv run agathos-audit --strict

# Run all checks
check: lint typecheck test-posix audit
    @echo "✓ All checks passed"

# Start agathos daemon
start:
    uv run agathos

# Run interactive setup
setup-wizard:
    uv run agathos-setup

# Check daemon status
status:
    uv run agathos status

# Clean build artifacts
clean:
    rm -rf build/
    rm -rf dist/
    rm -rf .eggs/
    rm -rf src/*.egg-info
    rm -rf .pytest_cache
    rm -rf .mypy_cache
    rm -rf .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Update lock files
lock:
    uv pip compile pyproject.toml -o requirements.lock
    uv pip compile pyproject.toml --extra dev -o requirements-dev.lock

# Sync dependencies from lock files
sync:
    uv pip sync requirements-dev.lock
    uv pip install -e .
