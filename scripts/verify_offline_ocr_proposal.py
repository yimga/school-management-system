#!/usr/bin/env python3
"""Phase P2 gate: OCR is local-capable, proposal-only, and human-confirmed."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "static" / "js" / "vendor" / "tesseract"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    errors: list[str] = []
    manifest_path = VENDOR / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"vendor manifest unreadable: {exc}")
        manifest = {}
    if manifest.get("version") != "7.0.0":
        errors.append("Tesseract.js must remain pinned to 7.0.0")
    for name, metadata in (manifest.get("assets") or {}).items():
        path = VENDOR / name
        if not path.is_file():
            errors.append(f"missing vendored asset: {name}")
        elif sha256(path) != metadata.get("sha256"):
            errors.append(f"checksum mismatch: {name}")

    views = (ROOT / "apps" / "evals" / "views.py").read_text(encoding="utf-8")
    upload_start = views.find(
        'elif request.method == "POST" and marksheet_file:'
    )
    upload_end = views.find('elif request.method == "POST":', upload_start + 1)
    upload_branch = views[upload_start:upload_end]
    if "_apply_ocr_entries(" in upload_branch:
        errors.append("upload branch must not write OCR results before confirmation")
    for token in (
        'request.POST.get("confirm_human_review") != "1"',
        "upload_manual_review_pending = bool(entries)",
        "_validate_ocr_entries(entries_to_apply)",
    ):
        if token not in views:
            errors.append(f"server OCR confirmation contract missing: {token}")

    template = (ROOT / "templates" / "teacher" / "marks_entry.html").read_text(
        encoding="utf-8"
    )
    for token in (
        "Run on this device",
        "it never saves a grade",
        'name="confirm_human_review"',
        "Apply teacher-confirmed proposal",
        'data-rmc-ocr-field="seq1_score"',
    ):
        if token not in template:
            errors.append(f"OCR template contract missing: {token}")

    browser = (
        ROOT / "static" / "js" / "rmc-marksheet-device-ocr.js"
    ).read_text(encoding="utf-8")
    for forbidden in (".submit(", "fetch(", "rmcWAL.append", "rmcOfflineEnqueue"):
        if forbidden in browser:
            errors.append(f"device OCR must remain proposal-only: {forbidden}")
    for token in ("blocks: true", "proposal.bbox", "data-rmc-ocr-proposal"):
        if token not in browser:
            errors.append(f"device OCR evidence contract missing: {token}")

    commands = [
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "apps.evals.tests.test_import_and_helper_hardening.OCRPendingEntryHelperTests",
            "apps.evals.tests.test_grade_approval_workflow.GradeApprovalWorkflowTestCase.test_ocr_upload_never_writes_until_teacher_confirms",
            "--verbosity=1",
        ],
        [
            "node",
            "node_modules/vitest/vitest.mjs",
            "run",
            "tests/js/rmc_marksheet_device_ocr.test.ts",
        ],
        ["node", "scripts/smoke_tesseract_browser_ocr.mjs"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            errors.append(f"test command failed: {' '.join(command)}")

    if errors:
        print("OFFLINE_OCR_PROPOSAL_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OFFLINE_OCR_PROPOSAL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
