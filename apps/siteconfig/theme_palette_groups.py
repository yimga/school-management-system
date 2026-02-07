"""Shared grouping helpers for admin theme packs."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple


# Canonical theme pack groups used by Site Settings and Theme & Experience pages.
THEME_PALETTE_GROUPS: Sequence[Tuple[str, Sequence[str]]] = (
    (
        "School (Admin)",
        (
            "admin-academic-authority",
            "admin-executive-ivy",
            "admin-modern-chancellor",
            "admin-sophisticated-slate",
            "admin-digital-lavender",
            "admin-modern-sage",
            "admin-focused-classroom",
            "admin-verdant-growth",
            "admin-sensory-room",
        ),
    ),
    ("Neutrals", ("admin-academic-slate", "admin-slate-gray")),
    ("Blues", ("admin-campus-blue", "admin-sky-blue", "admin-ocean-blue", "admin-indigo-lecture")),
    ("Greens", ("admin-forest-academy", "admin-forest-green")),
    ("Warm", ("admin-gilead-warm-pink", "admin-sunset-study", "admin-sunset-warm")),
    (
        "Dark",
        ("admin-midnight-scholar", "admin-gilead-dark-neutral", "admin-deep-space-midnight", "admin-the-midnight-scholar"),
    ),
    (
        "Niche (STEM / Specialized / Boutique)",
        (
            "admin-cyber-lab",
            "admin-blueprint",
            "admin-tech-pioneer",
            "admin-high-contrast-accessible",
            "admin-focus-mode",
            "admin-conservatory",
            "admin-modern-gallery",
        ),
    ),
    (
        "Contemporary",
        (
            "admin-glassmorphism",
            "admin-neo-brutalist",
            "admin-eco-digital",
            "admin-monochrome-pro",
            "admin-retro-future",
            "admin-bento-box",
        ),
    ),
    ("Accessibility", ("admin-high-contrast-light", "admin-high-contrast-dark")),
)


def build_theme_pack_groups(
    packs: Iterable,
    groups: Sequence[Tuple[str, Sequence[str]]] = THEME_PALETTE_GROUPS,
) -> List[Tuple[str, list]]:
    """Return grouped packs by known slugs, plus an 'Other' bucket for unmatched packs."""
    all_packs = list(packs)
    slug_to_pack = {pack.slug: pack for pack in all_packs}
    grouped: List[Tuple[str, list]] = []

    for group_label, slugs in groups:
        packs_in_group = [slug_to_pack[slug] for slug in slugs if slug in slug_to_pack]
        if packs_in_group:
            grouped.append((group_label, packs_in_group))

    in_any_group = {pack for _, plist in grouped for pack in plist}
    other = [pack for pack in all_packs if pack not in in_any_group]
    if other:
        grouped.append(("Other", other))
    return grouped
