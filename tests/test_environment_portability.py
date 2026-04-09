#!/usr/bin/env python3
"""
Environment Portability Test Suite for Agathos
Tests that fixes work across dev, production, and fresh install environments.
"""

import os
import sys
import subprocess
from pathlib import Path


def get_project_root():
    """Determine project root based on test file location."""
    test_file = Path(__file__).resolve()
    # tests/ is under agathos/, so project root is test_file.parent.parent.parent
    return test_file.parent.parent.parent


def test_agathos_imports():
    """Test that agathos can be imported with various path configurations."""
    results = []
    
    # Test 1: Direct import (works if installed as package - optional)
    try:
        import agathos
        results.append(("Direct import (installed)", True, agathos.__file__))
    except ImportError as e:
        # This is OK - agathos may not be installed as global package
        results.append(("Direct import (installed)", True, "Not installed (OK)"))
    
    # Test 2: Import with project root in path (dev mode - REQUIRED)
    project_root = get_project_root()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        import agathos
        results.append(("Dev path import (REQUIRED)", True, agathos.__file__))
    except ImportError as e:
        results.append(("Dev path import (REQUIRED)", False, str(e)))
    
    return results


def test_daemon_mgmt_exports():
    """Verify all required daemon_mgmt functions are exported from agathos package."""
    project_root = get_project_root()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    import agathos
    
    required = [
        "_get_agathos_pid_path",
        "write_agathos_pid_file",
        "remove_agathos_pid_file",
        "is_agathos_running",
        "agathos_launchd_install",
        "agathos_launchd_uninstall",
    ]
    
    results = []
    for name in required:
        try:
            obj = getattr(agathos, name, None)
            results.append((name, obj is not None, type(obj).__name__ if obj else None))
        except Exception as e:
            results.append((name, False, str(e)))
    
    return results


def test_agathos_main():
    """Verify main() can be imported and has correct signature."""
    project_root = get_project_root()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    try:
        from agathos.agathos import main
        import inspect
        sig = inspect.signature(main)
        return [("main() import", True, str(sig))]
    except Exception as e:
        return [("main() import", False, str(e))]


def test_control_script_exists():
    """Verify agathos-control script exists and is executable."""
    project_root = get_project_root()
    control_script = project_root / "agathos" / "bin" / "agathos-control"
    
    exists = control_script.exists()
    executable = os.access(control_script, os.X_OK) if exists else False
    
    return [
        ("Control script exists", exists, str(control_script)),
        ("Control script executable", executable, None),
    ]


def test_control_script_portability():
    """Test that control script has portability functions."""
    project_root = get_project_root()
    control_script = project_root / "agathos" / "bin" / "agathos-control"
    
    content = control_script.read_text()
    
    checks = [
        ("locate_agathos_root function", "locate_agathos_root" in content),
        ("AGATHOS_ROOT env var", "AGATHOS_ROOT" in content),
        ("Dev path check", "SCRIPT_DIR/../" in content or "dirname" in content),
        ("Production path check", "hermes-agent/agathos" in content),
        ("Fallback import pattern", "except ImportError" in content),
    ]
    
    return [(name, result, None) for name, result in checks]


def test_no_stale_argus_references():
    """Verify no stale 'argus' references in critical files."""
    project_root = get_project_root()
    
    # Files to check for stale references
    critical_files = [
        project_root / "agathos" / "bin" / "agathos-control",
        project_root / "agathos" / "agathos.py",
    ]
    
    results = []
    stale_patterns = ["from argus import", "argus_launchd_install", "argus_launchd_uninstall"]
    
    for filepath in critical_files:
        if not filepath.exists():
            results.append((f"{filepath.name} exists", False, "File not found"))
            continue
            
        content = filepath.read_text()
        found_stale = []
        for pattern in stale_patterns:
            if pattern in content:
                found_stale.append(pattern)
        
        results.append((
            f"{filepath.name} - no stale refs",
            len(found_stale) == 0,
            ", ".join(found_stale) if found_stale else None
        ))
    
    return results


def run_all_tests():
    """Run all portability tests."""
    all_tests = [
        ("Agathos Imports", test_agathos_imports),
        ("Daemon Mgmt Exports", test_daemon_mgmt_exports),
        ("Agathos Main Function", test_agathos_main),
        ("Control Script Exists", test_control_script_exists),
        ("Control Script Portability", test_control_script_portability),
        ("No Stale References", test_no_stale_argus_references),
    ]
    
    print("=" * 70)
    print("AGATHOS ENVIRONMENT PORTABILITY TEST SUITE")
    print("=" * 70)
    print(f"Project root: {get_project_root()}")
    print(f"Python: {sys.executable}")
    print(f"Platform: {sys.platform}")
    print()
    
    total_passed = 0
    total_failed = 0
    
    for test_name, test_func in all_tests:
        print(f"\n--- {test_name} ---")
        try:
            results = test_func()
            for item, passed, detail in results:
                status = "✓ PASS" if passed else "✗ FAIL"
                detail_str = f" ({detail})" if detail else ""
                print(f"  {status}: {item}{detail_str}")
                if passed:
                    total_passed += 1
                else:
                    total_failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            total_failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {total_passed} passed, {total_failed} failed")
    if total_failed == 0:
        print("✓ All portability tests passed!")
    else:
        print("✗ Some tests failed - review above")
    print("=" * 70)
    
    return total_failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
