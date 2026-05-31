"""Tenant-aware terminology resolver (Wave A — G1, extends North Star SLICE 4).

Cascade (most-specific wins):

    0. Classroom override       Classroom.settings["terminology"][key]   (Wave K1, optional)
    1. School override          School.settings["terminology"][key]
    2. District / ancestors     walk School.parent_school chain
    3. Curriculum template      School.settings["curriculum_template_key"]
                                -> curriculum_templates_registry.terminology_map
    4. Country overlay          RuntimeDefaults.payload["lexicon.country_overrides"][country]
    5. Registry default         apps.siteconfig.lexicon_catalog.LEXICON_REGISTRY

Override storage shape is intentionally permissive — both the legacy 4-key
flat-string form (``{"grade": "Note"}``) and the v2 plural-aware form
(``{"student": {"singular": "Scholar", "plural": "Scholars"}}``) are accepted
at every layer. See ``lexicon_catalog.normalise_override``.

Public surface kept stable:

    DEFAULT_TERMINOLOGY                 # the 4 legacy keys, still flat-string
    TERMINOLOGY_KEYS                    # frozenset of the 4 legacy keys
    get_effective_terminology_for_school(school) -> dict[str, str]
    get_grade_label / get_gpa_label / get_term_label / get_report_label
    describe_terminology_resolution(school) -> str

Added in Wave A:

    resolve_term(school, key, *, plural=False) -> str
    resolve_all_terms(school) -> dict[str, dict[str, str]]
    lexicon_payload(school) -> dict          # JSON-serialisable for meta tag
"""

from __future__ import annotations

from typing import Any

from apps.siteconfig.curriculum_templates_service import get_template_terminology
from apps.siteconfig.lexicon_catalog import (
    LEXICON_REGISTRY,
    auto_plural,
    default_singular as _registry_singular,
)


# --- Back-compat constants -------------------------------------------------

# Canonical keys aligned with curriculum_templates_registry terminology_map.
TERMINOLOGY_KEYS = frozenset({"grade", "gpa", "term", "report_card"})

DEFAULT_TERMINOLOGY: dict[str, str] = {
    "grade": "Grade",
    "gpa": "GPA",
    "term": "Term",
    "report_card": "Report card",
}


# --- Internals -------------------------------------------------------------


def _school_settings_dict(school: Any) -> dict[str, Any]:
    raw = getattr(school, "settings", None)
    return raw if isinstance(raw, dict) else {}


def _country_overlay(country_code: str) -> dict[str, Any]:
    """Country layer terminology, sourced from ``RuntimeDefaults.payload``.

    Operator-editable: ``RuntimeDefaults.payload["lexicon.country_overrides"]``
    is a dict keyed by ISO alpha-2 country code, each value a terminology
    override dict in the same shape the school layer accepts.

    Reads the platform singleton directly (id=1 row); returns ``{}`` if the
    singleton is missing, the payload is empty, or the country has no entry.
    """
    code = (country_code or "").strip().upper()
    if not code:
        return {}
    try:
        from django.db import DatabaseError

        from apps.platform_runtime.models import RuntimeDefaults

        row = RuntimeDefaults.objects.order_by("pk").first()
    except (DatabaseError, ImportError, RuntimeError, ValueError, AttributeError):
        return {}
    if row is None:
        return {}
    payload = getattr(row, "payload", None) or {}
    overlay = payload.get("lexicon.country_overrides")
    if not isinstance(overlay, dict):
        return {}
    bucket = overlay.get(code)
    return bucket if isinstance(bucket, dict) else {}


def _ancestor_overrides(school: Any) -> list[dict[str, Any]]:
    """Walk School.parent_school chain from most-distant (root) to closest.

    Returned in root→nearest-parent order so the closest ancestor's overrides
    apply *last* (and therefore win over more-distant ones).
    """
    if school is None:
        return []
    chain: list[dict[str, Any]] = []
    seen: set[Any] = {getattr(school, "pk", None)}
    current = getattr(school, "parent_school", None)
    safety = 0
    while current is not None and safety < 16:
        safety += 1
        pk = getattr(current, "pk", None)
        if pk in seen:
            break
        seen.add(pk)
        terms = _school_settings_dict(current).get("terminology")
        if isinstance(terms, dict) and terms:
            chain.append(terms)
        current = getattr(current, "parent_school", None)
    # chain is currently nearest-first; reverse so root applies first, nearest last
    chain.reverse()
    return chain


def _apply_overlay(merged: dict[str, dict[str, str]], src: object) -> None:
    """Merge ``src`` into ``merged`` with override-aware plural semantics.

    Differs from raw ``merge_overrides`` in one important way: when a layer
    sets a new ``singular`` without an explicit ``plural``, any prior
    ``plural`` is **discarded** so the resolver can re-derive a plural from
    the new singular at lookup time. Otherwise a school overriding
    ``student → Scholar`` would inherit the default ``"Students"`` plural
    instead of "Scholars".
    """
    if not isinstance(src, dict):
        return
    for key, raw in src.items():
        from apps.siteconfig.lexicon_catalog import normalise_override

        norm = normalise_override(raw)
        if not norm:
            continue
        slot = merged.setdefault(key, {})
        if "singular" in norm and "plural" not in norm:
            slot.pop("plural", None)
        slot.update(norm)


def _classroom_overrides(classroom: Any) -> dict[str, Any]:
    """Return ``Classroom.settings["terminology"]`` if present and dict-shaped."""
    if classroom is None:
        return {}
    raw = getattr(classroom, "settings", None)
    if not isinstance(raw, dict):
        return {}
    terms = raw.get("terminology")
    return terms if isinstance(terms, dict) else {}


def _build_full_overlay(school: Any, classroom: Any = None) -> dict[str, dict[str, str]]:
    """Apply the cascade and return ``{key: {"singular"?:..., "plural"?:...}}``.

    Slots are **sparse** — a key is present only if some layer contributed
    to it. Callers (`resolve_term`, `resolve_all_terms`, `lexicon_payload`)
    fill in registry defaults at lookup time. This keeps plural derivation
    honest when an override sets only the singular.

    When ``classroom`` is supplied, ``Classroom.settings["terminology"]``
    applies as the **most-specific** layer (overrides the school's own).
    """
    merged: dict[str, dict[str, str]] = {}

    if school is None and classroom is None:
        return merged

    raw = _school_settings_dict(school) if school is not None else {}

    # Layer 2: country overlay
    country_code = getattr(school, "country_code", "") or ""
    _apply_overlay(merged, _country_overlay(country_code))

    # Layer 3: curriculum template (legacy 4-key flat shape from JSON registry)
    template_key = str(raw.get("curriculum_template_key") or "").strip()
    if template_key:
        tmpl_map = get_template_terminology(template_key)
        # tmpl_map is {"grade": "Note", ...} — flat strings; _apply_overlay handles.
        _apply_overlay(merged, tmpl_map)

    # Layer 4: ancestor schools (district / group)
    if school is not None:
        for ancestor_terms in _ancestor_overrides(school):
            _apply_overlay(merged, ancestor_terms)

    # Layer 5: school's own terminology override
    _apply_overlay(merged, raw.get("terminology"))

    # Layer 6 (Wave K1): classroom-level override — most specific, applied last.
    _apply_overlay(merged, _classroom_overrides(classroom))

    return merged


# --- New generic resolver --------------------------------------------------


def resolve_term(
    school: Any, key: str, *, plural: bool = False, classroom: Any = None
) -> str:
    """Resolve one term for ``school`` to its singular or plural form.

    Falls back to the registry default when no layer overrode the key.
    Unknown keys (not in the registry) return the key itself for singular
    and an auto-plural for plural.

    When ``classroom`` is supplied, classroom-level terminology overrides
    take precedence over the school's own (Wave K1).
    """
    overlay = _build_full_overlay(school, classroom=classroom)
    slot = overlay.get(key, {})
    singular = slot.get("singular") or _registry_singular(key)
    if not plural:
        return singular
    explicit_plural = slot.get("plural")
    if explicit_plural:
        return explicit_plural
    return _derive_plural(singular, key)


def _derive_plural(singular: str, key: str) -> str:
    """If a layer set singular but no plural, derive a sensible plural.

    Prefer the registry's curated plural (so "Class"→"Classes" still works
    when only a country layer set the singular). Only fall back to naive
    English rule if the singular has been changed enough that the registry
    plural no longer applies.
    """
    if key in LEXICON_REGISTRY:
        reg_sing, reg_plur, _cat, _desc = LEXICON_REGISTRY[key]
        if singular == reg_sing:
            return reg_plur
    return auto_plural(singular)


def resolve_all_terms(
    school: Any, classroom: Any = None
) -> dict[str, dict[str, str]]:
    """Return the entire resolved registry for one school.

    Useful for the settings UI preview and the meta-tag JSON payload.
    Shape: ``{key: {"singular": str, "plural": str}}``.

    When ``classroom`` is supplied, classroom-level overrides apply
    (Wave K1).
    """
    overlay = _build_full_overlay(school, classroom=classroom)
    out: dict[str, dict[str, str]] = {}
    for key, (def_sing, def_plur, _cat, _desc) in LEXICON_REGISTRY.items():
        slot = overlay.get(key, {})
        sing = slot.get("singular") or def_sing
        if "plural" in slot and slot["plural"]:
            plur = slot["plural"]
        elif "singular" in slot:
            # An overlay supplied a new singular without an explicit plural;
            # derive from the override rather than reusing the registry plural.
            plur = _derive_plural(sing, key)
        else:
            plur = def_plur
        out[key] = {"singular": sing, "plural": plur}
    return out


def lexicon_payload(
    school: Any, classroom: Any = None
) -> dict[str, dict[str, str]]:
    """Compact JSON-serialisable payload for the ``<meta name="rmc-lexicon">``
    bridge consumed by ``static/js/rmc-lexicon.js`` / ``RMC.term()``.

    Only emits entries that differ from the registry default to keep the
    meta-tag small on the wire. The JS helper falls back to its own
    bundled defaults when a key is absent.

    When ``classroom`` is supplied, classroom-level overrides take
    precedence (Wave K1).
    """
    all_terms = resolve_all_terms(school, classroom=classroom)
    out: dict[str, dict[str, str]] = {}
    for key, (def_sing, def_plur, _cat, _desc) in LEXICON_REGISTRY.items():
        slot = all_terms.get(key, {})
        sing = slot.get("singular") or def_sing
        plur = slot.get("plural") or def_plur
        if sing == def_sing and plur == def_plur:
            continue
        out[key] = {"s": sing, "p": plur}  # compact keys to shrink JSON
    return out


# --- Back-compat surface (kept stable) -------------------------------------


def get_effective_terminology_for_school(school: Any) -> dict[str, str]:
    """Resolve the four legacy keys for ``school``.

    Preserves the original {key: flat-string-singular} shape; existing
    callers and templates need not change.
    """
    overlay = _build_full_overlay(school)
    out = dict(DEFAULT_TERMINOLOGY)
    for key in TERMINOLOGY_KEYS:
        slot = overlay.get(key)
        if not slot:
            continue
        sing = slot.get("singular")
        if isinstance(sing, str) and sing.strip():
            out[key] = sing.strip()
    return out


def describe_terminology_resolution(school: Any) -> str:
    """Human-readable provenance for operator UI (preview only)."""
    if school is None:
        return "defaults"
    raw = _school_settings_dict(school)
    template_key = (raw.get("curriculum_template_key") or "").strip()
    overrides = raw.get("terminology") if isinstance(raw.get("terminology"), dict) else {}
    has_ov = any(
        overrides.get(k) and str(overrides.get(k) or "").strip() for k in overrides
    )
    if template_key and has_ov:
        return f"curriculum template ({template_key}) + tenant terminology override"
    if has_ov:
        return "tenant terminology override"
    if template_key:
        return f"curriculum template ({template_key})"
    return "product defaults"


def get_grade_label(school: Any) -> str:
    return get_effective_terminology_for_school(school)["grade"]


def get_gpa_label(school: Any) -> str:
    return get_effective_terminology_for_school(school)["gpa"]


def get_term_label(school: Any) -> str:
    return get_effective_terminology_for_school(school)["term"]


def get_report_label(school: Any) -> str:
    return get_effective_terminology_for_school(school)["report_card"]


def matrix_institution_vocabulary(country_code: str | None) -> dict[str, Any]:
    """
    Institution-type vocabulary from the country governance matrix (Phase 3C).

    Complements viewport-only ``prompt_shaping`` with lexicon keys operators
    expect in templates — ministry name, admin levels, school-type labels.
    """
    from apps.governance.country_matrix_service import get_matrix_row

    row = get_matrix_row(country_code)
    if not row:
        return {}

    local = row.get("local_terminology")
    if not isinstance(local, dict):
        local = {}

    out: dict[str, Any] = {
        "country_code": str(row.get("iso_alpha2") or "").upper(),
        "country_name": str(row.get("name_en") or ""),
        "governance_archetype": str(row.get("governance_archetype") or ""),
    }

    for key in ("teacher", "principal", "term", "report_card", "grade_level", "student"):
        entry = local.get(key)
        if isinstance(entry, dict):
            label = entry.get("en") or next(
                (v for v in entry.values() if isinstance(v, str) and v.strip()),
                None,
            )
            if label:
                out[key] = str(label)

    ministry = local.get("ministry_name")
    if isinstance(ministry, dict):
        label = ministry.get("en") or next(
            (v for v in ministry.values() if isinstance(v, str) and v.strip()),
            None,
        )
        if label:
            out["ministry_name"] = str(label)

    school_types = local.get("school_type_labels")
    if isinstance(school_types, list):
        out["school_type_labels"] = [
            item for item in school_types if isinstance(item, dict)
        ]

    admin_levels = row.get("admin_levels")
    if isinstance(admin_levels, list):
        out["admin_level_labels"] = admin_levels

    return out


def academic_structure_breadcrumb(school: Any, *, limit: int = 16) -> list[dict[str, str]]:
    """
    Active academic structure nodes for operator chrome (Phase 3C extension).

    Complements ``matrix_institution_vocabulary`` — country-level labels plus
    tenant-specific cycle/cohort/leaf trail from ``AcademicStructureNode``.
    """
    if school is None:
        return []
    try:
        from apps.academics.academic_structure import AcademicStructureNode
    except ImportError:
        return []

    cap = max(1, min(int(limit), 32))
    qs = (
        AcademicStructureNode.objects.filter(school=school, is_active=True)
        .order_by("sort_order", "local_label")[:cap]
    )
    trail: list[dict[str, str]] = []
    for node in qs:
        trail.append(
            {
                "id": str(node.id),
                "label": str(node.local_label or ""),
                "node_type": str(node.node_type or ""),
            }
        )
    return trail


def matrix_institution_vocabulary_with_structure(
    country_code: str | None,
    school: Any = None,
    *,
    breadcrumb_limit: int = 16,
) -> dict[str, Any]:
    """Matrix vocabulary plus optional tenant academic-structure breadcrumb."""
    out = matrix_institution_vocabulary(country_code)
    if school is not None:
        crumb = academic_structure_breadcrumb(school, limit=breadcrumb_limit)
        if crumb:
            out["academic_structure_breadcrumb"] = crumb
    return out


__all__ = [
    "DEFAULT_TERMINOLOGY",
    "TERMINOLOGY_KEYS",
    "describe_terminology_resolution",
    "get_effective_terminology_for_school",
    "get_grade_label",
    "get_gpa_label",
    "get_report_label",
    "get_term_label",
    "lexicon_payload",
    "academic_structure_breadcrumb",
    "matrix_institution_vocabulary",
    "matrix_institution_vocabulary_with_structure",
    "resolve_all_terms",
    "resolve_term",
]
