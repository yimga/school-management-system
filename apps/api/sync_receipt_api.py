"""Was this bundle already accepted? — turning an ambiguous timeout into an answer.

THE AMBIGUITY. A box pushes a bundle; the cloud accepts, applies it, records the
receipt — and the RESPONSE dies on the way back (a gateway 502, a read timeout on a
village link). The box cannot distinguish "you never got it" from "you got it and I
lost the answer", so it leaves its cursor unmoved and re-ships the whole page on the
next cycle.

That re-ship is CORRECT and always was: ``export_delta_bundle`` regenerates the nonce
per BUILD, so a rebuilt bundle is a new bundle to the replay guard and the apply is
idempotent. Nothing is lost or duplicated. What it costs is bandwidth — the entire
page again, over the link that just proved it is unreliable.

This endpoint removes that cost. The cloud already knows the answer: ``SyncBundleReceipt``
is uniquely keyed on ``(school, nonce)`` and indexed. There was simply no way to ask.

THE LIMIT, STATED HONESTLY. Receipts are pruned to
``RMC_SYNC_BUNDLE_REPLAY_WINDOW_SECONDS`` (7 days by default), so "not seen" means
"not seen WITHIN the replay window" and nothing more. A box that was offline longer
than the window gets ``unknown`` rather than a confident ``false`` — because a
confident false there would tell it to re-ship data that had in fact landed, and being
wrong in that direction is how you resurrect rows somebody deleted. Empty bundles are
never receipted (``replay_guard`` skips ``row_count <= 0``), and are never pushed
either, so they cannot reach this question.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from apps.api.edge_auth import EdgeCredentialAuthentication
from apps.schools.tenant_api_guards import user_may_operate_on_school


class SyncBundleReceiptView(APIView):
    """GET ``?nonce=<hex>`` — did this school's cloud already accept that bundle?"""

    authentication_classes = [
        EdgeCredentialAuthentication,
        *api_settings.DEFAULT_AUTHENTICATION_CLASSES,
    ]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="sync_bundle_receipt_lookup",
        description=(
            "Ask whether a bundle nonce has already been accepted for this school. "
            "Lets a box resolve an ambiguous push timeout without re-shipping the "
            "page. Answers are authoritative only within the replay window."
        ),
        responses={200: None, 400: None, 403: None},
    )
    def get(self, request):
        from django.utils import timezone

        from apps.sync_engine.models import SyncBundleReceipt
        from apps.sync_engine.replay_guard import replay_window_seconds

        school = getattr(request, "school", None)
        if school is None:
            return Response({"ok": False, "error": "school_required"}, status=403)
        if not user_may_operate_on_school(request, school):
            return Response({"ok": False, "error": "forbidden"}, status=403)

        nonce = (request.GET.get("nonce") or "").strip()[:64]
        if not nonce:
            return Response({"ok": False, "error": "nonce_required"}, status=400)

        receipt = (
            SyncBundleReceipt.objects.filter(school=school, nonce=nonce)
            .only("received_at", "row_count", "direction")
            .first()
        )
        if receipt is not None:
            return Response(
                {
                    "ok": True,
                    "seen": True,
                    "received_at": receipt.received_at.isoformat(),
                    "row_count": receipt.row_count,
                    "direction": receipt.direction,
                },
                status=200,
            )

        # Absent from the table is only meaningful INSIDE the window. Outside it, the
        # row may simply have been pruned, and answering a confident "no" would tell the
        # box to re-ship rows that already landed — which can resurrect a row the far
        # side has since deleted. Say "unknown" and let the box do the safe thing.
        window = replay_window_seconds()
        asked_about = request.GET.get("built_at", "").strip()
        age_known = False
        too_old = False
        if asked_about.isdigit():
            age_known = True
            too_old = (timezone.now().timestamp() - int(asked_about)) > window
        return Response(
            {
                "ok": True,
                "seen": False,
                "confident": bool(age_known and not too_old),
                "replay_window_seconds": window,
            },
            status=200,
        )


__all__ = ["SyncBundleReceiptView"]
