"""
Context processors for schools app.
Exposes MARKETING_BASE_URL so tenant and manager templates can link to the canonical marketing site.
"""

from django.conf import settings as django_settings

from .host_routing import get_canonical_base_domain


def marketing_base_url(request):
    """
    Add MARKETING_BASE_URL to template context: the canonical base URL for the marketing site
    (e.g. https://runmycampus.com). Use this for links from tenant or manager to pricing,
    status, trust center, signup, and other marketing pages so they open on the apex domain.
    """
    base_domain = get_canonical_base_domain()
    scheme = "https"
    if getattr(django_settings, "MARKETING_BASE_SCHEME", None):
        scheme = django_settings.MARKETING_BASE_SCHEME
    elif getattr(request, "scheme", None):
        scheme = request.scheme
    return {"MARKETING_BASE_URL": f"{scheme}://{base_domain}"}


def operator_surface_ia_context(request):
    """Cross-surface IA strip for manager /super/, /configuration/, /admin/."""
    try:
        from django.urls import NoReverseMatch

        from apps.schools.super_admin_paired_surfaces import (
            build_operator_surface_ia_context,
        )

        return build_operator_surface_ia_context(request)
    except (ImportError, NoReverseMatch, TypeError, ValueError):
        return {
            "RMC_OPERATOR_SURFACE_IA": False,
            "RMC_OPERATOR_SURFACE_STRIP_VISIBLE": False,
            "RMC_OPERATOR_SURFACE_SPINE": [],
            "RMC_OPERATOR_PAIRED_LINKS": [],
            "RMC_OPERATOR_SURFACE_CURRENT": None,
        }


def conversion_enforcement_context(request):
    """
    Template toggles for strict conversion / single-primary UI (see CONVERSION_* settings).
    """
    return {
        "rmc_conversion_single_action_enforced": getattr(
            django_settings, "CONVERSION_SINGLE_ACTION_ENFORCED", False
        ),
        "rmc_activation_gate_allow_dismiss": getattr(
            django_settings, "ACTIVATION_GATE_ALLOW_DISMISS", True
        ),
    }
