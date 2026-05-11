"""Pass 9.E: FERPA §99.32 disclosure detail view.

Operator-facing read surface for a single disclosure record. Closes the
"FERPA disclosure detail" gap noted in the audit-log roadmap — the admin
already lists disclosures, but auditors need a non-admin URL they can link
to from a compliance report.

Access is restricted to school officials (superuser, staff, or holders of
`compliance.view_ferpadisclosure`) within the disclosure's tenant. The
view is itself audit-logged via `@audit_pii_view` since it exposes the
student name + record categories.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.compliance.decorators import audit_pii_view
from apps.compliance.models import FerpaDisclosure


def _is_ferpa_officer(user) -> bool:
    if not (user and user.is_authenticated):
        return False
    return (
        user.is_superuser
        or user.is_staff
        or user.has_perm("compliance.view_ferpadisclosure")
    )


@login_required
@user_passes_test(_is_ferpa_officer)
@require_GET
@audit_pii_view(
    model_name="FerpaDisclosure",
    object_id_kwarg="pk",
    sensitivity="HIGH",
    reason="FERPA disclosure detail view",
)
def ferpa_disclosure_detail(request, pk: int):
    """Show a single FERPA disclosure row with all §99.32-required fields."""
    school = getattr(request, "school", None)
    qs = FerpaDisclosure.objects.select_related(
        "school", "student", "student__user", "disclosed_by"
    )
    if school is not None:
        qs = qs.filter(school=school)
    disclosure = get_object_or_404(qs, pk=pk)

    return render(
        request,
        "compliance/ferpa_disclosure_detail.html",
        {
            "disclosure": disclosure,
            "record_types": disclosure.record_types_disclosed or [],
        },
    )
