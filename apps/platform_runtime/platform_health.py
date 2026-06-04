"""Platform Health — connective tissue between the accountability registries
and the runtime assist dock (v4.01.x, 2026-06-03).

Aggregates two independent signals into one operator-facing health view:

* **Broken feature-gap proofs** — ``shipped`` rows in
  ``apps.schools.feature_gap_register.FEATURE_REGISTER`` whose declared proof
  does NOT resolve right now. Resolved *in-request* because ``reverse()`` and
  ``apps.get_model()`` are cheap and side-effect-free. A route proof counts as
  resolved if it resolves on ANY of the platform urlconfs (matching the
  feature-gap regression test's intent), so a route only mounted on the manager
  host is not falsely "broken" when checked from a tenant host.

* **Over-SLA backlog items** — items in the cached backlog-unlock snapshot
  flagged ``sla_waiting_breached`` / ``sla_ready_attention_breached``. Read from
  the Django cache ONLY (``snapshot_cache_key``); this module NEVER calls
  ``evaluate_all()`` because that shells out to scripts/pytest and must not run
  in a web request. When no snapshot is cached the backlog signal is empty +
  ``snapshot_available=False``.

Everything here is defensive: a missing cache, an unimportable model, or a
malformed snapshot yields an empty/zeroed result, never an exception. This
mirrors the assist-dock context processor's "never break the page" contract.

See ``docs/PLATFORM_HEALTH_CONNECTIVE_TISSUE_2026_06_03.md``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Severity levels — reused for both the summary and the dock badge pill.
LEVEL_CRITICAL = "critical"
LEVEL_WARNING = "warning"
LEVEL_SUCCESS = "success"

# Workflow key for the one-click re-check. Intentionally NOT registered in the
# curated ``workflow_registry.WORKFLOWS`` seed (which has its own count audit);
# ``begin_run`` degrades gracefully to a title-cased label for unknown keys.
RECHECK_WORKFLOW_KEY = "platform_health_recheck"

# urlconfs a route proof may live on. A proof is "resolved" if it reverses on
# any of them — the same multi-urlconf semantics the feature-gap test uses.
_PROOF_URLCONFS: tuple[str, ...] = (
    "config.urls",
    "config.manager_urls",
    "config.tenant_urls",
)


@dataclass(frozen=True)
class BrokenProof:
    """One shipped feature whose proof does not currently resolve."""

    feature_slug: str
    label: str
    capability_domain: str
    proof_kind: str          # "route" | "model"
    proof_ref: str           # the route name or "app_label.Model"
    error: str
    public_promise: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacklogBreach:
    """One backlog item currently over its waiting / ready_attention SLA."""

    item_id: str
    title: str
    category: str
    column: str              # "waiting" | "ready_attention"
    days_in_column: int
    max_days: int
    doc_href: str = ""
    action_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _reverse_on_any_urlconf(route_name: str) -> str | None:
    """Return the resolved path if ``route_name`` reverses on any platform
    urlconf, else ``None``. Never raises."""

    from django.urls import NoReverseMatch, reverse

    # Try the request's active urlconf first (None = current), then each named
    # urlconf. The first success wins.
    candidates: tuple[Any, ...] = (None, *_PROOF_URLCONFS)
    for uc in candidates:
        try:
            return reverse(route_name, urlconf=uc)
        except NoReverseMatch:
            continue
        except Exception:  # noqa: BLE001 — a broken urlconf import must not crash health
            logger.debug("platform_health: urlconf %s failed for %s", uc, route_name, exc_info=True)
            continue
    return None


def feature_gap_broken_proofs() -> list[BrokenProof]:
    """Return shipped feature rows whose route/model proof does not resolve.

    Only route + model proofs are checkable in-request; rows whose only proof is
    a management command or CI gate are not route-resolvable here and are treated
    as not-broken (the feature-gap pytest covers those). Pure + cheap; never
    raises.
    """

    out: list[BrokenProof] = []
    try:
        from apps.schools.feature_gap_register import iter_features
    except Exception:  # noqa: BLE001
        logger.debug("platform_health: feature register import failed", exc_info=True)
        return out

    try:
        from django.apps import apps as django_apps
    except Exception:  # noqa: BLE001
        return out

    for f in iter_features():
        if getattr(f, "status", "") != "shipped":
            continue
        route_name = getattr(f, "proof_route_name", "") or ""
        model_ref = getattr(f, "proof_model", "") or ""

        if route_name:
            if _reverse_on_any_urlconf(route_name) is None:
                out.append(
                    BrokenProof(
                        feature_slug=f.feature_slug,
                        label=str(f.label),
                        capability_domain=f.capability_domain,
                        proof_kind="route",
                        proof_ref=route_name,
                        error=f"Route '{route_name}' does not reverse on any platform urlconf.",
                        public_promise=bool(getattr(f, "public_promise", False)),
                    )
                )
            continue

        if model_ref:
            broken_error = ""
            try:
                app_label, model_name = model_ref.split(".", 1)
                django_apps.get_model(app_label, model_name)
            except (LookupError, ValueError) as exc:
                broken_error = str(exc)
            except Exception as exc:  # noqa: BLE001
                broken_error = str(exc)
            if broken_error:
                out.append(
                    BrokenProof(
                        feature_slug=f.feature_slug,
                        label=str(f.label),
                        capability_domain=f.capability_domain,
                        proof_kind="model",
                        proof_ref=model_ref,
                        error=broken_error,
                        public_promise=bool(getattr(f, "public_promise", False)),
                    )
                )
            continue

        # command / ci_gate / none — not route-resolvable in-request; skip.

    return out


def _load_backlog_snapshot() -> dict[str, Any] | None:
    """Return the cached backlog-unlock snapshot dict, or ``None`` if absent /
    malformed. Cache-only — NEVER evaluates live."""

    try:
        from django.core.cache import cache

        from apps.platform_runtime.backlog_unlock_engine import (
            PROFILE_FULL,
            snapshot_cache_key,
        )
    except Exception:  # noqa: BLE001
        return None

    raw = cache.get(snapshot_cache_key(PROFILE_FULL))
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def backlog_sla_breaches() -> tuple[list[BacklogBreach], bool]:
    """Return ``(breaches, snapshot_available)`` from the cached backlog snapshot.

    ``snapshot_available`` is ``False`` when no evaluation has been cached yet
    (so the caller can say "run evaluate_backlog_unlocks --update-cache" rather
    than implying a clean bill of health). Cache-only; never raises.
    """

    snapshot = _load_backlog_snapshot()
    if snapshot is None:
        return [], False

    out: list[BacklogBreach] = []
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict):
            continue
        waiting_breached = bool(item.get("sla_waiting_breached"))
        attention_breached = bool(item.get("sla_ready_attention_breached"))
        if not (waiting_breached or attention_breached):
            continue
        if waiting_breached:
            column = "waiting"
            days = item.get("days_in_waiting")
            max_days = item.get("sla_waiting_max_days")
        else:
            column = "ready_attention"
            days = item.get("days_in_ready_attention")
            max_days = item.get("sla_ready_attention_max_days")
        out.append(
            BacklogBreach(
                item_id=str(item.get("id", "")),
                title=str(item.get("title", item.get("id", ""))),
                category=str(item.get("category", "")),
                column=column,
                days_in_column=int(days) if isinstance(days, (int, float)) else 0,
                max_days=int(max_days) if isinstance(max_days, (int, float)) else 0,
                doc_href=str(item.get("doc_href", "")),
                action_hint=str(item.get("action_hint", "")),
            )
        )
    return out, True


# The badge resolver runs on every assist-dock poll / SSE tick (every 2-5s per
# staff tab). The summary is platform-wide (not per-user/tenant), so a single
# short-TTL cache entry keeps that hot path off the ~45-feature × reverse() scan
# every tick — important given the free-tier SSE thread-budget. The center page
# and tests use the uncached path (use_cache=False) for fresh, deterministic data.
_SUMMARY_CACHE_KEY = "platform_health:summary:v1"
_SUMMARY_CACHE_TTL_SECONDS = 45


def bust_summary_cache() -> None:
    """Drop the cached summary so the next badge poll recomputes immediately.

    Called after a one-click re-check so the operator sees the change reflected
    without waiting out the TTL. Best-effort; never raises.
    """
    try:
        from django.core.cache import cache

        cache.delete(_SUMMARY_CACHE_KEY)
    except Exception:  # noqa: BLE001
        logger.debug("platform_health: summary cache bust failed", exc_info=True)


def platform_health_summary(use_cache: bool = False) -> dict[str, Any]:
    """Aggregate both signals into a dock/badge-friendly summary.

    Shape::

        {
          "feature_gap_broken": <int>,
          "backlog_breaches": <int>,
          "count": <int>,                # total problems
          "level": "critical|warning|success",
          "backlog_snapshot_available": <bool>,
        }

    Severity: any broken shipped proof => critical (a promise is broken); else
    any SLA breach => warning; else success.

    ``use_cache=True`` (the badge hot path) serves a short-TTL cached copy; the
    default (center page / tests) always computes fresh.
    """

    if use_cache:
        try:
            from django.core.cache import cache

            cached = cache.get(_SUMMARY_CACHE_KEY)
            if isinstance(cached, dict):
                return cached
        except Exception:  # noqa: BLE001
            logger.debug("platform_health: summary cache read failed", exc_info=True)

    broken = feature_gap_broken_proofs()
    breaches, snapshot_available = backlog_sla_breaches()
    feature_gap_broken = len(broken)
    backlog_breaches = len(breaches)
    count = feature_gap_broken + backlog_breaches

    if feature_gap_broken > 0:
        level = LEVEL_CRITICAL
    elif backlog_breaches > 0:
        level = LEVEL_WARNING
    else:
        level = LEVEL_SUCCESS

    result = {
        "feature_gap_broken": feature_gap_broken,
        "backlog_breaches": backlog_breaches,
        "count": count,
        "level": level,
        "backlog_snapshot_available": snapshot_available,
    }

    if use_cache:
        try:
            from django.core.cache import cache

            cache.set(_SUMMARY_CACHE_KEY, result, _SUMMARY_CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.debug("platform_health: summary cache write failed", exc_info=True)

    return result


__all__ = [
    "LEVEL_CRITICAL",
    "LEVEL_WARNING",
    "LEVEL_SUCCESS",
    "RECHECK_WORKFLOW_KEY",
    "BrokenProof",
    "BacklogBreach",
    "feature_gap_broken_proofs",
    "backlog_sla_breaches",
    "platform_health_summary",
    "bust_summary_cache",
]
