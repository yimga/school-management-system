"""LTI 1.3 tool-registration admin surface (Wave 25 v4.00.92, H7).

Operator workflow: register Khan / Quizlet / Kahoot / etc. as LTI 1.3 tools
so they appear in the LTI launch grid. Each registration writes a
``ServiceIntegration`` row (``service_type=LTI``) with all the tool's
metadata stored in ``config`` JSON.

Surface:

- :class:`LTIToolRegistrationForm` — Django form for the registration
  payload, including a closed-vocab ``permitted_scopes`` MultipleChoice
  bound to the 5 standard LTI 1.3 scope URIs.
- :class:`LTIToolRegistrationListView` — staff-only list at
  ``/super/lti/tools/``.
- :class:`LTIToolRegistrationCreateView` — staff-only create at
  ``/super/lti/tools/register/``. On save mints a one-time secret shown
  ONCE on the result page (only ``sha256[:64]`` of it is persisted under
  ``config["lti_tool_secret_hash"]``).
- :class:`LTIToolRegistrationDetailView` — staff-only detail/edit at
  ``/super/lti/tools/<id>/``.

# rbac-allow: super-staff-lti-tool-registration-admin
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from apps.schools.lti_tool_token import STANDARD_LTI_SCOPES

logger = logging.getLogger(__name__)


_SCOPE_CHOICES = tuple((s, s.split("/")[-1]) for s in STANDARD_LTI_SCOPES)


class LTIToolRegistrationForm(forms.Form):
    """Registration form for a new LTI 1.3 tool integration."""

    tool_name = forms.CharField(
        max_length=80, label="Tool name",
        help_text="Display name shown in operator and teacher LTI launchers.",
    )
    tool_client_id = forms.CharField(
        max_length=128, label="Client ID",
        help_text="Stable identifier the tool will send in client_assertion.iss/sub.",
    )
    platform_id = forms.URLField(
        label="Platform iss (RunMyCampus host)",
        help_text="The iss claim our platform uses when signing JWTs to this tool.",
    )
    deployment_id = forms.CharField(
        max_length=64, label="Deployment ID",
        help_text="LTI 1.3 deployment_id claim (one per tenant per tool).",
    )
    tool_jwks_url = forms.URLField(
        label="Tool JWKS URL",
        help_text="HTTPS URL where the tool publishes its public keys.",
    )
    tool_oidc_login_url = forms.URLField(
        label="Tool OIDC login URL",
        help_text="Where the platform redirects to start the OIDC flow.",
    )
    tool_redirect_uris = forms.CharField(
        max_length=1024,
        label="Tool redirect URIs (comma-separated)",
        help_text="Allowed redirect_uri values for OIDC callbacks.",
    )
    permitted_scopes = forms.MultipleChoiceField(
        choices=_SCOPE_CHOICES,
        label="Permitted scopes",
        widget=forms.CheckboxSelectMultiple,
        help_text="LTI 1.3 scope URIs this tool is permitted to request.",
    )
    tool_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=2000,
        label="Description",
    )

    def clean_tool_jwks_url(self) -> str:
        value = (self.cleaned_data.get("tool_jwks_url") or "").strip()
        if not value.startswith("https://"):
            raise forms.ValidationError("JWKS URL must use https://")
        return value

    def clean_tool_oidc_login_url(self) -> str:
        value = (self.cleaned_data.get("tool_oidc_login_url") or "").strip()
        if not value.startswith("https://"):
            raise forms.ValidationError("OIDC login URL must use https://")
        return value

    def clean_tool_redirect_uris(self) -> list[str]:
        raw = self.cleaned_data.get("tool_redirect_uris") or ""
        out: list[str] = []
        for item in raw.split(","):
            uri = item.strip()
            if not uri:
                continue
            if not (uri.startswith("https://") or uri.startswith("http://localhost")):
                raise forms.ValidationError(
                    f"Redirect URI {uri!r} must use https:// (or http://localhost for dev)"
                )
            out.append(uri)
        if not out:
            raise forms.ValidationError("At least one redirect URI is required.")
        return out

    def clean_permitted_scopes(self) -> list[str]:
        scopes = self.cleaned_data.get("permitted_scopes") or []
        invalid = [s for s in scopes if s not in STANDARD_LTI_SCOPES]
        if invalid:
            raise forms.ValidationError(
                f"Unknown LTI scopes: {invalid}"
            )
        return list(scopes)


def _generate_tool_secret() -> tuple[str, str]:
    """Generate a fresh 32-byte secret and return ``(raw, sha256_hex[:64])``."""
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
    return raw, digest


def _resolve_default_school():
    """Pick the first active School row. Tool registration is platform-scoped
    but the underlying ``ServiceIntegration`` model requires a school FK."""
    from apps.schools.models import School

    # tenant-isolation-allow: lti-tool-registration-platform-scoped-control-plane
    return School.objects.filter(is_active=True).order_by("pk").first()


def _build_config_from_form(cleaned: dict[str, Any], *, secret_hash: str) -> dict[str, Any]:
    return {
        "tool_name": cleaned["tool_name"],
        "client_id": cleaned["tool_client_id"],
        "tool_client_id": cleaned["tool_client_id"],
        "platform_id": cleaned["platform_id"],
        "deployment_id": cleaned["deployment_id"],
        "tool_jwks_url": cleaned["tool_jwks_url"],
        "lti_tool_jwks_url": cleaned["tool_jwks_url"],
        "tool_oidc_login_url": cleaned["tool_oidc_login_url"],
        "tool_redirect_uris": cleaned["tool_redirect_uris"],
        "permitted_scopes": cleaned["permitted_scopes"],
        "lti_permitted_scopes": cleaned["permitted_scopes"],
        "tool_description": cleaned.get("tool_description") or "",
        "lti_tool_secret_hash": secret_hash,
        "registered_at": timezone.now().isoformat(),
    }


def save_tool_registration(form: LTIToolRegistrationForm, *, school=None):
    """Persist a registered LTI tool as a ``ServiceIntegration`` row.

    Returns ``(integration, raw_secret)``. ``raw_secret`` MUST be shown to
    the operator ONCE; only its sha256 hash is stored.
    """
    from apps.integrations_marketplace.models import ServiceIntegration

    cleaned = form.cleaned_data
    raw_secret, secret_hash = _generate_tool_secret()
    target_school = school or _resolve_default_school()
    if target_school is None:
        raise RuntimeError("no_active_school_for_lti_registration")
    cfg = _build_config_from_form(cleaned, secret_hash=secret_hash)
    integration = ServiceIntegration.objects.create(
        school=target_school,
        service_name=cleaned["tool_name"],
        service_type=ServiceIntegration.ServiceType.LTI,
        client_id=cleaned["tool_client_id"],
        endpoint_url=cleaned["tool_oidc_login_url"],
        enabled_scopes=list(cleaned["permitted_scopes"]),
        config=cfg,
        is_active=True,
    )
    logger.info(
        "LTI tool registered tool_name=%s integration_id=%s school_id=%s "
        "scope_count=%d",
        cleaned["tool_name"],
        integration.pk,
        integration.school_id,
        len(cleaned["permitted_scopes"]),
    )
    return integration, raw_secret


@method_decorator(staff_member_required, name="dispatch")
class LTIToolRegistrationListView(View):
    """``GET /super/lti/tools/`` — list registered LTI tools."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from apps.integrations_marketplace.models import ServiceIntegration

        # tenant-isolation-allow: lti-tool-registration-platform-scoped-control-plane
        qs = (
            ServiceIntegration.objects.filter(
                service_type=ServiceIntegration.ServiceType.LTI
            )
            .select_related("school")
            .order_by("-created_at")[:200]
        )
        rows = []
        for row in qs:
            cfg = row.config or {}
            rows.append(
                {
                    "id": row.pk,
                    "tool_name": cfg.get("tool_name") or row.service_name,
                    "client_id": row.client_id or cfg.get("client_id") or "",
                    "deployment_id": cfg.get("deployment_id") or "",
                    "scopes": cfg.get("permitted_scopes") or [],
                    "is_active": row.is_active,
                    "school": row.school.name if row.school_id else "",
                    "detail_url": reverse(
                        "lti_tool_registration_detail", args=[row.pk]
                    ),
                }
            )
        ctx = {
            "rows": rows,
            "register_url": reverse("lti_tool_registration_create"),
            "standard_scopes": list(STANDARD_LTI_SCOPES),
            "view_mode": "list",
        }
        return render(request, "lti_admin/tool_registration.html", ctx)


@method_decorator(staff_member_required, name="dispatch")
class LTIToolRegistrationCreateView(View):
    """``GET|POST /super/lti/tools/register/`` — register a new LTI tool."""

    def get(self, request: HttpRequest) -> HttpResponse:
        form = LTIToolRegistrationForm()
        return render(
            request,
            "lti_admin/tool_registration.html",
            {
                "form": form,
                "view_mode": "create",
                "list_url": reverse("lti_tool_registration_list"),
                "standard_scopes": list(STANDARD_LTI_SCOPES),
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = LTIToolRegistrationForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "lti_admin/tool_registration.html",
                {
                    "form": form,
                    "view_mode": "create",
                    "list_url": reverse("lti_tool_registration_list"),
                    "standard_scopes": list(STANDARD_LTI_SCOPES),
                },
                status=400,
            )
        integration, raw_secret = save_tool_registration(form)
        return render(
            request,
            "lti_admin/tool_registration.html",
            {
                "view_mode": "result",
                "integration_id": integration.pk,
                "tool_name": integration.service_name,
                "one_time_secret": raw_secret,
                "detail_url": reverse(
                    "lti_tool_registration_detail", args=[integration.pk]
                ),
                "list_url": reverse("lti_tool_registration_list"),
            },
        )


@method_decorator(staff_member_required, name="dispatch")
class LTIToolRegistrationDetailView(View):
    """``GET /super/lti/tools/<id>/`` — view a registered LTI tool."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        from apps.integrations_marketplace.models import ServiceIntegration

        # tenant-isolation-allow: lti-tool-registration-platform-scoped-control-plane
        integration = get_object_or_404(
            ServiceIntegration.objects.filter(
                service_type=ServiceIntegration.ServiceType.LTI
            ),
            pk=pk,
        )
        cfg = integration.config or {}
        ctx = {
            "view_mode": "detail",
            "integration": integration,
            "cfg": cfg,
            "list_url": reverse("lti_tool_registration_list"),
            "scopes": cfg.get("permitted_scopes") or [],
        }
        return render(request, "lti_admin/tool_registration.html", ctx)


__all__ = [
    "LTIToolRegistrationCreateView",
    "LTIToolRegistrationDetailView",
    "LTIToolRegistrationForm",
    "LTIToolRegistrationListView",
    "save_tool_registration",
]
