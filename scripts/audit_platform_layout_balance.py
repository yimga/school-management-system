from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "generated" / "platform_layout_balance_audit.json"

REQUIRED_TEMPLATE_CONTRACTS = {
    "templates/accounts/profile.html": [
        'data-rmc-balanced-layout="account-profile"',
        'data-dashboard-column="rail"',
    ],
    "templates/accounts/partials/operator_profile_body.html": [
        'data-rmc-balanced-layout="account-profile"',
        'data-dashboard-column="rail"',
    ],
    "templates/parent/dashboard.html": [
        'data-rmc-balanced-layout="tenant-dashboard-rail"',
        'data-dashboard-column="rail"',
    ],
    "templates/schools/super_support_ticket_detail.html": [
        'data-rmc-balanced-layout="operator-detail-rail"',
        'data-dashboard-column="rail"',
    ],
    "templates/schools/partials/manager_help_center_body.html": [
        'data-rmc-balanced-layout="operator-form-rail"',
        'data-dashboard-column="rail"',
    ],
    "templates/schools/super_migration_cloud.html": [
        'data-rmc-balanced-layout="operator-detail-rail"',
        '<table class="table table-sm align-middle mb-0 table-family rmc-data-table"',
    ],
}

REQUIRED_CSS_CONTRACTS = {
    "static/css/rmc-platform-inner-pages.css": [
        '[data-rmc-balanced-layout$="-rail"]',
        'operator-detail-rail',
        'operator-form-rail',
        'tenant-dashboard-rail',
        '@media (max-width: 991.98px)',
    ],
    "static/css/rmc-account-surface.css": [
        'rmc-account-layout-grid',
        'data-rmc-balanced-layout="account-profile"',
    ],
}

CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

HIGH_RISK_PATTERNS = (
    ("bootstrap_8_4", re.compile(r"<div[^>]+class=\"[^\"]*row[^\"]*\"(?:(?!</div>).){0,2400}col-lg-8(?:(?!</div>).){0,2400}col-lg-4", re.S)),
    ("bootstrap_7_5", re.compile(r"<div[^>]+class=\"[^\"]*row[^\"]*\"(?:(?!</div>).){0,2400}col-lg-7(?:(?!</div>).){0,2400}col-lg-5", re.S)),
    ("bootstrap_xl_4_8", re.compile(r"<div[^>]+class=\"[^\"]*row[^\"]*\"(?:(?!</div>).){0,2400}col-xl-4(?:(?!</div>).){0,2400}col-xl-8", re.S)),
)


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def line_for(text: str, needle: str) -> int:
    idx = text.find(needle)
    if idx < 0:
        return 0
    return text.count("\n", 0, idx) + 1


def main() -> int:
    checks: list[dict[str, object]] = []

    for rel_path, tokens in REQUIRED_TEMPLATE_CONTRACTS.items():
        text = read(rel_path)
        for token in tokens:
            checks.append(
                {
                    "name": f"{rel_path} contains {token}",
                    "status": "pass" if token in text else "fail",
                    "file": rel_path,
                    "line": line_for(text, token),
                }
            )
        bad_controls = CONTROL_CHAR_RE.findall(text)
        checks.append(
            {
                "name": f"{rel_path} has no stray control characters",
                "status": "pass" if not bad_controls else "fail",
                "file": rel_path,
                "count": len(bad_controls),
            }
        )

    for rel_path in sorted(
        [p.relative_to(ROOT).as_posix() for p in (ROOT / "templates").rglob("*.html")]
    ):
        text = read(rel_path)
        bad_controls = CONTROL_CHAR_RE.findall(text)
        checks.append(
            {
                "name": f"{rel_path} has no stray control characters",
                "status": "pass" if not bad_controls else "fail",
                "file": rel_path,
                "count": len(bad_controls),
            }
        )

    for rel_path, tokens in REQUIRED_CSS_CONTRACTS.items():
        text = read(rel_path)
        for token in tokens:
            checks.append(
                {
                    "name": f"{rel_path} contains {token}",
                    "status": "pass" if token in text else "fail",
                    "file": rel_path,
                    "line": line_for(text, token),
                }
            )

    for rel_path in sorted(
        [p.relative_to(ROOT).as_posix() for p in (ROOT / "templates").rglob("*.html")]
    ):
        if "/generated/" in rel_path:
            continue
        text = read(rel_path)
        if "data-rmc-balanced-layout" in text:
            continue
        hits = [name for name, pattern in HIGH_RISK_PATTERNS if pattern.search(text)]
        if hits and (
            rel_path.startswith("templates/accounts/")
            or rel_path.startswith("templates/parent/")
            or rel_path.startswith("templates/student/")
            or rel_path.startswith("templates/teacher/")
            or rel_path.startswith("templates/schools/")
        ):
            checks.append(
                {
                    "name": f"{rel_path} high-risk rail row is either contracted or audited",
                    "status": "warn",
                    "file": rel_path,
                    "patterns": hits,
                }
            )

    failures = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warn"]
    payload = {
        "status": "pass" if not failures else "fail",
        "summary": {
            "checks": len(checks),
            "failures": len(failures),
            "warnings": len(warnings),
        },
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"PLATFORM_LAYOUT_BALANCE_FAIL ({len(failures)} failures, {len(warnings)} warnings)")
        for failure in failures:
            print(f"FAIL: {failure['name']}")
        return 1

    print(f"PLATFORM_LAYOUT_BALANCE_PASS ({len(checks)} checks, {len(warnings)} warnings)")
    if warnings:
        print("WARNINGS:")
        for warning in warnings[:20]:
            print(f"WARN: {warning['file']} {','.join(warning.get('patterns', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
