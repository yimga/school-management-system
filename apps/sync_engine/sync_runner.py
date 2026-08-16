"""Self-healing edge<->cloud sync runner for the Sync Center "Sync now" button.

A thin, NEVER-RAISING wrapper over the SAME edge services the scheduled
``edge_sync_cycle`` command drives:

  * PUSH — ``edge_outbox.build_edge_delta_bundle`` + ``edge_outbox.post_bundle``
  * PULL — ``edge_outbox.pull_bundle`` + ``edge_inbox.apply_pulled_bundle``

Whatever happens — the flag is off, the operator is unreachable, a bundle is rejected —
:func:`run_sync_cycle` returns a result dict AND records EXACTLY ONE
:class:`~apps.sync_engine.models.EdgeSyncRun`, so a tenant-admin click shows an outcome
instead of crashing the page. Each direction is wrapped independently (mirroring
``edge_sync_cycle``'s resilience) so a failing push never aborts the pull, and vice versa.

GATED by ``settings.RMC_EDGE_SYNC_ENABLED`` exactly like the command: off => no network,
a recorded ok=False "not enabled" row, and a clean ``{"enabled": False, ...}`` return.

Money stays cloud-authoritative — this only drives the existing protocol and changes no
conflict/money policy.

    mode="live"  push local changes UP, then pull cloud changes DOWN and apply them.
    mode="dry"   NO-WRITE CHECK: builds the local delta only to preview the pending count
                 (never POSTs it) and fetches the cloud download endpoint only to confirm
                 reachability + that the credential is accepted (never applies the bundle).
                 Nothing is written in EITHER direction — this is the safe connectivity
                 probe the pre-offline sync gate runs before a box may go dark.
"""
from __future__ import annotations

import os

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone


def _operator_base() -> str:
    """Operator (cloud) base URL the box pushes/pulls against, same knobs the box uses
    elsewhere. Empty is tolerated — the transport call simply fails and is recorded."""
    base = (getattr(settings, "RMC_EDGE_OPERATOR_BASE", "") or "").strip()
    if not base:
        base = (getattr(settings, "RMC_HUB_BASE_URL", "") or "").strip()
    return base.rstrip("/")


def _edge_token() -> str:
    """Edge machine credential — the same env var the commands read (RMC_EDGE_CREDENTIAL)."""
    return (os.getenv("RMC_EDGE_CREDENTIAL") or "").strip()


def _endpoint(base: str, url_name: str, fallback_path: str) -> str:
    try:
        path = reverse(url_name)
    except NoReverseMatch:
        path = fallback_path
    return base + path


def _resolve_principal(school):
    """Local admin principal to apply pulled rows as — mirrors ``pull_edge_inbox``'s
    resolver (school owner, else any superuser)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        from apps.schools.models import SchoolMembership

        owner = (
            SchoolMembership.objects.filter(school=school, role="owner")
            .select_related("user")
            .first()
        )
        if owner is not None and getattr(owner, "user", None) is not None:
            return owner.user
    except Exception:  # noqa: BLE001 — membership model shape varies; fall through
        pass
    return User.objects.filter(is_superuser=True).order_by("pk").first()


def run_sync_cycle(school, *, mode="live") -> dict:
    """Run one edge<->cloud sync cycle for ``school`` and record exactly one EdgeSyncRun.

    NEVER raises. Returns a result dict:
    ``{enabled, mode, ok, pushed, pulled, conflicts, created, upserted, message, error}``.
    """
    from apps.sync_engine.models import EdgeSyncRun

    mode = "dry" if str(mode).strip().lower() == "dry" else "live"
    started = timezone.now()
    result = {
        "enabled": True,
        "mode": mode,
        "ok": False,
        "pushed": 0,
        "pulled": 0,
        "conflicts": 0,
        "created": 0,
        "upserted": 0,
        "message": "",
        "error": "",
    }

    # Flag-gated exactly like edge_sync_cycle: off => a hard no-op (no network), but we
    # still record a visible ok=False row so the UI can explain why nothing happened.
    if not getattr(settings, "RMC_EDGE_SYNC_ENABLED", False):
        result["enabled"] = False
        result["message"] = "Edge sync is not enabled on this deployment"
        EdgeSyncRun.record(
            school,
            mode=mode,
            ok=False,
            message=result["message"],
            started_at=started,
            finished_at=timezone.now(),
        )
        return result

    base = _operator_base()
    token = _edge_token()
    errors: list[str] = []
    notes: list[str] = []

    from apps.sync_engine import edge_outbox

    # 1) PUSH local changes UP. In dry mode we build the delta to preview the count but
    #    NEVER post it (no cloud-bound write). A failure here does NOT abort the pull.
    try:
        data, meta = edge_outbox.build_edge_delta_bundle(school, since=None, entities=None)
        if mode == "dry":
            notes.append(f"dry run: {meta['row_count']} local change(s) NOT pushed")
        elif meta["row_count"] == 0:
            notes.append("nothing to push")
        else:
            endpoint = _endpoint(
                base, "api:sync-bundle-upload", "/api/v1/sync/bundle/upload/"
            )
            status, body = edge_outbox.post_bundle(endpoint, token, data)
            if status == 200 and body.get("ok"):
                result["pushed"] = meta["row_count"]
                result["conflicts"] += int(body.get("conflicts") or 0)
                notes.append(f"pushed {result['pushed']}")
            else:
                errors.append(f"push rejected (HTTP {status})")
    except Exception as exc:  # noqa: BLE001 — never crash the tenant page
        errors.append(f"push failed: {exc}")

    # 2) PULL cloud changes DOWN. LIVE applies them (inbound/local; cloud is
    #    authoritative). DRY only confirms the cloud is reachable and the credential is
    #    accepted (HTTP 200) and applies NOTHING — a true no-write probe. Independent of
    #    the push result either way.
    try:
        endpoint = _endpoint(
            base, "api:sync-bundle-download", "/api/v1/sync/bundle/download/"
        )
        status, body, _high_water = edge_outbox.pull_bundle(
            endpoint, token, since=None, entities=None
        )
        if status != 200:
            errors.append(f"pull rejected (HTTP {status})")
        elif mode == "dry":
            notes.append("cloud reachable, credential accepted (no changes applied)")
        else:
            from apps.sync_engine.edge_inbox import apply_pulled_bundle

            user = _resolve_principal(school)
            if user is None:
                errors.append("pull skipped: no local principal to apply as")
            else:
                applied = apply_pulled_bundle(school, user, body, origin="cloud-pull")
                if not applied.get("ok"):
                    errors.append(f"pull verification failed: {applied.get('errors')}")
                else:
                    result["pulled"] = int(applied.get("received") or 0)
                    result["created"] += int(applied.get("created") or 0)
                    result["upserted"] += int(applied.get("upserted") or 0)
                    result["conflicts"] += int(applied.get("conflicts") or 0)
                    notes.append(
                        f"pulled {result['pulled']} (created {result['created']}, "
                        f"upserted {result['upserted']}, conflicts {result['conflicts']})"
                    )
    except Exception as exc:  # noqa: BLE001 — never crash the tenant page
        errors.append(f"pull failed: {exc}")

    result["ok"] = not errors
    result["error"] = "; ".join(errors)
    result["message"] = "; ".join(notes) or (
        "Sync complete" if result["ok"] else "Sync finished with errors"
    )

    EdgeSyncRun.record(
        school,
        mode=mode,
        ok=result["ok"],
        pushed=result["pushed"],
        pulled=result["pulled"],
        conflicts=result["conflicts"],
        created=result["created"],
        upserted=result["upserted"],
        message=result["message"],
        error=result["error"],
        started_at=started,
        finished_at=timezone.now(),
    )
    return result


__all__ = ["run_sync_cycle"]
