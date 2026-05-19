"""DRF endpoints for social feed read, publish, moderation, and analytics."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import IsAdminUser
from apps.social_media.models import SocialModerationItem
from apps.social_media.scope import (
    SocialTenantScopeError,
    queryset_for_scope,
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
        return Response(
            {
                "scope": "platform" if platform_scope else "tenant",
                "school_id": str(school.id) if school else None,
                "items": items,
            }
        )


class SocialPublishAPI(APIView):
    """Cross-post to all connected providers for the active tenant."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(summary="Enqueue multi-channel social publish")
    def post(self, request):
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
            return Response(
                {"queued": len(rows), "outbox_ids": [str(r.id) for r in rows]},
                status=status.HTTP_202_ACCEPTED,
            )
        except SocialTenantScopeError as exc:
            return scope_denied_response(exc)


class SocialModerationAPI(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(summary="List pending proud-campus moderation items")
    def get(self, request):
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
    def post(self, request, item_id):
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
            amount_cents=int(request.data.get("amount_cents") or 0),
            transaction_id=request.data.get("transaction_id") or "",
            post_id=request.data.get("post_id") or "",
        )
        return Response({"id": str(row.id)}, status=status.HTTP_201_CREATED)
