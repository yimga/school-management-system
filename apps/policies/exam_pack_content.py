"""
Regional exam-pack README/copy resolver — sources content from the tenant's
active `BlueprintPack.policy_snapshot["exam_registration_pack"]` when set,
falls back to a generic neutral default otherwise.

This replaces the previous hardcoded "Cameroon Exams Registration Pack" text
in `apps/accounts/views_certification.py`. Tenants get region-specific copy
by storing the README dict in their BlueprintPack at install time; until that
happens, every region sees the neutral generic copy below (NOT Cameroon-specific
text masquerading as a default).

See `docs/CONFIGURABILITY.md` (Layer A — tenant-level config via BlueprintPack).
"""
from __future__ import annotations

from typing import Any


# Neutral generic README — used when no BlueprintPack override is set.
# When you add a new region (Kenya KCSE, Nigeria WAEC, UK IGCSE etc.), set the
# region-specific README via `BlueprintPack.policy_snapshot["exam_registration_pack"]`
# during pack provisioning. The shape is `{"title": str, "intro": str, "phases":
# list[str], "references": list[dict[name, url]], "files": dict[csv_name, str]}`.
_GENERIC_PACK = {
    "title": "Exams Registration Pack",
    "intro": (
        "This pack helps your centre run the official exam-registration flow "
        "for your country. Adapt the phases below to your exam board's process."
    ),
    "phases": [
        "Pre-registration & data entry (the board's e-registration system "
        "typically generates a candidate ID / CIN)",
        "Candidate payment via mobile money / bank transfer using the issued ID",
        "Validation using the transaction ID and printing of timetables / receipts",
    ],
    "references": [],
    "files": {
        "candidates.csv": "Your internal list — UID (matricule), CIN, payment transaction ID tracking",
    },
}

# Built-in regional presets — used when neither the BlueprintPack nor the
# tenant has specified a custom pack but we know the country.
# Adding a country here is the right path until the data lives in BlueprintPack.
_REGIONAL_PRESETS: dict[str, dict[str, Any]] = {
    "CM": {  # Cameroon (GCEB)
        "title": "Cameroon Exams Registration Pack",
        "intro": (
            "This pack is designed to help your centre follow the official 3-phase flow:"
        ),
        "phases": [
            "Pre-registration & data entry (board e-registration software generates CIN)",
            "Candidate payment via MTN Mobile Money using CIN",
            "Validation using Transaction ID + printing timetables/receipts",
        ],
        "references": [
            {"name": "E-REG user manual (2026)", "url": "https://camgceb.org/wp-content/uploads/2025/10/2026-E-Reg-user-manual.pdf"},
            {"name": "Data submission page", "url": "https://camgceb.org/submit-reg-data/"},
        ],
        "files": {
            "candidates.csv": "your internal list with UID (matricule), CIN, payment transaction ID tracking",
        },
    },
}


def resolve_exam_registration_pack(
    *,
    school=None,
    year=None,
    country_code: str | None = None,
) -> dict[str, Any]:
    """Return the exam-registration README content for a tenant.

    Resolution order:
    1. `school.blueprint_pack.policy_snapshot["exam_registration_pack"]` — full per-tenant override
    2. Built-in `_REGIONAL_PRESETS[country_code]` — region preset by ISO code
    3. `_GENERIC_PACK` — neutral fallback

    Returns a dict with keys: title, intro, phases, references, files.

    Callers (e.g. apps/accounts/views_certification.py) format these into
    the README the export ships. No more hardcoded Cameroon text in views.
    """
    # 1. Tenant override via BlueprintPack snapshot
    pack = None
    if school is not None:
        bp = getattr(school, "blueprint_pack", None) or getattr(school, "active_blueprint_pack", None)
        if bp is not None:
            snapshot = getattr(bp, "policy_snapshot", None) or {}
            pack = snapshot.get("exam_registration_pack") if isinstance(snapshot, dict) else None

    if isinstance(pack, dict) and pack:
        return _merge_with_default(pack)

    # 2. Country preset
    cc = (country_code or "").strip().upper()
    if not cc and year is not None:
        cc = (getattr(year, "country_code", None) or "").strip().upper()
    if cc and cc in _REGIONAL_PRESETS:
        return _merge_with_default(_REGIONAL_PRESETS[cc])

    # 3. Neutral generic default
    return dict(_GENERIC_PACK)


def _merge_with_default(custom: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge so callers always get all keys even if the source omits some."""
    merged = dict(_GENERIC_PACK)
    for key in ("title", "intro", "phases", "references", "files"):
        if key in custom:
            merged[key] = custom[key]
    return merged


def format_pack_as_readme_lines(pack: dict[str, Any]) -> list[str]:
    """Format the resolved pack dict as plain-text README lines."""
    lines: list[str] = []
    lines.append(pack.get("title", "Exams Registration Pack"))
    lines.append("")
    if pack.get("intro"):
        lines.append(pack["intro"])
    phases = pack.get("phases") or []
    for i, phase in enumerate(phases, 1):
        lines.append(f"{i}) {phase}")
    lines.append("")
    refs = pack.get("references") or []
    if refs:
        lines.append("Useful references:")
        for r in refs:
            if isinstance(r, dict):
                lines.append(f"- {r.get('name', 'Reference')}: {r.get('url', '')}".rstrip(": "))
            else:
                lines.append(f"- {r}")
        lines.append("")
    files = pack.get("files") or {}
    if files:
        lines.append("Files included:")
        for csv_name, descr in files.items():
            lines.append(f"- {csv_name}: {descr}")
    return lines
