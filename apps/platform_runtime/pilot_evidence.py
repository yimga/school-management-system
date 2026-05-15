"""Pilot readiness scorecard load, validation, and display-safe redaction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

TESTIMONIAL_STATES = frozenset(
    {"not_requested", "requested", "approved_internal", "approved_public"}
)
REFERENCE_STATES = frozenset({"none", "internal_only", "public_reference"})
PILOT_VERDICT_STATES = frozenset(
    {
        "not_started",
        "blocked",
        "in_progress",
        "pilot_ready_internal",
        "pilot_complete_internal",
        "public_reference_ready",
    }
)

REQUIRED_PILOT_NON_PII_KEYS = frozenset(
    {
        "slot",
        "country_region",
        "modules_enabled",
        "onboarding_status",
        "first_action_completed",
        "first_result_completed",
        "attendance_completed",
        "marks_completed",
        "report_generated",
        "invoice_created",
        "receipt_or_payment_captured",
        "parent_portal_viewed",
        "offline_sync_used",
        "defects_found",
        "defects_resolved",
        "testimonial_permission_status",
        "reference_status",
        "evidence_link_or_notes",
        "pilot_verdict",
    }
)


def scorecard_path() -> Path:
    return (
        Path(settings.BASE_DIR)
        / "docs"
        / "generated"
        / "pilot_readiness_scorecard.json"
    )


def load_raw_scorecard() -> dict[str, Any]:
    path = scorecard_path()
    return json.loads(path.read_text(encoding="utf-8"))


def validate_scorecard_schema(data: dict[str, Any]) -> list[str]:
    """Return human-readable issues; empty means OK for dashboard use."""
    errors: list[str] = []
    if int(data.get("schema_version") or 0) < 1:
        errors.append("schema_version must be >= 1")
    pilots = data.get("pilots")
    if not isinstance(pilots, list) or not pilots:
        errors.append("pilots must be a non-empty list")
        return errors
    for i, p in enumerate(pilots):
        if not isinstance(p, dict):
            errors.append(f"pilot[{i}] must be object")
            continue
        missing = sorted(REQUIRED_PILOT_NON_PII_KEYS - set(p.keys()))
        if missing:
            errors.append(f"pilot slot {p.get('slot', i)} missing keys: {missing}")
        ts = p.get("testimonial_permission_status")
        if ts is not None and ts not in TESTIMONIAL_STATES:
            errors.append(f"pilot {i} invalid testimonial_permission_status")
        rs = p.get("reference_status")
        if rs is not None and rs not in REFERENCE_STATES:
            errors.append(f"pilot {i} invalid reference_status")
        verdict = p.get("pilot_verdict")
        if verdict is not None and verdict not in PILOT_VERDICT_STATES:
            errors.append(f"pilot {i} invalid pilot_verdict")
        has_public_reference = (
            p.get("reference_status") == "public_reference"
            or p.get("testimonial_permission_status") == "approved_public"
            or p.get("pilot_verdict") == "public_reference_ready"
        )
        if (
            has_public_reference
            and not str(p.get("evidence_link_or_notes") or "").strip()
        ):
            errors.append(f"pilot {i} public reference requires evidence_link_or_notes")
        if p.get("pilot_verdict") == "public_reference_ready" and not (
            p.get("reference_status") == "public_reference"
            and p.get("testimonial_permission_status") == "approved_public"
        ):
            errors.append(
                f"pilot {i} public_reference_ready requires public reference and approval"
            )
    return errors


def redact_pilot_for_display(pilot: dict[str, Any]) -> dict[str, Any]:
    """
    Strip identifying fields unless public reference is explicitly approved.

    No PII should be required for schema; school_name may be empty.
    """
    out = dict(pilot)
    rs = out.get("reference_status") or "none"
    ts = out.get("testimonial_permission_status") or "not_requested"
    can_name = rs == "public_reference" and ts == "approved_public"
    if not can_name:
        out["school_name"] = ""
        out["admin_contact"] = ""
        out["teacher_contact"] = ""
        out["parent_test_user"] = ""
        if rs == "public_reference":
            out["display_reference_note"] = (
                "Public reference pending explicit approval — identity withheld in-product."
            )
        elif rs == "internal_only":
            out["display_reference_note"] = (
                "Internal reference only — not shown as a public logo/name."
            )
        else:
            out["display_reference_note"] = "No reference recorded."
    else:
        out["display_reference_note"] = (
            "Public reference approved for controlled use only."
        )
    return out


def build_pilot_dashboard_rows(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    data = raw if raw is not None else load_raw_scorecard()
    issues = validate_scorecard_schema(data)
    pilots_in = data.get("pilots") or []
    pilots_out = [
        redact_pilot_for_display(dict(p)) for p in pilots_in if isinstance(p, dict)
    ]
    return {
        "schema_ok": not issues,
        "schema_issues": issues,
        "lane": data.get("lane", ""),
        "north_star_metric": data.get("north_star_metric", ""),
        "workflow_evidence_template": data.get("workflow_evidence_template") or {},
        "pilots": pilots_out,
    }
