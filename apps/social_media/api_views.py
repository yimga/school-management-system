"""DRF endpoints for social feed read, publish, moderation, and analytics."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.api_contract import parse_int_param
from apps.api.permissions import IsAdminUser
from apps.social_media.models import SocialModerationItem
from apps.social_media.scope import (
    SocialTenantScopeError,
    resolve_feed_scope,
    scope_denied_response,
)
from apps.social_media.services import aggregator, analytics, emergency, publisher
from apps.social_media.services.analytics import record_utm_attribution


class SocialFeedAPI(APIView):
    """Context-aware feed: platform scope on marketing/manager; tenant on school host."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Read cached social feed for active scope")
    def get(self, request):
        school, platform_scope = resolve_feed_scope(request)
        if not platform_scope and school is None:
            return Response(
                {"error": "tenant_required", "detail": "School context required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        items = aggregator.read_cached_feed(
            school_id=getattr(school, "id", None),
            platform_scope=platform_scope,
        )
        # ``connected_accounts`` distinguishes "quiet campus" from "no account has
        # ever been connected" -- an empty ``items`` list alone cannot, and the
        # second is the state every tenant is really in until an OAuth connect
        # surface exists. Additive: existing consumers read ``items``.
        connected = aggregator.connected_account_count(
            school_id=getattr(school, "id", None),
            platform_scope=platform_scope,
        )
        return Response(
            {
                "scope": "platform" if platform_scope else "tenant",
                "school_id": str(school.id) if school else None,
                "items": items,
                "connected_accounts": connected,
            }
        )


class SocialPublishAPI(APIView):
    """Cross-post to all connected providers for the active tenant."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    NO_ACCOUNTS_DETAIL = (
        "No active social accounts are connected for this scope, so nothing was "
        "sent. Connect an account before publishing."
    )

    @extend_schema(summary="Enqueue multi-channel social publish")
    def post(self, request):
        # Every other view in this file resolves scope and refuses an unresolved
        # tenant; this one did not, and handed the raw request to a publisher that
        # read a missing school as "platform scope" -- i.e. the company's own
        # accounts. Resolve first, and refuse on the same terms as SocialFeedAPI.
        school, platform_scope = resolve_feed_scope(request)
        if not platform_scope and school is None:
            return Response(
                {"error": "tenant_required", "detail": "School context required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"error": "body_required"}, status=status.HTTP_400_BAD_REQUEST)
        providers = request.data.get("providers")
        media_urls = request.data.get("media_urls") or []
        emergency_flag = bool(request.data.get("emergency"))
        try:
            if emergency_flag:
                result = emergency.route_emergency_broadcast(
                    request, body=body, media_urls=media_urls
                )
                if result.posted == 0 and result.failed == 0:
                    # A campus-closure broadcast that reached ZERO channels is the
                    # worst possible thing to report as 202 Accepted. Nothing in
                    # the codebase creates a SocialMediaIntegration yet, so this is
                    # the state every real tenant is actually in -- say so loudly
                    # instead of returning a confident {"posted": 0}.
                    return Response(
                        {
                            "error": "no_connected_accounts",
                            "mode": "emergency",
                            "detail": self.NO_ACCOUNTS_DETAIL,
                            "posted": 0,
                            "failed": 0,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                return Response(
                    {
                        "mode": "emergency",
                        "posted": result.posted,
                        "failed": result.failed,
                        "elapsed_ms": result.elapsed_ms,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            rows = publisher.enqueue_cross_post(
                request,
                body=body,
                providers=providers,
                media_urls=media_urls,
                source=request.data.get("source") or "api",
            )
            if not rows:
                # 202 + {"queued": 0} let an admin click Publish, see success, and
                # have nothing ever post. An empty integration set is a refusal,
                # not an acceptance.
                return Response(
                    {
                        "error": "no_connected_accounts",
                        "detail": self.NO_ACCOUNTS_DETAIL,
                        "queued": 0,
                        "outbox_ids": [],
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {"queued": len(rows), "outbox_ids": [str(r.id) for r in rows]},
                status=status.HTTP_202_ACCEPTED,
            )
        except SocialTenantScopeError as exc:
            return scope_denied_response(exc)


class SocialModerationAPI(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(summary="List pending proud-campus moderation items")
    # One class serves BOTH `social/moderation/` and `social/moderation/<item_id>/`.
    # `get` had no `item_id` (500 on the detail route) and `post` required one
    # (500 on the list route) -- the same mismatch in both directions at once.
    def get(self, request, item_id=None):
        school, platform_scope = resolve_feed_scope(request)
        if platform_scope or school is None:
            return Response(
                {"error": "tenant_required"},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = SocialModerationItem.objects.filter(
            school=school, status=SocialModerationItem.Status.PENDING
        ).order_by("-created_at")[:50]
        return Response(
            {
                "items": [
                    {
                        "id": str(item.id),
                        "caption": item.caption,
                        "image_url": item.image_url,
                        "hashtag": item.hashtag,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in qs
                ]
            }
        )

    @extend_schema(summary="Approve or reject a moderation item")
    def post(self, request, item_id=None):
        if item_id is None:
            return Response(
                {"error": "item_id_required"}, status=status.HTTP_400_BAD_REQUEST
            )
        school, platform_scope = resolve_feed_scope(request)
        if platform_scope or school is None:
            return Response({"error": "tenant_required"}, status=status.HTTP_403_FORBIDDEN)
        action = (request.data.get("action") or "").lower()
        try:
            item = SocialModerationItem.objects.get(pk=item_id, school=school)
        except SocialModerationItem.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        if action == "approve":
            item.status = SocialModerationItem.Status.APPROVED
            item.reviewed_by = request.user
            from django.utils import timezone

            item.reviewed_at = timezone.now()
            item.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        elif action == "reject":
            item.status = SocialModerationItem.Status.REJECTED
            item.reviewed_by = request.user
            from django.utils import timezone

            item.reviewed_at = timezone.now()
            item.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        else:
            return Response({"error": "invalid_action"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": str(item.id), "status": item.status})


class SocialAnalyticsPulseAPI(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(summary="Social engagement pulse timeseries for charts")
    def get(self, request):
        school, platform_scope = resolve_feed_scope(request)
        if platform_scope or school is None:
            return Response({"error": "tenant_required"}, status=status.HTTP_403_FORBIDDEN)
        points = analytics.pulse_timeseries_for_school(school.id)
        return Response({"tenant_id": str(school.id), "points": points})


class SocialAttributionAPI(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(summary="Record UTM attribution for donation/enrollment funnel")
    def post(self, request):
        school, platform_scope = resolve_feed_scope(request)
        if platform_scope or school is None:
            return Response({"error": "tenant_required"}, status=status.HTTP_403_FORBIDDEN)
        target_id = request.data.get("school_id")
        if target_id and str(school.id) != str(target_id):
            return Response(
                {"error": "cross_tenant", "detail": "Cannot record attribution for another school."},
                status=status.HTTP_403_FORBIDDEN,
            )
        row = record_utm_attribution(
            school_id=school.id,
            provider=request.data.get("provider") or "facebook",
            utm_source=request.data.get("utm_source") or "",
            utm_medium=request.data.get("utm_medium") or "",
            utm_campaign=request.data.get("utm_campaign") or "",
            amount_cents=parse_int_param(request.data.get("amount_cents"), 0, minimum=0),
            transaction_id=request.data.get("transaction_id") or "",
            post_id=request.data.get("post_id") or "",
        )
        return Response({"id": str(row.id)}, status=status.HTTP_201_CREATED)
