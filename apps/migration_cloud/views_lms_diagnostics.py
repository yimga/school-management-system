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
    """
    try:
        limit = max(1, min(200, int(request.GET.get("limit") or "50")))
    except (ValueError, TypeError):
        limit = 50

    since = _parse_window_iso(request.GET.get("since"))
    before = _parse_window_iso(request.GET.get("before"))

    return JsonResponse({
        "success": True,
        "generated_at": timezone.now().isoformat(),
        "limit": limit,
        "since": since.isoformat() if since else "",
        "before": before.isoformat() if before else "",
        "totals": _action_totals(),
        "entries": get_last_action_snapshot(limit=limit, since=since, before=before),
    })


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
