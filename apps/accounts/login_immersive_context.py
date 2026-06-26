"""Anonymous login page immersive canvas — ticker, carousel, moments, dash feed."""

from __future__ import annotations

from typing import Any

from apps.accounts.login_immersive_canvas import build_login_immersive_render_context


def build_login_immersive_context(request: Any) -> dict[str, Any]:
    """Build template-safe immersive login payload (anonymous-safe reads only)."""
    return build_login_immersive_render_context(request)
