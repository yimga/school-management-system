"""
Phase 7: Gradebook/Evals runtime — resolve grading and publish config from request.tenant_runtime.
Use these instead of SiteSettings or school.settings for pass_mark, scale, workflow.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Typed exceptions for pass_mark parsing (Decimal(str(val))).
_EVALS_GRADEBOOK_PASS_MARK_PARSE_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    InvalidOperation,
)


def get_gradebook_config(runtime: Any) -> Dict[str, Any]:
    """Return runtime.modules.gradebook or empty dict."""
    if runtime is None:
        return {}
    modules = getattr(runtime, "modules", None)
    if modules is None:
        return {}
    return getattr(modules, "gradebook", None) or {}


def get_pass_mark(runtime: Any, default: Optional[Decimal] = None) -> Decimal:
    """Pass mark from runtime.modules.gradebook; default typically 10.00 or 50."""
    cfg = get_gradebook_config(runtime)
    val = cfg.get("pass_mark")
    if val is not None:
        try:
            return Decimal(str(val))
        except _EVALS_GRADEBOOK_PASS_MARK_PARSE_ERRORS as e:
            logger.debug("evals.runtime_gradebook: pass_mark parse failed, using default: %s", e)
    if default is not None:
        return default
    return Decimal("10.00")


def get_grading_family(runtime: Any) -> Optional[str]:
    """Grading scale family from policy/registry."""
    cfg = get_gradebook_config(runtime)
    return cfg.get("grading_family")


def get_publish_workflow(runtime: Any) -> Optional[Dict[str, Any]]:
    """Grade publication/approval workflow from runtime."""
    cfg = get_gradebook_config(runtime)
    return cfg.get("publish_workflow")
