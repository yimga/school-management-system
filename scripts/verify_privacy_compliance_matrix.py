#!/usr/bin/env python
"""Metric #19 — privacy framework matrix verifier (repo-contained).

Asserts the compliance story is not scattered theater: SECURITY.md names the
regimes, DSAR subject kinds exist in code, and erase/consent models are importable.
Exit 0 = PRIVACY_MATRIX_PASS.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURITY_MD = ROOT / "docs" / "SECURITY.md"
DSAR_SUBJECTS = ROOT / "apps" / "compliance" / "dsar_subjects.py"
COMPLIANCE_MODELS = ROOT / "apps" / "compliance" / "models.py"

REQUIRED_REGIMES = ("GDPR", "FERPA", "COPPA")
REQUIRED_SUBJECT_KINDS = (
    "SUBJECT_STUDENT",
    "SUBJECT_STAFF",
    "SUBJECT_GUARDIAN",
)
REQUIRED_MODEL_NAMES = ("EraseRequest", "ConsentRequest")


def _fail(msg: str) -> int:
    print(f"PRIVACY_MATRIX_FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    if not SECURITY_MD.is_file():
        return _fail("docs/SECURITY.md missing")
    security = SECURITY_MD.read_text(encoding="utf-8")
    for regime in REQUIRED_REGIMES:
        if regime not in security:
            return _fail(f"SECURITY.md missing regime {regime}")

    if not DSAR_SUBJECTS.is_file():
        return _fail("apps/compliance/dsar_subjects.py missing")
    dsar = DSAR_SUBJECTS.read_text(encoding="utf-8")
    for kind in REQUIRED_SUBJECT_KINDS:
        if kind not in dsar:
            return _fail(f"dsar_subjects missing {kind}")
    if "def scrub_user_subject" not in dsar:
        return _fail("scrub_user_subject missing")

    if not COMPLIANCE_MODELS.is_file():
        return _fail("apps/compliance/models.py missing")
    tree = ast.parse(COMPLIANCE_MODELS.read_text(encoding="utf-8"), filename=str(COMPLIANCE_MODELS))
    class_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    for name in REQUIRED_MODEL_NAMES:
        if name not in class_names:
            return _fail(f"compliance.models missing class {name}")

    # Erasure UI must accept multi-subject kinds (Wave 17+).
    erasure_tpl = ROOT / "templates" / "compliance" / "erasure_request.html"
    if not erasure_tpl.is_file():
        return _fail("erasure_request.html missing")
    tpl = erasure_tpl.read_text(encoding="utf-8")
    if 'name="subject_kind"' not in tpl:
        return _fail("erasure_request.html missing subject_kind")
    if "staff" not in tpl or "guardian" not in tpl:
        return _fail("erasure_request.html missing staff/guardian options")

    print("PRIVACY_MATRIX_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
