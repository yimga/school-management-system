"""Blueprint → module (``School.features``) bridge.

Historically ``apply_blueprint()`` only wrote ``School.settings``; the opt-in modules a
blueprint's archetype implies (a boarding school's dormitory, a low-connectivity school's
offline sync) still had to be switched on by hand in the Module Market afterward. This
bridge resolves the toggleable feature codes a blueprint *explicitly* names and turns them
on in ``School.features`` when the blueprint is applied.

Only codes that (a) the blueprint explicitly declares — via ``requires_features``, or a
``modules`` / ``requires_modules`` label that maps to a real registry code — AND (b) exist
in the live feature registry are enabled. Nothing is fabricated: a blueprint whose modules
are all core surfaces (Attendance, Reports, Fees) enables nothing, which is correct — those
are always on. Paywalled modules are protected by the optional ``entitled_codes`` gate: a
code outside that set is reported as ``skipped_unentitled`` and never silently granted.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Blueprint module label → registry feature code(s). Keys are normalised
# (lowercase, "-" and "/" → space, whitespace collapsed). Only labels with a real
# toggleable module equivalent appear; core surfaces (attendance/reports/fees/…) are
# deliberately absent so they map to nothing and are left alone (they are always on).
_LABEL_TO_CODES: dict[str, tuple[str, ...]] = {
    "library": ("library",),
    "transport": ("transport",),
    "canteen": ("canteen",),
    "cafeteria": ("canteen",),
    "meals": ("canteen",),
    "meal plans": ("canteen",),
    "parent chat": ("parent_chat",),
    "parent portal": ("parent_chat",),
    "communication": ("parent_chat",),
    "messaging": ("parent_chat",),
    "cahier de texte": ("cahier_de_texte",),
    "homework diary": ("cahier_de_texte",),
    "class diary": ("cahier_de_texte",),
    "offline sync": ("offline_mode",),
    "offline mode": ("offline_mode",),
    "offline": ("offline_mode",),
    "alumni": ("alumni",),
    "hostel": ("dormitory",),
    "dormitory": ("dormitory",),
    "boarding": ("dormitory",),
    "inventory": ("inventory",),
    "stock": ("inventory",),
    "clinic": ("clinic",),
    "health": ("clinic",),
    "infirmary": ("clinic",),
    "timetable": ("timetabling",),
    "timetabling": ("timetabling",),
    "scheduling": ("timetabling",),
    "substitutes": ("substitutes",),
    "cover": ("substitutes",),
    "visitor log": ("visitor_log",),
    "reception": ("visitor_log",),
    "facilities": ("facilities_ops",),
    "maintenance": ("facilities_ops",),
    "pos": ("pos_stub",),
    "till": ("pos_stub",),
}


def _norm(label: str) -> str:
    return " ".join(
        (label or "").strip().lower().replace("-", " ").replace("/", " ").split()
    )


def _available_codes() -> set[str]:
    """Every feature code the platform actually exposes (static registry ∪ live DB registry)."""
    codes: set[str] = set()
    try:
        from apps.schools.feature_registry import (
            FEATURE_REGISTRY,
            get_available_modules,
        )

        for module in FEATURE_REGISTRY:
            code = (module.get("code") or "").strip()
            if code:
                codes.add(code)
        try:
            for module in get_available_modules():
                code = (module.get("code") or "").strip()
                if code:
                    codes.add(code)
        except Exception:  # noqa: BLE001 — DB registry is a bonus source, never fatal
            pass
    except Exception:  # noqa: BLE001 — registry import must never break blueprint apply
        pass
    return codes


def resolve_blueprint_feature_codes(blueprint) -> list[str]:
    """Toggleable feature codes a blueprint explicitly implies, filtered to real registry codes.

    Union of explicit ``requires_features`` machine codes and codes mapped from the
    blueprint's ``modules`` / ``requires_modules`` labels. Unknown labels contribute
    nothing (never fabricated). Result is filtered to codes the live registry exposes.
    """
    wanted: set[str] = set()
    for code in getattr(blueprint, "requires_features", ()) or ():
        code = (code or "").strip()
        if code:
            wanted.add(code)
    labels = list(getattr(blueprint, "modules", ()) or ()) + list(
        getattr(blueprint, "requires_modules", ()) or ()
    )
    for label in labels:
        for code in _LABEL_TO_CODES.get(_norm(label), ()):
            wanted.add(code)
    available = _available_codes()
    if available:
        wanted = {code for code in wanted if code in available}
    return sorted(wanted)


def enable_blueprint_modules(
    school, blueprint, *, persist: bool = True, entitled_codes=None
) -> dict:
    """Switch on a blueprint's implied module codes in ``School.features``.

    ``entitled_codes``: optional iterable of codes the school may enable. When provided,
    codes outside it are skipped (reported under ``skipped_unentitled``) so a paywalled
    module is never silently granted. When ``None`` (default), every resolved registry
    code is enabled — correct today because the opt-in modules are Free and plan gating
    is not enforced, and future-proof because callers can pass the entitled set later.

    Returns a summary dict: ``resolved`` / ``enabled`` / ``already_on`` / ``skipped_unentitled``.
    """
    result: dict[str, list[str]] = {
        "enabled": [],
        "already_on": [],
        "skipped_unentitled": [],
        "resolved": [],
    }
    if school is None or blueprint is None:
        return result
    resolved = resolve_blueprint_feature_codes(blueprint)
    result["resolved"] = resolved
    if not resolved:
        return result

    entitled = None if entitled_codes is None else {str(c) for c in entitled_codes}
    current = dict(getattr(school, "features", None) or {})
    changed = False
    for code in resolved:
        if entitled is not None and code not in entitled:
            result["skipped_unentitled"].append(code)
            continue
        if current.get(code) is True:
            result["already_on"].append(code)
            continue
        current[code] = True
        result["enabled"].append(code)
        changed = True

    if persist and changed:
        school.features = current
        school.save(update_fields=["features", "updated_at"])
        try:
            from apps.policies.policy_registry import invalidate_policy_cache

            invalidate_policy_cache(school)
        except Exception:  # noqa: BLE001 — cache invalidation is best-effort
            pass
    return result
