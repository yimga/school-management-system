"""Official-catalog import (increment s) — pure data population, no deploy.

Increment (q) gave subject codes the same region-level override home term windows
already had (``EducationSystemProfile.config['subject_codes']`` /
``['term_windows']``). This module is the operational other half: it loads a
country's REAL official data — ministry/board subject codes, real term-date
windows — from a plain JSON catalog straight into that shared profile config, so
an operator or ministry liaison enters official data ONCE for a country and every
school in it inherits it, with NO code change and NO deploy.

That is the honest completion of *"more countries' ministry-exact term dates and
official numeric board codes is pure data population through the same rows and
tables"*: the rows are ``EducationSystemProfile.config``, the table is one JSON
file per country, and this importer is the pump between them.

Catalog file shape (one JSON object per country)::

    {
      "country": "KE",              # ISO alpha-2 or alpha-3
      "sub_system": "",             # optional education sub-system code
      "source": "KNEC KCSE 2024",   # provenance, for the audit trail
      "term_windows": [[1,8,4,10],[5,2,8,8],[9,2,11,28]],   # optional
      "subject_codes": {"english": "101", "mathematics": "121"},  # optional
      "notes": "..."
    }

``subject_codes`` keys are subject names (matched case-insensitively at resolve
time); ``term_windows`` is a single list of ``[start_month, start_day, end_month,
end_day]`` tuples for the country's term structure. Merging is additive — existing
config keys the catalog does not mention are preserved — and idempotent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The shipped catalog directory (operator-editable JSON, one file per country).
DEFAULT_CATALOG_DIR = Path(__file__).resolve().parent / "data" / "official_catalogs"


class OfficialCatalogError(ValueError):
    """A catalog file is structurally invalid (bad country, malformed windows…)."""


def _normalized_subject_codes(raw: Any) -> dict[str, str]:
    """Coerce a ``{name: code}`` map to lowercase-keyed, non-empty string values."""
    if not isinstance(raw, dict):
        raise OfficialCatalogError("subject_codes must be an object of name -> code")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        code = "" if value is None else str(value).strip()
        name = key.strip().lower()
        if name and code:
            out[name] = code
    return out


def _normalized_term_windows(raw: Any) -> list[list[int]]:
    """Coerce term windows to a list of ``[sm, sd, em, ed]`` int lists."""
    if not isinstance(raw, (list, tuple)):
        raise OfficialCatalogError("term_windows must be a list of [sm, sd, em, ed]")
    out: list[list[int]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            raise OfficialCatalogError(f"term window {item!r} must have exactly 4 integers")
        try:
            out.append([int(x) for x in item])
        except (TypeError, ValueError) as exc:
            raise OfficialCatalogError(f"term window {item!r} has non-integer values") from exc
    return out


def parse_catalog(data: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalize a raw catalog dict. Raises ``OfficialCatalogError``."""
    if not isinstance(data, dict):
        raise OfficialCatalogError("catalog must be a JSON object")
    country = str(data.get("country") or "").strip().upper()
    if not (2 <= len(country) <= 3):
        raise OfficialCatalogError(f"country must be an ISO alpha-2/3 code, got {country!r}")
    parsed: dict[str, Any] = {
        "country": country,
        "sub_system": str(data.get("sub_system") or "").strip(),
        "source": str(data.get("source") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
    }
    if "subject_codes" in data and data.get("subject_codes") is not None:
        parsed["subject_codes"] = _normalized_subject_codes(data.get("subject_codes"))
    if "term_windows" in data and data.get("term_windows") is not None:
        parsed["term_windows"] = _normalized_term_windows(data.get("term_windows"))
    if "subject_codes" not in parsed and "term_windows" not in parsed:
        raise OfficialCatalogError("catalog has neither subject_codes nor term_windows")
    return parsed


def _merge_into_config(config: dict[str, Any], parsed: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Return ``(new_config, changes)`` — additive merge that never clobbers keys
    the catalog does not mention. ``subject_codes`` overlays key-by-key;
    ``term_windows`` (a whole-calendar value) is replaced."""
    new_config = dict(config or {})
    changes = {"subject_codes": 0, "term_windows": 0}
    if "subject_codes" in parsed:
        existing = dict(new_config.get("subject_codes") or {}) if isinstance(new_config.get("subject_codes"), dict) else {}
        for name, code in parsed["subject_codes"].items():
            if existing.get(name) != code:
                changes["subject_codes"] += 1
            existing[name] = code
        new_config["subject_codes"] = existing
    if "term_windows" in parsed:
        if new_config.get("term_windows") != parsed["term_windows"]:
            changes["term_windows"] = 1
        new_config["term_windows"] = parsed["term_windows"]
    return new_config, changes


def _existing_country_profile(country: str, sub_system: str):
    """Find the region-shared approved profile for a country WITHOUT creating rows.

    Lets ``--dry-run`` be truly side-effect-free (``ensure_country_profile`` would
    otherwise create the region + an approved profile shell). ``None`` when no
    region/profile exists yet."""
    from apps.siteconfig.education_profile_engine import normalize_sub_system
    from apps.siteconfig.models_platform_catalog import EducationSystemProfile, RegionConfig

    codes = {country.upper()}
    try:
        import pycountry

        rec = (
            pycountry.countries.get(alpha_2=country.upper())
            if len(country) == 2
            else pycountry.countries.get(alpha_3=country.upper())
        )
        if rec is not None:
            codes.add(rec.alpha_2)
            codes.add(rec.alpha_3)
    except Exception:  # noqa: BLE001 — pycountry lookup is best-effort
        logger.debug("_existing_country_profile: pycountry lookup failed", exc_info=True)

    region = RegionConfig.objects.filter(code__in=codes).first()
    if region is None:
        return None
    target_sub = normalize_sub_system(sub_system or None)
    approved = EducationSystemProfile.objects.filter(
        is_active=True,
        approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
        region=region,
    )
    return (
        approved.filter(sub_system=target_sub).order_by("-is_default", "name").first()
        or approved.filter(sub_system=EducationSystemProfile.SubSystem.ANY)
        .order_by("-is_default", "name")
        .first()
    )


def import_catalog(parsed: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Write a parsed catalog into the shared country ``EducationSystemProfile.config``.

    Resolves (creating if needed, unless ``dry_run``) the country/region profile the
    resolver already reads (``_lookup_windows`` / ``_profile_subject_codes``), so
    imported data is live for every school in that country. Idempotent. ``dry_run``
    writes nothing and creates no rows; returns a summary dict."""
    from apps.siteconfig.education_profile_engine import ensure_country_profile

    subject_add = len(parsed.get("subject_codes", {}) or {})
    term_add = 1 if "term_windows" in parsed else 0

    profile = _existing_country_profile(parsed["country"], parsed["sub_system"])
    if profile is None:
        if dry_run:
            return {
                "country": parsed["country"],
                "profile": "(would create)",
                "status": "dry-run",
                "subject_codes_changed": subject_add,
                "term_windows_changed": term_add,
                "source": parsed.get("source", ""),
            }
        profile = ensure_country_profile(
            region_code=parsed["country"],
            sub_system=parsed["sub_system"] or None,
        )
        if profile is None:
            return {
                "country": parsed["country"],
                "status": "skipped",
                "reason": "no_region_or_profile",
                "subject_codes_changed": 0,
                "term_windows_changed": 0,
            }

    # Profile exists — report the real delta (whether applying or dry-running).
    new_config, changes = _merge_into_config(getattr(profile, "config", None) or {}, parsed)
    applied = bool(changes["subject_codes"] or changes["term_windows"])
    if applied and not dry_run:
        profile.config = new_config
        profile.save(update_fields=["config", "updated_at"])
    if dry_run:
        status = "dry-run"
    else:
        status = "applied" if applied else "unchanged"
    return {
        "country": parsed["country"],
        "profile": str(profile),
        "status": status,
        "subject_codes_changed": changes["subject_codes"],
        "term_windows_changed": changes["term_windows"],
        "source": parsed.get("source", ""),
    }


def load_catalog_file(path: str | Path) -> dict[str, Any]:
    """Read + parse a single catalog JSON file. Raises ``OfficialCatalogError``."""
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OfficialCatalogError(f"catalog file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise OfficialCatalogError(f"catalog file {p} is not valid JSON: {exc}") from exc
    return parse_catalog(raw)


def iter_catalog_files(directory: str | Path):
    """Yield ``*.json`` catalog paths in a directory, sorted (README/other skipped)."""
    d = Path(directory)
    if not d.is_dir():
        return
    for path in sorted(d.glob("*.json")):
        yield path


# --- Template export: curated defaults -> editable catalog ---------------------
#
# The other end of the demand-driven loop. `import_country_official_catalog` loads
# a country's real data IN; this exports the curated representative defaults OUT as
# an editable catalog file (the real subject taxonomy + representative windows,
# pre-filled), so onboarding a country's real data is export -> fill official values
# -> import, never starting from a blank file. No fabrication: exported codes are
# the curated mnemonics (or the real KE/IN codes) an operator then replaces.

_TEMPLATE_SOURCE = "TEMPLATE — RunMyCampus curated representative defaults"
_TEMPLATE_NOTES = (
    "Pre-filled from RunMyCampus curated defaults. subject_codes are readable "
    "MNEMONICS (or curated real codes where a country publishes them, e.g. KE/IN) — "
    "replace with your official board/ministry codes. term_windows are "
    "REPRESENTATIVE — confirm your school's real dates. Then load with: "
    "manage.py import_country_official_catalog --file <this file>."
)


def curated_countries() -> list[str]:
    """ISO alpha-2 codes that have curated subject codes and/or term windows."""
    from apps.academics.country_subject_codes import _NATIONAL_SUBJECT_CODES
    from apps.academics.country_term_calendars import _TERM_CALENDARS

    codes = {c for c in _NATIONAL_SUBJECT_CODES if len(c) == 2}
    codes |= {c for c in _TERM_CALENDARS if len(c) == 2}
    return sorted(codes)


def build_catalog_template(country: str) -> dict[str, Any]:
    """Return an editable catalog dict for a country, pre-filled from the curated
    defaults (real subject taxonomy + representative windows).

    Round-trips through :func:`parse_catalog` / :func:`import_catalog`. Raises
    ``OfficialCatalogError`` when the country has no curated data to seed from."""
    from apps.academics.country_subject_codes import _NATIONAL_SUBJECT_CODES
    from apps.academics.country_term_calendars import _TERM_CALENDARS, _to_alpha2

    raw = (country or "").strip().upper()
    iso2 = raw if len(raw) == 2 else _to_alpha2(raw)
    if not iso2:
        raise OfficialCatalogError(f"unknown country code: {country!r}")
    codes = _NATIONAL_SUBJECT_CODES.get(iso2)
    windows = _TERM_CALENDARS.get(iso2)
    if not codes and not windows:
        raise OfficialCatalogError(f"no curated data for {iso2} to build a template from")
    template: dict[str, Any] = {
        "country": iso2,
        "sub_system": "",
        "source": _TEMPLATE_SOURCE,
        "notes": _TEMPLATE_NOTES,
    }
    if codes:
        template["subject_codes"] = {str(k): str(v) for k, v in codes.items()}
    if windows:
        template["term_windows"] = [list(w) for w in windows]
    return template


def serialize_catalog(catalog: dict[str, Any]) -> str:
    """Pretty-print a catalog dict as JSON (matches the shipped file style)."""
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
