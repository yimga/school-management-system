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
