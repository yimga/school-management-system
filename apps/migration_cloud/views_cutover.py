"""Audit G-3 — CutoverRunbook operator view.

GET + POST ``/super/migration/cutover/`` (operator) and the mirrored path
under the portal mount — staff-only.

The single surface lets an operator:

  * **create** a cutover runbook for a district (draft);
  * **attach** the rehearsal and/or real cutover bundles and advance the
    status (draft → rehearsed → executed);
  * **sign off** a runbook — capturing the signer's verbatim name/title and
    anchoring the SHA-256 of the real bundle's reconciliation scorecard.

The competitive acceptance test — *"migration is done when N districts'
cutover runbook is executed and signed"* — is exactly what this surface makes
recordable.

Security / discipline:

  * Staff-only via ``@method_decorator(require_control_plane_access, name="dispatch")``
    (matches the sibling operator surfaces: health, DSAR runbook).
  * Bundle attachment is cross-district-guarded: a bundle may only be attached
    to a runbook of its OWN school (404-style refusal otherwise).
  * Sign-off is append-only — a second sign-off raises
    ``CutoverRunbookAlreadySignedError`` (surfaced as an error message), and the
    model's ``save()`` refuses to mutate the sign-off anchor fields.
  * The signer's raw name/title never enters the audit hash-chain (see
    ``CutoverRunbook._emit_signoff_audit``); this view only renders it back to
    the same staff operator who recorded it.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from apps.schools.control_plane import require_control_plane_access
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from .models import (
    CutoverRunbook,
    CutoverRunbookAlreadySignedError,
    CutoverRunbookNotReadyError,
    CutoverRunbookStatus,
    MigrationBundle,
)

logger = logging.getLogger(__name__)

_MAX_RUNBOOKS = 100
_MAX_SCHOOLS = 500


def _load_schools() -> list[dict]:
    """Return a lightweight (id, name) list of schools for the create select."""
    try:
        from apps.schools.models import School
    except Exception:  # noqa: BLE001 — degrade to empty picker
        return []
    try:
        rows = list(
            School.objects  # tenant-isolation-allow: operator-cross-tenant-cutover-console-school-picker
            .all()
            .order_by("name")
            .values("id", "name")[:_MAX_SCHOOLS]
        )
    except Exception:  # noqa: BLE001
        logger.warning("migration_cloud.cutover: school picker load failed", exc_info=True)
        return []
    return [{"id": r["id"], "name": r.get("name") or f"school {r['id']}"} for r in rows]


def _resolve_bundle_for_school(bundle_id_raw: str, school_id: int) -> MigrationBundle | None:
    """Resolve a bundle id string, refusing a bundle from a different school.

    Returns ``None`` for an empty input (nothing to attach). Raises
    ``ValueError`` for a non-numeric id, a missing bundle, or a cross-district
    bundle so the caller can surface a precise error.
    """
    raw = (bundle_id_raw or "").strip()
    if not raw:
        return None
    try:
        bundle_id = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{raw}' is not a valid bundle id.")
    bundle = (
        MigrationBundle.objects  # tenant-isolation-allow: operator-cross-tenant-cutover-console-bundle-lookup-then-school-guarded
        .filter(pk=bundle_id)
        .first()
    )
    if bundle is None:
        raise ValueError(f"Bundle {bundle_id} does not exist.")
    if bundle.school_id != school_id:
        raise ValueError(
            f"Bundle {bundle_id} belongs to a different district; refusing to attach."
        )
    return bundle


# rbac-allow: super-staff-migration-cloud-cutover-runbook
@method_decorator(require_control_plane_access, name="dispatch")
class CutoverRunbookView(View):
    """GET + POST — operator cutover-runbook console (create / advance / sign)."""

    template_name = "migration_cloud/operator/cutover_runbook.html"

    def get(self, request, *args, **kwargs):
        runbooks = list(
            CutoverRunbook.objects  # tenant-isolation-allow: operator-cross-tenant-cutover-console-full-list
            .all()
            .select_related("school", "rehearsal_bundle", "real_bundle", "signed_off_by")
            .order_by("-created_at")[:_MAX_RUNBOOKS]
        )
        signed = sum(1 for r in runbooks if r.is_signed)
        ctx = {
            "page_title": "Cutover runbooks",
            "runbooks": runbooks,
            "runbooks_count": len(runbooks),
            "signed_count": signed,
            "schools": _load_schools(),
            "max_runbooks": _MAX_RUNBOOKS,
            "shell": kwargs.get("shell", "super"),
        }
        resp = render(request, self.template_name, ctx)
        resp["Cache-Control"] = "no-store"
        return resp

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        handler = {
            "create": self._create,
            "set_bundles": self._set_bundles,
            "sign": self._sign,
        }.get(action)
        if handler is None:
            messages.error(request, f"Unknown action '{action}'.")
        else:
            handler(request)
        return self._redirect_self(request, kwargs.get("shell", "super"))

    # ── actions ────────────────────────────────────────────────────────

    def _create(self, request) -> None:
        raw_school = (request.POST.get("school_id") or "").strip()
        label = (request.POST.get("label") or "").strip()[:200]
        try:
            school_id = int(raw_school)
        except (TypeError, ValueError):
            messages.error(request, "Select a district to create a runbook.")
            return
        try:
            from apps.schools.models import School

            school = (
                School.objects  # tenant-isolation-allow: operator-cross-tenant-cutover-console-create-school-resolve
                .filter(pk=school_id)
                .first()
            )
        except Exception:  # noqa: BLE001
            school = None
        if school is None:
            messages.error(request, f"District {raw_school} not found.")
            return
        runbook = CutoverRunbook.objects.create(
            school=school,
            label=label,
            created_by=request.user if getattr(request.user, "pk", None) else None,
        )
        messages.success(
            request, f"Created cutover runbook #{runbook.pk} for {school}."
        )

    def _get_unsigned_runbook(self, request):
        raw = (request.POST.get("runbook_id") or "").strip()
        try:
            runbook_id = int(raw)
        except (TypeError, ValueError):
            messages.error(request, "Missing or invalid runbook id.")
            return None
        runbook = (
            CutoverRunbook.objects  # tenant-isolation-allow: operator-cross-tenant-cutover-console-runbook-by-pk
            .filter(pk=runbook_id)
            .select_related("real_bundle")
            .first()
        )
        if runbook is None:
            messages.error(request, f"Runbook {runbook_id} not found.")
            return None
        return runbook

    def _set_bundles(self, request) -> None:
        runbook = self._get_unsigned_runbook(request)
        if runbook is None:
            return
        if runbook.is_signed:
            messages.error(request, "Runbook is already signed; bundles are locked.")
            return
        try:
            rehearsal = _resolve_bundle_for_school(
                request.POST.get("rehearsal_bundle_id"), runbook.school_id
            )
            real = _resolve_bundle_for_school(
                request.POST.get("real_bundle_id"), runbook.school_id
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return

        fields = ["updated_at"]
        if rehearsal is not None:
            runbook.rehearsal_bundle = rehearsal
            fields.append("rehearsal_bundle")
        if real is not None:
            runbook.real_bundle = real
            fields.append("real_bundle")

        # Advance status honestly from what is attached (never downgrade).
        if runbook.real_bundle_id is not None:
            runbook.status = CutoverRunbookStatus.EXECUTED
        elif runbook.rehearsal_bundle_id is not None:
            runbook.status = CutoverRunbookStatus.REHEARSED
        fields.append("status")
        runbook.save(update_fields=fields)
        messages.success(request, f"Updated runbook #{runbook.pk} → {runbook.status}.")

    def _sign(self, request) -> None:
        runbook = self._get_unsigned_runbook(request)
        if runbook is None:
            return
        signer_name = (request.POST.get("signer_name") or "").strip()
        signer_title = (request.POST.get("signer_title") or "").strip()
        try:
            runbook.record_signoff(
                user=request.user,
                signer_name=signer_name,
                signer_title=signer_title,
            )
        except CutoverRunbookAlreadySignedError as exc:
            messages.error(request, str(exc))
            return
        except CutoverRunbookNotReadyError as exc:
            messages.error(request, str(exc))
            return
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "migration_cloud.cutover.sign_failed runbook_id=%s err_type=%s",
                runbook.pk, type(exc).__name__,
            )
            messages.error(request, f"Sign-off failed: {type(exc).__name__}.")
            return
        messages.success(
            request,
            f"Runbook #{runbook.pk} signed off — scorecard anchor "
            f"{runbook.reconciliation_scorecard_sha256[:12]}…",
        )

    # ── helpers ────────────────────────────────────────────────────────

    def _redirect_self(self, request, shell: str):
        url_name = (
            "migration_cloud_super:cutover_runbook"
            if shell == "super"
            else "migration_cloud_portal:cutover_runbook"
        )
        try:
            return redirect(reverse(url_name))
        except Exception:  # noqa: BLE001
            return redirect(request.path)


__all__ = ["CutoverRunbookView"]
