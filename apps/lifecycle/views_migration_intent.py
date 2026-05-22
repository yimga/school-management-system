"""Migration-intent setter — sidesteps the locked wizard.

URL: /super/schools/<uuid:school_id>/migration-intent/

Operator sets school.settings['migration_intent'] post-creation so
the L5 auto-launch hook can draft a MigrationBundle. The wizard
itself is locked from modification, so this is the canonical
operator surface for backfilling intent on schools created via
either the wizard, bulk CSV, or clone API.

POST body (form-encoded or JSON):
    vendor          : powerschool|blackbaud|veracross|alma|facts|
                      skyward|oneroster|runmycampus|csv
    intake_method   : file_upload|archive|url|sftp|... (default file_upload)
    expected_students: optional int
    label           : optional label string

Triggers ensure_draft_migration_bundle() inline so the bundle lands
in the same request — no signal indirection from this surface.
"""

from __future__ import annotations

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View

from apps.schools.models import School

from .services_migration import ensure_draft_migration_bundle

logger = logging.getLogger(__name__)


_VALID_VENDORS = {
    "powerschool",
    "blackbaud",
    "veracross",
    "alma",
    "facts",
    "skyward",
    "oneroster",
    "runmycampus",
    "csv",
    "other",
}

_VALID_INTAKE_METHODS = {
    "file_upload",
    "archive",
    "url",
    "sftp",
    "s3",
    "sql_dump",
    "database",
    "oauth_folder",
    "email",
    "api_pull",
    "pdf",
    "access_db",
}


@method_decorator(staff_member_required, name="dispatch")
class SchoolMigrationIntentView(View):
    """POST-only — updates school.settings['migration_intent'] + drafts bundle."""

    def post(self, request, school_id):
        school = get_object_or_404(School, id=school_id)
        body = self._decode_body(request)
        vendor = (body.get("vendor") or "").strip().lower()
        if vendor and vendor not in _VALID_VENDORS:
            return JsonResponse(
                {"ok": False, "error": f"vendor must be one of {sorted(_VALID_VENDORS)}"},
                status=400,
            )
        intake_method = (body.get("intake_method") or "file_upload").strip().lower()
        if intake_method not in _VALID_INTAKE_METHODS:
            intake_method = "file_upload"
        try:
            expected_students = int(body.get("expected_students") or 0)
        except (TypeError, ValueError):
            expected_students = 0
        label = (body.get("label") or "")[:200]
        intent = {
            "vendor": vendor or "csv",
            "intake_method": intake_method,
            "expected_students": expected_students,
            "label": label,
        }
        existing = (getattr(school, "settings", None) or {})
        if not isinstance(existing, dict):
            existing = {}
        existing["migration_intent"] = intent
        school.settings = existing
        school.save(update_fields=["settings"])
        bundle = ensure_draft_migration_bundle(school)
        return JsonResponse(
            {
                "ok": True,
                "school_id": str(school.id),
                "migration_intent": intent,
                "bundle_id": str(bundle.id) if bundle else None,
            }
        )

    @staticmethod
    def _decode_body(request) -> dict:
        content_type = (request.content_type or "").lower()
        if "application/json" in content_type:
            try:
                return json.loads(request.body or b"{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
        return {key: request.POST.get(key, "") for key in (
            "vendor",
            "intake_method",
            "expected_students",
            "label",
        )}
