"""Operator-facing control-plane brand tokens (manager host).

Maps RuntimeDefaults ``public_brand_*`` (and env fallbacks already applied in
the context processor) into CSS custom properties consumed by control-plane shells.
"""

from __future__ import annotations


def control_plane_brand_css_vars(
    *,
    primary_color: str,
    accent_color: str,
) -> str:
    """Inline :root rules for ``control_plane_skeleton`` / ``control_plane_base``."""
    primary = (primary_color or "#002147").strip()
    accent = (accent_color or "#d4af37").strip()
    return (
        ":root{"
        f"--rmc-operator-primary:{primary};"
        f"--rmc-operator-accent:{accent};"
        f"--school-primary:{primary};"
        f"--color-primary:{primary};"
        "}"
        "body.control-plane-shell{"
        f"--cp-ultra-gold:var(--rmc-operator-accent);"
        f"--cp-gold-600:var(--rmc-operator-accent);"
        f"--cp-gold-500:var(--rmc-operator-accent);"
        f"--cp-gold-700:var(--rmc-operator-accent);"
        f"--cp-accent-2:var(--rmc-operator-accent);"
        f"--cp-operator-chrome-primary:var(--rmc-operator-primary);"
        "}"
    )
