"""Wave L2 — preflight before flipping ``CSP_ENFORCE=True``.

Wraps :func:`apps.security.csp_readiness.assess_csp_readiness` with
operator-friendly output and exit semantics suitable for CI / cron.

Usage:

    # Quick check (exit 0/1 based on readiness):
    python manage.py verify_csp_readiness

    # Suppress per-row output:
    python manage.py verify_csp_readiness --quiet

The preflight only checks **config + wiring** preconditions, not
runtime violation rates (reports are log-only — see
``apps/security/csp_report_view.py``). Operators must still watch the
warning log stream for ``csp_violation`` events for an
ops-appropriate observation window before flipping.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Preflight check before flipping CSP_ENFORCE=True. "
        "Verifies middleware wiring, report URI, required directive "
        "coverage, and that script-src lacks unsafe-inline / unsafe-eval."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet", action="store_true",
            help="Suppress per-row output; rely on exit code (0=ready, 1=not).",
        )

    def handle(self, *args, **opts):
        from apps.security.csp_readiness import assess_csp_readiness

        quiet = bool(opts.get("quiet"))
        report = assess_csp_readiness()

        if not quiet:
            self._render(report)

        if not report.ready:
            raise SystemExit(1)

    def _render(self, report) -> None:  # noqa: ANN001 — CspReadinessReport
        self.stdout.write("=== CSP enforcement readiness preflight ===")
        self.stdout.write(
            f"Middleware wired:        {'YES' if report.middleware_wired else 'NO'}"
        )
        self.stdout.write(
            f"Report URI configured:   {report.report_uri or '(blank)'}"
        )
        self.stdout.write(
            "Directives present:      " + ", ".join(report.directives_present)
        )
        self.stdout.write("")

        # Blockers
        any_blocker = False
        if not report.middleware_wired:
            self.stdout.write(self.style.ERROR(
                "!!  Middleware not wired. Add "
                "'apps.security.csp_middleware.ContentSecurityPolicyMiddleware' "
                "to settings.MIDDLEWARE."
            ))
            any_blocker = True
        if not report.report_uri:
            self.stdout.write(self.style.ERROR(
                "!!  CSP_REPORT_URI is empty. Set the env var so violations "
                "are reported before enforcement begins."
            ))
            any_blocker = True
        if report.directives_missing:
            self.stdout.write(self.style.ERROR(
                "!!  Required directives missing: "
                + ", ".join(report.directives_missing)
            ))
            any_blocker = True
        if report.script_src_has_unsafe_inline:
            self.stdout.write(self.style.ERROR(
                "!!  script-src contains 'unsafe-inline' — enforcement gives "
                "no XSS protection. Remove inline scripts before flipping."
            ))
            any_blocker = True
        if report.script_src_has_unsafe_eval:
            self.stdout.write(self.style.ERROR(
                "!!  script-src contains 'unsafe-eval' — enforcement allows "
                "string-eval injection. Audit and remove."
            ))
            any_blocker = True

        # Known-debt warnings (not blockers)
        if report.style_src_has_unsafe_inline:
            self.stdout.write(self.style.WARNING(
                "..  style-src contains 'unsafe-inline' (known debt — see "
                "scan_inline_style_off_token CI gate). Style-CSP buys less "
                "defense than script-CSP; not a blocker."
            ))

        self.stdout.write("")
        if report.ready:
            self.stdout.write(self.style.SUCCESS(
                "READY — config preflight clean.\n"
                "Next: monitor 'csp_violation' warning logs for an "
                "ops-appropriate window (7+ days for production) before "
                "setting CSP_ENFORCE=1."
            ))
        else:
            n = report.issue_count()
            self.stdout.write(self.style.WARNING(
                f"NOT READY — {n} blocker(s) above must be resolved first."
            ))
        # Touch the variable so linters don't complain about unused.
        del any_blocker
