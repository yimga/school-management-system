"""
Lost-belongings QR micro-friction views (batch 1509).

Wires `apps.schoolops.lost_belongings_qr` to a real Django route surface:

- `lost_belongings_mint`  — staff mints a new tag (auth required)
- `lost_belongings_lookup` — anonymous finder enters a short_code and records a
                              sighting (intentionally ANONYMOUS; rate-limited
                              at the middleware layer in production)
- `lost_belongings_recover` — staff records a final recovery against a tag

Statelessness: tags are minted in-memory and surfaced once. In production a
persistence model is required so anonymous finders can resolve the short_code
back to a tag; this batch focuses on wiring + audit hygiene + form validation.

PII discipline: the public lookup page reflects ONLY the short_code, the
label_hint and the hashed tenant. Asset / staff / tenant IDs in the raw form
never appear in the rendered HTML or in the audit log.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.schoolops.lost_belongings_qr import AssetTag

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.schools.mixins import require_school

from .forms_lost_belongings import (
    FinderSightingForm,
    MintTagForm,
    StaffRecoveryForm,
)
from .lost_belongings_qr import (
    LostBelongingsError,
    mint_tag,
    record_finder_sighting,
    record_staff_recovery,
)
from .micro_friction_persistence import (
    lookup_tag_global_short_code,
    persist_custody_event,
    persist_lost_belongings_tag,
    tag_record_to_asset_tag,
)


logger = logging.getLogger(__name__)


def _staff_roles_ok(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    role = (getattr(user, "role", "") or "").upper()
    return role in {"ADMIN", "PRINCIPAL", "LEADERSHIP", "HOD", "TEACHER", "IT_ADMIN"}


@login_required
@user_passes_test(_staff_roles_ok)
@require_school
@require_http_methods(["GET", "POST"])
def lost_belongings_mint(request):
    school = request.school
    tenant_id = str(school.pk) if school is not None else ""
    error = None
    tag: AssetTag | None = None
    form = MintTagForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        try:
            tag = mint_tag(
                tenant_id=tenant_id,
                asset_id=cleaned["asset_id"],
                label_hint=cleaned["label_hint"],
            )
        except LostBelongingsError as exc:
            error = str(exc)
        else:
            persist_lost_belongings_tag(
                school_id=school.pk,
                user_id=request.user.pk,
                tag=tag,
                asset_id=cleaned["asset_id"],
            )
            form = MintTagForm()
    return render(
        request,
        "schoolops/lost_belongings_mint.html",
        {"form": form, "tag": tag, "error": error},
    )


@require_http_methods(["GET", "POST"])
def lost_belongings_lookup(request):
    """Anonymous finder endpoint.

    Deliberately unauthenticated. In production a per-IP rate limit and a
    persistence backend resolve the short_code; this stub validates the form
    and emits a sighting event in-memory.
    """
    error = None
    event = None
    form = FinderSightingForm(request.POST or None, initial={"notify_parent": True})
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        tag_record = lookup_tag_global_short_code(cleaned["short_code"])
        if tag_record is None:
            error = "Tag not found or already recovered."
        else:
            tag = tag_record_to_asset_tag(tag_record)
            try:
                event = record_finder_sighting(
                    tag=tag,
                    notes=cleaned.get("notes") or "",
                    notify_parent=bool(cleaned.get("notify_parent")),
                )
                persist_custody_event(
                    school_id=tag_record.school_id,
                    tag_record=tag_record,
                    event=event,
                )
            except LostBelongingsError as exc:
                error = str(exc)
                event = None
            if event is not None:
                form = FinderSightingForm(initial={"notify_parent": True})
    return render(
        request,
        "schoolops/lost_belongings_lookup.html",
        {"form": form, "event": event, "error": error},
    )


@login_required
@user_passes_test(_staff_roles_ok)
@require_school
@require_http_methods(["GET", "POST"])
def lost_belongings_recover(request):
    school = request.school
    tenant_id = str(school.pk) if school is not None else ""
    error = None
    event = None
    form = StaffRecoveryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        from .micro_friction_persistence import lookup_tag_by_short_code

        tag_record = lookup_tag_by_short_code(
            school_id=school.pk,
            short_code=cleaned["short_code"],
        )
        if tag_record is None:
            error = "Tag not found or already recovered."
        else:
            tag = tag_record_to_asset_tag(tag_record)
            try:
                event = record_staff_recovery(
                    tag=tag,
                    staff_id=cleaned["staff_id"],
                    notes=cleaned.get("notes") or "",
                )
                persist_custody_event(
                    school_id=school.pk,
                    tag_record=tag_record,
                    event=event,
                    staff_id=cleaned["staff_id"],
                )
            except LostBelongingsError as exc:
                error = str(exc)
                event = None
        if not error:
            # Swap to a fresh form so raw staff_id / short_code from the POST
            # do not echo back into the rendered HTML.
            form = StaffRecoveryForm()
    return render(
        request,
        "schoolops/lost_belongings_recover.html",
        {"form": form, "event": event, "error": error},
    )


def _hash_tenant_for_log(tenant_id: str) -> str:
    import hashlib

    if not tenant_id:
        return "unknown"
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:12]
