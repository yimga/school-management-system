"""Shared grouping helpers for admin theme packs."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple


# Canonical theme groups for distinct visual feel (avoid near-duplicate catalog rows).
THEME_PALETTE_GROUPS: Sequence[Tuple[str, Sequence[str]]] = (
    (
        "Leadership & Academic",
        (
            "admin-academic-slate",
            "admin-academic-authority",
            "admin-campus-blue",
        ),
    ),
    (
        "Blue Spectrum",
        (
            "admin-ocean-blue",
            "admin-indigo-lecture",
            "admin-digital-lavender",
        ),
    ),
    (
        "Warm & Human",
        (
            "admin-runmycampus-warm-pink",
            "admin-sunset-study",
            "admin-sunset-warm",
        ),
    ),
    (
        "Nature & Growth",
        (
            "admin-forest-academy",
            "admin-modern-sage",
            "admin-verdant-growth",
        ),
    ),
    (
        "STEM & Contemporary",
        (
            "admin-tech-pioneer",
            "admin-cyber-lab",
            "admin-glassmorphism",
        ),
    ),
    (
        "Accessibility & Premium",
        (
            "admin-midnight-scholar",
            "admin-high-contrast-accessible",
            "admin-conservatory",
        ),
    ),
    (
        "Ultra High-End",
        (
            "admin-ultra-gallery",
            "admin-ultra-noir",
            "admin-ultra-platinum",
        ),
    ),
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
