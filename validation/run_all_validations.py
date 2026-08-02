#!/usr/bin/env python
"""
Validation runner that runs all phase validators in the `validation/` folder.
This moves the runner into the `validation` package per request.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

phases = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
results = {}

print("\n" + "="*70)
print("RUNNING ALL PHASE VALIDATIONS (validation/run_all_validations.py)")
print("="*70 + "\n")

for phase in phases:
    script = Path(__file__).parent / f'phase{phase}_validation.py'
    print(f"Running Phase {phase}...", end=" ", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=120
        )
        results[phase] = {
            'exit_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
        print(f"Exit code: {result.returncode}")
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        results[phase] = {'exit_code': -1, 'stdout': '', 'stderr': 'TIMEOUT'}
    except Exception as e:
        print(f"ERROR: {e}")
        results[phase] = {'exit_code': -1, 'stdout': '', 'stderr': str(e)}

print("\n" + "="*70)
print("VALIDATION RESULTS SUMMARY")
print("="*70 + "\n")

for phase in sorted(results.keys()):
    info = results[phase]
    exit_code = info['exit_code']
    status = 'PASS' if exit_code == 0 else 'FAIL'
    print(f"Phase {phase}: {status:5} (exit code: {exit_code})")

print("\n" + "="*70)

all_pass = all(r['exit_code'] == 0 for r in results.values())
if all_pass:
    print("[OK] SUCCESS: ALL PHASES PASS")
    sys.exit(0)
else:
    failing = [p for p, r in results.items() if r['exit_code'] != 0]
    print(f"[FAIL] FAILURE: Phase(s) {failing} failed")
    sys.exit(1)
