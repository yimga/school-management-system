"""v4.00.43 — Public unauthenticated status page at /status/.

Lists the operator-promoted ``PublicIncident`` rows so users (anyone with the
URL) can see in-flight outages without logging in. Renders the active/recent
incidents grouped by status. The page is intentionally cacheable for 30s so a
spike in tenant traffic doesn't compound during an outage.

v4.00.45 adds:
  - ``/status/feed.xml`` Atom feed for monitoring systems + feed readers.
  - ``PublicIncidentSubscription`` opt-in (email + verification + unsubscribe).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.syndication.views import Feed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.feedgenerator import Atom1Feed
from django.utils.html import escape
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET, require_http_methods


@require_GET
@cache_control(public=True, max_age=30)
# rbac-allow: public-status-page-anonymous-by-design
def public_status_page(request):
    """Public outage / incident listing — anonymous-readable."""
    from apps.siteconfig.models_feature_controls import PublicIncident

    now = timezone.now()
    recent_window = now - timedelta(days=14)
    active = list(
        PublicIncident.objects.exclude(status=PublicIncident.Status.RESOLVED)
        .order_by("-started_at")[:25]
    )
    recently_resolved = list(
        PublicIncident.objects.filter(
            status=PublicIncident.Status.RESOLVED,
            resolved_at__gte=recent_window,
        ).order_by("-resolved_at")[:25]
    )
    return render(
        request,
        "siteconfig/public_status.html",
        {
            "active": active,
            "recently_resolved": recently_resolved,
            "now": now,
            "active_count": len(active),
            "all_systems_normal": not active,
        },
    )


# v4.00.45 — Atom feed for monitoring systems and feed readers.
# rbac-allow: public-status-feed-anonymous-by-design
class PublicStatusFeed(Feed):
    """Atom 1.0 feed of the 50 most-recent public incidents."""

    feed_type = Atom1Feed
    title = "RunMyCampus platform status"
    link = "/status/"
    description = "Operator-acknowledged platform incidents."
    subtitle = "Operator-acknowledged platform incidents."

    def items(self):
        from apps.siteconfig.models_feature_controls import PublicIncident

        return PublicIncident.objects.order_by("-started_at")[:50]

    def item_title(self, item):
        return f"[{item.severity}] {item.title}"

    def item_description(self, item):
        parts = []
        if item.summary:
            parts.append(escape(item.summary))
        parts.append(
            f"<p><strong>Severity:</strong> {item.get_severity_display()} · "
            f"<strong>Status:</strong> {item.get_status_display()}</p>"
        )
        if item.resolved_at:
            parts.append(f"<p>Resolved at {item.resolved_at.isoformat()}.</p>")
        return "".join(parts)

    def item_link(self, item):
        return f"/status/#incident-{item.pk}"

    def item_pubdate(self, item):
        return item.started_at

    def item_updateddate(self, item):
        return item.updated_at

    def item_guid(self, item):
        return f"public-incident:{item.pk}"

    def item_guid_is_permalink(self, item):
        return False


_ALLOWED_CHANNELS = {"EMAIL", "SMS", "SLACK", "DISCORD"}


@require_http_methods(["POST"])
# rbac-allow: public-status-subscribe-anonymous-by-design
def public_status_subscribe(request):
    """Anonymous multi-channel opt-in (EMAIL / SMS / SLACK / DISCORD).

    EMAIL flow is double opt-in (verification link before any send). SMS /
    Slack / Discord webhook flows auto-confirm at subscribe time because
    possession of the destination IS the proof of intent (you can't accept
    a Slack webhook URL you don't control).
    """
    from apps.siteconfig.models_feature_controls import PublicIncidentSubscription
    from apps.siteconfig.notifications_public_status import validate_address

    channel = (request.POST.get("channel") or "EMAIL").upper().strip()
    if channel not in _ALLOWED_CHANNELS:
        messages.error(request, "Pick a supported channel.")
        return redirect("public_status")

    # Accept both the legacy "email" field and the new generic "address" field.
    if channel == "EMAIL":
        address = (
            request.POST.get("email")
            or request.POST.get("address")
            or ""
        ).strip().lower()[:240]
    else:
        address = (request.POST.get("address") or "").strip()[:500]

    err = validate_address(channel, address)
    if err is not None:
        messages.error(request, f"That {channel.lower()} destination looks wrong ({err}).")
        return redirect("public_status")

    # Look up or create by (channel, address) — partial unique constraint.
    lookup = {"channel": channel, "address": address}
    sub = PublicIncidentSubscription.objects.filter(**lookup).first()
    created = False
    if sub is None:
        sub = PublicIncidentSubscription.objects.create(
            channel=channel,
            address=address,
            email=address if channel == "EMAIL" else "",
            verification_token=secrets.token_urlsafe(32),
            unsubscribe_token=secrets.token_urlsafe(32),
            # Non-email channels auto-confirm at subscribe time.
            confirmed_at=None if channel == "EMAIL" else timezone.now(),
        )
        created = True
    elif sub.unsubscribed_at is not None:
        sub.unsubscribed_at = None
        sub.confirmed_at = None if channel == "EMAIL" else timezone.now()
        sub.verification_token = secrets.token_urlsafe(32)
        sub.unsubscribe_token = secrets.token_urlsafe(32)
        sub.save(
            update_fields=[
                "unsubscribed_at",
                "confirmed_at",
                "verification_token",
                "unsubscribe_token",
                "updated_at",
            ]
        )

    if channel == "EMAIL":
        try:
            from django.conf import settings
            from django.core.mail import send_mail

            verify_url = request.build_absolute_uri(
                reverse("public_status_verify", args=[sub.verification_token])
            )
            unsub_url = request.build_absolute_uri(
                reverse("public_status_unsubscribe", args=[sub.unsubscribe_token])
            )
            from_email = (
                getattr(settings, "DEFAULT_FROM_EMAIL", None)
                or "no-reply@runmycampus.com"
            )
            send_mail(
                "Confirm your RunMyCampus status updates",
                (
                    "Thanks for subscribing to RunMyCampus platform status updates.\n\n"
                    f"Confirm to start receiving alerts:\n{verify_url}\n\n"
                    f"Or unsubscribe at any time:\n{unsub_url}\n"
                ),
                from_email,
                [address],
                fail_silently=True,
            )
        except Exception:  # noqa: BLE001 — never block the response
            pass
        messages.success(
            request,
            "Check your inbox for a confirmation link. You'll start receiving updates once you confirm.",
        )
    else:
        if created:
            messages.success(
                request,
                f"{channel.title()} subscription added. You'll receive updates as incidents change.",
            )
        else:
            messages.success(
                request,
                f"{channel.title()} subscription is already live.",
            )
    return redirect("public_status")


@require_GET
# rbac-allow: public-status-verify-anonymous-by-design
def public_status_verify(request, token: str):
    from apps.siteconfig.models_feature_controls import PublicIncidentSubscription

    sub = PublicIncidentSubscription.objects.filter(verification_token=token).first()
    if sub is None:
        messages.error(request, "Verification link is invalid or expired.")
        return redirect("public_status")
    if sub.confirmed_at is None:
        sub.confirmed_at = timezone.now()
        sub.save(update_fields=["confirmed_at", "updated_at"])
    messages.success(request, "Subscription confirmed. Watch this space for updates.")
    return redirect("public_status")


@require_GET
# rbac-allow: public-status-unsubscribe-anonymous-by-design
def public_status_unsubscribe(request, token: str):
    from apps.siteconfig.models_feature_controls import PublicIncidentSubscription

    sub = PublicIncidentSubscription.objects.filter(unsubscribe_token=token).first()
    if sub is None:
        messages.error(request, "Unsubscribe link is invalid.")
        return redirect("public_status")
    if sub.unsubscribed_at is None:
        sub.unsubscribed_at = timezone.now()
        sub.save(update_fields=["unsubscribed_at", "updated_at"])
    messages.success(request, "Unsubscribed. You will no longer receive status updates.")
    return redirect("public_status")


# --- v4.00.49 — Monthly history aggregations ------------------------------


_HISTORY_MONTHS = 12


def _month_floor(dt):
    """Truncate a datetime to the first second of its month (UTC-naive ok)."""
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_month(dt, *, delta_months: int):
    """Add ``delta_months`` to ``dt``'s month, wrapping the year as needed."""
    total = dt.year * 12 + (dt.month - 1) + delta_months
    new_year, new_month = divmod(total, 12)
    return dt.replace(year=new_year, month=new_month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def _aggregate_monthly_history(months: int = _HISTORY_MONTHS):
    """Return up to ``months`` of month-bucketed incident stats, newest first.

    Each bucket carries: counts by severity, MTTR (mean time to resolve) in
    minutes (None when no resolved incident in that month), total open count.
    Resolved incidents are bucketed by ``resolved_at``; open ones by
    ``started_at`` so an incident that opened in April but resolved in May
    counts toward May's MTTR and April's open count.
    """
    from apps.siteconfig.models_feature_controls import PublicIncident

    now = timezone.now()
    current = _month_floor(now)
    earliest = _shift_month(current, delta_months=-(months - 1))

    qs_resolved = PublicIncident.objects.filter(
        status=PublicIncident.Status.RESOLVED,
        resolved_at__gte=earliest,
    )
    qs_started = PublicIncident.objects.filter(started_at__gte=earliest)

    buckets: dict[tuple[int, int], dict] = {}
    for offset in range(months):
        bucket_start = _shift_month(current, delta_months=-offset)
        key = (bucket_start.year, bucket_start.month)
        buckets[key] = {
            "year": bucket_start.year,
            "month": bucket_start.month,
            "label": bucket_start.strftime("%b %Y"),
            "started": 0,
            "resolved": 0,
            "by_severity": {"MINOR": 0, "MAJOR": 0, "CRITICAL": 0},
            "mttr_minutes": None,
            "_resolution_total_seconds": 0,
            "_resolution_count": 0,
        }

    for inc in qs_started.only("severity", "started_at"):
        key = (inc.started_at.year, inc.started_at.month)
        bucket = buckets.get(key)
        if bucket is None:
            continue
        bucket["started"] += 1
        sev = inc.severity if inc.severity in bucket["by_severity"] else "MINOR"
        bucket["by_severity"][sev] += 1

    for inc in qs_resolved.only("started_at", "resolved_at"):
        if not inc.resolved_at or not inc.started_at:
            continue
        key = (inc.resolved_at.year, inc.resolved_at.month)
        bucket = buckets.get(key)
        if bucket is None:
            continue
        bucket["resolved"] += 1
        delta_seconds = max(0, int((inc.resolved_at - inc.started_at).total_seconds()))
        bucket["_resolution_total_seconds"] += delta_seconds
        bucket["_resolution_count"] += 1

    out = []
    for key in sorted(buckets.keys(), reverse=True):
        bucket = buckets[key]
        if bucket["_resolution_count"] > 0:
            bucket["mttr_minutes"] = round(
                bucket["_resolution_total_seconds"] / bucket["_resolution_count"] / 60.0,
                1,
            )
        bucket.pop("_resolution_total_seconds", None)
        bucket.pop("_resolution_count", None)
        out.append(bucket)
    return out


@require_GET
@cache_control(public=True, max_age=300)
# rbac-allow: public-status-history-anonymous-by-design
def public_status_history(request):
    """Render the last 12 months of incident counts + MTTR for transparency.

    Cached 5 minutes (monthly aggregations don't move fast). Renders even when
    there are zero incidents — an empty history table is itself a useful
    signal.
    """
    months_param = (request.GET.get("months") or "").strip()
    try:
        months = max(3, min(int(months_param or _HISTORY_MONTHS), 24))
    except ValueError:
        months = _HISTORY_MONTHS

    history = _aggregate_monthly_history(months=months)
    totals = {
        "started": sum(b["started"] for b in history),
        "resolved": sum(b["resolved"] for b in history),
        "by_severity": {
            "MINOR": sum(b["by_severity"]["MINOR"] for b in history),
            "MAJOR": sum(b["by_severity"]["MAJOR"] for b in history),
            "CRITICAL": sum(b["by_severity"]["CRITICAL"] for b in history),
        },
    }
    return render(
        request,
        "siteconfig/public_status_history.html",
        {
            "history": history,
            "totals": totals,
            "months": months,
        },
    )
