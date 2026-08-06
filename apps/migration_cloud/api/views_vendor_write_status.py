"""Wave 9 Agent N (v3.58.x) — vendor write-path authorization status dashboard.

Control-plane operator surface at ``/super/migration/vendor-write-status/``
that reports the current authorization state for each of the 6 vendor
slugs the platform recognizes. Gated with ``require_control_plane_access``
(not ``staff_member_required``) because the shared migration_cloud urlconf is
also mounted on the tenant ``migration_cloud_portal`` namespace, and the platform
mints ``is_staff=True`` tenant admins — so a staff gate here would let a tenant
admin reach this cross-tenant operator surface from their own subdomain. Pairs with
:mod:`apps.migration_cloud.services.vendor_write_gate`.

The view NEVER reads or renders:

  * the approval token bytes (only the boolean "set / not set");
  * the counsel signoff PDF SHA (only the boolean + well-formed bool);
  * any actual vendor write payload.

URL pattern carries
``# rbac-allow: super-staff-vendor-write-authorization-status``.
"""
from __future__ import annotations

import logging
from typing import Any

from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

from apps.schools.control_plane import require_control_plane_access

from apps.migration_cloud.services.vendor_write_gate import (
    COUNSEL_DOCKETED_VENDORS,
    VENDOR_SLUGS,
    get_vendor_write_status_snapshot,
)

logger = logging.getLogger(__name__)


_DOCKET_DOC_PATH = "docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md"
_RUNBOOK_DOC_PATH = "docs/FACTS_SKYWARD_WRITE_PATH_FLIP_RUNBOOK.md"
_GATE_MODULE_PATH = "apps/migration_cloud/services/vendor_write_gate.py"


@method_decorator(require_control_plane_access, name="dispatch")
class VendorWriteStatusView(View):
    """GET-only status surface.

    Six rows (one per vendor slug). Two cross-links at the top: the
    counsel docket and the operator runbook.
    """

    template_name = "migration_cloud/super/vendor_write_status.html"

    def get(self, request, *args, **kwargs) -> Any:
        try:
            snapshot = get_vendor_write_status_snapshot()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "vendor_write_status.snapshot_failed reason=%s",
                type(exc).__name__,
            )
            snapshot = [
                {
                    "vendor_slug": slug,
                    "counsel_docketed": slug in COUNSEL_DOCKETED_VENDORS,
                    "approval_token_configured": False,
                    "counsel_signoff_sha_configured": False,
                    "counsel_signoff_sha_well_formed": False,
                    "authorized": False,
                    "refusal_reason": "snapshot_error",
                }
                for slug in VENDOR_SLUGS
            ]

        any_authorized = any(r["authorized"] for r in snapshot)
        docketed_authorized = any(
            r["authorized"] and r["counsel_docketed"] for r in snapshot
        )

        context = {
            "page_title": "Vendor write-path authorization status",
            "snapshot": snapshot,
            "any_authorized": any_authorized,
            "docketed_authorized": docketed_authorized,
            "docket_doc_path": _DOCKET_DOC_PATH,
            "runbook_doc_path": _RUNBOOK_DOC_PATH,
            "gate_module_path": _GATE_MODULE_PATH,
            "vendor_count": len(snapshot),
            "counsel_docketed_count": len(COUNSEL_DOCKETED_VENDORS),
        }
        return render(request, self.template_name, context)


__all__ = ["VendorWriteStatusView"]
