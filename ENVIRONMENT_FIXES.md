# Agathos Environment Portability Fixes

**Date:** 2026-04-09  
**Context:** Fixes applied to ensure Agathos startup works across dev, production, and fresh install environments.

## Summary of Fixes

### 1. agathos/bin/agathos-control (Shell Script)

#### Problem
Script was hardcoded to dev environment and used stale filename references.

#### Fixes Applied
- **Line 16:** Fixed `argus.py` → `agathos.py` (file was renamed)
- **Lines 293, 294, 313, 314:** Fixed function names `argus_launchd_install/uninstall` → `agathos_launchd_install/uninstall`
- **Lines 99-122:** Added `locate_agathos_root()` function for cross-environment detection
- **Lines 154-175:** Rewrote `start_argus()` with:
  - `AGATHOS_ROOT` environment variable export
  - Dual import strategy (module import + fallback)
  - Better error messages showing all checked paths

#### Environment Detection Strategy
The control script now searches for agathos in this priority order:
1. **Dev environment:** `$SCRIPT_DIR/../` (agathos.py and __init__.py present)
2. **Parent of dev:** `$SCRIPT_DIR/../../agathos/` (if bin/ is inside agathos/)
3. **Production:** `$HOME/.hermes/hermes-agent/agathos/`
4. **Environment override:** `$HERMES_AGENT/agathos/`

#### Runtime Execution
Uses Python `-c` with dynamic path setup:
```python
# Add agathos parent to PYTHONPATH
sys.path.insert(0, parent_of_agathos)
os.chdir(parent_of_agathos)

# Primary import strategy
from agathos.agathos import main
main()

# Fallback if package import fails
sys.path.insert(0, agathos_root)
import agathos
from agathos.agathos import main
main()
```

### 2. agathos/agathos.py (Main Module)

#### Problem
Missing import and variable name bug prevented startup.

#### Fixes Applied
- **Line 215:** Added `_get_agathos_pid_path` to imports from `daemon_mgmt`
- **Line 1128:** Fixed `argus = Argus()` → `daemon = Agathos()` (class was renamed, variable was inconsistent)
- **Line 1141:** Comment updated "Run Argus" → "Run Agathos"

### 3. agathos/__init__.py (Package Exports)

#### Problem
`_get_agathos_pid_path` was not exported from package.

#### Fixes Applied
- **Line 13:** Added `_get_agathos_pid_path` to imports
- **Line 105:** Added `_get_agathos_pid_path` to `__all__` list

## Environment Assumptions

### Required for All Environments
1. **Python 3.11+** - Checked by `validate_python()` function
2. **Write access to `~/hermes/`** - For logs, data, PID files
3. **agathos package discoverable** - Via dev path, production path, or $HERMES_AGENT

### Dev Environment Structure
```
~/Projects/hermes-dev/
├── agathos/
│   ├── __init__.py
│   ├── agathos.py
│   ├── bin/
│   │   └── agathos-control
│   └── ...
└── .local/venv/bin/python3 (priority 2)
```

### Production Environment Structure
```
~/.hermes/
├── hermes-agent/
│   ├── venv/bin/python3 (priority 3)
│   └── agathos/ (priority 3 for package)
└── ...
```

### Override Mechanisms
- `HERMES_VENV` - Use specific virtual environment
- `HERMES_AGENT` - Use specific hermes-agent path for agathos

## Testing

### Portability Test Suite
```bash
cd ~/Projects/hermes-dev
source .local/venv/bin/activate
python agathos/tests/test_environment_portability.py
```

**Expected output:**
```
======================================================================
AGATHOS ENVIRONMENT PORTABILITY TEST SUITE
======================================================================
...
Results: 18 passed, 0 failed
✓ All portability tests passed!
======================================================================
```

### Manual Verification Commands
```bash
# Test control script can find agathos
~/Projects/hermes-dev/agathos/bin/agathos-control status

# Test start/stop cycle
~/Projects/hermes-dev/agathos/bin/agathos-control restart

# Verify running
~/Projects/hermes-dev/agathos/bin/agathos-control status
```

## Compatibility Notes

### What Works
- ✅ Dev environment (~/Projects/hermes-dev)
- ✅ Production venv (~/.hermes/hermes-agent/venv)
- ✅ System Python 3.11+ (fallback)
- ✅ Relative imports in agathos modules
- ✅ All daemon_mgmt exports

### What Requires Setup
- Direct `import agathos` without PYTHONPATH setup requires agathos to be installed as a package (pip install -e .)
- Fresh installs need either dev path or production path structure

### Backward Compatibility
- ✅ Still supports `HERMES_VENV` override
- ✅ Still supports `AGATHOS_PYTHON` export
- ✅ PID file format unchanged
- ✅ Log directory unchanged

## Files Modified

| File | Lines Changed | Purpose |
|------|--------------|---------|
| `agathos/bin/agathos-control` | +70/-10 | Cross-env detection, fallback imports |
| `agathos/agathos.py` | +2/-2 | Missing import, variable fix |
| `agathos/__init__.py` | +2 | Package exports |
| `agathos/tests/test_environment_portability.py` | +131 | New test suite |

## Rollback Plan

If issues arise, restore from git:
```bash
git checkout -- agathos/bin/agathos-control agathos/agathos.py agathos/__init__.py
```

Then verify original state:
```bash
~/Projects/hermes-dev/agathos/bin/agathos-control status
```
