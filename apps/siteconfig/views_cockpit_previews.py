"""Operator preview viewer for the v3.55+ design previews — v3.57.2.

Surfaces the two byte-stable HTML preview artifacts committed under
``docs/generated/`` so operators can compare current shell behavior against
the published design previews WITHOUT having to clone the repo or open the
files from the filesystem:

  * ``preview_app_shell_manager_v8_200x.html`` — manager / control plane
    200x luxury preview (10 elements: AI Copilot rail, world map, forecast
    lane, tenant heatmap, revenue waterfall, audit feed, trust nutrition,
    SLO clocks, operator presence, operator notebook).
  * ``preview_app_shell_tenant_portal_v3.html`` — tenant portal v3 100x
    preview (community band, newsletter band, achievement card, parent
    testimonial rotator, district map, etc.).

Access:
  * ``GET /siteconfig/super/configure/cockpit/previews/`` — staff-only index
    page with embedded iframes (one preview per panel).
  * ``GET /siteconfig/super/configure/cockpit/previews/<slug>/`` — raw HTML
    served directly (so iframes can load it; also for direct sharing).

PII safety:
  * Previews ship with placeholder data only (no real tenant/student/staff
    identifiers). The Django view does NOT inject any request-context
    values into them — they render exactly as committed.
  * Staff-only (``UserPassesTestMixin``) so even with placeholder data the
    surface stays behind operator auth.

Path-traversal safety:
  * The ``slug`` parameter is matched against a hardcoded SLUG_TO_PATH map.
  * No filesystem walks; an unknown slug returns 404 explicitly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404, HttpRequest, HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View


# Resolve docs/generated/ relative to the repo root. settings.BASE_DIR is the
# canonical Django root (config/settings.py uses pathlib here).
_REPO_ROOT = Path(getattr(settings, "BASE_DIR", Path(__file__).resolve().parent.parent.parent))
_PREVIEW_DIR = _REPO_ROOT / "docs" / "generated"


# Slug → (filename, label, description). The slugs are intentionally short
# and hyphenated so the URL fragment is stable for sharing.
PREVIEWS: dict[str, dict[str, str]] = {
    "manager-v8-200x": {
        "filename": "preview_app_shell_manager_v8_200x.html",
        "label": "Manager v8 · 200x luxury preview",
        "description": (
            "Control plane shell with 10 luxury elements: AI Copilot rail · "
            "world map · forecast lane · tenant heatmap · revenue waterfall · "
            "audit feed · trust nutrition · SLO clocks · operator presence · "
            "operator notebook."
        ),
    },
    "tenant-portal-v3-100x": {
        "filename": "preview_app_shell_tenant_portal_v3.html",
        "label": "Tenant portal v3 · 100x preview",
        "description": (
            "Tenant shell with civic 4-tier footer + community band "
            "(student of the month · parent testimonial rotator · district "
            "map) + newsletter signup band + 100x luxury elements (B-Corp / "
            "Green School certification chips · calendar .ics download)."
        ),
    },
}


def _staff_test(user: Any) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


class CockpitPreviewIndexView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Operator-facing index page with embedded iframes for each preview."""

    template_name = "siteconfig/super/cockpit_previews.html"
    raise_exception = True

    def test_func(self) -> bool:
        return _staff_test(self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        previews: list[dict[str, Any]] = []
        for slug, meta in PREVIEWS.items():
            file_path = _PREVIEW_DIR / meta["filename"]
            previews.append(
                {
                    "slug": slug,
                    "label": meta["label"],
                    "description": meta["description"],
                    "filename": meta["filename"],
                    "exists": file_path.exists(),
                    "size_kb": (
                        round(file_path.stat().st_size / 1024, 1)
                        if file_path.exists()
                        else 0
                    ),
                }
            )
        ctx["previews"] = previews
        ctx["page_title"] = _("Cockpit design previews")
        return ctx


class CockpitPreviewServeView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Serve a single preview HTML by slug — used as the iframe src."""

    raise_exception = True

    def test_func(self) -> bool:
        return _staff_test(self.request.user)

    def get(self, request: HttpRequest, slug: str) -> HttpResponse:
        meta = PREVIEWS.get(slug)
        if not meta:
            raise Http404("preview slug not registered")
        file_path = _PREVIEW_DIR / meta["filename"]
        if not file_path.exists():
            raise Http404(f"preview file missing: {meta['filename']}")
        try:
            html = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise Http404(f"preview read failed: {exc}") from exc
        # Serve as HTML — no caching headers so updates take effect immediately
        # after deploy. Previews are operator-only so cache-busting is fine.
        response = HttpResponse(html, content_type="text/html; charset=utf-8")
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        # Same-origin only — previews can be iframed only by other pages on
        # this host (the index view above).
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response
