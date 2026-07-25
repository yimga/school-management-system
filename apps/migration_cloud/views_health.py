"""Migration Cloud operator status / health dashboard (v3.38.0 Agent 4).

Single staff-only HTML surface aggregating real-time operational data
for incident response. Six panels:

  1. Last-24h webhook deliveries (count by status).
  2. Last-7d MAA signs (count by version).
  3. Last-24h Companion uploads (count + bytes-total per tenant; tenant
     id is hashed via :func:`apps.migration_cloud.metrics._hash_tenant_id`
     so the dashboard NEVER reveals plaintext tenant slugs).
  4. Active Companion keypairs per tenant (count only).
  5. Pending legacy hash sunsets (count of accounts whose sunset email
     was sent but not yet null-passworded).
  6. Recent zero-tolerance scanner status — reads 8 baseline JSON files
     at ``var/security-audit-baseline-*.json`` defensively (missing file
     → "unknown", malformed JSON → "unknown"; the dashboard renders
     even when half the gates haven't been baselined yet).

Permission model: ``staff_member_required`` via
``@method_decorator(... , name="dispatch")``. URL pattern carries
``# rbac-allow: super-staff-migration-cloud-health-status``.

Logging discipline:

  * tenant slugs are NEVER passed to the template (only the 12-hex
    sha256 prefix);
  * signature_text / payload bytes / MAA bodies / private key material
    are never read;
  * cross-tenant aggregation queries each carry an explicit
    ``# tenant-isolation-allow: platform-wide-...-aggregation`` marker.

Auto-refresh via ``<meta http-equiv="refresh" content="60">`` in the
template — fits the incident-response use case where the operator
keeps the page open during a wave.
"""
from __future__ import annotations

import json
import logging
import math
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from .metrics import _hash_tenant_id

logger = logging.getLogger(__name__)

# ─── Migration-fleet SLO panel (audit G-6) ──────────────────────────────
#
# The migration path had only a bundle-apply SUCCESS-RATE objective
# (`migration.bundle_apply`). G-6 adds the latency + reconcile-parity +
# outbox-drain panel that answers "is the migration fleet meeting its SLA".
# Thresholds are read from the SLO registry (apps/observability/slo.py) so
# the dashboard and the objective SOT can never drift; the panel measures
# the numbers straight from persisted bundle / heavy-work-outbox data, so no
# Sentry emit site is required for it to be honest.
_APPLY_LATENCY_WINDOW_DAYS = 30
_PARITY_WINDOW_DAYS = 30
_SECONDS_PER_MINUTE = 60
_MS_PER_SECOND = 1000.0
# Fallbacks used only when the SLO registry can't be imported. They mirror the
# registry values (30-min apply ceiling; 99% parity floor) so a degraded import
# never silently loosens the objective.
_DEFAULT_APPLY_THRESHOLD_MS = 1_800_000  # magic-number-allow: mirrors migration.apply_latency SLO threshold
_DEFAULT_PARITY_TARGET_PCT = 99.0
# Matches apps/platform_runtime/heavy_work_outbox.py::_STALE_PENDING_ALERT_SECONDS;
# imported from there at call time so the two definitions stay in lock-step, with
# this as the fallback if that module can't be imported in a given environment.
_DEFAULT_OUTBOX_STALE_SECONDS = 600  # magic-number-allow: mirrors heavy-work stale-pending alert seconds


def _human_duration(seconds: float | None) -> str:
    """Render a duration in seconds as a compact human string (—, <1s, s, min, h)."""
    if seconds is None:
        return "—"
    s = float(seconds)
    if s < 1:
        return "<1s"
    if s < _SECONDS_PER_MINUTE:
        return f"{round(s)}s"
    if s < _SECONDS_PER_MINUTE * _SECONDS_PER_MINUTE:
        return f"{round(s / _SECONDS_PER_MINUTE, 1)} min"
    return f"{round(s / (_SECONDS_PER_MINUTE * _SECONDS_PER_MINUTE), 1)} h"


def _human_ms(ms: float | None) -> str:
    return _human_duration(None if ms is None else float(ms) / _MS_PER_SECOND)


def _percentile(sorted_vals: list[float], pct: float) -> float | None:
    """Nearest-rank percentile of an ascending-sorted list (pct in 0..100)."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = math.ceil((pct / 100.0) * len(sorted_vals))
    idx = min(max(rank - 1, 0), len(sorted_vals) - 1)
    return sorted_vals[idx]


def _fleet_slo_thresholds() -> tuple[int, float]:
    """(apply_threshold_ms, parity_target_pct) sourced from the SLO registry."""
    threshold_ms = _DEFAULT_APPLY_THRESHOLD_MS
    parity_target = _DEFAULT_PARITY_TARGET_PCT
    try:
        from apps.observability.slo import get_slo

        apply_slo = get_slo("migration.apply_latency")
        if apply_slo is not None and apply_slo.threshold_ms:
            threshold_ms = int(apply_slo.threshold_ms)
        parity_slo = get_slo("migration.reconcile_parity")
        if parity_slo is not None:
            parity_target = float(parity_slo.target)
    except Exception as exc:  # noqa: BLE001 — registry import must never break the dashboard
        logger.warning(
            "migration_cloud.health: slo_registry_load_failed err=%s",
            type(exc).__name__,
        )
    return threshold_ms, parity_target


# The 8 zero-tolerance scanners surfaced on the health dashboard. Order
# is stable so the panel layout doesn't shuffle between refreshes. Each
# entry maps a human-readable label to the baseline JSON filename in
# ``BASE_DIR / "var"``. Missing files render as "unknown" so the
# dashboard degrades gracefully when a baseline hasn't been written yet.
SCANNER_BASELINE_FILES: tuple[tuple[str, str], ...] = (
    ("drf-schema-coverage", "security-audit-baseline-drf-schema-coverage.json"),
    ("money-float", "security-audit-baseline-money-float.json"),
    ("migration-model-imports", "security-audit-baseline-migration-model-imports.json"),
    ("tenant-isolation-marker-quality", "security-audit-baseline-tenant-isolation-marker-quality.json"),
    ("pii-logging-smell", "security-audit-baseline-pii-logging-smell.json"),
    ("print-statements", "security-audit-baseline-print-statements.json"),
    ("bare-except", "security-audit-baseline-bare-except.json"),
    ("subprocess-shell", "security-audit-baseline-subprocess-shell.json"),
)


def _var_dir() -> Path:
    """Resolve the ``var/`` directory under ``BASE_DIR``.

    Defensive: returns a ``Path`` even when ``BASE_DIR`` isn't a Path
    instance in some test harness — the JSON loader downstream tolerates
    a non-existent directory.
    """
    base = getattr(settings, "BASE_DIR", None)
    if base is None:
        return Path("var")
    return Path(base) / "var"


def _read_baseline_finding_count(filename: str) -> Any:
    """Return ``finding_count`` for a baseline JSON, or ``"unknown"``.

    Defensive — every error path collapses to ``"unknown"`` so the
    health view never raises when a baseline file is missing or
    malformed.
    """
    path = _var_dir() / filename
    try:
        if not path.exists():
            return "unknown"
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError):
        return "unknown"
    if not isinstance(data, dict):
        return "unknown"
    fc = data.get("finding_count")
    if isinstance(fc, int):
        return fc
    # Some scanners write {"findings": [...]} without finding_count.
    findings = data.get("findings")
    if isinstance(findings, list):
        return len(findings)
    total = data.get("total")
    if isinstance(total, int):
        return total
    return "unknown"


# ─── Panels ─────────────────────────────────────────────────────────────


def _webhook_deliveries_24h() -> dict[str, Any]:
    """Last-24h delivery counts grouped by status.

    Cross-tenant by design: operator incident response needs the
    platform-wide picture.
    """
    try:
        from apps.migration_cloud.models import MigrationCloudWebhookDelivery
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.health: webhook_deliveries_load_failed err=%s",
            type(exc).__name__,
        )
        return {"total": 0, "by_status": [], "load_error": True}

    since = timezone.now() - timedelta(hours=24)
    # tenant-isolation-allow: platform-wide-webhook-health-aggregation
    qs = MigrationCloudWebhookDelivery.objects.filter(created_at__gte=since)
    counts: Counter[str] = Counter()
    # tenant-isolation-allow: platform-wide-webhook-health-aggregation
    for status in qs.values_list("status", flat=True):
        counts[status or "unknown"] += 1
    by_status = [
        {"status": k, "count": v}
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "total": sum(counts.values()),
        "by_status": by_status,
        "load_error": False,
    }


def _maa_signs_7d() -> dict[str, Any]:
    """Last-7d MAA sign counts grouped by agreement_version."""
    try:
        from apps.migration_cloud.models import MigrationAuthorizationAgreement
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.health: maa_signs_load_failed err=%s",
            type(exc).__name__,
        )
        return {"total": 0, "by_version": [], "load_error": True}

    since = timezone.now() - timedelta(days=7)
    # tenant-isolation-allow: platform-wide-maa-sign-health-aggregation
    qs = MigrationAuthorizationAgreement.objects.filter(signed_at__gte=since)
    counts: Counter[str] = Counter()
    # tenant-isolation-allow: platform-wide-maa-sign-health-aggregation
    for v in qs.values_list("agreement_version", flat=True):
        counts[v or "unknown"] += 1
    by_version = [
        {"version": k, "count": v}
        for k, v in sorted(counts.items())
    ]
    return {
        "total": sum(counts.values()),
        "by_version": by_version,
        "load_error": False,
    }


def _companion_uploads_24h() -> dict[str, Any]:
    """Last-24h Companion uploads — count + bytes total per HASHED tenant.

    The tenant id is hashed via :func:`_hash_tenant_id` BEFORE being
    placed in the response so the template (and operator's eyeballs)
    never see plaintext tenant slugs.
    """
    try:
        from apps.migration_cloud.models import CompanionUploadReceipt
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.health: companion_uploads_load_failed err=%s",
            type(exc).__name__,
        )
        return {"total": 0, "bytes_total": 0, "by_tenant": [], "load_error": True}

    since = timezone.now() - timedelta(hours=24)
    # tenant-isolation-allow: platform-wide-companion-upload-health-aggregation
    qs = CompanionUploadReceipt.objects.filter(received_at__gte=since)
    per_tenant: dict[str, dict[str, int]] = {}
    total = 0
    bytes_total = 0
    # tenant-isolation-allow: platform-wide-companion-upload-health-aggregation
    for tenant_id, size in qs.values_list("tenant_id", "plaintext_byte_size"):
        hashed = _hash_tenant_id(tenant_id)
        bucket = per_tenant.setdefault(
            hashed, {"tenant_id_hash": hashed, "count": 0, "bytes_total": 0},
        )
        bucket["count"] = int(bucket["count"]) + 1
        bucket["bytes_total"] = int(bucket["bytes_total"]) + int(size or 0)
        total += 1
        bytes_total += int(size or 0)
    by_tenant = sorted(
        per_tenant.values(), key=lambda r: (-int(r["count"]), r["tenant_id_hash"]),
    )
    return {
        "total": total,
        "bytes_total": bytes_total,
        "by_tenant": by_tenant,
        "load_error": False,
    }


def _active_companion_keypairs() -> dict[str, Any]:
    """Active Companion keypair count grouped by HASHED tenant id."""
    try:
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.health: keypairs_load_failed err=%s",
            type(exc).__name__,
        )
        return {"total": 0, "by_tenant": [], "load_error": True}

    # tenant-isolation-allow: platform-wide-companion-keypair-health-aggregation
    qs = MigrationCloudCompanionKeypair.objects.filter(is_active=True)
    per_tenant: dict[str, int] = {}
    # tenant-isolation-allow: platform-wide-companion-keypair-health-aggregation
    for tenant_id in qs.values_list("tenant_id", flat=True):
        hashed = _hash_tenant_id(tenant_id)
        per_tenant[hashed] = per_tenant.get(hashed, 0) + 1
    by_tenant = [
        {"tenant_id_hash": k, "count": v}
        for k, v in sorted(per_tenant.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "total": sum(per_tenant.values()),
        "by_tenant": by_tenant,
        "load_error": False,
    }


def _pending_legacy_hash_sunsets() -> dict[str, Any]:
    """Count of accounts in the email-eligible legacy-hash sunset state.

    "Email-eligible" here means the sunset job sent the one-time-setup
    email but the operator has not yet logged in and we have not yet
    null-passworded the row.
    """
    try:
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.health: legacy_sunset_user_model_load_failed err=%s",
            type(exc).__name__,
        )
        return {"count": 0, "load_error": True}

    try:
        # tenant-isolation-allow: platform-wide-legacy-hash-sunset-aggregation
        qs = UserModel.objects.filter(
            legacy_hash_sunset_email_sent_at__isnull=False,
        ).exclude(legacy_password_hash="")
        # tenant-isolation-allow: platform-wide-legacy-hash-sunset-aggregation
        count = qs.count()
    except Exception as exc:  # noqa: BLE001 - schema may not yet have the field in some test envs
        logger.warning(
            "migration_cloud.health: legacy_sunset_count_failed err=%s",
            type(exc).__name__,
        )
        return {"count": 0, "load_error": True}
    return {"count": count, "load_error": False}


def _scanner_baselines() -> dict[str, Any]:
    """Read all 8 zero-tolerance scanner baseline JSONs defensively."""
    rows = []
    for label, filename in SCANNER_BASELINE_FILES:
        rows.append({
            "label": label,
            "finding_count": _read_baseline_finding_count(filename),
            "filename": filename,
        })
    return {"rows": rows}


def _apply_latency_panel(threshold_ms: int) -> dict[str, Any]:
    """Apply p50/p95 wall-clock from SUCCEEDED mc_apply_bundle outbox rows (30d).

    The heavy-work outbox stamps ``claimed_at`` (worker picked the row up →
    APPLYING) and ``finished_at`` (apply landed → APPLIED), so the delta is a
    real, persisted apply-compute window — no Sentry trace required. Applies
    that ran synchronously (no outbox row) are out of scope; the panel is the
    async-fleet SLA and is labelled as such.
    """
    try:
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.health: apply_latency_load_failed err=%s",
            type(exc).__name__,
        )
        return {"load_error": True, "sample_count": 0}

    since = timezone.now() - timedelta(days=_APPLY_LATENCY_WINDOW_DAYS)
    durations_ms: list[float] = []
    try:
        # tenant-isolation-allow: platform-wide-migration-apply-latency-aggregation
        qs = HeavyWorkOutbox.objects.filter(
            kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE,
            status=HeavyWorkOutbox.Status.SUCCEEDED,
            claimed_at__isnull=False,
            finished_at__isnull=False,
            finished_at__gte=since,
        )
        # tenant-isolation-allow: platform-wide-migration-apply-latency-aggregation
        for claimed, finished in qs.values_list("claimed_at", "finished_at"):
            if claimed and finished and finished >= claimed:
                durations_ms.append((finished - claimed).total_seconds() * _MS_PER_SECOND)
    except Exception as exc:  # noqa: BLE001 — table/field may be absent in some envs
        logger.warning(
            "migration_cloud.health: apply_latency_query_failed err=%s",
            type(exc).__name__,
        )
        return {"load_error": True, "sample_count": 0}
    durations_ms.sort()
    n = len(durations_ms)
    p50 = _percentile(durations_ms, 50)
    p95 = _percentile(durations_ms, 95)
    within = sum(1 for d in durations_ms if d <= threshold_ms)
    return {
        "load_error": False,
        "sample_count": n,
        "p50_human": _human_ms(p50),
        "p95_human": _human_ms(p95),
        "threshold_human": _human_ms(threshold_ms),
        "attainment_pct": round(100.0 * within / n, 2) if n else None,
        "meets": bool(n) and p95 is not None and p95 <= threshold_ms,
    }


def _reconcile_parity_panel(target_pct: float) -> dict[str, Any]:
    """Reconciliation parity distribution over reconciled/applied bundles (30d).

    Reads ``reconciliation_summary['overall_parity_pct']`` in Python (not via a
    JSON DB lookup) so it works identically on SQLite and Postgres. A bundle
    that never recorded a parity number is simply not in the sample.
    """
    try:
        from apps.migration_cloud.models import BundleStatus, MigrationBundle
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.health: reconcile_parity_load_failed err=%s",
            type(exc).__name__,
        )
        return {"load_error": True, "sample_count": 0}

    since = timezone.now() - timedelta(days=_PARITY_WINDOW_DAYS)
    parities: list[float] = []
    try:
        # tenant-isolation-allow: platform-wide-migration-reconcile-parity-aggregation
        qs = MigrationBundle.objects.filter(
            status__in=[BundleStatus.RECONCILED, BundleStatus.APPLIED],
            updated_at__gte=since,
        )
        # tenant-isolation-allow: platform-wide-migration-reconcile-parity-aggregation
        for summary in qs.values_list("reconciliation_summary", flat=True):
            if isinstance(summary, dict):
                val = summary.get("overall_parity_pct")
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    parities.append(float(val))
    except Exception as exc:  # noqa: BLE001 — table/field may be absent in some envs
        logger.warning(
            "migration_cloud.health: reconcile_parity_query_failed err=%s",
            type(exc).__name__,
        )
        return {"load_error": True, "sample_count": 0}
    n = len(parities)
    met = sum(1 for p in parities if p >= target_pct)
    return {
        "load_error": False,
        "sample_count": n,
        "target_pct": target_pct,
        "met_count": met,
        "below_count": n - met,
        "attainment_pct": round(100.0 * met / n, 2) if n else None,
        "mean_parity_pct": round(sum(parities) / n, 2) if n else None,
        "min_parity_pct": round(min(parities), 2) if n else None,
        "meets": bool(n) and (100.0 * met / n) >= target_pct,
    }


def _outbox_freshness_panel() -> dict[str, Any]:
    """Heavy-work outbox drain freshness for the two Migration Cloud kinds.

    A PENDING mc_apply / mc_advance row older than the stale threshold means
    the fleet is backing up — applies are queueing rather than running. The
    threshold is imported from the outbox module so it stays in lock-step with
    the platform's own stale-pending alert.
    """
    try:
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.health: outbox_freshness_load_failed err=%s",
            type(exc).__name__,
        )
        return {"load_error": True}

    try:
        from apps.platform_runtime.heavy_work_outbox import _STALE_PENDING_ALERT_SECONDS as stale_seconds
    except Exception:  # noqa: BLE001
        stale_seconds = _DEFAULT_OUTBOX_STALE_SECONDS

    now = timezone.now()
    mc_kinds = [HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE, HeavyWorkOutbox.Kind.MC_ADVANCE_BUNDLE]
    try:
        # tenant-isolation-allow: platform-wide-migration-outbox-freshness-aggregation
        pending = HeavyWorkOutbox.objects.filter(
            kind__in=mc_kinds, status=HeavyWorkOutbox.Status.PENDING,
        )
        # tenant-isolation-allow: platform-wide-migration-outbox-freshness-aggregation
        processing = HeavyWorkOutbox.objects.filter(
            kind__in=mc_kinds, status=HeavyWorkOutbox.Status.PROCESSING,
        )
        pending_count = pending.count()
        processing_count = processing.count()
        oldest = pending.order_by("created_at").values_list("created_at", flat=True).first()
        oldest_age = (now - oldest).total_seconds() if oldest else None
        stale_cutoff = now - timedelta(seconds=stale_seconds)
        # tenant-isolation-allow: platform-wide-migration-outbox-freshness-aggregation
        stale_count = pending.filter(created_at__lte=stale_cutoff).count()
    except Exception as exc:  # noqa: BLE001 — table may be absent in some envs
        logger.warning(
            "migration_cloud.health: outbox_freshness_query_failed err=%s",
            type(exc).__name__,
        )
        return {"load_error": True}
    return {
        "load_error": False,
        "pending_count": pending_count,
        "processing_count": processing_count,
        "oldest_age_human": _human_duration(oldest_age),
        "stale_count": stale_count,
        "stale_threshold_human": _human_duration(stale_seconds),
        "fresh": stale_count == 0,
    }


def _migration_fleet_panel() -> dict[str, Any]:
    """G-6 migration-fleet SLO panel: apply latency + reconcile parity + outbox drain.

    Reads thresholds from the SLO registry so editing an objective in
    ``apps/observability/slo.py`` flows straight to this dashboard.
    """
    threshold_ms, parity_target = _fleet_slo_thresholds()
    return {
        "apply": _apply_latency_panel(threshold_ms),
        "parity": _reconcile_parity_panel(parity_target),
        "outbox": _outbox_freshness_panel(),
    }


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudHealthView(View):
    """GET /super/migration/health/ — staff-only platform health dashboard.

    Single GET surface; no POST. Auto-refresh every 60 seconds via
    ``<meta http-equiv="refresh" content="60">`` in the template.
    """

    template_name = "migration_cloud/super/health.html"

    def get(self, request, *args, **kwargs):
        webhooks = _webhook_deliveries_24h()
        maa_signs = _maa_signs_7d()
        uploads = _companion_uploads_24h()
        keypairs = _active_companion_keypairs()
        sunsets = _pending_legacy_hash_sunsets()
        scanners = _scanner_baselines()
        fleet = _migration_fleet_panel()

        logger.info(
            "migration_cloud_health_view_rendered user_id=%s "
            "webhook_total=%s maa_total=%s upload_total=%s keypair_total=%s "
            "sunset_count=%s scanner_rows=%s apply_samples=%s parity_samples=%s "
            "outbox_pending=%s",
            request.user.pk,
            webhooks["total"], maa_signs["total"], uploads["total"],
            keypairs["total"], sunsets["count"], len(scanners["rows"]),
            fleet["apply"].get("sample_count"), fleet["parity"].get("sample_count"),
            fleet["outbox"].get("pending_count"),
        )

        ctx = {
            "page_title": "Migration Cloud — operator health",
            "shell": kwargs.get("shell", "super"),
            "webhooks": webhooks,
            "maa_signs": maa_signs,
            "uploads": uploads,
            "keypairs": keypairs,
            "sunsets": sunsets,
            "scanners": scanners,
            "fleet": fleet,
        }
        return render(request, self.template_name, ctx)
