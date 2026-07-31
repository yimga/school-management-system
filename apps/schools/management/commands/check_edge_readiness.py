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

import os
import shutil

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

        # --- Email deliverability + offline queue ---------------------------
        email_backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")
        is_smtp = "smtp" in email_backend.lower()
        try:
            from apps.schoolops.email_delivery import _offline_email_queue_enabled

            offline_email = _offline_email_queue_enabled()
        except Exception:  # noqa: BLE001 — import guard; never break readiness
            offline_email = profile == "edge"
        if is_smtp:
            if not (getattr(settings, "EMAIL_HOST_USER", "") and getattr(settings, "EMAIL_HOST_PASSWORD", "")):
                findings.append((WARN, "EMAIL_BACKEND is SMTP but host credentials are empty — mail will NOT deliver."))
            else:
                findings.append((OK, "SMTP email configured with credentials."))
        elif offline_email:
            findings.append((OK, "Non-SMTP backend + offline email queue ON — mail parks durably and forwards via `drain_edge_outbox` on reconnect (nothing dropped)."))
        else:
            findings.append((
                WARN,
                "Non-SMTP backend AND the offline email queue is OFF — outbound mail is "
                "silently DROPPED (the console backend reports a false success). Set "
                "RMC_EMAIL_OFFLINE_QUEUE=1 (or RMC_DEPLOYMENT_PROFILE=edge) so it parks + forwards.",
            ))

        # --- SMS / WhatsApp outbound queue ----------------------------------
        if _truthy(getattr(settings, "RMC_AUTO_ENQUEUE_OUTBOUND", "1")):
            findings.append((OK, "SMS/WhatsApp auto-enqueue-on-failure is ON — a send that can't reach its provider queues durably (OutboundMessageQueue) instead of being lost."))
        else:
            findings.append((WARN, "RMC_AUTO_ENQUEUE_OUTBOUND is OFF — a failed SMS/WhatsApp send is LOST rather than queued. Set it to 1 for an offline box."))

        # --- Broker-less background drain -----------------------------------
        # No broker => NO beat/worker, so every periodic job is dead unless a cron
        # revives the in-process registry.
        if not str(getattr(settings, "CELERY_BROKER_URL", "") or "").strip():
            findings.append((
                WARN,
                "No CELERY_BROKER_URL — there is NO beat/worker, so every periodic job is "
                "dead: the email + SMS/WhatsApp queue drainers, the events outbox that fires "
                "internal subscribers, reminders, monitors. Schedule `python manage.py "
                "run_periodic_jobs` on cron (e.g. */5) — it runs the WHOLE registry beat-less, "
                "each job at its own cadence, with per-job locking. (`drain_edge_outbox` "
                "forwards only email + SMS/WhatsApp — a subset, and it misses the events outbox.)",
            ))
        else:
            findings.append((OK, "A Celery broker is configured — the periodic jobs run under beat/worker."))

        # --- OCR (offline FOSS = Tesseract) ---------------------------------
        ocr_cmd = str(getattr(settings, "MARKSHEET_OCR_COMMAND", "") or "").strip() or "tesseract"
        ocr_binary = shutil.which(ocr_cmd)
        if ocr_binary:
            findings.append((OK, f"Tesseract OCR binary present ({ocr_binary}) — marksheet/receipt OCR works offline (no cloud Vision needed)."))
        else:
            findings.append((
                WARN,
                f"Tesseract binary '{ocr_cmd}' is not on PATH — marksheet/receipt OCR will be "
                "unavailable (it degrades to manual entry, never a crash). Install Tesseract only "
                "if this school uses OCR; keep the finance receipt method at 'pattern'/'ocr_tesseract' "
                "(a cloud OCR method fails offline).",
            ))

        # --- Audit signing + at-rest encryption (offline via local keys) ----
        signing_backend = str(getattr(settings, "MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND", "") or "local-env-key").strip().lower()
        cloud_signing = {"aws-kms", "azure-keyvault", "gcp-kms", "hashicorp-vault"}
        if signing_backend in cloud_signing:
            findings.append((
                WARN,
                f"MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND={signing_backend!r} is a network-bound "
                "HSM/Vault backend and will fail on an offline box. Use 'local-env-key' (the default).",
            ))
        elif getattr(settings, "MIGRATION_CLOUD_AUDIT_SIGNING_KEY", ""):
            findings.append((OK, "Audit signing uses the offline local-env-key backend with a signing key set."))
        else:
            findings.append((WARN, "Audit signing is local-env-key but MIGRATION_CLOUD_AUDIT_SIGNING_KEY is unset — audit events are recorded UNSIGNED. Set a key for tamper-evidence."))

        crypto_source = str(getattr(settings, "DJANGO_CRYPTOGRAPHY_KEYS_SOURCE", "env") or "env").strip().lower()
        crypto_keys = getattr(settings, "DJANGO_CRYPTOGRAPHY_KEYS", None) or getattr(settings, "DJANGO_CRYPTOGRAPHY_KEY", None) or os.environ.get("DJANGO_CRYPTOGRAPHY_KEY")
        if crypto_source == "vault":
            findings.append((WARN, "DJANGO_CRYPTOGRAPHY_KEYS_SOURCE=vault is network-bound and fails offline — use the default env key source on the box."))
        elif crypto_keys:
            findings.append((OK, "At-rest field-encryption key (Fernet) is set and offline."))
        else:
            findings.append((WARN, "No explicit DJANGO_CRYPTOGRAPHY_KEY(S) — at-rest field encryption derives a key from SECRET_KEY (works, but set an explicit key so a SECRET_KEY rotation can't strand encrypted data)."))

        # --- Payment collection (webhook-settled; offline = fail-closed) ----
        if _truthy(getattr(settings, "RMC_GATEWAY_COLLECTION_ENABLED", False)):
            findings.append((
                WARN,
                "RMC_GATEWAY_COLLECTION_ENABLED is ON: outbound card / mobile-money collection needs "
                "the internet and FAILS CLOSED offline (the charge intent is not queued). Record offline "
                "payments as OfflinePaymentIntent and let the inbound signed webhook settle them online.",
            ))
        else:
            findings.append((OK, "Outbound payment collection is off — capture offline cash/manual payments (OfflinePaymentIntent); they reconcile when the box is online."))

        # --- Media durability -----------------------------------------------
        storages = getattr(settings, "STORAGES", {}) or {}
        media_backend = str(
            (storages.get("default") or {}).get("BACKEND", "")
            or getattr(settings, "DEFAULT_FILE_STORAGE", "")
        )
        if "s3" in media_backend.lower() or "minio" in media_backend.lower():
            findings.append((OK, f"Media uses an object-storage backend ({media_backend.rsplit('.', 1)[-1]}) — durable across redeploys and off-box."))
        else:
            findings.append((
                WARN,
                "Media is on the LOCAL filesystem (MEDIA_ROOT). Uploads — student/teacher "
                "photos, evaluation evidence, logos, receipts — are WIPED on redeploy unless "
                "MEDIA_ROOT sits on a persistent volume. The self-host compose now mounts a "
                "`mediadata` volume (a bind mount you back up off-box is safer); there is no "
                "off-box media backup unless you add one. For scale set MEDIA_STORAGE_BACKEND=s3 "
                "(self-hosted MinIO / Cloudflare R2).",
            ))

        # --- Local AI (Ollama) endpoint (edge profile) ----------------------
        if profile == "edge":
            ollama = str(
                getattr(settings, "OLLAMA_ENDPOINT", "")
                or os.environ.get("OLLAMA_ENDPOINT", "")
            ).strip()
            if ollama:
                findings.append((OK, f"OLLAMA_ENDPOINT set ({ollama}) — run `ollama serve` + pull a model; if it's down, AI degrades to deterministic rules (no crash)."))
            else:
                findings.append((WARN, "RMC_DEPLOYMENT_PROFILE=edge but OLLAMA_ENDPOINT is unset — AI will use deterministic rules only (no local LLM)."))

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
