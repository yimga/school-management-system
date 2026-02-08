"""Shared grouping helpers for admin theme packs."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple


# Canonical theme groups for distinct visual feel (avoid near-duplicate catalog rows).
THEME_PALETTE_GROUPS: Sequence[Tuple[str, Sequence[str]]] = (
    (
        "Leadership & Academic",
        (
            "admin-academic-authority",
            "admin-executive-ivy",
            "admin-modern-chancellor",
            "admin-focused-classroom",
            "admin-academic-slate",
            "admin-slate-gray",
        ),
    ),
    (
        "Campus Warmth",
        (
            "admin-gilead-warm-pink",
            "admin-sunset-study",
            "admin-sunset-warm",
            "admin-modern-sage",
            "admin-verdant-growth",
            "admin-digital-lavender",
        ),
    ),
    (
        "Blue Spectrum",
        (
            "admin-campus-blue",
            "admin-sky-blue",
            "admin-ocean-blue",
            "admin-indigo-lecture",
            "admin-sophisticated-slate",
        ),
    ),
    (
        "STEM & Technical",
        (
            "admin-tech-pioneer",
            "admin-cyber-lab",
            "admin-blueprint",
            "admin-retro-future",
            "admin-bento-box",
        ),
    ),
    (
        "Accessibility & Inclusion",
        (
            "admin-high-contrast-light",
            "admin-high-contrast-dark",
            "admin-high-contrast-accessible",
            "admin-sensory-room",
            "admin-focus-mode",
        ),
    ),
    (
        "Boutique & Conservatory",
        (
            "admin-conservatory",
            "admin-modern-gallery",
            "admin-forest-academy",
            "admin-forest-green",
            "admin-eco-digital",
        ),
    ),
    (
        "Contemporary Experimental",
        (
            "admin-glassmorphism",
            "admin-neo-brutalist",
            "admin-monochrome-pro",
        ),
    ),
    (
        "Dark Focus",
        (
            "admin-midnight-scholar",
            "admin-the-midnight-scholar",
            "admin-gilead-dark-neutral",
            "admin-deep-space-midnight",
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
