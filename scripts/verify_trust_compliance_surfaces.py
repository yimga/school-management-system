#!/usr/bin/env python3
"""Verify trust / security-compliance marketing surfaces ship required markers."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_PARTIAL_MARKERS = {
    "marketing/partials/trust_compliance_command_center.html": [
        'data-mkt-trust-command-center="1"',
        "Proof command center",
    ],
    "marketing/partials/trust_compliance_control_framework.html": [
        'data-mkt-trust-control-framework="1"',
        "Mechanism",
    ],
    "marketing/partials/trust_compliance_regulatory_grid.html": [
        'data-mkt-trust-regulatory="1"',
        "Regulatory & accessibility readiness",
    ],
    "marketing/partials/trust_compliance_external_honesty.html": [
        'data-mkt-trust-external-honesty="1"',
        "Not published",
    ],
    "marketing/pages/type_security_compliance.html": [
        'data-mkt-security-compliance="1"',
        "trust_compliance_command_center.html",
        "trust_compliance_regulatory_grid.html",
    ],
    "marketing/pages/type_trust_center.html": [
        'data-mkt-trust-center="1"',
        "trust_compliance_command_center.html",
        "trust_compliance_external_honesty.html",
    ],
    "marketing/pages/type_platform_security.html": [
        'data-mkt-platform-security="1"',
        "trust_compliance_control_framework.html",
        "marketing-trust-compliance.css",
    ],
}

REQUIRED_PY_SYMBOLS = [
    ("apps/schools/trust_center_evidence.py", "build_trust_compliance_context"),
    ("apps/schools/trust_center_evidence.py", "_TRUST_MATRIX_SPECS"),
    ("apps/schools/trust_center_evidence.py", "_REGULATORY_CARD_SPECS"),
    ("apps/schools/marketing_views.py", "build_trust_compliance_context"),
    ("apps/schools/marketing_views.py", "trust_compliance_anchor_mode"),
]

TRUST_HTTP_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "/security-compliance/",
        (
            'data-mkt-security-compliance="1"',
            "data-mkt-trust-command-center",
            "data-mkt-trust-control-framework",
            "data-mkt-trust-regulatory",
            "data-mkt-trust-external-honesty",
        ),
    ),
    (
        "/trust-center/",
        (
            'data-mkt-trust-center="1"',
            "data-mkt-trust-command-center",
            "data-mkt-trust-control-framework",
            "data-mkt-trust-regulatory",
        ),
    ),
    (
        "/platform/security/",
        (
            'data-mkt-platform-security="1"',
            "data-mkt-trust-command-center",
            "data-mkt-trust-control-framework",
        ),
    ),
    ("/trust-center/coppa/", ("trust-center-coppa", "COPPA")),
    ("/trust-center/accessibility/", ("trust-center-accessibility", "WCAG")),
)


def _verify_http_routes(failures: list[str]) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.test import Client

    host = os.environ.get("MKT_LIGHTHOUSE_HOST", "runmycampus.com")
    client = Client(HTTP_HOST=host)
    for path, markers in TRUST_HTTP_ROUTES:
        response = client.get(path, follow=True)
        if response.status_code != 200:
            failures.append(f"HTTP {path} -> {response.status_code}")
            continue
        body = response.content.decode("utf-8", errors="replace")
        missing = [m for m in markers if m not in body]
        if missing:
            failures.append(f"HTTP {path} missing markers: {missing!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="No-op; parity with other verifiers")
    parser.add_argument(
        "--skip-http",
        action="store_true",
        help="Skip Django test-client HTTP checks (static/template only)",
    )
    args = parser.parse_args()

    failures: list[str] = []
    templates = ROOT / "templates"
    for rel, needles in REQUIRED_PARTIAL_MARKERS.items():
        path = templates / rel
        if not path.exists():
            failures.append(f"missing template: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                failures.append(f"{rel}: missing {needle!r}")

    css_path = ROOT / "static/marketing/css/marketing-trust-compliance.css"
    if not css_path.is_file():
        failures.append("missing static/marketing/css/marketing-trust-compliance.css")
    elif ".mkt-trust-command-center" not in css_path.read_text(encoding="utf-8"):
        failures.append("marketing-trust-compliance.css missing command-center styles")

    for rel, symbol in REQUIRED_PY_SYMBOLS:
        path = ROOT / rel
        if not path.exists():
            failures.append(f"missing module: {rel}")
            continue
        if symbol not in path.read_text(encoding="utf-8"):
            failures.append(f"{rel}: missing symbol {symbol!r}")

    try:
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()
        from apps.schools.trust_center_evidence import (
            TRUST_COMPLIANCE_ANCHOR_SLUGS,
            build_trust_compliance_context,
        )

        if len(TRUST_COMPLIANCE_ANCHOR_SLUGS) < 4:
            failures.append("TRUST_COMPLIANCE_ANCHOR_SLUGS expected >= 4 slugs")

        ctx = build_trust_compliance_context()
        for key in (
            "trust_matrix_rows",
            "trust_procurement_cards",
            "trust_regulatory_cards",
            "trust_certification_honesty",
            "trust_ci_gates",
        ):
            if not ctx.get(key):
                failures.append(f"context missing non-empty {key}")
        if len(ctx.get("trust_matrix_rows") or []) < 8:
            failures.append("trust_matrix_rows expected >= 8 controls")
        if len(ctx.get("trust_regulatory_cards") or []) < 6:
            failures.append("trust_regulatory_cards expected >= 6 cards")
        soc2 = next(
            (c for c in ctx["trust_certification_honesty"] if "SOC 2" in c.get("label", "")),
            None,
        )
        if not soc2 or soc2.get("status") != "not_published":
            failures.append("certification honesty must not claim SOC 2 by default")

        if not args.skip_http:
            _verify_http_routes(failures)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"trust compliance verification failed: {exc}")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1
    print("OK: trust compliance surfaces verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
