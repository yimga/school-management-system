"""PDP runtime enforcement helpers — Move 3 follow-up.

Two surfaces:

  - `pdp_advisory(action, resource_kind, ...)` — view decorator that calls the
    PDP at request time, **never blocks**, and writes a `PolicyDecisionLog`
    row so we can see what *would* have happened. This is the safe-path opt-in
    used while the rule library is being built out.

  - `pdp_enforce(action, resource_kind, ...)` — same wiring but raises
    `PermissionDenied` on `deny`/`implicit_deny`. Use this once the rules
    for a path are complete and reviewed.

The site-wide mode is controlled by ``settings.POLICY_PDP_ENFORCEMENT_MODE``
which can be one of:
  - ``"advisory"`` (default) — every decorated view runs PDP in advisory mode
    regardless of which decorator is applied. Safe for production rollout.
  - ``"enforce"`` — `pdp_enforce` decorators block; `pdp_advisory` still logs.
  - ``"off"`` — both decorators short-circuit (no PDP call, no log).

This means production can deploy with `advisory`, collect a week of
`PolicyDecisionLog` rows, find the rules that would have caused legitimate
denials, fix them, then flip the flag to `enforce`.
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
    }


def _school_from_request(request):
    return getattr(request, "school", None)


def _resource_from_request(request, resource_kind: str, kwargs, *, rebac_permission: str = ""):
    resource = {"entity": resource_kind, "id": kwargs.get("pk") or ""}
    if rebac_permission:
        resource["permission_code"] = rebac_permission
    return resource


def pdp_advisory(*, action: str, resource_kind: str, rebac_permission: str = ""):
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
                    decide(
                        _subject_from_request(request),
                        action,
                        _resource_from_request(
                            request,
                            resource_kind,
                            kwargs,
                            rebac_permission=rebac_permission,
                        ),
                        school=_school_from_request(request),
                        log=True,
                    )
                except Exception as exc:
                    logger.warning("pdp_advisory failed (%s): %s", action, exc)
            return view_fn(request, *args, **kwargs)

        return wrapped

    return decorator


def pdp_enforce(*, action: str, resource_kind: str, rebac_permission: str = ""):
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
                d = decide(
                    _subject_from_request(request),
                    action,
                    _resource_from_request(
                        request,
                        resource_kind,
                        kwargs,
                        rebac_permission=rebac_permission,
                    ),
                    school=_school_from_request(request),
                    log=True,
                )
            except Exception as exc:
                logger.warning("pdp_enforce failed soft (%s): %s", action, exc)
                return view_fn(request, *args, **kwargs)
            if mode == "enforce" and not d.allowed:
                raise PermissionDenied(d.reason)
            return view_fn(request, *args, **kwargs)

        return wrapped

    return decorator
