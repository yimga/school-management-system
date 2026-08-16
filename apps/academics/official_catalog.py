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
      "term_windows_by_count": {    # optional — more than one real structure
        "2": [[9,1,1,31],[2,1,6,30]],
        "3": [[9,1,12,15],[1,8,4,10],[4,25,7,25]]
      },
      "subject_codes": {"english": "101", "mathematics": "121"},  # optional
      "notes": "..."
    }

``subject_codes`` keys are subject names (matched case-insensitively at resolve
time); ``term_windows`` is a single list of ``[start_month, start_day, end_month,
end_day]`` tuples for the country's term structure. ``term_windows_by_count`` is
optional and lets a country carry MORE THAN ONE real structure (keyed by term
count, e.g. a 2-semester AND a 3-trimester calendar) — the resolver prefers the
entry matching a school's requested term count, then falls back to the single
``term_windows``. Merging is additive — existing config keys the catalog does not
mention are preserved — and idempotent.
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


def _normalized_term_windows_by_count(raw: Any) -> dict[str, list[list[int]]]:
    """Coerce a ``{term_count: [[sm,sd,em,ed], ...]}`` map to str-keyed int-count →
    validated window lists. Each list's length MUST equal its term count (that is
    the whole point — a 3-term entry has 3 windows). Lets a country carry more than
    one real term structure (e.g. a 2-semester AND a 3-trimester calendar)."""
    if not isinstance(raw, dict):
        raise OfficialCatalogError("term_windows_by_count must be an object of count -> windows")
    out: dict[str, list[list[int]]] = {}
    for key, value in raw.items():
        try:
            count = int(key)
        except (TypeError, ValueError) as exc:
            raise OfficialCatalogError(
                f"term_windows_by_count key {key!r} must be an integer term count"
            ) from exc
        if count < 1:
            raise OfficialCatalogError(
                f"term_windows_by_count key {key!r} must be a positive term count"
            )
        windows = _normalized_term_windows(value)
        if len(windows) != count:
            raise OfficialCatalogError(
                f"term_windows_by_count[{count}] must have exactly {count} window(s), got {len(windows)}"
            )
        out[str(count)] = windows
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
    if "term_windows_by_count" in data and data.get("term_windows_by_count") is not None:
        parsed["term_windows_by_count"] = _normalized_term_windows_by_count(
            data.get("term_windows_by_count")
        )
    if not any(k in parsed for k in ("subject_codes", "term_windows", "term_windows_by_count")):
        raise OfficialCatalogError(
            "catalog has none of subject_codes / term_windows / term_windows_by_count"
        )
    return parsed


def _merge_into_config(config: dict[str, Any], parsed: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(new_config, changes)`` — additive merge that never clobbers keys
    the catalog does not mention. ``subject_codes`` overlays key-by-key;
    ``term_windows`` (a whole-calendar value) is replaced.

    ``changes`` keeps the integer counts callers already rely on
    (``changes['subject_codes']`` / ``changes['term_windows']``) AND adds a
    conflict-aware breakdown: ``subject_added`` / ``subject_overwritten`` counts, a
    ``subject_diffs`` list of ``{name, old, new, kind}`` (only the codes that
    actually change), and a ``term_window_diff`` of ``{old, new}`` — so an operator
    (and ``--dry-run``) sees exactly what an import would change before applying,
    and an overwrite of a pre-existing code is never silent."""
    new_config = dict(config or {})
    changes: dict[str, Any] = {
        "subject_codes": 0,
        "term_windows": 0,
        "term_windows_by_count": 0,
        "subject_added": 0,
        "subject_overwritten": 0,
        "subject_diffs": [],
        "term_window_diff": None,
    }
    if "subject_codes" in parsed:
        existing = dict(new_config.get("subject_codes") or {}) if isinstance(new_config.get("subject_codes"), dict) else {}
        for name, code in parsed["subject_codes"].items():
            old = existing.get(name)
            if old == code:
                existing[name] = code
                continue
            kind = "added" if old is None else "overwritten"
            if kind == "added":
                changes["subject_added"] += 1
            else:
                changes["subject_overwritten"] += 1
            changes["subject_codes"] += 1
            changes["subject_diffs"].append(
                {"name": name, "old": old or "", "new": code, "kind": kind}
            )
            existing[name] = code
        new_config["subject_codes"] = existing
    if "term_windows" in parsed:
        old_windows = new_config.get("term_windows")
        if old_windows != parsed["term_windows"]:
            changes["term_windows"] = 1
            changes["term_window_diff"] = {"old": old_windows, "new": parsed["term_windows"]}
        new_config["term_windows"] = parsed["term_windows"]
    if "term_windows_by_count" in parsed:
        existing = (
            dict(new_config.get("term_windows_by_count") or {})
            if isinstance(new_config.get("term_windows_by_count"), dict)
            else {}
        )
        for count, windows in parsed["term_windows_by_count"].items():
            if existing.get(count) != windows:
                changes["term_windows_by_count"] += 1
            existing[count] = windows
        new_config["term_windows_by_count"] = existing
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


# Cap the persisted import log so config never grows unbounded on repeated imports.
_MAX_PROVENANCE_ENTRIES = 20


def _provenance_entry(parsed: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """A single audit record of one applied catalog import (WHO/WHAT/WHEN source)."""
    from django.utils import timezone

    return {
        "source": parsed.get("source", ""),
        "notes": parsed.get("notes", ""),
        "when": timezone.now().isoformat(),
        "subject_codes_changed": changes["subject_codes"],
        "subject_added": changes.get("subject_added", 0),
        "subject_overwritten": changes.get("subject_overwritten", 0),
        "term_windows_changed": changes["term_windows"],
        "term_windows_by_count_changed": changes.get("term_windows_by_count", 0),
    }


def _summary(parsed, profile, status, changes) -> dict[str, Any]:
    """Assemble the caller-facing import summary (counts + conflict-aware diffs)."""
    return {
        "country": parsed["country"],
        "profile": str(profile),
        "status": status,
        "subject_codes_changed": changes["subject_codes"],
        "term_windows_changed": changes["term_windows"],
        "term_windows_by_count_changed": changes.get("term_windows_by_count", 0),
        "subject_added": changes.get("subject_added", 0),
        "subject_overwritten": changes.get("subject_overwritten", 0),
        "diffs": changes.get("subject_diffs", []),
        "term_window_diff": changes.get("term_window_diff"),
        "source": parsed.get("source", ""),
    }


def import_catalog(parsed: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Write a parsed catalog into the shared country ``EducationSystemProfile.config``.

    Resolves (creating if needed, unless ``dry_run``) the country/region profile the
    resolver already reads (``_lookup_windows`` / ``_profile_subject_codes``), so
    imported data is live for every school in that country. Idempotent. ``dry_run``
    writes nothing and creates no rows; returns a summary dict that includes the
    conflict-aware ``diffs`` (each ``{name, old, new, kind}``) so a caller sees the
    exact ``old → new`` changes — including overwrites of a pre-existing code —
    before applying. An applied import appends a provenance record (source + when +
    counts) to ``config['catalog_provenance']`` for the audit trail."""
    from apps.siteconfig.education_profile_engine import ensure_country_profile

    profile = _existing_country_profile(parsed["country"], parsed["sub_system"])

    if profile is None:
        # No profile yet — compute the delta against an empty config so a dry-run of
        # a brand-new country still reports exactly what WOULD be added.
        _new_config, changes = _merge_into_config({}, parsed)
        if dry_run:
            return _summary(parsed, "(would create)", "dry-run", changes)
        profile = ensure_country_profile(
            region_code=parsed["country"],
            sub_system=parsed["sub_system"] or None,
        )
        if profile is None:
            summary = _summary(parsed, "(none)", "skipped", changes)
            summary["reason"] = "no_region_or_profile"
            summary["subject_codes_changed"] = 0
            summary["term_windows_changed"] = 0
            return summary

    # Profile exists — report the real delta (whether applying or dry-running).
    new_config, changes = _merge_into_config(getattr(profile, "config", None) or {}, parsed)
    applied = bool(
        changes["subject_codes"] or changes["term_windows"] or changes["term_windows_by_count"]
    )
    if applied and not dry_run:
        log = list(new_config.get("catalog_provenance") or [])
        log.append(_provenance_entry(parsed, changes))
        new_config["catalog_provenance"] = log[-_MAX_PROVENANCE_ENTRIES:]
        profile.config = new_config
        profile.save(update_fields=["config", "updated_at"])
    status = "dry-run" if dry_run else ("applied" if applied else "unchanged")
    return _summary(parsed, profile, status, changes)


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
    from apps.academics.country_term_calendars import (
        _TERM_CALENDARS,
        _TERM_CALENDARS_BY_COUNT,
        _to_alpha2,
    )

    raw = (country or "").strip().upper()
    iso2 = raw if len(raw) == 2 else _to_alpha2(raw)
    if not iso2:
        raise OfficialCatalogError(f"unknown country code: {country!r}")
    codes = _NATIONAL_SUBJECT_CODES.get(iso2)
    windows = _TERM_CALENDARS.get(iso2)
    by_count = _TERM_CALENDARS_BY_COUNT.get(iso2)
    if not codes and not windows and not by_count:
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
    if by_count:
        template["term_windows_by_count"] = {
            str(count): [list(w) for w in wins] for count, wins in by_count.items()
        }
    return template


def serialize_catalog(catalog: dict[str, Any]) -> str:
    """Pretty-print a catalog dict as JSON (matches the shipped file style)."""
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
