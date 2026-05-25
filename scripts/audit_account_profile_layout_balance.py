#!/usr/bin/env python3
"""
Account/profile layout balance audit.

Guards the manager and tenant profile pages against the failure mode where a
long left column sits beside a mostly empty right column.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "account_profile_layout_balance_audit.json"


@dataclass
class Check:
    check_id: str
    status: str
    detail: str
    proof: str


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _ok(rows: list[Check], check_id: str, passed: bool, detail: str, proof: str) -> None:
    rows.append(Check(check_id, "PASS" if passed else "FAIL", detail, proof))


def main() -> int:
    rows: list[Check] = []
    operator_profile = _read("templates/accounts/partials/operator_profile_body.html")
    tenant_profile = _read("templates/accounts/profile.html")
    account_css = _read("static/css/rmc-account-surface.css")
    operator_page = _read("templates/siteconfig/operator_control_plane_page.html")
    sidebar_builder = _read("apps/schools/manager_nav_convergence.py")

    for rel, text in (
        ("templates/accounts/partials/operator_profile_body.html", operator_profile),
        ("templates/accounts/profile.html", tenant_profile),
    ):
        _ok(
            rows,
            f"{rel}:balanced_marker",
            'data-rmc-balanced-profile="1"' in text
            and 'data-rmc-balanced-layout="account-profile"' in text,
            "profile template declares the balanced account layout contract",
            rel,
        )
        _ok(
            rows,
            f"{rel}:primary_and_rail",
            "rmc-account-layout-grid__primary" in text
            and "rmc-account-layout-grid__rail" in text,
            "profile template has explicit primary and rail regions",
            rel,
        )
        _ok(
            rows,
            f"{rel}:quick_links_not_lonely",
            text.find("rmc-account-quick-links") < text.find("_profile_security_hub.html")
            and text.find("_profile_security_hub.html") < text.find("rmc-account-identity-card"),
            "quick links rail is followed by security hub and identity content",
            rel,
        )

    css_needles = (
        ".rmc-account-layout-grid",
        "grid-template-columns: var(--rmc-account-primary-min) var(--rmc-account-rail-min)",
        ".rmc-account-layout-grid__rail",
        "max-height: min(19rem, 42vh)",
        "@media (max-width: 1199.98px)",
    )
    _ok(
        rows,
        "account_css_balanced_grid",
        all(needle in account_css for needle in css_needles),
        "shared CSS defines desktop balance, rail stacking, and mobile collapse",
        "static/css/rmc-account-surface.css",
    )
    _ok(
        rows,
        "operator_shell_loads_account_css",
        "rmc-account-surface.css" in operator_page,
        "manager operator shell loads account surface CSS",
        "templates/siteconfig/operator_control_plane_page.html",
    )
    _ok(
        rows,
        "complete_sidebar_dedupe_contract",
        "_dedupe_complete_sidebar_groups" in sidebar_builder
        and "label.casefold()" in sidebar_builder
        and "_dedupe_complete_sidebar_items" in sidebar_builder,
        "complete manager sidebar merges repeated section labels and duplicate items",
        "apps/schools/manager_nav_convergence.py",
    )

    risky_profile_files: list[str] = []
    quick_link_re = re.compile(r"Quick (?:links|actions)", re.IGNORECASE)
    for path in sorted((ROOT / "templates").rglob("*.html")):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith("templates/auth/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if 'data-rmc-balanced-profile="1"' in text or "rmc-account-layout-grid" in text:
            continue
        for match in quick_link_re.finditer(text):
            window = text[max(0, match.start() - 1400) : min(len(text), match.end() + 800)]
            if "col-lg-6" in window and "profile" in window.lower():
                risky_profile_files.append(rel)
                break
    _ok(
        rows,
        "quick_links_two_column_risk_scan",
        not risky_profile_files,
        f"quick-link two-column templates without balanced contract: {len(risky_profile_files)}",
        ", ".join(risky_profile_files[:20]),
    )

    failed = [row for row in rows if row.status != "PASS"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "ACCOUNT_PROFILE_LAYOUT_BALANCED" if not failed else "ACCOUNT_PROFILE_LAYOUT_GAPS",
        "failed": len(failed),
        "checks": [asdict(row) for row in rows],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"{payload['verdict']} ({len(rows) - len(failed)} pass, {len(failed)} fail)")
    if failed:
        for row in failed:
            print(f"- {row.check_id}: {row.proof}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
