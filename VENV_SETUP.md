# ARGUS Virtual Environment Setup Guide

ARGUS is designed to work seamlessly across multiple virtual environment contexts. This guide explains how to configure and run ARGUS in isolated Python environments.

## Overview

ARGUS now includes comprehensive virtual environment support through the `venv_utils.py` module. This ensures:

- **Context Preservation**: Subprocesses inherit the correct Python environment
- **Hermes Integration**: Automatically finds and uses the hermes-agent venv
- **Cross-Platform**: Works on macOS, Linux, and Windows
- **Flexible Deployment**: Supports dev, production, and custom venv layouts

## Quick Start

### Option 1: Using Dev Venv (Recommended for Development)

```bash
# Navigate to dev environment
cd ~/Projects/hermes-dev

# Activate dev venv
source .local/venv/bin/activate

# Run argus directly (uses venv Python automatically)
python -m argus.argus

# Or use control script (auto-detects venv)
./argus/bin/argus-control start
```

### Option 2: Using Production Hermes Venv

```bash
# ARGUS auto-detects ~/.hermes/hermes-agent/venv
# No manual activation required

~/hermes/scripts/watcher/bin/argus-control start
```

### Option 3: Custom Venv Location

```bash
# Set environment variable to override
export HERMES_VENV=/path/to/your/venv

argus-control start
```

## Python Detection Priority

The `argus-control` script and `venv_utils` module use this priority order:

1. **`HERMES_VENV`** environment variable (if set and contains Python 3.11+)
2. **`~/Projects/hermes-dev/.local/venv`** (dev environment)
3. **`~/.hermes/hermes-agent/venv`** (production install)
4. **System `python3`** (must be Python 3.11+)

## Virtual Environment Utilities

The `venv_utils.py` module provides these key functions:

### Detection Functions

```python
from argus.venv_utils import (
    is_running_in_venv,
    get_venv_path,
    detect_hermes_venv,
)

# Check if we're in a venv
if is_running_in_venv():
    print("Running inside virtual environment")

# Get current venv path
venv_path = get_venv_path()  # Returns Path or None

# Find hermes venv
hermes_venv = detect_hermes_venv()  # Returns Path or None
```

### Python Resolution

```python
from argus.venv_utils import (
    get_venv_python,
    get_hermes_python,
    resolve_venv_python,
)

# Get Python for a specific venv
python_path = get_venv_python('/path/to/venv')

# Get the best hermes-compatible Python
hermes_python = get_hermes_python()

# Resolve any Python command
resolved = resolve_venv_python('python3')  # Returns absolute path
```

### Environment Building

```python
from argus.venv_utils import (
    build_agathos_subprocess_env,
    get_agathos_venv_paths,
)

# Build environment for subprocess calls
env = build_agathos_subprocess_env()
# Returns: dict with PATH, VIRTUAL_ENV, HERMES_HOME, etc.

# Get PATH entries for ARGUS operations
paths = get_agathos_venv_paths()
# Returns: ['/path/to/venv/bin', '/usr/local/bin', ...]
```

## Subprocess Context Preservation

ARGUS actions now automatically preserve venv context:

```python
# In actions.py - automatically uses venv-aware env
from argus.actions import safe_subprocess

# This subprocess will have access to the same venv
result = safe_subprocess(['python3', '-c', 'import hermes_state'])
```

The `build_agathos_subprocess_env()` function ensures:
- `PATH` includes venv bin directory at the front
- `VIRTUAL_ENV` is set correctly
- `HERMES_HOME` is preserved
- `HOME` is set for file operations

## Setting Up a Fresh Venv for Argus

If you need to create a new isolated environment for ARGUS testing:

```bash
# Create venv
python3.12 -m venv ~/hermes/argus-venv

# Activate
source ~/hermes/argus-venv/bin/activate

# Install dependencies (minimal for Argus)
pip install python-dotenv pyyaml rich tenacity

# Set environment variable
export HERMES_VENV=~/hermes/argus-venv

# Run Argus
argus-control start
```

## Launchd Service with Venv

When installing as a launchd service, the plist automatically includes:

```xml
<key>EnvironmentVariables</key>
<dict>
    <key>PATH</key>
    <string>/path/to/venv/bin:/opt/homebrew/bin:/usr/local/bin:...</string>
    <key>HERMES_HOME</key>
    <string>~/.hermes</string>
    <key>VIRTUAL_ENV</key>
    <string>/path/to/venv</string>
</dict>
```

The `generate_argus_launchd_plist()` function in `argus.py` automatically detects:
- Venv location (`~/.hermes/hermes-agent/venv`)
- Python executable from venv
- Full PATH with venv bin at front

## Testing Venv Support

Run the venv utilities test:

```bash
cd ~/Projects/hermes-dev

# Activate dev venv
source .local/venv/bin/activate

# Test venv detection
python -c "
from argus.venv_utils import *
print('In venv:', is_running_in_venv())
print('Venv path:', get_venv_path())
print('Hermes venv:', detect_hermes_venv())
print('Hermes python:', get_hermes_python())
"

# Verify subprocess context
python -c "
from argus.venv_utils import build_agathos_subprocess_env
import os

env = build_agathos_subprocess_env()
print('PATH:', env['PATH'][:100], '...')
print('VIRTUAL_ENV:', env.get('VIRTUAL_ENV', 'None'))
print('HERMES_HOME:', env.get('HERMES_HOME', 'None'))
"
```

## Troubleshooting

### Issue: "No suitable Python (3.11+) found"

**Cause**: Argus requires Python 3.11+ but none found in expected locations.

**Solution**:
```bash
# Install Python 3.11+ via Homebrew
brew install python@3.12

# Or specify custom venv
export HERMES_VENV=/path/to/python3.12/venv
argus-control start
```

### Issue: ModuleNotFoundError for hermes modules

**Cause**: Subprocess not using correct venv context.

**Solution**: Verify venv detection:
```bash
python -c "from argus.venv_utils import get_hermes_python; print(get_hermes_python())"
```

Should output path to venv Python, not system python3.

### Issue: Cron jobs fail in sandboxed environment

**Cause**: Cron agents run with minimal PATH in restricted context.

**Solution**: The `safe_subprocess()` function in `actions.py` now uses `build_agathos_subprocess_env()` which ensures full PATH propagation including venv paths.

## Configuration Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `HERMES_VENV` | Override venv location | `/opt/hermes/venv` |
| `VIRTUAL_ENV` | Standard venv indicator (auto-set) | `~/.hermes/hermes-agent/venv` |
| `HERMES_HOME` | Hermes config directory | `~/.hermes` |
| `PATH` | Search path with venv bin | `/venv/bin:/usr/local/bin:...` |

## Migration from Non-Venv Setup

If you previously ran ARGUS without virtual environments:

1. **Backup your database**:
   ```bash
   cp ~/hermes/data/watcher/argus.db ~/hermes/data/watcher/argus.db.backup
   ```

2. **Install to production venv**:
   ```bash
   # Dependencies are already in hermes-agent venv
   # Just ensure argus/ is in PYTHONPATH or ~/.hermes/hermes-agent/
   ```

3. **Restart with new control script**:
   ```bash
   argus-control restart
   ```

The new control script auto-detects the hermes-agent venv and uses it automatically.

## Advanced: Multiple Venv Support

For testing across multiple Python versions:

```bash
# Create test matrix
for py in 3.11 3.12 3.13; do
    python${py} -m venv ~/hermes/test-venv-${py}
done

# Test with specific version
export HERMES_VENV=~/hermes/test-venv-3.12
argus-control start
argus-control status
argus-control stop
```

## API Reference

### venv_utils.py

| Function | Returns | Description |
|----------|---------|-------------|
| `is_running_in_venv()` | `bool` | Check if in venv |
| `get_venv_path()` | `Path \| None` | Get current venv root |
| `get_venv_bin_dir(path)` | `Path` | Get bin/Scripts directory |
| `get_venv_python(path)` | `str` | Get Python executable path |
| `detect_hermes_venv()` | `Path \| None` | Find hermes venv |
| `get_hermes_python()` | `str` | Get best hermes Python |
| `build_agathos_subprocess_env()` | `dict` | Build env for subprocess |
| `resolve_venv_python(cmd)` | `str` | Resolve Python command |

## See Also

- `actions.py` - Uses venv utilities for subprocess calls
- `argus-control` - Shell script with venv detection
- `argus.py` - Launchd plist generation with venv support
