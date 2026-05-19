"""Resize attached media to provider-specific dimensions (URL passthrough metadata)."""

from __future__ import annotations

# Provider max dimensions (width, height) for feed cards / posts.
_PROVIDER_DIMS: dict[str, tuple[int, int]] = {
    "x": (1200, 675),
    "instagram": (1080, 1080),
    "linkedin": (1200, 627),
    "facebook": (1200, 630),
}


def resize_for_provider(url: str, provider: str) -> str:
    """
    Return a CDN/transform URL when ``SOCIAL_ASSET_CDN_BASE`` is set; otherwise
    annotate via query params for downstream workers.
    """
    from django.conf import settings

    w, h = _PROVIDER_DIMS.get(provider, (1200, 630))
    base = getattr(settings, "SOCIAL_ASSET_CDN_BASE", "").rstrip("/")
    if base:
        return f"{base}/resize?url={url}&w={w}&h={h}&provider={provider}"
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}rmc_social_w={w}&rmc_social_h={h}&rmc_provider={provider}"
