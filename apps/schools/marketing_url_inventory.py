"""
Marketing URL names on the root urlconf: reverse paths and smoke-test metadata.

Used by ``manage.py validate_marketing_urls --full`` and marketing tests so the
inventory stays aligned with ``config/urls.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import NoReverseMatch, get_resolver, reverse


@dataclass(frozen=True)
class MarketingUrlSmokeTarget:
    """One smoke target (usually GET). POST-only routes may legitimately return 405 on GET."""

    name: str
    path: str
    ok_statuses: frozenset[int]

    def accepts(self, status_code: int) -> bool:
        return status_code in self.ok_statuses


# ``marketing_book_demo_submit`` is ``@require_POST``; GET must return 405, not 200.
_POST_ONLY_MARKETING_NAMES = frozenset(
    {
        "marketing_book_demo_submit",
        "marketing_contact_submit",
        "marketing_security_packet_submit",
    }
)
_GET_OK_DEFAULT = frozenset({200})
_GET_OK_POST_ONLY = frozenset({200, 405})


# Slug must exist after ``seed_marketing_cms`` (or equivalent) for 200.
BLOG_DETAIL_SEED_SLUG = "from-spreadsheets-to-one-platform"

# MULTI-PERSONALITY-GRID + acquisition engine (batch 1567).
ACQUISITION_PERSONALITY_SLUGS: tuple[str, ...] = (
    "zero-ui",
    "enterprise-ledger",
    "edge-mesh",
    "academics",
    "compliance",
    "pricing",
)

_MARKETING_REVERSE_KWARGS: dict[str, dict] = {
    "marketing_blog_detail": {"slug": BLOG_DETAIL_SEED_SLUG},
    "marketing_buyer_toolkit_download": {"document": "buyer-checklist"},
    "marketing_topic": {"topic_slug": "admissions-software"},
}

def _collect_marketing_url_names() -> list[str]:
    found: list[str] = []

    def walk(patterns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns)
                continue
            n = getattr(p, "name", None)
            if n and isinstance(n, str) and n.startswith("marketing_"):
                found.append(n)

    walk(get_resolver().url_patterns)
    return sorted(set(found))


# Role, institution, migrate, and conversion entrypoints linked from marketing shell (root urlconf).
_MARKETING_ADJACENT_REVERSE: list[tuple[str, dict | None]] = [
    ("institution_k12", None),
    ("institution_universities", None),
    ("institution_technical_schools", None),
    ("institution_private_schools", None),
    ("institution_government_education", None),
    ("role_school_admin", None),
    ("role_teachers", None),
    ("role_parents", None),
    ("role_students", None),
    ("role_it_directors", None),
    ("role_government", None),
    ("migrate_marketing_page", None),
    ("migrate_marketing_page_source", {"source_slug": "from-power-school"}),
    ("onboard_wizard", None),
    ("signup_school", None),
    ("global_login_discovery", None),
    ("find_school", None),
    ("developer_public_api_docs", None),
]


def iter_marketing_adjacent_smoke_targets() -> list[MarketingUrlSmokeTarget]:
    """Public routes commonly linked from marketing nav/footer (not ``marketing_*`` names)."""
    targets: list[MarketingUrlSmokeTarget] = []
    for name, kwargs in _MARKETING_ADJACENT_REVERSE:
        try:
            path = reverse(name, kwargs=kwargs) if kwargs else reverse(name)
        except NoReverseMatch:
            continue
        targets.append(
            MarketingUrlSmokeTarget(name=name, path=path, ok_statuses=frozenset({200}))
        )
    return targets


def iter_marketing_smoke_targets() -> list[MarketingUrlSmokeTarget]:
    """
    All ``marketing_*`` names from the active URLconf, reversed with sample kwargs where needed.
    """
    targets: list[MarketingUrlSmokeTarget] = []
    for name in _collect_marketing_url_names():
        kwargs = _MARKETING_REVERSE_KWARGS.get(name)
        try:
            if kwargs is not None:
                path = reverse(name, kwargs=kwargs)
            else:
                path = reverse(name)
        except NoReverseMatch:
            continue
        ok = (
            _GET_OK_POST_ONLY
            if name in _POST_ONLY_MARKETING_NAMES
            else _GET_OK_DEFAULT
        )
        targets.append(MarketingUrlSmokeTarget(name=name, path=path, ok_statuses=ok))
    return targets


def iter_marketing_acquisition_smoke_targets() -> list[MarketingUrlSmokeTarget]:
    """Storefront + experience/* personality pages (batch 1567 acquisition engine)."""
    targets: list[MarketingUrlSmokeTarget] = []
    storefront = resolve_marketing_url("marketing_intent_homepage")
    if storefront:
        targets.append(
            MarketingUrlSmokeTarget(
                name="marketing_intent_homepage",
                path=storefront,
                ok_statuses=_GET_OK_DEFAULT,
            )
        )
    for slug in ACQUISITION_PERSONALITY_SLUGS:
        path = resolve_marketing_url(
            "marketing_personality_page", kwargs={"personality_slug": slug}
        )
        if not path:
            continue
        targets.append(
            MarketingUrlSmokeTarget(
                name=f"marketing_personality_page:{slug}",
                path=path,
                ok_statuses=_GET_OK_DEFAULT,
            )
        )
    return targets


def resolve_marketing_url(name: str, *, kwargs: dict | None = None) -> str | None:
    try:
        return reverse(name, kwargs=kwargs) if kwargs else reverse(name)
    except NoReverseMatch:
        return None
