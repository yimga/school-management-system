"""
Beyond-reach BR items: migration CSV diff, governed NL query, legacy CSV preview.
"""

from __future__ import annotations

import csv
import logging
from io import StringIO

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _is_superuser(u):
    return bool(u and u.is_authenticated and u.is_superuser)


@user_passes_test(_is_superuser)
@require_http_methods(["GET", "POST"])
def super_migration_csv_diff(request):
    """Compare two CSV uploads (same headers); BR-04."""
    ctx = {
        "dashboard_url": reverse("super:dashboard"),
        "trust_center_url": reverse("super:trust_center"),
        "result": None,
        "error": None,
    }
    if request.method != "POST":
        return render(request, "schools/super_migration_csv_diff.html", ctx)
    f_a = request.FILES.get("csv_a")
    f_b = request.FILES.get("csv_b")
    key_col = (request.POST.get("key_column") or "").strip() or None
    if not f_a or not f_b:
        ctx["error"] = "Upload both CSV files."
        return render(request, "schools/super_migration_csv_diff.html", ctx)
    try:
        raw_a = f_a.read().decode("utf-8-sig", errors="replace")
        raw_b = f_b.read().decode("utf-8-sig", errors="replace")
        r_a = list(csv.DictReader(StringIO(raw_a)))
        r_b = list(csv.DictReader(StringIO(raw_b)))
        if not r_a and not r_b:
            ctx["error"] = "Both files empty."
            return render(request, "schools/super_migration_csv_diff.html", ctx)
        headers = list(r_a[0].keys()) if r_a else list(r_b[0].keys())
        k = key_col or headers[0]
        if k not in headers:
            ctx["error"] = f"Key column {k!r} not in headers {headers[:10]}..."
            return render(request, "schools/super_migration_csv_diff.html", ctx)
        map_a = {str(row.get(k, "")): row for row in r_a}
        map_b = {str(row.get(k, "")): row for row in r_b}
        keys_a = set(map_a.keys()) - {""}
        keys_b = set(map_b.keys()) - {""}
        only_a = sorted(keys_a - keys_b)[:500]
        only_b = sorted(keys_b - keys_a)[:500]
        value_diffs = []
        for key in sorted(keys_a & keys_b)[:200]:
            ra, rb = map_a[key], map_b[key]
            for h in headers:
                if (ra.get(h) or "") != (rb.get(h) or ""):
                    value_diffs.append(
                        {"key": key, "field": h, "a": ra.get(h), "b": rb.get(h)}
                    )
                    break
        ctx["result"] = {
            "key": k,
            "count_a": len(r_a),
            "count_b": len(r_b),
            "only_a_count": len(keys_a - keys_b),
            "only_b_count": len(keys_b - keys_a),
            "only_a_sample": only_a[:50],
            "only_b_sample": only_b[:50],
            "value_diff_count": len(
                [x for x in keys_a & keys_b if map_a[x] != map_b[x]]
            ),
            "value_diffs_sample": value_diffs[:50],
        }
    except Exception as e:
        logger.exception("super_migration_csv_diff")
        ctx["error"] = str(e)
    return render(request, "schools/super_migration_csv_diff.html", ctx)


@require_http_methods(["GET", "POST"])
def super_legacy_sis_csv_preview(request):
    """Read-only table preview; BR-09."""
    ctx = {
        "dashboard_url": reverse("super:dashboard"),
        "rows": [],
        "headers": [],
        "error": None,
    }
    if request.method != "POST":
        return render(request, "schools/super_legacy_sis_csv_preview.html", ctx)
    f = request.FILES.get("csv")
    if not f:
        ctx["error"] = "Upload a CSV."
        return render(request, "schools/super_legacy_sis_csv_preview.html", ctx)
    try:
        raw = f.read().decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(StringIO(raw)))
        headers = list(rows[0].keys()) if rows else []
        ctx["headers"] = headers
        ctx["row_values"] = [
            [str(row.get(h, "") or "") for h in headers] for row in rows[:500]
        ]
    except Exception as e:
        ctx["error"] = str(e)
    return render(request, "schools/super_legacy_sis_csv_preview.html", ctx)


# Whitelisted intents only — no raw SQL (BR-07)
_GOVERNED_INTENTS = {
    "active_schools_count": lambda: {
        "intent": "active_schools_count",
        "value": __import__("apps.schools.models", fromlist=["School"])
        .School.objects.filter(is_active=True)
        .count(),
    },
    "platform_events_24h": lambda: _platform_events_24h(),
    "inactive_schools_count": lambda: {
        "intent": "inactive_schools_count",
        "value": __import__("apps.schools.models", fromlist=["School"])
        .School.objects.filter(is_active=False)
        .count(),
    },
}


def _platform_events_24h():
    from datetime import timedelta

    from django.utils import timezone

    from apps.platform_runtime.models import PlatformEventLog

    since = timezone.now() - timedelta(hours=24)
    return {
        "intent": "platform_events_24h",
        "value": PlatformEventLog.objects.filter(created_at__gte=since).count(),
    }


@require_http_methods(["GET", "POST"])
def super_governed_data_query(request):
    """POST intent=active_schools_count|platform_events_24h|inactive_schools_count; BR-07."""
    ctx = {
        "dashboard_url": reverse("super:dashboard"),
        "intents": list(_GOVERNED_INTENTS.keys()),
        "result": None,
        "error": None,
    }
    if request.method == "POST":
        intent = (request.POST.get("intent") or "").strip()
        if intent not in _GOVERNED_INTENTS:
            ctx["error"] = "Unknown or disallowed intent."
        else:
            try:
                out = _GOVERNED_INTENTS[intent]()
                from apps.platform_runtime.events import emit_platform_event

                emit_platform_event(
                    "nl_governed_query_executed",
                    {"intent": intent, "user_id": request.user.id},
                    tenant_id="platform",
                    school_id=None,
                )
                ctx["result"] = out
            except Exception as e:
                logger.exception("super_governed_data_query")
                ctx["error"] = str(e)
    return render(request, "schools/super_governed_data_query.html", ctx)
