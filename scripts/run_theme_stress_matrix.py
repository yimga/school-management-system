#!/usr/bin/env python3
"""
Theme stress-test matrix: run theme visibility checks and fail if any ERROR.
Use from CI or run_phase_checks. Exit 0 if all pass, 1 if any ERROR.
"""

import os
import subprocess
import sys


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(root)
    script = os.path.join(root, "scripts", "dev", "test_theme_visibility.py")
    if not os.path.isfile(script):
        print("run_theme_stress_matrix: test_theme_visibility.py not found")
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=root,
    )
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        print(out)
        sys.exit(result.returncode)
    if "ERROR" in out:
        print(out)
        print("Theme stress matrix: FAIL (ERROR found in theme visibility check)")
        sys.exit(1)
    print("Theme stress matrix: OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
