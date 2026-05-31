"""Universal LMS connector dispatcher.

v4.00.91 Studio-OS-10X W1 Pillar B11. Provides a single ``call(provider, op, **kwargs)``
entry that routes to the correct ``lms_connector_*`` module based on the SOT
registry in :mod:`apps.integrations_marketplace.lms_supported_providers`.

The dispatcher is intentionally thin — it does NOT add audit, retry, or
secret-handling logic. Those concerns belong in the per-provider modules so
the live-path helpers (``oauth_live_path_helpers``) and the audit SOT model
(``LMSDiagActionAudit``) stay in one place. The dispatcher only:

  * resolves provider slug -> module via the registry
  * normalises the op name (snake_case, case-insensitive)
  * raises ``UnknownLMSProviderError`` / ``UnsupportedLMSOperationError``
    with structured details so callers can surface a clean 400/501.

Supported ops (every OAUTH_READY+ provider should implement these):

  * ``exchange_authorization_code_for_token``   (state, code) -> result dict
  * ``refresh_access_token``                    (refresh_token) -> result dict
  * ``push_grade_live``                         (target_class, target_user, value) -> result dict
  * ``mint_oauth_state``                        (next_url) -> str
  * ``read_oauth_state``                        (state) -> (reason, payload)

If a SCAFFOLD-tier provider is asked for a live op, the dispatcher returns a
structured ``{"status": "scaffold_only", ...}`` instead of raising. That lets the
operator UI render the maturity pill without crashing.
"""

from __future__ import annotations

import importlib
from typing import Any

from apps.integrations_marketplace.lms_supported_providers import (
    OAUTH_READY_LMS_PROVIDERS,
    PRODUCTION_LMS_PROVIDERS,
    SCAFFOLD_LMS_PROVIDERS,
)

SUPPORTED_OPS: tuple[str, ...] = (
    "exchange_authorization_code_for_token",
    "refresh_access_token",
    "push_grade_live",
    "pull_courses",
    "mint_oauth_state",
    "read_oauth_state",
)

# Provider slug -> module dotted path. Registered only for providers whose
# adapter modules actually exist; callers asking for an unregistered slug get
# UnknownLMSProviderError even if the slug appears in the lifecycle registry.
_MODULE_MAP: dict[str, str] = {
    "canvas": "apps.api.lms_adapters",
    "moodle": "apps.api.lms_adapters",
    "google_classroom": "apps.api.lms_adapters",
    "google": "apps.api.lms_adapters",
    "schoology": "apps.integrations_marketplace.lms_connector_schoology",
    "d2l_brightspace": "apps.integrations_marketplace.lms_connector_d2l",
    "blackboard": "apps.integrations_marketplace.lms_connector_blackboard",
    "powerschool": "apps.integrations_marketplace.lms_connector_powerschool",
    "sakai": "apps.integrations_marketplace.lms_connector_sakai",
    "itslearning": "apps.integrations_marketplace.lms_connector_itslearning",
    # v4.00.91 Studio-OS-10X W1 Pillar B8-B10 — 3 new scaffold connectors.
    "ms_teams_edu": "apps.integrations_marketplace.lms_connector_ms_teams_edu",
    "clever": "apps.integrations_marketplace.lms_connector_clever",
    "classlink": "apps.integrations_marketplace.lms_connector_classlink",
}


class UnknownLMSProviderError(LookupError):
    """Raised when ``provider`` is not in the SOT registry."""


class UnsupportedLMSOperationError(LookupError):
    """Raised when ``op`` is not in :data:`SUPPORTED_OPS`."""


def _normalise_provider(provider: str) -> str:
    return str(provider or "").strip().lower().replace("-", "_")


def _normalise_op(op: str) -> str:
    return str(op or "").strip().lower()


def maturity_tier(provider: str) -> str:
    """Return ``production`` / ``oauth_ready`` / ``scaffold`` / ``unknown``."""
    slug = _normalise_provider(provider)
    if slug in PRODUCTION_LMS_PROVIDERS:
        return "production"
    if slug in OAUTH_READY_LMS_PROVIDERS:
        return "oauth_ready"
    if slug in SCAFFOLD_LMS_PROVIDERS:
        return "scaffold"
    return "unknown"


def _resolve_module(provider: str):
    slug = _normalise_provider(provider)
    if slug not in _MODULE_MAP:
        raise UnknownLMSProviderError({
            "provider": slug,
            "supported": sorted(_MODULE_MAP.keys()),
        })
    return importlib.import_module(_MODULE_MAP[slug]), slug


def call(provider: str, op: str, **kwargs: Any) -> dict[str, Any]:
    """Dispatch a single op to a provider module.

    Returns the underlying call's return value (typically a dict).
    Raises ``UnsupportedLMSOperationError`` for unsupported ops.
    Returns ``{"status": "scaffold_only", "tier": ...}`` for SCAFFOLD-tier
    providers asked for live ops (``exchange_*``, ``refresh_*``,
    ``push_grade_live``, ``pull_courses``).

    Every live call is tracked through the Workflow Progress Bus so operators
    see real-time progress + AI-suggested remediation when an integration
    fails. Tracking is best-effort and never breaks dispatch on failure.
    """
    op_norm = _normalise_op(op)
    if op_norm not in SUPPORTED_OPS:
        raise UnsupportedLMSOperationError({
            "op": op_norm,
            "supported": list(SUPPORTED_OPS),
        })
    module, slug = _resolve_module(provider)
    tier = maturity_tier(slug)
    if tier == "scaffold" and op_norm in (
        "exchange_authorization_code_for_token",
        "refresh_access_token",
        "push_grade_live",
        "pull_courses",
    ):
        return {
            "status": "scaffold_only",
            "provider": slug,
            "op": op_norm,
            "tier": tier,
            "reason": "provider_not_yet_oauth_ready",
        }
    fn = getattr(module, op_norm, None)
    if fn is None:
        raise UnsupportedLMSOperationError({
            "op": op_norm,
            "provider": slug,
            "tier": tier,
            "reason": f"module {module.__name__} has no attribute {op_norm}",
        })

    run = None
    try:
        from apps.platform_runtime.workflow_tracker import (
            begin_run,
            finalize_run,
            heartbeat,
        )

        run = begin_run(
            workflow_key=f"lms_{op_norm}",
            steps=("dispatch", "upstream", "respond"),
            expected_duration_seconds=30,
            payload={"provider": slug, "op": op_norm, "tier": tier},
        )
    except Exception:
        run = None

    try:
        result = fn(**kwargs)
    except Exception as exc:
        if run is not None:
            try:
                finalize_run(run, status="failed", error=exc)
            except Exception:
                pass
        raise
    if run is not None:
        try:
            heartbeat(run)
            finalize_run(run, status="succeeded")
        except Exception:
            pass
    return result


def list_providers() -> list[dict[str, str]]:
    """Operator UI helper — flat list of providers with maturity tier."""
    return [
        {"slug": slug, "tier": maturity_tier(slug), "module": dotted}
        for slug, dotted in sorted(_MODULE_MAP.items())
    ]
