"""v4.00.56 — LMS connector diagnostics operator dashboard.

Surfaces live token-health metrics so on-call can spot a misconfigured
or stale LMS integration before pushgrade traffic starts failing:

  * per-provider token count + how many are configured (have an access
    token) vs unconfigured stubs
  * tokens past their stated ``expires_at`` (expired by the wall clock)
  * tokens past the rotation grace window (7d after expiry, per
    :mod:`apps.integrations_marketplace.lms_token_rotation`)
  * tokens missing a refresh token (cannot recover unattended)
  * last-24h push-grade audit outcomes per provider (ok / failed)
  * last-24h rotation outcomes per provider
  * timestamp of the most recent successful refresh per provider

Surface is staff-only and read-only. Designed to be polled by external
monitors via ``?format=json``.
"""
from __future__ import annotations

import json as _json
import logging
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_DIAG_LOOKBACK_HOURS = 24
_ROTATION_GRACE_SECONDS = 7 * 24 * 60 * 60  # mirrors lms_token_rotation default


def _compute_lms_diagnostics() -> dict:
    """Pure-function aggregator. Returns a dict the view renders as either
    JSON or template-context. NEVER raises — wraps each section in try/except
    and surfaces ``error`` flags per section."""
    out: dict = {
        "generated_at": timezone.now().isoformat(),
        "lookback_hours": _DIAG_LOOKBACK_HOURS,
        "rotation_grace_seconds": _ROTATION_GRACE_SECONDS,
        "providers": [],
        "totals": {
            "configured": 0,
            "unconfigured": 0,
            "expired": 0,
            "past_grace": 0,
            "missing_refresh": 0,
        },
        "errors": [],
    }

    try:
        from apps.integrations_marketplace.models_lms_token import LMSConnectorToken
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"token_model_unavailable: {exc}")
        return out

    try:
        from apps.integrations_marketplace.models_lms_audit import LMSPushGradeAudit
    except Exception as exc:  # noqa: BLE001
        LMSPushGradeAudit = None  # type: ignore[assignment]
        out["errors"].append(f"audit_model_unavailable: {exc}")

    now = timezone.now()
    grace_cutoff = now - timedelta(seconds=_ROTATION_GRACE_SECONDS)
    audit_since = now - timedelta(hours=_DIAG_LOOKBACK_HOURS)

    by_provider: dict[str, dict] = {}
    try:
        for row in LMSConnectorToken.objects.all().iterator(chunk_size=500):  # tenant-isolation-allow: lms-diagnostics-platform-scope-staff-only
            p = row.provider or ""
            d = by_provider.setdefault(p, {
                "provider": p,
                "total": 0,
                "configured": 0,
                "unconfigured": 0,
                "expired": 0,
                "past_grace": 0,
                "missing_refresh": 0,
                "latest_refresh_at": "",
            })
            d["total"] += 1
            configured = bool(row.access_token)
            if configured:
                d["configured"] += 1
                out["totals"]["configured"] += 1
            else:
                d["unconfigured"] += 1
                out["totals"]["unconfigured"] += 1
            if row.expires_at and row.expires_at < now:
                d["expired"] += 1
                out["totals"]["expired"] += 1
            if row.expires_at and row.expires_at < grace_cutoff:
                d["past_grace"] += 1
                out["totals"]["past_grace"] += 1
            if configured and not row.refresh_token:
                d["missing_refresh"] += 1
                out["totals"]["missing_refresh"] += 1
            # Track newest updated_at as a refresh-recency proxy (the existing
            # row only carries one timestamp; specific refresh history lives in
            # audit rows handled below).
            iso = row.updated_at.isoformat() if row.updated_at else ""
            if iso > d["latest_refresh_at"]:
                d["latest_refresh_at"] = iso
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms_diagnostics: token enum failed: %s", exc)
        out["errors"].append(f"token_enum_failed: {exc}")

    # Push-grade + rotation audit rollups per provider.
    # v4.00.61 — adds _auto_prune outcome partition alongside _rotation +
    # _health_check + push. Tracks dry_run vs real prune via assignment_id
    # prefix (v4.00.60 lms_oauth_auto_prune writes "dry_run:<reason>" or
    # just "<reason>" depending on RMC_LMS_OAUTH_AUTO_PRUNE_DRY_RUN).
    if LMSPushGradeAudit is not None:
        try:
            rotation_marker = "_rotation"
            prune_marker = "_auto_prune"
            health_marker = "_health_check"
            qs = LMSPushGradeAudit.objects.filter(created_at__gte=audit_since)  # tenant-isolation-allow: lms-diagnostics-audit-rollup-staff-only
            for r in qs.iterator(chunk_size=1000):
                p = r.provider or ""
                d = by_provider.setdefault(p, {
                    "provider": p, "total": 0, "configured": 0, "unconfigured": 0,
                    "expired": 0, "past_grace": 0, "missing_refresh": 0,
                    "latest_refresh_at": "",
                })
                course = r.course_id or ""
                if course == rotation_marker:
                    d.setdefault("rotation_ok_24h", 0)
                    d.setdefault("rotation_failed_24h", 0)
                    if r.ok:
                        d["rotation_ok_24h"] += 1
                    else:
                        d["rotation_failed_24h"] += 1
                elif course == prune_marker:
                    d.setdefault("prune_24h", 0)
                    d.setdefault("prune_dry_run_24h", 0)
                    assignment = str(getattr(r, "assignment_id", "") or "")
                    if assignment.startswith("dry_run:"):
                        d["prune_dry_run_24h"] += 1
                    else:
                        d["prune_24h"] += 1
                elif course == health_marker:
                    d.setdefault("health_ok_24h", 0)
                    d.setdefault("health_failed_24h", 0)
                    if r.ok:
                        d["health_ok_24h"] += 1
                    else:
                        d["health_failed_24h"] += 1
                else:
                    d.setdefault("push_ok_24h", 0)
                    d.setdefault("push_failed_24h", 0)
                    if r.ok:
                        d["push_ok_24h"] += 1
                    else:
                        d["push_failed_24h"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("lms_diagnostics: audit rollup failed: %s", exc)
            out["errors"].append(f"audit_rollup_failed: {exc}")

    # Default missing-key zeros so JSON consumers get a stable shape.
    for d in by_provider.values():
        for k in (
            "push_ok_24h", "push_failed_24h",
            "rotation_ok_24h", "rotation_failed_24h",
            "prune_24h", "prune_dry_run_24h",
            "health_ok_24h", "health_failed_24h",
        ):
            d.setdefault(k, 0)
    # v4.00.61 — total prune count for the rollup card at the top.
    out["totals"]["pruned_24h"] = sum(d.get("prune_24h", 0) for d in by_provider.values())
    out["totals"]["pruned_dry_run_24h"] = sum(d.get("prune_dry_run_24h", 0) for d in by_provider.values())

    out["providers"] = sorted(by_provider.values(), key=lambda r: r.get("provider", ""))
    return out


@staff_member_required
@require_http_methods(["GET"])
def lms_diagnostics(request: HttpRequest):
    """v4.00.56 — Operator dashboard at /super/migration/lms/diagnostics/.

    v4.00.60 — emits the last-action ring snapshot alongside the diag rollup.
    """
    diag = _compute_lms_diagnostics()
    last_actions = get_last_action_snapshot(limit=20)
    action_totals = _action_totals()
    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": not diag["errors"],
            **diag,
            "last_actions": last_actions,
            "action_totals": action_totals,
        })
    return render(request, "migration_cloud/super/lms_diagnostics.html", {
        "diag": diag,
        "last_actions": last_actions,
        "action_totals": action_totals,
    })


# ---------------------------------------------------------------------------
# v4.00.59 — Operator action buttons: force-refresh + force-rotate per
# provider. POSTs land here from the diagnostics dashboard; CSRF-protected
# Django session auth via @staff_member_required.
# ---------------------------------------------------------------------------


def _safe_provider(raw: str) -> str:
    """Whitelist allow-list of provider slugs so the action endpoints can't
    be coerced into operating on arbitrary input."""
    p = (raw or "").strip().lower()
    return p if p in {"canvas", "moodle", "google_classroom", "google"} else ""


# ---------------------------------------------------------------------------
# v4.00.60 — Last-action history ring buffer.
#
# Records every successful force-refresh / force-rotate click so operators
# can see recent diagnostic actions inline on the dashboard. Bounded ring
# (cap 200) keeps memory predictable; oldest-first eviction. Each entry
# records: timestamp, actor (username SHA-256[:12] — PII-safe), action,
# provider, and the resulting counters.
# ---------------------------------------------------------------------------

_LAST_ACTION_RING: list[dict] = []
_LAST_ACTION_RING_CAP = 200

# v4.00.71 — Cumulative retention sweep counters.
#
# Each successful retention sweep (preview OR force-purge) bumps these
# counters so operators have a quick-glance "how much have we purged
# this month" gauge. Process-lifetime only — persistent rollup lives in
# the LMSDiagActionAudit table; this is the fast hot-cache.
_RETENTION_SWEEP_COUNTERS: dict[str, int] = {
    "previews_count": 0,
    "purges_count": 0,
    "rows_considered_total": 0,
    "rows_deleted_total": 0,
}


def get_retention_sweep_counters() -> dict[str, int]:
    """Return a snapshot copy of the cumulative retention counters."""
    return dict(_RETENTION_SWEEP_COUNTERS)


def reset_retention_sweep_counters() -> None:
    """Test-only helper. Tenant-isolation-allow: process-singleton-counter-reset."""
    for k in list(_RETENTION_SWEEP_COUNTERS.keys()):
        _RETENTION_SWEEP_COUNTERS[k] = 0


def _bump_retention_sweep_counter(*, kind: str, considered: int, deleted: int) -> None:
    """``kind`` is 'preview' or 'purge'. NEVER raises."""
    try:
        if kind == "preview":
            _RETENTION_SWEEP_COUNTERS["previews_count"] += 1
        elif kind == "purge":
            _RETENTION_SWEEP_COUNTERS["purges_count"] += 1
        _RETENTION_SWEEP_COUNTERS["rows_considered_total"] += int(considered or 0)
        _RETENTION_SWEEP_COUNTERS["rows_deleted_total"] += int(deleted or 0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("retention counters bump failed: %s", exc)


def compute_diagnostics_alarms(*, success_floor_pct: float = 80.0,
                                min_actions: int = 5,
                                limit: int = 500) -> list[dict]:
    """v4.00.77 — Return the list of providers whose success rate dipped
    below ``success_floor_pct`` over the last ``limit`` actions.

    Skips providers with fewer than ``min_actions`` actions (not enough
    data to alert on — noise floor).

    Returns ``[{provider, success_rate_pct, total_actions, threshold_pct,
    severity}]`` sorted by severity desc (worst first). NEVER raises.
    """
    rollup = diagnostics_health_rollup_by_provider(limit=limit)
    out: list[dict] = []
    for provider, bucket in rollup.items():
        if bucket.get("total_actions", 0) < min_actions:
            continue
        rate = float(bucket.get("success_rate_pct") or 0.0)
        if rate >= success_floor_pct:
            continue
        # Severity classification — 4 tiers.
        if rate < 50.0:
            severity = "critical"
        elif rate < 70.0:
            severity = "high"
        elif rate < 80.0:
            severity = "warning"
        else:
            severity = "info"
        out.append({
            "provider": provider,
            "success_rate_pct": rate,
            "total_actions": bucket["total_actions"],
            "threshold_pct": success_floor_pct,
            "severity": severity,
        })
    # Worst first.
    _SEVERITY_RANK = {"critical": 0, "high": 1, "warning": 2, "info": 3}
    out.sort(key=lambda r: (_SEVERITY_RANK.get(r["severity"], 9),
                            r["success_rate_pct"]))
    return out


def diagnostics_health_rollup_by_provider(*, limit: int = 500) -> dict[str, dict]:
    """v4.00.75 — Health rollup keyed by provider.

    Returns ``{provider: {total_actions, ok_total, failed_total,
    success_rate_pct, latest_action_iso, latest_action_name}}`` so the
    operator dashboard can render a per-provider health card.
    """
    out: dict[str, dict] = {}
    try:
        snap = get_last_action_snapshot(limit=limit, durable=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("health rollup snapshot failed: %s", exc)
        return out
    for evt in snap:
        provider = str(evt.get("provider") or "unknown")
        bucket = out.setdefault(provider, {
            "total_actions": 0, "ok_total": 0, "failed_total": 0,
            "latest_action_iso": "", "latest_action_name": "",
        })
        bucket["total_actions"] += 1
        bucket["ok_total"] += int(evt.get("ok") or 0)
        bucket["failed_total"] += int(evt.get("failed") or 0)
        ts = str(evt.get("ts_iso") or "")
        if ts > bucket["latest_action_iso"]:
            bucket["latest_action_iso"] = ts
            bucket["latest_action_name"] = str(evt.get("action") or "")
    for provider, bucket in out.items():
        total_ops = bucket["ok_total"] + bucket["failed_total"]
        bucket["success_rate_pct"] = (
            round(100.0 * bucket["ok_total"] / total_ops, 2) if total_ops else 0.0
        )
    return out


def build_diagnostics_forensic_export(*, since=None, before=None,
                                       provider: str = "", action: str = "",
                                       limit: int = 2000) -> dict:
    """v4.00.73 — Build a forensic export packet of the action-history.

    Returns ``{generated_at, filters, rollup_by_action, entries}`` where
    ``entries`` is the windowed snapshot, ``rollup_by_action`` is the
    by-action aggregation over the same window. Designed for incident-
    response forensic walks — when an operator suspects a misuse pattern
    they pull this, attach to a Linear ticket, and hand to security.
    """
    try:
        entries = get_last_action_snapshot(limit=max(1, min(5000, limit)),
                                           since=since, before=before, durable=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("forensic export snapshot failed: %s", exc)
        entries = []
    filtered = []
    for evt in entries:
        if provider and str(evt.get("provider") or "").lower() != provider.lower():
            continue
        if action and str(evt.get("action") or "").lower() != action.lower():
            continue
        filtered.append(evt)
    rollup: dict[str, dict[str, int]] = {}
    for evt in filtered:
        a = str(evt.get("action") or "unknown")
        bucket = rollup.setdefault(a, {"count": 0, "ok_total": 0,
                                       "failed_total": 0, "considered_total": 0})
        bucket["count"] += 1
        bucket["ok_total"] += int(evt.get("ok") or 0)
        bucket["failed_total"] += int(evt.get("failed") or 0)
        bucket["considered_total"] += int(evt.get("considered") or 0)
    return {
        "generated_at": timezone.now().isoformat(),
        "filters": {
            "since": since.isoformat() if since else "",
            "before": before.isoformat() if before else "",
            "provider": provider or "",
            "action": action or "",
            "limit": limit,
        },
        "rollup_by_action": rollup,
        "entries": filtered,
        "entry_count": len(filtered),
    }


def action_history_rollup_by_action(*, limit: int = 200) -> dict[str, dict[str, int]]:
    """v4.00.72 — Roll up the last-action history ring by action name.

    Returns ``{action_name: {count, ok_total, failed_total, considered_total}}``.
    Empty when the ring is empty. NEVER raises.
    """
    out: dict[str, dict[str, int]] = {}
    try:
        snap = get_last_action_snapshot(limit=limit, durable=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("action_history_rollup_by_action: snapshot failed: %s", exc)
        return out
    for evt in snap:
        action = str(evt.get("action") or "unknown")
        bucket = out.setdefault(action, {"count": 0, "ok_total": 0,
                                        "failed_total": 0, "considered_total": 0})
        bucket["count"] += 1
        bucket["ok_total"] += int(evt.get("ok") or 0)
        bucket["failed_total"] += int(evt.get("failed") or 0)
        bucket["considered_total"] += int(evt.get("considered") or 0)
    return out

# v4.00.61 — DB persistence beyond worker lifetime. Each force-refresh /
# force-rotate click is mirrored to LMSPushGradeAudit with
# course_id="_diag_action" (matches the established _health_check /
# _rotation / _auto_prune discriminator pattern — no new migration). The
# in-process ring stays as a fast cache; the DB row is the durable SOT.
_DIAG_ACTION_COURSE_ID = "_diag_action"


def _persist_action_to_db(*, action: str, provider: str, actor_hash: str,
                          actor_user_id: str, summary: dict) -> None:
    """Write the action to LMSDiagActionAudit + LMSPushGradeAudit.

    v4.00.62 — dual-write during transition: new dedicated
    ``LMSDiagActionAudit`` table is canonical; legacy
    ``LMSPushGradeAudit`` with ``course_id="_diag_action"`` still
    written so any operator tooling watching the legacy table during
    deploy doesn't go blind mid-flight. Read paths prefer the new
    table; legacy rows are read only on fall-through.
    NEVER raises — DB unavailability degrades gracefully to in-process ring.
    """
    considered = int(summary.get("considered") or 0)
    ok_count = int(summary.get("refreshed") or summary.get("rotated") or 0)
    failed = int(summary.get("failed") or 0)

    # v4.00.62 canonical: dedicated LMSDiagActionAudit table.
    try:
        from apps.integrations_marketplace.models import LMSDiagActionAudit
        LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: lms-diagnostics-action-audit-platform-scope-staff-only
            action=action,
            provider=provider,
            actor_hash=actor_hash,
            actor_user_id=(actor_user_id or ""),
            considered=considered,
            ok_count=ok_count,
            failed_count=failed,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_diagnostics: diag-action db persist failed: %s", exc)

    # Legacy mirror — kept during the transition window so any operator
    # tooling watching the legacy table during deploy doesn't go blind.
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        detail = f"considered={considered} ok={ok_count} failed={failed}"
        LMSPushGradeAudit.objects.create(  # tenant-isolation-allow: lms-diagnostics-action-audit-legacy-mirror-platform-scope
            school_id=None,
            provider=provider,
            course_id=_DIAG_ACTION_COURSE_ID,
            assignment_id=action,
            user_hash=actor_hash,
            score_text="",
            ok=(failed == 0 and ok_count >= 0),
            status_code=200,
            detail=detail[:512],
            actor_user_id=(actor_user_id or ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_diagnostics: legacy db persist failed: %s", exc)


def _row_to_action_event(row) -> dict:
    """Project an LMSPushGradeAudit row back into the ring-buffer shape."""
    detail = str(getattr(row, "detail", "") or "")
    # Parse "considered=N ok=K failed=F" — keys we wrote.
    counters = {"considered": 0, "ok": 0, "failed": 0}
    for tok in detail.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            if k in counters:
                try:
                    counters[k] = int(v)
                except (ValueError, TypeError):
                    pass
    ts = getattr(row, "created_at", None)
    return {
        "ts_iso": ts.isoformat() if ts else "",
        "actor_hash": str(getattr(row, "user_hash", "") or ""),
        "action": str(getattr(row, "assignment_id", "") or ""),
        "provider": str(getattr(row, "provider", "") or ""),
        "considered": counters["considered"],
        "ok": counters["ok"],
        "failed": counters["failed"],
    }


def _diag_row_to_event(row) -> dict:
    """v4.00.62 — Project an LMSDiagActionAudit row into the ring-buffer shape."""
    ts = getattr(row, "created_at", None)
    return {
        "ts_iso": ts.isoformat() if ts else "",
        "actor_hash": str(getattr(row, "actor_hash", "") or ""),
        "action": str(getattr(row, "action", "") or ""),
        "provider": str(getattr(row, "provider", "") or ""),
        "considered": int(getattr(row, "considered", 0) or 0),
        "ok": int(getattr(row, "ok_count", 0) or 0),
        "failed": int(getattr(row, "failed_count", 0) or 0),
    }


def _read_action_history_from_db(
    *,
    limit: int = 50,
    since=None,
    before=None,
) -> list[dict]:
    """Newest-first DB read of recent diag-action rows. NEVER raises.

    v4.00.62 — prefers the new dedicated ``LMSDiagActionAudit`` table;
    falls through to legacy ``LMSPushGradeAudit`` when the new table is
    empty (covers the deploy transition before the first action lands).
    Supports ``since`` + ``before`` datetime window (T5 v4.00.62).
    """
    # New canonical table.
    try:
        from apps.integrations_marketplace.models import LMSDiagActionAudit
        qs = LMSDiagActionAudit.objects.all()  # tenant-isolation-allow: lms-diagnostics-action-history-read-platform-scope-staff-only
        if since is not None:
            qs = qs.filter(created_at__gte=since)
        if before is not None:
            qs = qs.filter(created_at__lt=before)
        qs = qs.order_by("-created_at")[:max(1, limit)]
        rows = list(qs)
        if rows:
            return [_diag_row_to_event(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_diagnostics: diag-table db read failed: %s", exc)

    # Legacy fall-through.
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        qs = LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: lms-diagnostics-action-history-legacy-read-platform-scope-staff-only
            course_id=_DIAG_ACTION_COURSE_ID,
        )
        if since is not None:
            qs = qs.filter(created_at__gte=since)
        if before is not None:
            qs = qs.filter(created_at__lt=before)
        qs = qs.order_by("-created_at")[:max(1, limit)]
        return [_row_to_action_event(r) for r in qs]
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_diagnostics: legacy db read failed: %s", exc)
        return []


def _record_action(*, request: HttpRequest, action: str, provider: str, summary: dict) -> None:
    """Append to the action ring AND persist to DB. NEVER raises."""
    try:
        import hashlib
        username = ""
        actor_user_id = ""
        if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False):
            username = str(getattr(request.user, "username", "") or "")
            actor_user_id = str(getattr(request.user, "pk", "") or "")
        actor_hash = hashlib.sha256(username.encode("utf-8")).hexdigest()[:12] if username else ""
        evt = {
            "ts_iso": timezone.now().isoformat(),
            "actor_hash": actor_hash,
            "action": action,
            "provider": provider,
            "considered": int(summary.get("considered") or 0),
            "ok": int(summary.get("refreshed") or summary.get("rotated") or 0),
            "failed": int(summary.get("failed") or 0),
        }
        _LAST_ACTION_RING.append(evt)
        if len(_LAST_ACTION_RING) > _LAST_ACTION_RING_CAP:
            del _LAST_ACTION_RING[: len(_LAST_ACTION_RING) - _LAST_ACTION_RING_CAP]
        # v4.00.61 — mirror to DB so action history survives worker restarts.
        _persist_action_to_db(
            action=action, provider=provider,
            actor_hash=actor_hash, actor_user_id=actor_user_id,
            summary=summary,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_diagnostics: action-ring append failed: %s", exc)


def get_last_action_snapshot(
    *,
    limit: int = 50,
    durable: bool = True,
    since=None,
    before=None,
) -> list[dict]:
    """Return a newest-first snapshot of recent actions.

    v4.00.61 — when ``durable=True`` (default), reads from the DB first so
    the operator sees actions from PRIOR worker generations too. Falls
    back to the in-process ring when DB is unavailable.
    v4.00.62 — optional ``since`` + ``before`` window (datetime); both
    must be tz-aware (request layer parses ISO-8601 -> UTC dt).
    """
    if limit <= 0:
        return []
    if durable:
        rows = _read_action_history_from_db(limit=limit, since=since, before=before)
        if rows:
            return rows
    out = list(reversed(_LAST_ACTION_RING))
    # In-process ring window filter (when DB read returned nothing).
    if since is not None or before is not None:
        from datetime import datetime as _dt
        filtered = []
        for e in out:
            try:
                ts = _dt.fromisoformat(e.get("ts_iso", "").replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if since is not None and ts < since:
                continue
            if before is not None and ts >= before:
                continue
            filtered.append(e)
        out = filtered
    return out[:limit]


def _action_totals() -> dict:
    """Aggregate the ring buffer for the dashboard summary card.

    v4.00.61 — prefers DB-backed snapshot so totals reflect persistent
    history rather than just current-worker actions.
    """
    snap = get_last_action_snapshot(limit=_LAST_ACTION_RING_CAP, durable=True)
    by_action: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    for e in snap:
        by_action[e.get("action", "")] = by_action.get(e.get("action", ""), 0) + 1
        by_provider[e.get("provider", "")] = by_provider.get(e.get("provider", ""), 0) + 1
    return {
        "total": len(snap),
        "by_action": by_action,
        "by_provider": by_provider,
        "durable": True,
    }


@staff_member_required
@require_http_methods(["GET"])
def lms_diagnostics_action_history(request: HttpRequest):
    """v4.00.60 — JSON-only endpoint returning the last-action ring snapshot.

    v4.00.62 — supports ISO-8601 ``?since=`` + ``?before=`` window
    pagination for forensic reads ("show me every operator click in this
    1-hour window"). Both bounds parsed as RFC-3339 / ISO-8601 strings
    and converted to tz-aware datetime (assumes UTC when no tz suffix).
    Bad timestamps fall through to the unwindowed default (logged, not
    error — operator-facing surface should NOT 400 on a typo).

    v4.00.63 — ``?format=csv`` returns a gzip-compressed RFC-4180 CSV
    export for operator forensic dumps. Columns: timestamp, action,
    provider, actor_hash, considered, ok, failed. Filename includes
    UTC date so the download can be filed cleanly.
    """
    try:
        limit = max(1, min(200, int(request.GET.get("limit") or "50")))
    except (ValueError, TypeError):
        limit = 50

    since = _parse_window_iso(request.GET.get("since"))
    before = _parse_window_iso(request.GET.get("before"))

    fmt = (request.GET.get("format") or "json").strip().lower()
    if fmt == "csv":
        return _action_history_csv_response(
            limit=limit, since=since, before=before,
        )

    return JsonResponse({
        "success": True,
        "generated_at": timezone.now().isoformat(),
        "limit": limit,
        "since": since.isoformat() if since else "",
        "before": before.isoformat() if before else "",
        "totals": _action_totals(),
        "entries": get_last_action_snapshot(limit=limit, since=since, before=before),
    })


def _action_history_csv_response(*, limit: int, since=None, before=None):
    """v4.00.63 — gzip-compressed CSV export of the action-history snapshot.

    Returns a Django HttpResponse with ``Content-Type: text/csv`` +
    ``Content-Encoding: gzip`` and a ``Content-Disposition: attachment``
    header. NEVER raises — DB errors fall through to an empty (header-only)
    CSV so the operator gets back a parseable file.
    """
    import csv
    import gzip
    import io
    from django.http import HttpResponse

    # Use a higher cap for export reads — operators want the full window.
    rows = get_last_action_snapshot(limit=max(1, min(2000, limit * 10)),
                                    since=since, before=before)

    # Build CSV in-memory; RFC-4180 quoting via csv module.
    text_buf = io.StringIO()
    writer = csv.writer(text_buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow([
        "timestamp_iso", "action", "provider",
        "actor_hash", "considered", "ok", "failed",
    ])
    for r in rows:
        writer.writerow([
            r.get("ts_iso", ""),
            r.get("action", ""),
            r.get("provider", ""),
            r.get("actor_hash", ""),
            int(r.get("considered") or 0),
            int(r.get("ok") or 0),
            int(r.get("failed") or 0),
        ])

    # gzip the CSV bytes.
    raw = text_buf.getvalue().encode("utf-8")
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode="wb", mtime=0) as gz:
        gz.write(raw)
    gz_bytes = gz_buf.getvalue()

    today = timezone.now().strftime("%Y-%m-%d")
    fname = f"lms_diag_action_history_{today}.csv.gz"
    resp = HttpResponse(gz_bytes, content_type="text/csv")
    resp["Content-Encoding"] = "gzip"
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    resp["Content-Length"] = str(len(gz_bytes))
    resp["X-Action-History-Row-Count"] = str(len(rows))
    return resp


# ---------------------------------------------------------------------------
# v4.00.64 — Retention dry-run preview UI surface.
#
# Operator-facing forecast of what the next retention sweep would purge,
# WITHOUT actually deleting anything. Reuses
# ``sweep_lms_diag_action_retention(dry_run=True)`` from the v4.00.63
# retention module so the cutoff math + considered-count logic stay
# identical to the beat-driven sweep — no drift between preview and
# real-sweep semantics.
#
# Inputs:
#   ?years=<N>   — override the retention window (default = beat env);
#                  N<=0 returns the retain-forever short-circuit shape.
#
# Output shape (JSON):
#   {success, generated_at, retention: {years, cutoff_iso, considered,
#    deleted, dry_run, skipped?, error?},
#    note: "preview only — nothing was deleted"}
# ---------------------------------------------------------------------------


# v4.00.66 — Retention force-purge token round-trip.
#
# The HTML preview surface emits a signed token bound to the exact
# ``(years, cutoff_iso)`` it just showed the operator. The force-purge
# POST view validates the token (Django TimestampSigner, 5min TTL) and
# THEN runs the real sweep with ``dry_run=False``. A token issued for
# 7y CANNOT be replayed against the 3y sweep — the cutoff is part of
# the signed payload — so the operator can't accidentally purge more
# than they previewed.
#
# Audit-trail safety: every successful purge writes an audit row via the
# v4.00.61 ``_record_action`` path with action="retention_purge" so the
# diagnostics history surface reflects the deletion.
_RETENTION_PURGE_TOKEN_SALT = "rmc.lms_diag_action.retention_purge.v4.00.66"
_RETENTION_PURGE_TOKEN_TTL_SECONDS = 300  # 5min

# v4.00.67 — Retention preview sparkline by-week.
#
# Buckets LMSDiagActionAudit rows by ISO-week relative to the sweep cutoff
# so the operator can see distribution skew before clicking purge. The
# 24-week window (12 weeks behind + 12 weeks ahead of cutoff) is wide
# enough to show whether the would-purge population is steady-state vs
# an unusual spike at the edge of the retention window.
_RETENTION_SPARKLINE_WEEKS_PER_SIDE = 12


def _retention_purge_sparkline(*, cutoff_dt, now=None) -> dict:
    """Return ``{buckets, max_count, weeks_per_side, before_total,
    after_total}`` for the preview UI sparkline.

    ``buckets`` is a list of 24 dicts each carrying
    ``{week_start_iso, count, side}`` where side ∈ ``before|after`` —
    operator sees the would-purge population on the left of the divider
    and the kept population on the right.
    NEVER raises — DB errors return an empty sparkline shape.
    """
    from django.utils import timezone as _tz
    from datetime import timedelta
    now = now or _tz.now()
    weeks = _RETENTION_SPARKLINE_WEEKS_PER_SIDE
    if cutoff_dt is None:
        return {"buckets": [], "max_count": 0, "weeks_per_side": weeks,
                "before_total": 0, "after_total": 0,
                "percentile_bands": {"p25": 0, "p25_y": 0, "p50": 0, "p50_y": 0,
                                     "p75": 0, "p75_y": 0, "nonzero_count": 0}}

    # Anchor each bucket to the start of a week (Monday 00:00 UTC).
    window_start = cutoff_dt - timedelta(weeks=weeks)
    window_end = cutoff_dt + timedelta(weeks=weeks)

    try:
        from apps.integrations_marketplace.models import LMSDiagActionAudit
    except Exception as exc:  # noqa: BLE001
        logger.debug("retention sparkline: model unavailable: %s", exc)
        return {"buckets": [], "max_count": 0, "weeks_per_side": weeks,
                "before_total": 0, "after_total": 0,
                "percentile_bands": {"p25": 0, "p25_y": 0, "p50": 0, "p50_y": 0,
                                     "p75": 0, "p75_y": 0, "nonzero_count": 0}}

    buckets = []
    for i in range(weeks * 2):
        bucket_start = window_start + timedelta(weeks=i)
        bucket_end = bucket_start + timedelta(weeks=1)
        side = "before" if bucket_end <= cutoff_dt else "after"
        try:
            cnt = LMSDiagActionAudit.objects.filter(  # tenant-isolation-allow: retention-preview-sparkline-platform-scope
                created_at__gte=bucket_start,
                created_at__lt=bucket_end,
            ).count()
        except Exception as exc:  # noqa: BLE001
            logger.debug("retention sparkline: bucket count failed: %s", exc)
            cnt = 0
        buckets.append({
            "week_start_iso": bucket_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": cnt,
            "side": side,
        })

    max_count = max((b["count"] for b in buckets), default=0)
    before_total = sum(b["count"] for b in buckets if b["side"] == "before")
    after_total = sum(b["count"] for b in buckets if b["side"] == "after")
    # Pre-compute SVG bar geometry so the template stays arithmetic-free.
    # viewBox is 288x60; bars are 10 wide, 12 apart.
    chart_h = 56
    chart_top_pad = 2
    for idx, b in enumerate(buckets):
        bar_h = int((b["count"] / max_count) * chart_h) if max_count else 0
        b["x"] = idx * 12
        b["bar_h"] = bar_h
        b["bar_y"] = chart_top_pad + (chart_h - bar_h)
    # v4.00.69 — Percentile bands (p25/p50/p75) over the non-zero bucket
    # counts. Operator overlay catches "this purge is hitting an unusual
    # spike" before it lands. Bands computed on non-zero counts only so a
    # mostly-empty window doesn't compress all three percentiles to 0.
    nonzero = sorted(b["count"] for b in buckets if b["count"] > 0)
    if nonzero:
        def _pct(p):
            idx = max(0, min(len(nonzero) - 1, int(p * len(nonzero) / 100)))
            return nonzero[idx]
        p25 = _pct(25)
        p50 = _pct(50)
        p75 = _pct(75)
    else:
        p25 = p50 = p75 = 0
    # Pre-compute the SVG y-coords for each band so the template just
    # renders `<line y="{p25_y}" ...>`.
    def _band_y(value):
        if not max_count:
            return chart_top_pad + chart_h
        h = int((value / max_count) * chart_h)
        return chart_top_pad + (chart_h - h)
    return {
        "buckets": buckets,
        "max_count": max_count,
        "weeks_per_side": weeks,
        "before_total": before_total,
        "after_total": after_total,
        "window_start_iso": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_end_iso": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "viewbox_width": 288,
        "viewbox_height": 60,
        "divider_x": 144,
        "percentile_bands": {
            "p25": p25, "p25_y": _band_y(p25),
            "p50": p50, "p50_y": _band_y(p50),
            "p75": p75, "p75_y": _band_y(p75),
            "nonzero_count": len(nonzero),
        },
    }


def _retention_preview_csv_response(*, retention: dict, sparkline: dict):
    """v4.00.68 — gzip-compressed CSV export of the retention preview's
    sparkline histogram.

    Layout:
      * ``#summary`` block (commented header rows) carries the retention
        scalar — years, cutoff_iso, considered, before_total, after_total,
        weeks_per_side, window_start_iso, window_end_iso.
      * Blank line.
      * Header row: ``week_start_iso, side, count, x, bar_h, bar_y``
      * 24 bucket rows (12 before + 12 after).
      * Empty buckets shape (cutoff_dt=None) emits the summary + header
        + zero data rows.
    """
    import csv
    import gzip
    import io
    from django.http import HttpResponse

    text_buf = io.StringIO()
    writer = csv.writer(text_buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

    cutoff_iso = str(retention.get("cutoff_iso") or "")
    years = int(retention.get("years") or 0)
    considered = int(retention.get("considered") or 0)
    before_total = int(sparkline.get("before_total") or 0)
    after_total = int(sparkline.get("after_total") or 0)
    weeks_per_side = int(sparkline.get("weeks_per_side") or 0)
    window_start_iso = str(sparkline.get("window_start_iso") or "")
    window_end_iso = str(sparkline.get("window_end_iso") or "")

    writer.writerow(["#summary", "key", "value"])
    writer.writerow(["#summary", "years", years])
    writer.writerow(["#summary", "cutoff_iso", cutoff_iso])
    writer.writerow(["#summary", "considered", considered])
    writer.writerow(["#summary", "before_total", before_total])
    writer.writerow(["#summary", "after_total", after_total])
    writer.writerow(["#summary", "weeks_per_side", weeks_per_side])
    writer.writerow(["#summary", "window_start_iso", window_start_iso])
    writer.writerow(["#summary", "window_end_iso", window_end_iso])
    # v4.00.69 — Percentile bands surfaced in CSV summary too.
    bands = sparkline.get("percentile_bands") or {}
    writer.writerow(["#summary", "p25", int(bands.get("p25") or 0)])
    writer.writerow(["#summary", "p50", int(bands.get("p50") or 0)])
    writer.writerow(["#summary", "p75", int(bands.get("p75") or 0)])
    writer.writerow([])
    writer.writerow(["week_start_iso", "side", "count", "x", "bar_h", "bar_y"])

    for b in sparkline.get("buckets") or []:
        writer.writerow([
            b.get("week_start_iso", ""),
            b.get("side", ""),
            int(b.get("count") or 0),
            int(b.get("x") or 0),
            int(b.get("bar_h") or 0),
            int(b.get("bar_y") or 0),
        ])

    raw = text_buf.getvalue().encode("utf-8")
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode="wb", mtime=0) as gz:
        gz.write(raw)
    gz_bytes = gz_buf.getvalue()

    today = timezone.now().strftime("%Y-%m-%d")
    fname = f"lms_diag_retention_preview_{today}.csv.gz"
    resp = HttpResponse(gz_bytes, content_type="text/csv")
    resp["Content-Encoding"] = "gzip"
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    resp["Content-Length"] = str(len(gz_bytes))
    resp["X-Retention-Sparkline-Bucket-Count"] = str(len(sparkline.get("buckets") or []))
    resp["X-Retention-Before-Total"] = str(before_total)
    resp["X-Retention-After-Total"] = str(after_total)
    return resp


def _retention_preview_jsonl_response(*, retention: dict, sparkline: dict):
    """v4.00.70 — Newline-delimited JSON export of the retention preview.

    Line 1: ``{"kind": "summary", ...retention scalars + sparkline totals}``
    Lines 2-25: one ``{"kind": "bucket", ...bucket fields}`` per sparkline bucket.
    Headers carry the bucket count + before/after totals.
    NOT gzipped (operators tend to pipe NDJSON straight to jq).
    """
    import io
    from django.http import HttpResponse

    text_buf = io.StringIO()
    bands = sparkline.get("percentile_bands") or {}
    summary = {
        "kind": "summary",
        "years": int(retention.get("years") or 0),
        "cutoff_iso": str(retention.get("cutoff_iso") or ""),
        "considered": int(retention.get("considered") or 0),
        "before_total": int(sparkline.get("before_total") or 0),
        "after_total": int(sparkline.get("after_total") or 0),
        "weeks_per_side": int(sparkline.get("weeks_per_side") or 0),
        "window_start_iso": str(sparkline.get("window_start_iso") or ""),
        "window_end_iso": str(sparkline.get("window_end_iso") or ""),
        "max_count": int(sparkline.get("max_count") or 0),
        "p25": int(bands.get("p25") or 0),
        "p50": int(bands.get("p50") or 0),
        "p75": int(bands.get("p75") or 0),
    }
    text_buf.write(_json.dumps(summary, separators=(",", ":")) + "\n")
    for b in sparkline.get("buckets") or []:
        text_buf.write(_json.dumps({
            "kind": "bucket",
            "week_start_iso": b.get("week_start_iso", ""),
            "side": b.get("side", ""),
            "count": int(b.get("count") or 0),
        }, separators=(",", ":")) + "\n")

    body = text_buf.getvalue().encode("utf-8")
    today = timezone.now().strftime("%Y-%m-%d")
    fname = f"lms_diag_retention_preview_{today}.jsonl"
    resp = HttpResponse(body, content_type="application/x-ndjson; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    resp["Content-Length"] = str(len(body))
    resp["X-Retention-Sparkline-Bucket-Count"] = str(len(sparkline.get("buckets") or []))
    resp["X-Retention-Before-Total"] = str(summary["before_total"])
    resp["X-Retention-After-Total"] = str(summary["after_total"])
    return resp


def _make_retention_purge_token(*, years: int, cutoff_iso: str) -> str:
    from django.core.signing import TimestampSigner
    signer = TimestampSigner(salt=_RETENTION_PURGE_TOKEN_SALT)
    payload = f"{int(years)}:{cutoff_iso or ''}"
    return signer.sign(payload)


def _read_retention_purge_token(raw: str):
    """Return ``(years, cutoff_iso)`` on valid token, else (None, reason)."""
    from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
    signer = TimestampSigner(salt=_RETENTION_PURGE_TOKEN_SALT)
    if not raw:
        return None, "missing_token"
    try:
        payload = signer.unsign(raw, max_age=_RETENTION_PURGE_TOKEN_TTL_SECONDS)
    except SignatureExpired:
        return None, "expired_token"
    except BadSignature:
        return None, "bad_token"
    if ":" not in payload:
        return None, "malformed_payload"
    years_s, cutoff_iso = payload.split(":", 1)
    try:
        years = int(years_s)
    except (ValueError, TypeError):
        return None, "bad_years"
    return (years, cutoff_iso), "ok"


@staff_member_required
@require_http_methods(["GET"])
def lms_diagnostics_retention_preview(request: HttpRequest):
    """v4.00.64 — Operator preview of the next retention sweep's footprint.

    Always runs ``sweep_lms_diag_action_retention(dry_run=True)`` regardless
    of any ``RMC_LMS_DIAG_ACTION_RETENTION_DRY_RUN`` env. Caller's
    ``?years=<N>`` overrides the retention window for the preview only —
    handy for "what if we lowered the window to 3y" planning conversations.

    v4.00.65 — Default to HTML for browser hits; ``?format=json`` keeps
    the original JSON shape for monitor / smoke probes.

    v4.00.66 — HTML render emits a 5min-TTL signed token bound to
    ``(years, cutoff_iso)`` so the operator can click "Confirm purge"
    without replay risk. The token is consumed by
    ``lms_diagnostics_retention_purge``.
    """
    try:
        from apps.integrations_marketplace.lms_diag_action_retention import (
            sweep_lms_diag_action_retention,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse(
            {"success": False, "error": f"sweep_unavailable: {exc}"},
            status=503,
        )

    years_raw = (request.GET.get("years") or "").strip()
    years: int | None = None
    if years_raw:
        try:
            years = int(years_raw)
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "error": "bad_years",
                 "reason": "expected_integer", "value": years_raw},
                status=400,
            )

    try:
        out = sweep_lms_diag_action_retention(years=years, dry_run=True)
    except Exception as exc:  # noqa: BLE001
        # Defense-in-depth — sweep is documented NEVER to raise, but if
        # someone breaks that contract the operator UI shouldn't 500.
        logger.warning("retention preview: sweep raised: %s", exc)
        return JsonResponse(
            {"success": False, "error": f"sweep_raised: {exc}"},
            status=503,
        )

    # v4.00.71 — Bump cumulative preview counter (operator dashboard).
    _bump_retention_sweep_counter(
        kind="preview",
        considered=int(out.get("considered") or 0),
        deleted=0,  # preview never deletes
    )

    # v4.00.66 — Mint a force-purge token only when the sweep produced a
    # real cutoff (i.e. years > 0 and the table has a row to purge). For
    # retain_forever / errored shapes the token is empty and the HTML
    # template gates the button off.
    purge_token = ""
    if out.get("considered", 0) > 0 and out.get("cutoff_iso"):
        purge_token = _make_retention_purge_token(
            years=int(out.get("years") or 0),
            cutoff_iso=str(out.get("cutoff_iso") or ""),
        )

    # v4.00.67 — Sparkline showing 24 weeks of row distribution around the
    # cutoff so operator sees skew before purging.
    cutoff_dt = _parse_window_iso(out.get("cutoff_iso") or "")
    sparkline = _retention_purge_sparkline(cutoff_dt=cutoff_dt)

    fmt = (request.GET.get("format") or "").strip().lower()
    if fmt == "json":
        return JsonResponse({
            "success": True,
            "generated_at": timezone.now().isoformat(),
            "retention": out,
            "purge_token": purge_token,
            "purge_token_ttl_seconds": _RETENTION_PURGE_TOKEN_TTL_SECONDS,
            "sparkline": sparkline,
            "note": "preview only — nothing was deleted",
        })
    # v4.00.68 — ?format=csv exports the sparkline histogram as a
    # gzip-compressed RFC-4180 CSV so operators can paste it into a sheet
    # or feed it to a downstream tool. The CSV opens with a #summary block
    # then transitions into the by-week bucket rows.
    if fmt == "csv":
        return _retention_preview_csv_response(
            retention=out, sparkline=sparkline,
        )
    # v4.00.70 — ?format=jsonl emits NDJSON: summary as line 1, then one
    # bucket per line. Easy to feed to operator command-line tools.
    if fmt == "jsonl":
        return _retention_preview_jsonl_response(
            retention=out, sparkline=sparkline,
        )

    return render(
        request,
        "migration_cloud/super/lms_diagnostics_retention_preview.html",
        {
            "retention": out,
            "generated_at": timezone.now().isoformat(),
            "years_override": years,
            "purge_token": purge_token,
            "purge_token_ttl_seconds": _RETENTION_PURGE_TOKEN_TTL_SECONDS,
            "sparkline": sparkline,
            "note": "preview only — nothing was deleted",
        },
    )


@staff_member_required
@require_http_methods(["POST"])
def lms_diagnostics_retention_purge(request: HttpRequest):
    """v4.00.66 — Honor the "Confirm purge" click from the preview UI.

    Validates the signed token + runs the REAL sweep with ``dry_run=False``.
    Emits an audit row via the v4.00.61 action-history path so the
    purge appears in the diagnostics dashboard alongside operator clicks.

    Response shape: JSON ``{success, action="retention_purge", considered,
    deleted, cutoff_iso, years, token_reason}``. Form-submitted clicks
    redirect back to the preview page w/ ``?purged_deleted=N`` so the
    operator sees the result inline.

    Failure modes:
      * Missing/expired/bad token → 401 ``invalid_purge_token`` w/ reason
      * Sweep unavailable (model import failure) → 503
      * Sweep raised (defense-in-depth) → 503
    """
    raw_token = (request.POST.get("token") or request.GET.get("token") or "").strip()
    parsed, reason = _read_retention_purge_token(raw_token)
    if parsed is None:
        return JsonResponse(
            {"success": False, "stage": "invalid_purge_token", "reason": reason},
            status=401,
        )
    years, cutoff_iso = parsed

    try:
        from apps.integrations_marketplace.lms_diag_action_retention import (
            sweep_lms_diag_action_retention,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse(
            {"success": False, "stage": "sweep_unavailable", "error": str(exc)},
            status=503,
        )

    try:
        out = sweep_lms_diag_action_retention(years=years, dry_run=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("retention purge: sweep raised: %s", exc)
        return JsonResponse(
            {"success": False, "stage": "sweep_raised", "error": str(exc)},
            status=503,
        )

    summary = {
        "success": True,
        "action": "retention_purge",
        "considered": out.get("considered", 0),
        "deleted": out.get("deleted", 0),
        "cutoff_iso": out.get("cutoff_iso", cutoff_iso),
        "years": out.get("years", years),
        "token_reason": reason,
    }
    # v4.00.71 — Bump cumulative purge counter.
    _bump_retention_sweep_counter(
        kind="purge",
        considered=int(summary["considered"] or 0),
        deleted=int(summary["deleted"] or 0),
    )
    # Wire into v4.00.61 action-history ring so the purge appears in
    # the operator audit trail alongside force-refresh / force-rotate clicks.
    try:
        _record_action(
            request=request,
            action="retention_purge",
            provider="lms_diag_action",
            summary={**summary, "ok": out.get("deleted", 0),
                     "failed": (out.get("considered", 0) - out.get("deleted", 0))},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("retention purge: audit emit failed: %s", exc)

    if (request.headers.get("Accept") or "").lower().startswith("application/json"):
        return JsonResponse(summary)

    # Form-submitted click → redirect back to the preview with a result query.
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(
        f"/super/migration/lms/diagnostics/retention-preview/"
        f"?purged_deleted={summary['deleted']}&purged_considered={summary['considered']}"
    )


def _parse_window_iso(raw):
    """v4.00.62 — Parse an ISO-8601 timestamp into a tz-aware datetime.

    Returns ``None`` on missing OR malformed input (operator-facing
    surface, so we don't 400). Accepts ``2026-05-29T12:00:00Z`` (Z
    suffix), ``2026-05-29T12:00:00+00:00``, ``2026-05-29T12:00:00`` (naive,
    treated as UTC), and ``2026-05-29`` (midnight UTC).
    """
    if not raw:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    from datetime import datetime, timezone as _tz_mod
    # Normalize trailing Z to +00:00 so fromisoformat accepts it on 3.10.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        logger.debug("lms_diagnostics: window parse failed: %r", raw)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz_mod.utc)
    return dt


@staff_member_required
@require_http_methods(["POST"])
def lms_diagnostics_force_refresh(request: HttpRequest):
    """v4.00.59 — Force-refresh every expired token for ``?provider=<slug>``.

    Reuses v4.00.59 ``lms_oauth_health.sweep_lms_oauth_health`` so the
    outcome lands in the audit ring via the existing ``_health_check``
    marker. Returns JSON summary; redirects to the diagnostics page when
    the request is form-submitted (no Accept JSON header).
    """
    provider = _safe_provider(request.POST.get("provider") or request.GET.get("provider") or "")
    if not provider:
        return JsonResponse({"success": False, "error": "missing_or_bad_provider"}, status=400)

    try:
        from apps.integrations_marketplace.lms_oauth_health import sweep_lms_oauth_health
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"success": False, "error": f"sweep_unavailable: {exc}"}, status=503)

    out = sweep_lms_oauth_health()
    # Filter the result for the requested provider so the operator sees
    # only what was relevant to their click.
    by_provider = [r for r in out.get("results", []) if r.get("provider") == provider]
    summary = {
        "success": True,
        "action": "force_refresh",
        "provider": provider,
        "considered": out.get("considered", 0),
        "refreshed": out.get("refreshed", 0),
        "failed": out.get("failed", 0),
        "results_for_provider": by_provider,
    }
    _record_action(request=request, action="force_refresh", provider=provider, summary=summary)

    if (request.headers.get("Accept") or "").lower().startswith("application/json"):
        return JsonResponse(summary)
    # Form-submitted: send the operator back to the dashboard.
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(
        f"/super/migration/lms/diagnostics/?action=force_refresh&provider={provider}"
        f"&considered={summary['considered']}&refreshed={summary['refreshed']}&failed={summary['failed']}"
    )


@staff_member_required
@require_http_methods(["POST"])
def lms_diagnostics_force_rotate(request: HttpRequest):
    """v4.00.59 — Force-rotate every token past the rotation-grace window
    for ``?provider=<slug>``.

    Reuses v4.00.54 ``lms_token_rotation.sweep_lms_tokens_due_rotation``.
    """
    provider = _safe_provider(request.POST.get("provider") or request.GET.get("provider") or "")
    if not provider:
        return JsonResponse({"success": False, "error": "missing_or_bad_provider"}, status=400)

    try:
        from apps.integrations_marketplace.lms_token_rotation import sweep_lms_tokens_due_rotation
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"success": False, "error": f"sweep_unavailable: {exc}"}, status=503)

    out = sweep_lms_tokens_due_rotation()
    by_provider = [r for r in out.get("results", []) if r.get("provider") == provider]
    summary = {
        "success": True,
        "action": "force_rotate",
        "provider": provider,
        "considered": out.get("considered", 0),
        "rotated": out.get("rotated", 0),
        "failed": out.get("failed", 0),
        "results_for_provider": by_provider,
    }
    _record_action(request=request, action="force_rotate", provider=provider, summary=summary)

    if (request.headers.get("Accept") or "").lower().startswith("application/json"):
        return JsonResponse(summary)
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(
        f"/super/migration/lms/diagnostics/?action=force_rotate&provider={provider}"
        f"&considered={summary['considered']}&rotated={summary['rotated']}&failed={summary['failed']}"
    )
