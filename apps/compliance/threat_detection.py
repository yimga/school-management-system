"""
Threat detection utilities for brute-force login attempts and after-hours access anomalies.
"""

from datetime import timedelta
from typing import List, Dict

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import ExtractHour
from django.utils import timezone

from apps.compliance.models_audit import AccessLog
from apps.compliance.alerts import send_threat_alert


def detect_threats(window_minutes: int | None = None) -> List[Dict]:
    cfg = getattr(settings, "THREAT_DETECTION", {})
    window = window_minutes or cfg.get("window_minutes", 60)
    since = timezone.now() - timedelta(minutes=window)

    failed_per_user_threshold = cfg.get("failed_per_user", 10)
    failed_per_ip_threshold = cfg.get("failed_per_ip", 20)
    after_hours_start = cfg.get("after_hours_start", 22)
    after_hours_end = cfg.get("after_hours_end", 6)
    after_hours_threshold = cfg.get("after_hours_threshold", 5)

    qs = AccessLog.objects.filter(timestamp__gte=since)

    # Normalize failures (numeric status >=400 or textual status representing failure)
    failed_filter = Q(status__gte=400) | Q(status__in=["FORBIDDEN", "NOT_FOUND", "ERROR"])

    findings: List[Dict] = []

    # Brute-force per user
    user_failures = (
        qs.filter(failed_filter)
        .values("user__username")
        .annotate(count=Count("id"))
        .filter(count__gte=failed_per_user_threshold)
    )
    for row in user_failures:
        findings.append({
            "type": "BRUTE_FORCE_USER",
            "user": row["user__username"] or "Unknown",
            "count": row["count"],
            "window": f"{window}m",
            "severity": "HIGH",
            "description": f"{row['count']} failed accesses for user in {window} minutes",
        })

    # Brute-force per IP
    ip_failures = (
        qs.filter(failed_filter)
        .values("ip_address")
        .annotate(count=Count("id"))
        .filter(count__gte=failed_per_ip_threshold)
    )
    for row in ip_failures:
        findings.append({
            "type": "BRUTE_FORCE_IP",
            "ip_address": row["ip_address"] or "Unknown",
            "count": row["count"],
            "window": f"{window}m",
            "severity": "HIGH",
            "description": f"{row['count']} failed accesses from IP in {window} minutes",
        })

    # After-hours access
    after_hours = (
        qs.annotate(hour=ExtractHour("timestamp"))
        .exclude(hour__in=range(after_hours_end, after_hours_start))
        .values("user__username")
        .annotate(count=Count("id"))
        .filter(count__gte=after_hours_threshold)
    )
    for row in after_hours:
        findings.append({
            "type": "AFTER_HOURS_ACCESS",
            "user": row["user__username"] or "Unknown",
            "count": row["count"],
            "window": f"{window}m",
            "severity": "MEDIUM",
            "description": f"{row['count']} accesses outside business hours",
        })

    return findings


def alert_findings(findings: List[Dict]) -> None:
    for finding in findings:
        send_threat_alert(finding)
