"""Test the platform email infrastructure end-to-end (v4.00.98 Phase 1).

Usage:

    python manage.py test_email_health                              # probe + dry-run audit
    python manage.py test_email_health --send-to operator@example.com  # actually send a test email
    python manage.py test_email_health --send-to operator@example.com --bulk  # exercise send_bulk path

Output is structured and stable so this can also be the CI smoke target.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Audit + (optionally) live-test the platform email infrastructure."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--send-to",
            type=str,
            default="",
            help="Recipient email address. When set, an actual send_transactional() call fires.",
        )
        parser.add_argument(
            "--bulk",
            action="store_true",
            help="Use send_bulk() instead of send_transactional() (only with --send-to).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit a single JSON envelope instead of human-readable lines (CI mode).",
        )
        parser.add_argument(
            "--fail-on-degraded",
            action="store_true",
            help="Exit 1 if the SMTP probe or send returns ok=False.",
        )

    def handle(self, *args, **options) -> None:
        from apps.schoolops.email_delivery import (
            get_recent_delivery_stats,
            get_recent_failures,
            get_resolved_smtp_config,
            send_bulk,
            send_transactional,
            smtp_probe,
        )

        json_mode = bool(options.get("json"))
        recipient = (options.get("send_to") or "").strip()
        use_bulk = bool(options.get("bulk"))
        fail_on_degraded = bool(options.get("fail_on_degraded"))

        backend = getattr(settings, "EMAIL_BACKEND", "") or ""
        debug = bool(getattr(settings, "DEBUG", False))
        envelope: dict = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": "v4.00.98 Phase 1",
            "backend": backend,
            "debug": debug,
            "default_from": getattr(settings, "DEFAULT_FROM_EMAIL", ""),
        }

        # 1) Resolve config
        try:
            cfg = get_resolved_smtp_config()
            envelope["resolved_config"] = {
                "host": cfg.get("host") or "",
                "port": cfg.get("port") or 0,
                "use_tls": bool(cfg.get("use_tls")),
                "source": cfg.get("source") or "env",
                # Never print secrets — only whether they are present.
                "host_user_set": bool(cfg.get("host_user")),
                "host_password_set": bool(cfg.get("host_password")),
                "from_header_visible": cfg.get("from_email")
                or cfg.get("default_from_email")
                or "",
            }
        except Exception as exc:
            cfg = {}
            envelope["resolved_config_error"] = f"{type(exc).__name__}: {exc}"

        # 1b) Deliverability diagnosis — the part that pinpoints "no email arrived".
        envelope["diagnosis"] = self._diagnose_deliverability(
            backend, debug, cfg, send_requested=bool(recipient)
        )

        # 2) SMTP probe
        try:
            probe = smtp_probe()
            envelope["smtp_probe"] = probe
        except Exception as exc:
            envelope["smtp_probe"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        # 3) Recent delivery stats
        try:
            envelope["recent_stats_24h"] = get_recent_delivery_stats(window_hours=24)
        except Exception as exc:
            envelope["recent_stats_24h_error"] = f"{type(exc).__name__}: {exc}"

        # 4) Recent failures
        try:
            envelope["recent_failures"] = get_recent_failures(limit=5)
        except Exception as exc:
            envelope["recent_failures_error"] = f"{type(exc).__name__}: {exc}"

        # 5) Optional live send
        if recipient:
            subject = "[RunMyCampus] Email infrastructure live test"
            body = (
                "This is a platform-generated test message.\n\n"
                "If you are reading this, the reliability layer is wired up correctly:\n"
                "  * EMAIL_BACKEND resolved\n"
                "  * SMTP host reachable (or console backend active)\n"
                "  * send_transactional() returned ok=True\n"
                "  * An EmailDeliveryEvent row was written for audit\n\n"
                f"Generated at: {envelope['generated_at']}\n"
            )
            html_body = (
                '<div style="font-family:system-ui,sans-serif;color:#111">'
                '<h2 style="margin:0 0 .5rem">RunMyCampus email infrastructure test</h2>'
                '<p style="margin:0 0 .5rem">If you received this, the reliability layer is healthy.</p>'
                "<ul>"
                "<li>EMAIL_BACKEND resolved</li>"
                "<li>SMTP host reachable (or console backend active)</li>"
                "<li>send_transactional() returned ok=True</li>"
                "<li>An EmailDeliveryEvent row was written for audit</li>"
                "</ul>"
                f"<p>Generated at: {envelope['generated_at']}</p>"
                "</div>"
            )
            try:
                if use_bulk:
                    result = send_bulk(
                        subject=subject,
                        body=body,
                        recipients=[recipient],
                        html_body=html_body,
                        priority="transactional",
                        idempotency_key=f"email_health_test_bulk_{envelope['generated_at']}",
                    )
                else:
                    result = send_transactional(
                        subject=subject,
                        body=body,
                        to=recipient,
                        html_body=html_body,
                        priority="transactional",
                        idempotency_key=f"email_health_test_{envelope['generated_at']}",
                    )
                envelope["send_result"] = result
            except Exception as exc:
                envelope["send_result"] = {
                    "ok": False,
                    "error_kind": "uncaught_exception",
                    "error_repr": f"{type(exc).__name__}: {exc}",
                }

        # 6) Health verdict (used by --fail-on-degraded)
        probe_ok = bool(envelope.get("smtp_probe", {}).get("ok", False))
        send_ok = (
            envelope.get("send_result", {}).get("ok", True)
            if "send_result" in envelope
            else True
        )
        # A "critical" diagnosis means mail cannot actually be delivered even when
        # the SMTP probe lies "ok" (console backend short-circuits the probe).
        has_critical = any(
            d.get("severity") == "critical" for d in envelope.get("diagnosis", [])
        )
        envelope["verdict"] = {
            "ok": probe_ok and send_ok and not has_critical,
            "probe_ok": probe_ok,
            "send_ok": send_ok,
            "deliverable": not has_critical,
        }

        if json_mode:
            self.stdout.write(json.dumps(envelope, indent=2, default=str))
        else:
            self._render_human(envelope)

        if fail_on_degraded and not envelope["verdict"]["ok"]:
            sys.exit(1)

    def _diagnose_deliverability(
        self, backend: str, debug: bool, cfg: dict, send_requested: bool = False
    ) -> list:
        """Return ordered {severity, code, message} findings explaining why mail
        may not be delivered. ``critical`` = mail definitely will not arrive.

        This is the heart of the "I never got the activation email" diagnosis.
        """
        findings: list = []
        b = (backend or "").lower()
        is_devnull_backend = (
            "console" in b or "locmem" in b or "dummy" in b or not b
        )

        if is_devnull_backend:
            # A non-SMTP backend is critical when (a) we're in production
            # (DEBUG=False) OR (b) the operator explicitly asked for a live send
            # via --send-to: in both cases real mail will NOT arrive, so the
            # verdict must not read HEALTHY.
            sev = "critical" if (not debug or send_requested) else "info"
            findings.append(
                {
                    "severity": sev,
                    "code": "non_smtp_backend",
                    "message": (
                        f"EMAIL_BACKEND is '{backend or '(unset -> console default)'}' - "
                        "messages are NOT transmitted over SMTP."
                        + (
                            " Real emails (e.g. tenant activation) will NOT arrive. "
                            "Set EMAIL_BACKEND="
                            "django.core.mail.backends.smtp.EmailBackend and the "
                            "EMAIL_HOST/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD env vars."
                            if (not debug or send_requested)
                            else " This is expected in local dev (DEBUG=True)."
                        )
                    ),
                }
            )
            # In a dev-null backend the credential checks below are moot.
            return findings

        # Real SMTP backend — check it can actually authenticate.
        if not cfg:
            return findings
        source = cfg.get("source") or "env"
        if not cfg.get("host"):
            findings.append(
                {
                    "severity": "critical",
                    "code": "no_smtp_host",
                    "message": "SMTP backend selected but EMAIL_HOST is empty.",
                }
            )
        if not cfg.get("host_user"):
            findings.append(
                {
                    "severity": "warning",
                    "code": "no_smtp_user",
                    "message": (
                        "EMAIL_HOST_USER is empty. Most providers (Gmail/Yahoo/"
                        "SES) require authentication; sends will be rejected."
                    ),
                }
            )
        if not cfg.get("host_password"):
            # Password empty can mean: never set, OR set-but-failed-to-decrypt.
            extra = ""
            if source in ("site_settings_override", "tenant_school_settings"):
                extra = (
                    " The config source is an operator/tenant override whose "
                    "password is Fernet-encrypted - an empty value here usually "
                    "means the encryption key (DJANGO_CRYPTOGRAPHY_KEYS) is "
                    "missing or wrong, so the stored password could not be "
                    "decrypted."
                )
            findings.append(
                {
                    "severity": "critical",
                    "code": "no_smtp_password",
                    "message": (
                        "EMAIL_HOST_PASSWORD resolved to empty - SMTP auth will "
                        "fail." + extra
                    ),
                }
            )

        # If an encrypted override is in play, verify the Fernet key is usable.
        if source in ("site_settings_override", "tenant_school_settings"):
            try:
                from apps.accounts.legacy_hashes.encryption import _get_fernet

                _get_fernet()
                fernet_ok = True
            except Exception as exc:  # noqa: BLE001 - report, never raise
                fernet_ok = False
                findings.append(
                    {
                        "severity": "critical",
                        "code": "fernet_unavailable",
                        "message": (
                            "Encrypted SMTP override is configured but the "
                            f"encryption key is unavailable ({type(exc).__name__}). "
                            "Set DJANGO_CRYPTOGRAPHY_KEYS so the password can be "
                            "decrypted."
                        ),
                    }
                )
            if fernet_ok:
                findings.append(
                    {
                        "severity": "info",
                        "code": "fernet_ok",
                        "message": "Encryption key present; encrypted overrides can be decrypted.",
                    }
                )

        if not findings:
            findings.append(
                {
                    "severity": "info",
                    "code": "smtp_configured",
                    "message": f"SMTP backend configured (source={source}); credentials present.",
                }
            )
        return findings

    def _render_human(self, env: dict) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("Email infrastructure audit"))
        self.stdout.write(f"  generated_at      = {env.get('generated_at')}")
        self.stdout.write(f"  EMAIL_BACKEND     = {env.get('backend') or '(unset -> console)'}")
        self.stdout.write(f"  DEBUG             = {env.get('debug')}")
        self.stdout.write(f"  DEFAULT_FROM      = {env.get('default_from') or '(unset)'}")
        cfg = env.get("resolved_config", {})
        if cfg:
            self.stdout.write(
                f"  resolved SMTP     = host={cfg.get('host') or '(none)'} "
                f"port={cfg.get('port')} tls={cfg.get('use_tls')} "
                f"source={cfg.get('source')} "
                f"user_set={cfg.get('host_user_set')} pass_set={cfg.get('host_password_set')}"
            )
        diagnosis = env.get("diagnosis", [])
        if diagnosis:
            self.stdout.write("  diagnosis         :")
            for d in diagnosis:
                sev = d.get("severity", "info")
                styler = {
                    "critical": self.style.ERROR,
                    "warning": self.style.WARNING,
                }.get(sev, self.style.SUCCESS)
                self.stdout.write(
                    f"    - [{styler(sev.upper())}] {d.get('code')}: {d.get('message')}"
                )
        probe = env.get("smtp_probe", {})
        if probe:
            mark = self.style.SUCCESS("OK") if probe.get("ok") else self.style.ERROR("FAIL")
            self.stdout.write(
                f"  smtp_probe        = [{mark}] latency={probe.get('latency_ms')}ms "
                f"backend={probe.get('backend')} error={probe.get('error')}"
            )
        stats = env.get("recent_stats_24h", {})
        if stats:
            self.stdout.write(
                "  last 24h          = "
                f"sent={stats.get('sent_count', 0)} "
                f"failed={stats.get('failed_count', 0)} "
                f"last_failure_kind={stats.get('last_failure_reason_kind') or '(none)'}"
            )
        failures = env.get("recent_failures", [])
        if failures:
            self.stdout.write("  recent failures   :")
            for failure in failures[:5]:
                self.stdout.write(
                    f"    - kind={failure.get('error_kind')} at={failure.get('created_at')}"
                )
        send_result = env.get("send_result")
        if send_result is not None:
            mark = self.style.SUCCESS("OK") if send_result.get("ok") else self.style.ERROR("FAIL")
            self.stdout.write(
                f"  test send_result  = [{mark}] "
                f"attempts={send_result.get('attempts')} "
                f"delivery_event_id={send_result.get('delivery_event_id')} "
                f"queued={send_result.get('queued')} "
                f"bounced={send_result.get('bounced')} "
                f"error_kind={send_result.get('error_kind')}"
            )
        verdict = env.get("verdict", {})
        mark = self.style.SUCCESS("HEALTHY") if verdict.get("ok") else self.style.WARNING("DEGRADED")
        self.stdout.write(f"  verdict           = [{mark}]")
