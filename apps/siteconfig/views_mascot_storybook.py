"""Mascot storybook — staff-only dev surface showing every advisor pose and
variant on a single page so designers can review the system in one glance.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render


@staff_member_required(login_url=settings.LOGIN_URL)
def mascot_storybook(request):
    """Render every advisor pose + variant in a single grid."""
    poses = [
        ("intro", "Calm intro — tablet at the waist."),
        ("listening", "Receptive — slight head turn, tablet at side."),
        ("explaining", "Pointing at a small floating diagram."),
        ("welcoming", "Open-handed wave — for arrival surfaces."),
        ("reviewing", "Head bent over a chart with magnifier."),
        ("thinking", "Hand on chin with thought dots."),
        ("celebrating", "Both hands gently raised with quiet confetti."),
        ("pointing-up", "Index finger raised with a tip dot."),
    ]
    variants = [
        ("", "Default ink"),
        ("mkt-advisor-figure--muted", "Muted (slate ink)"),
        ("mkt-advisor-figure--on-dark", "On dark surface"),
        ("mkt-advisor-figure--brand", "Brand color (tenant primary)"),
        ("mkt-advisor-figure--alive", "Alive (perpetual breathe)"),
        ("mkt-advisor-figure--reveal", "Reveal (one-shot fade-up)"),
    ]
    sizes = [64, 96, 128, 180, 240, 320]
    return render(
        request,
        "siteconfig/mascot_storybook.html",
        {
            "poses": poses,
            "variants": variants,
            "sizes": sizes,
        },
    )
