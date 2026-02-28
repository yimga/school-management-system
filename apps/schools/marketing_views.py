"""
RunMyCampus marketing landing: tagline, CTA to signup and discover.
Lightweight; no pricing/screenshots in this stub (add when branding is fixed).
"""
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def marketing_landing(request):
    """Marketing landing page: RunMyCampus brand, CTA to sign up or find school."""
    return render(request, "schools/marketing_landing.html", {})
