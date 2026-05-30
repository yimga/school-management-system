"""v4.00.69 — Single-source-of-truth for the LMS providers the platform's
OAuth flows, token-refresh sweeps, and audit beats recognize.

Historically each of those modules carried its own hardcoded
``{"canvas", "moodle", "google"}`` literal set (see
``lms_token_refresh.py``, ``lms_token_rotation.py``,
``lms_oauth_health.py``, ``lms_oauth_auto_prune.py``). That meant adding a
new provider — Schoology, Brightspace D2L, etc. — required hunting down 4+
files. This module is the single platform-constant tier and the place new
providers are registered going forward.

The ``LMSConnectorToken.Provider`` TextChoices enum on the model still
governs *legacy* persisted-row provider values (3 entries). New providers
land here first as "supported" but require a migration to be persisted via
the model — until then they live in a sibling key/value store keyed by
``service_name`` (already wired through the v3.39.x ``ServiceIntegration``
plumbing).

Scaffold vs ready:

* ``SUPPORTED_LMS_PROVIDERS`` — all providers the platform recognizes
  (regardless of OAuth-flow maturity)
* ``OAUTH_READY_LMS_PROVIDERS`` — providers with a fully-wired OAuth
  exchange path in ``lms_token_refresh.py::_refresh_one``
* ``SCAFFOLD_LMS_PROVIDERS`` — providers with adapter stubs but no
  production OAuth flow yet (do NOT attempt refresh; do NOT show in the
  consent-grant UI)

Wave history:
  v4.00.69 — module introduced; Schoology added as scaffold
  v4.00.70 — Brightspace D2L added as scaffold (planned)
  v4.00.71+ — Schoology OAuth promoted to OAUTH_READY
  v4.00.72+ — D2L OAuth promoted to OAUTH_READY
"""
from __future__ import annotations

# Stable provider slugs. Order is canonical (used by the rollup UI card).
PROVIDER_CANVAS = "canvas"
PROVIDER_MOODLE = "moodle"
PROVIDER_GOOGLE_CLASSROOM = "google_classroom"
# Some legacy code paths call Google Classroom just "google" (predates the
# v4.00.54 rename). Both work; we accept either as input but prefer
# ``google_classroom`` for new audit rows.
PROVIDER_GOOGLE_LEGACY_ALIAS = "google"
PROVIDER_SCHOOLOGY = "schoology"
PROVIDER_BRIGHTSPACE_D2L = "d2l_brightspace"
PROVIDER_BLACKBOARD = "blackboard"
PROVIDER_POWERSCHOOL = "powerschool"
PROVIDER_SAKAI = "sakai"
PROVIDER_ITSLEARNING = "itslearning"


# Canonical platform-wide list.
SUPPORTED_LMS_PROVIDERS = frozenset({
    PROVIDER_CANVAS,
    PROVIDER_MOODLE,
    PROVIDER_GOOGLE_CLASSROOM,
    PROVIDER_GOOGLE_LEGACY_ALIAS,
    PROVIDER_SCHOOLOGY,
    PROVIDER_BRIGHTSPACE_D2L,
    PROVIDER_BLACKBOARD,
    PROVIDER_POWERSCHOOL,
    PROVIDER_SAKAI,
    PROVIDER_ITSLEARNING,
})

# Providers whose OAuth refresh flow is wired in ``lms_token_refresh.py``.
OAUTH_READY_LMS_PROVIDERS = frozenset({
    PROVIDER_CANVAS,
    PROVIDER_MOODLE,
    PROVIDER_GOOGLE_CLASSROOM,
    PROVIDER_GOOGLE_LEGACY_ALIAS,
})

# Providers w/ adapter stubs only — DO NOT attempt OAuth exchange. The
# diagnostics UI surfaces these as "Scaffold (coming soon)" pills.
SCAFFOLD_LMS_PROVIDERS = frozenset({
    PROVIDER_SCHOOLOGY,
    PROVIDER_BRIGHTSPACE_D2L,
    PROVIDER_BLACKBOARD,
    PROVIDER_POWERSCHOOL,
    PROVIDER_SAKAI,
    PROVIDER_ITSLEARNING,
})


def is_supported_lms_provider(provider: str) -> bool:
    """Return True iff ``provider`` is recognized by the platform.

    Case-insensitive on the slug.
    """
    return (provider or "").strip().lower() in SUPPORTED_LMS_PROVIDERS


def is_oauth_ready_lms_provider(provider: str) -> bool:
    """Return True iff the provider has a wired OAuth refresh path."""
    return (provider or "").strip().lower() in OAUTH_READY_LMS_PROVIDERS


def is_scaffold_lms_provider(provider: str) -> bool:
    """Return True iff the provider is a v4.00.69+ scaffold (adapter only,
    no production OAuth flow yet)."""
    return (provider or "").strip().lower() in SCAFFOLD_LMS_PROVIDERS


def canonical_lms_provider_label(provider: str) -> str:
    """Operator-facing label. Honors the v4.00.54 google→google_classroom
    rename — legacy 'google' renders as 'Google Classroom'.
    """
    p = (provider or "").strip().lower()
    return {
        PROVIDER_CANVAS: "Canvas LMS",
        PROVIDER_MOODLE: "Moodle",
        PROVIDER_GOOGLE_CLASSROOM: "Google Classroom",
        PROVIDER_GOOGLE_LEGACY_ALIAS: "Google Classroom",
        PROVIDER_SCHOOLOGY: "Schoology",
        PROVIDER_BRIGHTSPACE_D2L: "Brightspace (D2L)",
        PROVIDER_BLACKBOARD: "Blackboard Learn",
        PROVIDER_POWERSCHOOL: "PowerSchool Learning",
        PROVIDER_SAKAI: "Sakai",
        PROVIDER_ITSLEARNING: "Itslearning",
    }.get(p, p or "unknown")


def lms_provider_rollup_order() -> tuple[str, ...]:
    """Canonical display order for the diagnostics rollup card."""
    return (
        PROVIDER_CANVAS,
        PROVIDER_MOODLE,
        PROVIDER_GOOGLE_CLASSROOM,
        PROVIDER_SCHOOLOGY,
        PROVIDER_BRIGHTSPACE_D2L,
        PROVIDER_BLACKBOARD,
        PROVIDER_POWERSCHOOL,
        PROVIDER_SAKAI,
        PROVIDER_ITSLEARNING,
    )


def lms_provider_rollup_card() -> list[dict]:
    """v4.00.73 — Render-ready list-of-dicts for the operator dashboard's
    "providers" card. Consumes ``lms_provider_rollup_order()`` and decorates
    each provider w/ label + maturity pill ("Production" vs "Scaffold").

    Returns: ``[{slug, label, maturity, oauth_ready, is_scaffold, pill}]``
    where ``pill`` is the rendered chip text the template displays.
    """
    cards: list[dict] = []
    for slug in lms_provider_rollup_order():
        oauth_ready = is_oauth_ready_lms_provider(slug)
        scaffold = is_scaffold_lms_provider(slug)
        if oauth_ready:
            maturity = "production"
            pill = "Production"
        elif scaffold:
            maturity = "scaffold"
            pill = "Scaffold (coming soon)"
        else:
            maturity = "unknown"
            pill = "Unknown"
        cards.append({
            "slug": slug,
            "label": canonical_lms_provider_label(slug),
            "maturity": maturity,
            "oauth_ready": oauth_ready,
            "is_scaffold": scaffold,
            "pill": pill,
        })
    return cards
