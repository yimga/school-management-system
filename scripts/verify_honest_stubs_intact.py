"""Wave Q6 (v3.95.2 — 2026-05-26) — Honest-stub immutability verifier.

CI gate. Asserts every counsel-blocked `# honest-stub: write-path
counsel-blocked` marker stays exactly where the v3.34.0 docket placed it.

If anyone accidentally removes a stub (or fills it in with real write code
without counsel signoff), this verifier fails the build.

The expected manifest lives below as a frozen dict[file_path -> count]. To
intentionally update it, the operator MUST:
1. Get counsel signoff (recorded in `docs/COUNSEL_DOCKET.md`).
2. Update the manifest below with the new expected count.
3. Commit both changes in the same PR.

Exit codes:
0 — all stubs in place
1 — stub count diverged (CI fails)
"""

from __future__ import annotations

import os
import sys
from typing import Any


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, ".."))


# Expected stub count per file. Counsel-frozen.
_EXPECTED_STUBS: dict[str, int] = {
    # 3 markers: 1 in docstring + 2 in code branches.
    "companion-docker/app/extractors/skyward.py": 3,
    # 3 markers: 1 in docstring + 2 in code branches.
    "companion-docker/app/extractors/facts.py": 3,
    # Extension write surfaces restored as honest stubs (read extractors live).
    "companion-extension/src/vendors/facts.ts": 3,
    "companion-extension/src/vendors/skyward.ts": 3,
}


_STUB_MARKER = "honest-stub: write-path counsel-blocked"


def _count_stubs_in_file(path: str) -> int:
    if not os.path.exists(path):
        return -1  # signal missing file
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if _STUB_MARKER in line)


def main() -> int:
    failures: list[str] = []
    for rel_path, expected in _EXPECTED_STUBS.items():
        full = os.path.normpath(os.path.join(REPO_ROOT, rel_path))
        actual = _count_stubs_in_file(full)
        if actual == -1:
            failures.append(f"MISSING {rel_path}")
            print(f"FAIL {rel_path}: file MISSING (counsel-blocked stub file removed)")
            continue
        if actual != expected:
            failures.append(f"{rel_path}: expected {expected} stubs, got {actual}")
            print(f"FAIL {rel_path}: expected {expected} stubs, got {actual}")
        else:
            print(f"PASS {rel_path}: {actual}/{expected} stubs intact")
    if failures:
        print(f"\nFAIL — {len(failures)} stub-file(s) diverged from counsel-frozen manifest")
        print("Action: get counsel signoff before modifying these files,")
        print("then update _EXPECTED_STUBS in this script.")
        return 1
    print("\nPASS — all counsel-blocked stubs intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
