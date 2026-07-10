"""Admin console — season & fixture administration for academic leadership.

Read gates on ``athletics.view``/``athletics.manage``; the season-create POST is a write
and additionally requires ``athletics.manage`` (via the effective-access facade) so a
view-only leader cannot create seasons. Every queryset is ``request.school``-scoped.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from apps.accounts.decorators import require_permission
from apps.athletics.constants import ADMIN_FIXTURE_LIST_LIMIT
from apps.athletics.forms import SeasonForm
from apps.athletics.models import Fixture, Season
from apps.schools.mixins import require_school


@login_required
@require_school
@require_permission("athletics.view", "athletics.manage")
def admin_seasons(request):
    """List seasons and create new ones (create requires athletics.manage)."""
    school = request.school

    if request.method == "POST":
        from apps.accounts import effective_access

        if not effective_access.permission_access(
            request.user, school, ("athletics.manage",)
        ):
            raise PermissionDenied
        form = SeasonForm(request.POST, school=school)
        # Bind the school onto the instance BEFORE validation so SeasonForm.clean()
        # can enforce the (school, sport, academic_year, name) uniqueness — school
        # isn't a form field, so ModelForm.validate_unique can't. A duplicate then
        # surfaces as a form error, not a DB IntegrityError 500.
        form.instance.school = school
        if form.is_valid():
            season = form.save()
            messages.success(request, f"Season '{season.name}' created.")
            return redirect("athletics:admin_seasons")
        messages.error(request, "Please correct the errors below.")
    else:
        form = SeasonForm(school=school)

    seasons = (
        Season.objects.filter(school=school)
        .select_related("sport", "academic_year")
        .order_by("-start_date")
    )
    return render(
        request,
        "athletics/admin/seasons.html",
        {"school": school, "seasons": seasons, "form": form},
    )


@login_required
@require_school
@require_permission("athletics.view", "athletics.manage")
def admin_fixtures(request):
    """School-wide fixture calendar for academic leadership."""
    school = request.school
    fixtures = (
        Fixture.objects.filter(school=school)
        .select_related("team", "season", "venue", "result")
        .order_by("-scheduled_start")[:ADMIN_FIXTURE_LIST_LIMIT]
    )
    return render(
        request,
        "athletics/admin/fixtures.html",
        {"school": school, "fixtures": fixtures},
    )
