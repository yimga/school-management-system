"""Validate a sovereign / offline edge deployment's configuration before go-live.

Catches the footguns that silently break a self-hosted mini-PC box — chiefly the
plain-HTTP-over-LAN secure-cookie trap (login 302s then bounces) and the
SINGLE_TENANT vs schema-mode mismatch (the bare-hostname fallback is inert under
django-tenants). Advisory by default; ``--strict`` turns any FAIL into a non-zero
exit so it can gate an automated bring-up.

    python manage.py check_edge_readiness
    python manage.py check_edge_readiness --strict
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"


def _truthy(value) -> bool:
    return str(value if value is not None else "").strip().lower() in {"1", "true", "yes", "on"}


class Command(BaseCommand):
    help = "Check a sovereign/offline edge deployment's settings for common misconfigurations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if any FAIL-level finding is present.",
        )

    def handle(self, *args, **options):
        findings: list[tuple[str, str]] = []

        debug = bool(getattr(settings, "DEBUG", False))
        single_tenant = _truthy(getattr(settings, "SINGLE_TENANT", False))
        use_django_tenants = bool(getattr(settings, "USE_DJANGO_TENANTS", False))
        secret = getattr(settings, "SECRET_KEY", "") or ""
        allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])

        # --- Secret / hosts (hard requirements at DEBUG=0) -------------------
        if not secret or secret.strip().lower() in {"", "change-me-to-a-long-random-string"} or len(secret) < 32:
            findings.append((FAIL, "SECRET_KEY is unset, a placeholder, or too short (<32 chars)."))
        else:
            findings.append((OK, "SECRET_KEY is set."))

        if not debug and not allowed_hosts:
            findings.append((FAIL, "ALLOWED_HOSTS is empty at DEBUG=0 — every request will 400."))
        elif not debug:
            findings.append((OK, f"ALLOWED_HOSTS has {len(allowed_hosts)} entr(y/ies)."))

        # --- Single-tenant / tenancy coherence ------------------------------
        if single_tenant and use_django_tenants:
            findings.append((
                WARN,
                "SINGLE_TENANT=True but USE_DJANGO_TENANTS=True: the bare-hostname "
                "fallback only works in shared/RLS mode. Set USE_DJANGO_TENANTS=0 for a "
                "bare-host single-school box, or reach the school via its subdomain.",
            ))
        elif single_tenant:
            findings.append((OK, "SINGLE_TENANT + shared mode: bare-hostname resolution active."))
            # Confirm exactly one active school (tolerant of an unmigrated/unavailable DB).
            try:
                from apps.schools.models import School

                count = School.objects.filter(is_active=True).count()
                if count == 0:
                    findings.append((WARN, "SINGLE_TENANT is on but no active school exists yet — provision one."))
                elif count == 1:
                    findings.append((OK, "Exactly one active school — bare-hostname will resolve to it."))
                else:
                    findings.append((FAIL, f"SINGLE_TENANT is on but {count} active schools exist — resolution is ambiguous (returns none)."))
            except Exception as exc:  # noqa: BLE001 — DB may be pre-migration during bring-up
                findings.append((WARN, f"Could not count active schools (DB not ready?): {exc}"))

        # --- Plain-HTTP-over-LAN secure-cookie trap -------------------------
        ssl_redirect = bool(getattr(settings, "SECURE_SSL_REDIRECT", False))
        session_secure = bool(getattr(settings, "SESSION_COOKIE_SECURE", False))
        csrf_secure = bool(getattr(settings, "CSRF_COOKIE_SECURE", False))
        hsts = int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0)
        secure_on = ssl_redirect or session_secure or csrf_secure or hsts > 0
        if not debug and secure_on:
            findings.append((
                WARN,
                "HTTPS-only hardening is ON (SECURE_SSL_REDIRECT=%s, SESSION_COOKIE_SECURE=%s, "
                "CSRF_COOKIE_SECURE=%s, HSTS=%ss). If this box is served over PLAIN HTTP on a LAN, "
                "login will silently fail — set all four to 0. If it is behind a TLS proxy, this is correct."
                % (ssl_redirect, session_secure, csrf_secure, hsts),
            ))
        elif not debug:
            findings.append((OK, "Secure-cookie/redirect hardening is off — correct for plain-HTTP LAN serving."))

        # --- AI posture -----------------------------------------------------
        profile = str(getattr(settings, "RMC_DEPLOYMENT_PROFILE", "") or "").strip().lower()
        if profile == "edge":
            findings.append((OK, "RMC_DEPLOYMENT_PROFILE=edge — AI routed to local Ollama, then rules."))
        elif profile in {"online", "hybrid"}:
            findings.append((WARN, f"RMC_DEPLOYMENT_PROFILE={profile!r}: AI prefers the CLOUD gateway — set 'edge' for an offline box."))

        # --- Email deliverability -------------------------------------------
        email_backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")
        if "smtp" in email_backend.lower():
            if not (getattr(settings, "EMAIL_HOST_USER", "") and getattr(settings, "EMAIL_HOST_PASSWORD", "")):
                findings.append((WARN, "EMAIL_BACKEND is SMTP but host credentials are empty — mail will NOT deliver."))
            else:
                findings.append((OK, "SMTP email configured with credentials."))
        else:
            findings.append((OK, "Email uses a non-SMTP backend (console/locmem) — offline-safe, delivers nothing."))

        # --- Report ---------------------------------------------------------
        styles = {OK: self.style.SUCCESS, WARN: self.style.WARNING, FAIL: self.style.ERROR}
        for level, msg in findings:
            self.stdout.write(f"[{styles[level](level)}] {msg}")

        n_fail = sum(1 for lvl, _ in findings if lvl == FAIL)
        n_warn = sum(1 for lvl, _ in findings if lvl == WARN)
        summary = f"Edge readiness: {n_fail} FAIL, {n_warn} WARN, {len(findings) - n_fail - n_warn} OK."
        if n_fail:
            self.stdout.write(self.style.ERROR(summary))
            if options.get("strict"):
                raise CommandError(f"{n_fail} blocking issue(s) — not ready for go-live.")
        elif n_warn:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary + " Ready."))
