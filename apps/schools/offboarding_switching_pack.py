"""Switching pack artifacts bundled into tenant portability exports."""

from __future__ import annotations

import json
from typing import Any


VENDOR_README: dict[str, str] = {
    "powerschool": (
        "PowerSchool: import canonical CSV domains via Data Export Manager or "
        "custom import templates. Map student_id, enrollment_status, guardian email."
    ),
    "blackbaud": (
        "Blackbaud: flatten dot-nested headers; relationship rows map to guardians."
    ),
    "veracross": (
        "Veracross: role-partitioned people columns (StudentEmail vs FacultyEmail)."
    ),
    "alma": (
        "Alma: JSON-in-CSV cells may need one-level flatten before Alma import."
    ),
}


def build_switching_pack_readme(*, school_slug: str, domains: list[str]) -> str:
    lines = [
        f"# RunMyCampus switching pack — {school_slug}",
        "",
        "This archive contains canonical CSV domains under `canonical/` and per-student JSON.",
        "Use these files when migrating to another SIS or retaining records offline.",
        "",
        "## Exported domains",
    ]
    for domain in sorted(domains):
        lines.append(f"- {domain}")
    lines.append("")
    lines.append("## Vendor notes")
    for vendor, note in VENDOR_README.items():
        lines.append(f"### {vendor}")
        lines.append(note)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_validation_report(
    *,
    school_slug: str,
    student_count: int,
    domains: list[str],
    inventory: dict[str, int],
) -> dict[str, Any]:
    return {
        "school_slug": school_slug,
        "students_exported": student_count,
        "canonical_domains": sorted(domains),
        "domain_count": len(domains),
        "row_total": sum(inventory.values()) if inventory else 0,
        "gaps": [] if domains else ["canonical_export_empty"],
    }


def validation_report_json(**kwargs: Any) -> str:
    return json.dumps(build_validation_report(**kwargs), indent=2, default=str)
