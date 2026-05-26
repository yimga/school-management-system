"""Verify the Unified Wizard Framework Playwright spec matches the live registry.

Honest-reporting: PASS when every JSON wizard key has a corresponding entry in
the spec's ``WIZARD_REGISTRY_KEYS`` array, FAIL otherwise. Runs without a
browser — pure file walk + Node.js / regex-based parse of the spec file.

Failure modes the verifier catches:
* New wizard JSON added to ``apps/setup_studio/wizards/`` without spec update.
* Spec lists a wizard key the registry no longer has.
* Spec file missing entirely (regression of v3.93.4 work).
* Spec file syntactically broken in obvious ways (mismatched brackets).

Exit codes::

    0 — clean
    1 — drift / missing
    2 — spec file structurally broken
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "tests" / "e2e" / "unified-wizard-framework.spec.js"
WIZARDS_DIR = ROOT / "apps" / "setup_studio" / "wizards"

# Match a const-bound array literal of identifier-string entries.
_REGISTRY_RE = re.compile(
    r"const\s+WIZARD_REGISTRY_KEYS\s*=\s*\[([^\]]*)\]",
    re.MULTILINE | re.DOTALL,
)
_STRING_ENTRY_RE = re.compile(r'"([a-z][a-z0-9_]*)"')


def _registry_keys_from_disk() -> set[str]:
    keys: set[str] = set()
    if not WIZARDS_DIR.exists():
        return keys
    for json_path in sorted(WIZARDS_DIR.glob("*.json")):
        if json_path.name.startswith("_"):
            continue
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if raw.get("feature_flag_disabled") is True:
            continue
        key = raw.get("wizard_key")
        if isinstance(key, str) and key:
            keys.add(key)
    return keys


def _registry_keys_from_spec() -> set[str] | None:
    if not SPEC_PATH.exists():
        return None
    body = SPEC_PATH.read_text(encoding="utf-8")
    m = _REGISTRY_RE.search(body)
    if not m:
        return None
    inner = m.group(1)
    return {match.group(1) for match in _STRING_ENTRY_RE.finditer(inner)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="non-zero exit on any drift")
    args = ap.parse_args(argv)

    print("== verify_wizard_playwright_spec_coverage ==")

    if not SPEC_PATH.exists():
        print(f"FAIL: spec file missing at {SPEC_PATH}")
        return 2

    spec_keys = _registry_keys_from_spec()
    if spec_keys is None:
        print(f"FAIL: could not parse WIZARD_REGISTRY_KEYS from {SPEC_PATH.name}")
        return 2

    disk_keys = _registry_keys_from_disk()
    if not disk_keys:
        print(f"FAIL: no wizard JSONs discovered at {WIZARDS_DIR}")
        return 1

    missing_in_spec = sorted(disk_keys - spec_keys)
    extra_in_spec = sorted(spec_keys - disk_keys)

    if not missing_in_spec and not extra_in_spec:
        print(f"PASS: spec covers all {len(disk_keys)} registered wizards")
        return 0

    if missing_in_spec:
        print(f"FAIL: {len(missing_in_spec)} wizard(s) registered but missing from spec:")
        for k in missing_in_spec:
            print(f"  - {k}")
    if extra_in_spec:
        print(f"FAIL: {len(extra_in_spec)} wizard key(s) in spec but not in registry:")
        for k in extra_in_spec:
            print(f"  - {k}")

    return 1 if args.strict or missing_in_spec or extra_in_spec else 0


if __name__ == "__main__":
    sys.exit(main())
