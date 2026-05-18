"""Body-only renders for Studio OS iframe / in-canvas embeds (no portal or CP chrome)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def request_wants_studio_embed(request: HttpRequest) -> bool:
    return (request.GET.get("embed") or "").strip().lower() in ("1", "true", "yes")


def render_studio_embed_body(
    request: HttpRequest,
    body_template: str,
    context: dict[str, Any] | None = None,
    *,
    title: str = "",
) -> HttpResponse:
    """Minimal document: tokens + bootstrap + single body partial (Wave 2 contract)."""
    ctx = dict(context or {})
    ctx["studio_embed_title"] = title
    ctx["studio_embed_body_template"] = body_template
    return render(request, "studio_os/studio_embed_body_shell.html", ctx)
