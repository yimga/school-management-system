"""Wave L2 — preflight check for ``CSP_ENFORCE=True``.

Flipping the Content-Security-Policy header from
``Content-Security-Policy-Report-Only`` to ``Content-Security-Policy``
changes "violations are reported" to "violations are blocked". On a
platform with even a handful of inline-script / inline-style leaks,
the flip will instantly break tenant pages — so the user-facing impact
of premature enforcement is severe.

This preflight asserts **config + wiring preconditions**. It does NOT
read CSP violation counts because the platform persists reports
log-only (see ``apps/security/csp_report_view.py``). For runtime
readiness, the operator runbook is:

  1. ``python manage.py verify_csp_readiness`` until exit 0
     (config preflight clean).
  2. Watch the warning log stream for ``csp_violation`` events over a
     N-day window proportional to traffic (Anthropic-style: 7+ days).
  3. If violation rate is acceptable (or all known leaks have been
     captured by ``CSP_EXTRA_*`` allowlists), set ``CSP_ENFORCE=1``.

Checks performed:

* **Middleware wired** — ``ContentSecurityPolicyMiddleware`` appears in
  ``settings.MIDDLEWARE`` chain.
* **Report endpoint configured** — ``CSP_REPORT_URI`` is non-empty and
  not the empty-string default that disables reporting.
* **Directive coverage** — the default policy contains the load-bearing
  directives (``default-src``, ``script-src``, ``object-src``,
  ``frame-ancestors``, ``base-uri``).
* **script-src hardening** — ``script-src`` does NOT contain
  ``'unsafe-inline'`` or ``'unsafe-eval'`` (these are the
  enforcement-time killers for XSS protection).
* **Known debt acknowledged** — ``style-src 'unsafe-inline'`` is
  surfaced as a known-debt warning, not a blocker. Removing it is
  tracked under the inline-style retirement docket and is not a CSP
  enforcement blocker (style-CSP buys far less defense than script-CSP).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from django.conf import settings


@dataclass
class CspReadinessReport:
    """Outcome of the CSP preflight check."""

    ready: bool = True
    middleware_wired: bool = False
    report_uri: str = ""
    directives_present: list[str] = field(default_factory=list)
    directives_missing: list[str] = field(default_factory=list)
    script_src_has_unsafe_inline: bool = False
    script_src_has_unsafe_eval: bool = False
    style_src_has_unsafe_inline: bool = False
    """Surfaced as a warning, not a blocker."""

    # Wave L-followup: runtime telemetry from cache-backed counters.
    # These are informational only — they don't influence ``ready`` /
    # ``issue_count`` because the cache backend may be unreachable, the
    # TTL may have expired, or the platform may not have served enough
    # traffic to accumulate signal. The operator interprets them
    # alongside the log stream.
    violations_last_hour: int = 0
    violations_last_24h: int = 0
    violations_by_directive_24h: dict[str, int] = field(default_factory=dict)

    def issue_count(self) -> int:
        return (
            (0 if self.middleware_wired else 1)
            + (0 if self.report_uri else 1)
            + len(self.directives_missing)
            + (1 if self.script_src_has_unsafe_inline else 0)
            + (1 if self.script_src_has_unsafe_eval else 0)
        )


# Load-bearing directives that MUST be present in the policy before
# enforcement is safe. Missing any one of these means the policy is
# effectively permissive in that dimension — flipping enforcement adds
# no protection but inherits the breakage cost.
REQUIRED_DIRECTIVES: tuple[str, ...] = (
    "default-src",
    "script-src",
    "object-src",
    "frame-ancestors",
    "base-uri",
)


def _middleware_wired() -> bool:
    """Return True if ContentSecurityPolicyMiddleware is in MIDDLEWARE."""
    chain = getattr(settings, "MIDDLEWARE", ()) or ()
    target = "apps.security.csp_middleware.ContentSecurityPolicyMiddleware"
    return target in chain


def _policy_directives() -> dict[str, Sequence[str]]:
    """Return the effective policy dict the middleware would emit today.

    Derives the base skeleton from ``csp_middleware._DEFAULT_DIRECTIVES`` — the
    single source of truth — so this preflight can NEVER drift from the policy the
    middleware actually ships (it previously hardcoded a parallel copy that modelled
    ``style-src`` WITH ``'unsafe-inline'`` while the middleware emitted strict
    ``'self'``, so the verifier reported on a policy that never shipped). Then merges
    the ``CSP_EXTRA_*`` settings, mirroring the middleware's assembly. The per-request
    nonce is intentionally omitted here (it is request-scoped, not a static property).
    """
    from apps.security.csp_middleware import _DEFAULT_DIRECTIVES

    base: dict[str, list[str]] = {
        k: list(v) for k, v in _DEFAULT_DIRECTIVES.items()
    }
    extras_map = {
        "script-src": "CSP_EXTRA_SCRIPT_SRC",
        "style-src": "CSP_EXTRA_STYLE_SRC",
        "img-src": "CSP_EXTRA_IMG_SRC",
        "connect-src": "CSP_EXTRA_CONNECT_SRC",
        "frame-ancestors": "CSP_EXTRA_FRAME_ANCESTORS",
    }
    for directive, setting_name in extras_map.items():
        extra = getattr(settings, setting_name, ()) or ()
        for token in extra:
            token_str = str(token).strip()
            if token_str and token_str not in base.setdefault(directive, []):
                base[directive].append(token_str)
    return base


def assess_csp_readiness() -> CspReadinessReport:
    """Run the full CSP preflight; never raises.

    Returns a structured report; callers (CLI / dashboard) decide how
    to format it and what exit code to use.
    """
    report = CspReadinessReport()
    report.middleware_wired = _middleware_wired()
    report.report_uri = (getattr(settings, "CSP_REPORT_URI", "") or "").strip()

    policy = _policy_directives()
    present = {name for name, sources in policy.items() if sources}
    report.directives_present = sorted(present)
    report.directives_missing = sorted(
        d for d in REQUIRED_DIRECTIVES if d not in present
    )

    script_src = policy.get("script-src", [])
    style_src = policy.get("style-src", [])
    report.script_src_has_unsafe_inline = "'unsafe-inline'" in script_src
    report.script_src_has_unsafe_eval = "'unsafe-eval'" in script_src
    report.style_src_has_unsafe_inline = "'unsafe-inline'" in style_src

    # Wave L-followup: pull cache-backed runtime counters. Reading is
    # best-effort — cache misses / backend offline return 0 and are
    # treated as "no signal" rather than "no violations".
    from apps.security.csp_violation_counter import (
        violations_by_directive_in_last_hours,
        violations_in_last_hours,
    )

    report.violations_last_hour = violations_in_last_hours(hours=1)
    report.violations_last_24h = violations_in_last_hours(hours=24)
    report.violations_by_directive_24h = violations_by_directive_in_last_hours(
        hours=24
    )

    report.ready = report.issue_count() == 0
    return report


__all__ = ["CspReadinessReport", "REQUIRED_DIRECTIVES", "assess_csp_readiness"]
