"""
Cross-border compliance gate — data sovereignty / border-lock enforcement.

Two surfaces live here:

* ``cross_border_export_blocked`` — the soft *(blocked, message)* predicate the
  UI calls to grey-out an export button. Backward compatible; unchanged shape.

* ``enforce_region_match`` / ``enforce_cross_border_export`` — the *hard* gate.
  When ``settings.DATA_RESIDENCY_ENFORCE`` is on, a cross-region PII access
  (a region-A tenant resolving to a region-B store, or an export to a foreign
  region) is **raised** as a typed :class:`ResidencyViolation` (a
  ``PermissionDenied`` subclass) and audited — it is no longer merely
  soft-logged. When the flag is off these functions are a no-op (return),
  preserving the pre-hardening default behaviour.

HONEST SCOPE NOTE
-----------------
This enforces residency at the **application data layer**: it refuses to *serve*
a request that would read/write a tenant's PII from a store outside that
tenant's regulatory ``data_region``. It does **not**, by itself, provide true
physical multi-region storage — separate per-region Postgres replicas (and the
``DATABASES`` aliases they back) remain an ops / deploy item. Until those
replicas are provisioned, this layer is the binding control: it fails closed
rather than silently letting cross-border data movement happen.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class ResidencyViolation(PermissionDenied):
    """Raised when a cross-region PII access is attempted under strict residency.

    Subclasses :class:`~django.core.exceptions.PermissionDenied` so it surfaces
    as an HTTP 403 (not a 500) and is caught by any existing
    ``PermissionDenied`` handling, while remaining a typed marker callers can
    catch specifically.
    """

    def __init__(
        self,
        message: str,
        *,
        source_region: str | None = None,
        target_region: str | None = None,
    ) -> None:
        super().__init__(message)
        self.source_region = source_region
        self.target_region = target_region


def residency_enforced() -> bool:
    """Whether strict data-residency enforcement is active.

    Honours both the env var (so an ops flip needs no redeploy) and the Django
    setting (so ``@override_settings(DATA_RESIDENCY_ENFORCE=True)`` works in
    tests). Either being truthy turns enforcement on.
    """
    env = os.environ.get("DATA_RESIDENCY_ENFORCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    return env or bool(getattr(settings, "DATA_RESIDENCY_ENFORCE", False))


def strict_unknown_regions() -> bool:
    """Whether unknown source/target regions BLOCK instead of silently passing.

    The default (off) keeps the backward-compatible posture: paths with no
    region concept — single-region deployments, un-pinned requests — proceed.
    Strict-sovereignty deployments flip this so a resolution failure can never
    become a silent cross-border pass. Same env-or-setting contract as
    :func:`residency_enforced`; only consulted when enforcement is on.
    """
    raw = os.environ.get("DATA_RESIDENCY_STRICT_UNKNOWN", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    explicit = getattr(settings, "DATA_RESIDENCY_STRICT_UNKNOWN", None)
    if explicit is not None:
        return bool(explicit)
    # B-validated closeout (2026-07-03): unset now FOLLOWS enforcement —
    # enforcing residency while silently passing an unresolvable region was
    # fail-open for the exact case this control exists for. Single-region
    # deployments that enforce cross-region matching but cannot resolve a
    # region on every path opt out EXPLICITLY (DATA_RESIDENCY_STRICT_UNKNOWN=0).
    return residency_enforced()


def _norm(region: Any) -> str:
    return str(region or "").strip().lower()


def _audit_residency_violation(
    *,
    source_region: str,
    target_region: str,
    school: Any,
    kind: str,
) -> None:
    """Record the blocked cross-region attempt.

    The data layer cannot assume a writable DB in the *correct* region is
    available at the moment we block (that's the whole point of failing
    closed), so the durable record is a structured ERROR log line — the same
    audit channel ``apps.schools.data_residency.assert_aligned_or_log`` already
    writes to. A best-effort :class:`AuditLog` row is *also* attempted so the
    event lands in the compliance trail when a usable DB is present, but its
    failure never masks the block.
    """
    school_slug = getattr(school, "slug", None) or getattr(school, "pk", "?")
    logger.error(
        "residency.violation kind=%s school=%s source_region=%s target_region=%s "
        "(blocked under DATA_RESIDENCY_ENFORCE)",
        kind,
        school_slug,
        source_region,
        target_region,
    )
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=AuditLog.Action.ACCESS_DENIED,
            model_name="DataResidency",
            object_id=str(school_slug),
            object_repr=f"residency:{kind}",
            sensitivity=AuditLog.Sensitivity.CRITICAL,
            app_label="compliance",
            reason=(
                f"cross-region {kind} blocked: source={source_region} "
                f"target={target_region}"
            )[:255],
        )
    except Exception:  # noqa: BLE001 — audit write must never mask the block
        logger.debug(
            "residency.violation: AuditLog row write failed (block still enforced)",
            exc_info=True,
        )


def enforce_region_match(
    school: Any,
    target_region: str | None,
    *,
    kind: str = "access",
) -> None:
    """Hard residency gate: block a region-A tenant touching a region-B store.

    ``school`` is the tenant whose regulatory region is authoritative;
    ``target_region`` is the region the request is actually being served
    from / routed to (e.g. the resolved DB alias's region, or an export
    destination). When strict enforcement is on and the two regions disagree,
    raise :class:`ResidencyViolation` (audited). No-op when:

    * enforcement is off (the flag is unset — the backward-compatible default);
    * there is no school;
    * ``target_region`` is empty and :func:`strict_unknown_regions` is off
      (nothing to compare against — but strict-sovereignty deployments flip
      ``DATA_RESIDENCY_STRICT_UNKNOWN`` so an unknown target BLOCKS instead);
    * the source region cannot be resolved and strict-unknown is off (note:
      ``effective_region`` never returns blank — it defaults to ``"global"``
      — so this arm is only reachable when resolution *raises* and the raw
      ``data_region`` field is also empty);
    * the regions match.
    """
    if school is None:
        return
    if not residency_enforced():
        return

    strict_unknown = strict_unknown_regions()
    target = _norm(target_region)

    try:
        from apps.schools.data_residency import effective_region

        source = _norm(effective_region(school))
    except Exception:  # noqa: BLE001 — never crash resolution; fall back to field
        source = _norm(getattr(school, "data_region", None))

    if not target:
        if strict_unknown:
            _audit_residency_violation(
                source_region=source or "unknown",
                target_region="unknown",
                school=school,
                kind=kind,
            )
            raise ResidencyViolation(
                f"Data residency: unknown target region for {kind} under "
                "strict-unknown enforcement. Cross-border operation blocked.",
                source_region=source or "unknown",
                target_region="unknown",
            )
        return
    if not source:
        if strict_unknown:
            _audit_residency_violation(
                source_region="unknown",
                target_region=target,
                school=school,
                kind=kind,
            )
            raise ResidencyViolation(
                f"Data residency: unknown tenant region for {kind} under "
                "strict-unknown enforcement. Cross-border operation blocked.",
                source_region="unknown",
                target_region=target,
            )
        return
    if source == target:
        return

    _audit_residency_violation(
        source_region=source,
        target_region=target,
        school=school,
        kind=kind,
    )
    raise ResidencyViolation(
        f"Data residency: tenant region={source!r} may not be served from "
        f"region={target!r}. Cross-border {kind} blocked.",
        source_region=source,
        target_region=target,
    )


def cross_border_export_blocked(
    school: Any,
    *,
    destination_region: str | None = None,
) -> tuple[bool, str]:
    """
    Return (blocked, message). Soft by default; strict when DATA_RESIDENCY_ENFORCE=1.

    This is the predicate used to grey-out export UI. It mirrors the strict
    gate's decision without raising, so callers that prefer a boolean (the
    download button) and callers that prefer fail-closed enforcement
    (:func:`enforce_cross_border_export`) agree.
    """
    if school is None:
        return False, ""
    if not residency_enforced():
        return False, ""

    # Mirror the enforcer's resolution (effective_region defaults "global")
    # so the UI predicate and the fail-closed gate can never disagree.
    try:
        from apps.schools.data_residency import effective_region as _eff

        school_region = _norm(_eff(school))
    except Exception:  # noqa: BLE001 — never crash the predicate; fall back to field
        school_region = _norm(getattr(school, "data_region", None))
    dest = _norm(destination_region)

    if not dest or not school_region:
        if strict_unknown_regions():
            missing = "destination" if not dest else "source"
            return (
                True,
                f"Export blocked: {missing} region unknown under strict "
                "residency enforcement. Resolve the region or explicitly set "
                "DATA_RESIDENCY_STRICT_UNKNOWN=0.",
            )
        return False, ""

    if school_region == dest:
        return False, ""

    return (
        True,
        f"Export blocked: school data_region={school_region!r} does not match "
        f"active region={dest!r}. Adjust residency or use in-region operator session.",
    )


def enforce_cross_border_export(
    school: Any,
    *,
    destination_region: str | None = None,
) -> None:
    """Fail-closed twin of :func:`cross_border_export_blocked`.

    Raises :class:`ResidencyViolation` (audited) when a cross-border export is
    attempted under strict enforcement. No-op when the flag is off. Call this
    on the actual export code path; call :func:`cross_border_export_blocked`
    to decide whether to render the button.
    """
    enforce_region_match(school, destination_region, kind="export")
