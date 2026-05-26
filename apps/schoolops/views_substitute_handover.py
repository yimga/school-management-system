"""
Substitute-handover micro-friction views (batch 1509).

Wires `apps.schoolops.substitute_handover` (service module shipped in batch
1506) to a real Django route + form + template + audit emission so the
workflow is no longer a contract-only facade.

Security posture:
- @login_required + role gate via `_substitute_handover_roles_ok`
- @require_school resolves the tenant via the existing tenant-host pipeline
  (NEVER from form input — we ignore any tenant_id the client tries to send)
- audit event emitted via the project logger with hashed tenant + actor IDs
- packet rendered with HASHED identifiers only; raw teacher / substitute IDs
  never appear in the rendered template
- medical/IEP exposure defaults False; admin role required to flip it
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.schools.mixins import require_school

from .forms_substitute_handover import SubstituteHandoverForm
from .micro_friction_persistence import persist_handover_packet
from .models_micro_friction import SubstituteHandoverPacketRecord
from .substitute_handover import (
    SubstituteHandoverError,
    TeacherAbsenceTrigger,
    build_packet,
)


logger = logging.getLogger(__name__)


def _substitute_handover_roles_ok(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    role = (getattr(user, "role", "") or "").upper()
    return role in {"ADMIN", "PRINCIPAL", "LEADERSHIP", "HOD", "DEAN"}


def _admin_can_expose_medical(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    return (getattr(user, "role", "") or "").upper() in {"ADMIN", "PRINCIPAL", "LEADERSHIP"}


@login_required
@user_passes_test(_substitute_handover_roles_ok)
@require_school
@require_http_methods(["GET", "POST"])
def substitute_handover_create(request):
    """Render form (GET) or build a packet from validated form (POST).

    Tenant resolution comes from `request.school`. The form's free-text
    fields are validated; tenant_id is NEVER taken from the form.
    """
    school = request.school
    tenant_id = str(school.pk) if school is not None else ""
    if not tenant_id:
        return render(
            request,
            "schoolops/substitute_handover_form.html",
            {"form": SubstituteHandoverForm(), "error": "tenant context required"},
            status=400,
        )

    packet = None
    error = None
    form = SubstituteHandoverForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        # Authorisation gate for medical/IEP exposure - the form may carry
        # the flag but only admin-level roles can actually flip it on.
        expose_medical = bool(
            cleaned.get("expose_medical_iep")
            and _admin_can_expose_medical(request.user)
        )
        try:
            trigger = TeacherAbsenceTrigger(
                tenant_id=tenant_id,
                teacher_id=cleaned["teacher_id"],
                absence_start=cleaned["absence_start"],
                absence_end=cleaned["absence_end"],
                reason_code=cleaned.get("reason_code") or "unspecified",
            )
            packet = build_packet(
                trigger=trigger,
                substitute_id=cleaned["substitute_id"],
                lesson_outline=cleaned.get("lesson_outline_json") or [],
                seating_chart_ref=cleaned.get("seating_chart_ref") or "",
                expose_medical_iep=expose_medical,
                grace_minutes=int(cleaned.get("grace_minutes") or 30),
            )
        except SubstituteHandoverError as exc:
            error = str(exc)
            packet = None
        else:
            persist_handover_packet(
                school_id=school.pk,
                user_id=request.user.pk,
                packet=packet,
                reason_code=cleaned.get("reason_code") or "unspecified",
                source=SubstituteHandoverPacketRecord.Source.ONLINE,
            )
            logger.info(
                "substitute_handover.ui.create packet=%s tenant_hash=%s actor_hash=%s gated=%s",
                packet.packet_id,
                packet.tenant_id_hash,
                packet.teacher_id_hash,
                packet.medical_iep_gated,
                extra={"scope": "substitute_handover.ui.create"},
            )
            # Swap to a fresh form so raw teacher_id / substitute_id values
            # from the submitted POST do not echo back into the response HTML.
            form = SubstituteHandoverForm()

    return render(
        request,
        "schoolops/substitute_handover_form.html",
        {
            "form": form,
            "packet": packet,
            "error": error,
        },
    )
