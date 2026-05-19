"""Deliver marketplace install/uninstall hook URLs (Linux pillar)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_HOOK_TIMEOUT_SECONDS = 8


def _post_hook(url: str, payload: dict[str, Any]) -> tuple[bool, str]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "RunMyCampus-Marketplace/1.0"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=_HOOK_TIMEOUT_SECONDS) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            if code and 200 <= int(code) < 300:
                return True, ""
            return False, f"http_{code}"
    except URLError as exc:
        return False, str(exc.reason)[:200]
    except (TimeoutError, OSError, ValueError) as exc:
        return False, str(exc)[:200]


def dispatch_install_hooks(
    installation: Any,
    app: Any,
    phase: str,
    hooks: list[Any],
    *,
    actor=None,
) -> None:
    """
    Record + asynchronously deliver install/upgrade/uninstall hook URLs.

    Failures are logged per hook; never propagate to the install transaction.
    """
    from apps.marketplace.lifecycle import _record_hooks

    _record_hooks(installation, app, phase, hooks)
    if not hooks:
        return

    try:
        from apps.marketplace.tasks import deliver_install_hooks_task

        deliver_install_hooks_task.delay(
            str(installation.pk),
            phase,
            [str(h).strip() for h in hooks if str(h).strip()],
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "install_hook_delivery: celery unavailable, running inline hooks phase=%s",
            phase,
            exc_info=True,
        )
        deliver_install_hooks_inline(installation, app, phase, hooks, actor=actor)


def deliver_install_hooks_inline(
    installation: Any,
    app: Any,
    phase: str,
    hooks: list[Any],
    *,
    actor=None,
) -> None:
    from apps.marketplace.models import AppAuditLog

    school = getattr(installation, "school", None)
    payload_base = {
        "phase": phase,
        "app_slug": getattr(app, "slug", ""),
        "installation_id": str(getattr(installation, "pk", "")),
        "school_id": str(getattr(school, "pk", "")) if school else "",
    }
    for raw_url in hooks:
        url = str(raw_url or "").strip()
        if not url.startswith("https://"):
            AppAuditLog.objects.create(
                school=school,
                app=app,
                installation=installation,
                action=f"marketplace.hook.{phase}.skipped",
                payload={"url": url, "reason": "https_required"},
                actor=actor,
            )
            continue
        ok, err = _post_hook(url, {**payload_base, "hook_url": url})
        AppAuditLog.objects.create(
            school=school,
            app=app,
            installation=installation,
            action=f"marketplace.hook.{phase}.{'delivered' if ok else 'failed'}",
            payload={"url": url, "error": err},
            actor=actor,
        )


__all__ = ["dispatch_install_hooks", "deliver_install_hooks_inline"]
