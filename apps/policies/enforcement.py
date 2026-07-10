"""PDP runtime enforcement helpers — Move 3 follow-up; promoted to ENFORCE 2026-07-09.

Two decorators:

  - `pdp_advisory(action, resource_kind, ...)` — view decorator that calls the
    PDP at request time, **never blocks**, and writes a `PolicyDecisionLog`
    row so we can see what *would* have happened. This is the safe-path opt-in
    used while the rule library for a new surface is being built out.

  - `pdp_enforce(action, resource_kind, ...)` — same wiring but raises
    `PermissionDenied` on `deny`/`implicit_deny`. Use this once the rules
    for a path are complete and reviewed.

The site-wide mode is controlled by ``settings.POLICY_PDP_ENFORCEMENT_MODE``
which can be one of:
  - ``"enforce"`` (the deployed default since the 2026-07-09 promotion) —
    `pdp_enforce` decorators block; `pdp_advisory` still logs. Safe because
    every enforced surface ships a platform-baseline PolicyRule (policies
    migration 0010) that allows exactly the population the surface's own
    canonical RBAC gate admits — see *parity probes* below. Rollback:
    ``POLICY_PDP_ENFORCEMENT_MODE=advisory``.
  - ``"advisory"`` — every decorated view runs PDP in advisory mode
    regardless of which decorator is applied (log-only rollback posture).
  - ``"off"`` — both decorators short-circuit (no PDP call, no log).

Parity probes
-------------
An enforced surface passes ``parity_probe=<callable(request) -> bool>`` — its
OWN canonical RBAC gate. The verdict lands in the PDP subject as
``subject.rbac_allowed`` and the seeded baseline allow-rules condition on it,
so enforcement starts at exact parity with the access the surface grants
today. From that floor the PDP can only *narrow*: tenant/operator deny rules
(default priority 100, i.e. ahead of the priority-500 baselines) actually
bind, and deactivating a baseline rule fail-closes its surface. A probe error
computes ``False`` — fail closed, never open. When no probe is given but a
``rebac_permission`` is declared, the canonical union resolver
(``apps.accounts.effective_access.permission_access``) is used instead.

Placement: enforce guards must sit INNERMOST on the view stack (below
``@login_required`` / ``@require_school`` / the coarse RBAC gates) so
anonymous users still get the login redirect and PDP rules only ever see
requests the coarse gates already admitted.
"""

from __future__ import annotations

import functools
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied

from apps.policies.pdp import decide

logger = logging.getLogger(__name__)


def _mode() -> str:
    raw = getattr(settings, "POLICY_PDP_ENFORCEMENT_MODE", "advisory")
    if raw not in ("advisory", "enforce", "off"):
        return "advisory"
    return raw


def _subject_from_request(request) -> dict:
    user = getattr(request, "user", None)
    return {
        "user_id": getattr(user, "pk", None),
        "role": (getattr(user, "role", "") or "").upper(),
        "school_id": str(getattr(getattr(request, "school", None), "pk", "") or ""),
        # Threads the god-mode fast path (pdp._subject_is_superuser) so the PDP
        # doesn't re-query the user row on every decision.
        "is_superuser": bool(getattr(user, "is_superuser", False)),
    }


def _school_from_request(request):
    return getattr(request, "school", None)


def _resource_from_request(request, resource_kind: str, kwargs, *, rebac_permission: str = ""):
    resource = {"entity": resource_kind, "id": kwargs.get("pk") or ""}
    if rebac_permission:
        resource["permission_code"] = rebac_permission
    return resource


def _parity_allowed(request, *, parity_probe, rebac_permission: str) -> bool:
    """Compute ``subject.rbac_allowed`` — the surface's own gate verdict.

    Fails CLOSED: any probe/resolver error computes False, so a broken gate can
    never widen access through the PDP (a superuser still passes via god-mode).
    """
    try:
        if parity_probe is not None:
            return bool(parity_probe(request))
        if rebac_permission:
            from apps.accounts.effective_access import permission_access

            return bool(
                permission_access(
                    getattr(request, "user", None),
                    getattr(request, "school", None),
                    (rebac_permission,),
                )
            )
    except Exception:
        logger.warning(
            "pdp parity probe failed — computing rbac_allowed=False (fail closed)",
            exc_info=True,
        )
    return False


def _decide_for_request(
    request,
    *,
    action: str,
    resource_kind: str,
    rebac_permission: str,
    parity_probe,
    kwargs,
):
    subject = _subject_from_request(request)
    subject["rbac_allowed"] = _parity_allowed(
        request, parity_probe=parity_probe, rebac_permission=rebac_permission
    )
    return decide(
        subject,
        action,
        _resource_from_request(
            request, resource_kind, kwargs, rebac_permission=rebac_permission
        ),
        school=_school_from_request(request),
        log=True,
    )


def pdp_advisory(
    *, action: str, resource_kind: str, rebac_permission: str = "", parity_probe=None
):
    """Run the PDP in advisory mode — log only, never block.

    Usage::

        @pdp_advisory(action="read", resource_kind="student")
        def student_detail_view(request, pk): ...
    """

    def decorator(view_fn):
        @functools.wraps(view_fn)
        def wrapped(request, *args, **kwargs):
            mode = _mode()
            if mode != "off":
                try:
                    _decide_for_request(
                        request,
                        action=action,
                        resource_kind=resource_kind,
                        rebac_permission=rebac_permission,
                        parity_probe=parity_probe,
                        kwargs=kwargs,
                    )
                except Exception as exc:
                    logger.warning("pdp_advisory failed (%s): %s", action, exc)
            return view_fn(request, *args, **kwargs)

        return wrapped

    return decorator


def pdp_enforce(
    *, action: str, resource_kind: str, rebac_permission: str = "", parity_probe=None
):
    """Same as ``pdp_advisory`` but blocks on deny when mode is ``"enforce"``.

    Falls back to advisory behavior when mode is ``"advisory"`` so flipping is
    a single config change.
    """

    def decorator(view_fn):
        @functools.wraps(view_fn)
        def wrapped(request, *args, **kwargs):
            mode = _mode()
            if mode == "off":
                return view_fn(request, *args, **kwargs)
            try:
                d = _decide_for_request(
                    request,
                    action=action,
                    resource_kind=resource_kind,
                    rebac_permission=rebac_permission,
                    parity_probe=parity_probe,
                    kwargs=kwargs,
                )
            except Exception as exc:
                # Fail CLOSED in enforce mode: a PDP error (DB loss, bad rule,
                # import failure) must NOT silently permit access. Advisory/off
                # modes never block, so they degrade open as designed.
                if mode == "enforce":
                    logger.error(
                        "pdp_enforce decision failed (%s) — denying", action,
                        exc_info=True,
                    )
                    raise PermissionDenied("Policy decision unavailable") from exc
                logger.warning("pdp_enforce failed soft (%s): %s", action, exc)
                return view_fn(request, *args, **kwargs)
            if mode == "enforce" and not d.allowed:
                raise PermissionDenied(d.reason)
            return view_fn(request, *args, **kwargs)

        return wrapped

    return decorator
