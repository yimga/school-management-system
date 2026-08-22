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

from apps.siteconfig.deploy_meta import UNKNOWN, resolve_deploy_commit_sha

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"


def _truthy(value) -> bool:
    return str(value if value is not None else "").strip().lower() in {"1", "true", "yes", "on"}


def _fernet_key_defects(raw) -> list[str]:
    """Name every configured key that cannot actually build a Fernet.

    Presence is not usability. A 20-char key on a live box satisfied every
    ``if key:`` test in the codebase while ``Fernet(key)`` raised ValueError,
    because nothing ever tried to construct one at boot.

    Returns a list of human-readable defects — lengths and exception types
    only. Key material is NEVER included in the result.
    """
    entries = raw if isinstance(raw, (list, tuple)) else [raw]
    defects: list[str] = []
    for index, entry in enumerate(entries):
        if isinstance(entry, bytes):
            entry = entry.decode("ascii", "replace")
        candidate = str(entry or "").strip()
        if not candidate:
            continue
        try:
            from cryptography.fernet import Fernet  # local: optional dependency
            Fernet(candidate.encode("ascii"))
        except Exception as exc:  # noqa: BLE001 - any failure means unusable
            defects.append(
                f"key #{index + 1} is {len(candidate)} chars (want 44): {type(exc).__name__}"
            )
    return defects


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

        # --- LAN hostname reachability (the .school.lan / base-domain trap) --
        # A stable LAN name like <slug>.school.lan only works if ALLOWED_HOSTS
        # accepts it. The default ALLOWED_HOSTS covers `.local`, NOT `.lan`; the
        # `.school.lan` wildcard is only injected when MULTI_TENANT_BASE_DOMAIN is
        # set (config/settings.py). So an unset base domain silently 400s every
        # `.school.lan` request. See docs/EDGE_LAN_HOSTNAME_DNS.md + the runbook's
        # configure_lan_hostname step.
        lowered_hosts = [str(h).strip().lower() for h in allowed_hosts]
        base_domain = (getattr(settings, "MULTI_TENANT_BASE_DOMAIN", "") or "").strip().lower()
        if not debug and allowed_hosts and "*" not in lowered_hosts:
            if not base_domain:
                findings.append((
                    WARN,
                    "MULTI_TENANT_BASE_DOMAIN is unset — ALLOWED_HOSTS covers only its exact "
                    "entries (the default adds .local, NOT .lan). A LAN hostname like "
                    "'<slug>.school.lan' will 400. Set MULTI_TENANT_BASE_DOMAIN=school.lan to "
                    "accept *.school.lan (or reach the box by IP: http://<box-ip>:<web-port>/).",
                ))
            else:
                dotted = f".{base_domain}"
                if base_domain in lowered_hosts or dotted in lowered_hosts:
                    findings.append((
                        OK,
                        f"ALLOWED_HOSTS covers *.{base_domain} — a LAN hostname like "
                        f"'<slug>.{base_domain}' is accepted. Reach the box over "
                        "http://<host>:<web-port>/ (plain HTTP; the box has no TLS).",
                    ))
                else:
                    findings.append((
                        WARN,
                        f"MULTI_TENANT_BASE_DOMAIN={base_domain} but ALLOWED_HOSTS has neither "
                        f"'{base_domain}' nor the wildcard '{dotted}' — a '{dotted}' hostname will "
                        f"400. Add '{dotted}' to ALLOWED_HOSTS.",
                    ))

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
            # The school resolving is only half of it. Until 2026-08-22 the URL layer
            # disagreed with the school layer: an IP-literal host got `config.urls`,
            # the DEVELOPER urlconf, which mounts no admin site (a 500 on
            # /authentication/backend/), cannot reverse the tenant admin (empty
            # sidebars), and DOES mount the /super/ control plane. Assert the two
            # layers now agree, because a box reached by IP is the normal case.
            try:
                from django.test import RequestFactory

                from apps.schools.middleware import UrlConfSwitcherMiddleware

                probe = RequestFactory().get("/", HTTP_HOST="10.0.0.1")
                UrlConfSwitcherMiddleware(lambda r: None).process_request(probe)
                if getattr(probe, "urlconf", "") == "config.tenant_urls":
                    findings.append((
                        OK,
                        "Bare-IP access routes to the tenant URL surface "
                        "(no control plane, tenant admin reversible).",
                    ))
                else:
                    findings.append((
                        FAIL,
                        "SINGLE_TENANT is on but a bare-IP host still routes to "
                        f"{getattr(probe, 'urlconf', '?')} — this box serves the operator "
                        "control plane to its school and 500s on /authentication/backend/.",
                    ))
            except Exception as exc:  # noqa: BLE001 — readiness must never crash
                findings.append((WARN, f"Could not probe host routing: {exc}"))
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
                "internal subscribers, the social cross-post drainer, the daily DR snapshot "
                "capture, reminders, monitors. Schedule `python manage.py run_periodic_jobs` "
                "on cron (e.g. */5) — it runs the WHOLE registry beat-less, each job at its own "
                "cadence, with per-job locking. (`drain_edge_outbox` forwards only email + "
                "SMS/WhatsApp — a subset that misses the events outbox AND the DR snapshot; "
                "run_periodic_jobs is the COMPLETE rail. The DR snapshot lands on this box's "
                "disk unless object storage is set, so still copy it off-box.)",
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
            # A key being PRESENT is not a key being USABLE, and this line used to
            # report OK for either. apps/accounts/legacy_hashes/encryption.py wraps
            # decrypt in try/except but NOT encrypt, so an unusable key reads clean
            # and 500s on write — a box can look healthy for months and then fail
            # the first time Migration Cloud imports a user with a legacy password.
            # Build the Fernet here so the boot check catches what boot-time silence
            # otherwise hides.
            _crypto_defects = _fernet_key_defects(crypto_keys)
            if _crypto_defects:
                findings.append((
                    FAIL,
                    "DJANGO_CRYPTOGRAPHY_KEY(S) is set but is NOT a usable Fernet key "
                    f"({'; '.join(_crypto_defects)}). Reads fall back to the raw stored "
                    "value, but EVERY non-empty write to an encrypted field — legacy "
                    "password hashes, social OAuth tokens — raises ValueError. Generate "
                    "a real one with: python -c \"from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())\" — and count existing "
                    "ciphertext before replacing a key that already encrypted data.",
                ))
            else:
                findings.append((OK, "At-rest field-encryption key (Fernet) is set, well-formed and offline."))
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

        # --- Build identity --------------------------------------------------
        # Can this box say what code it is running? `/-/version/` is the only way
        # an operator (or whoever they call for help) can answer that, and it
        # reported `commit_sha: unknown` on every self-hosted box until the image
        # started stamping itself. The same value drives post-deploy cache
        # busting, so while it is unknown a browser has nothing to notice a stale
        # shell by — it keeps serving the old one after every upgrade.
        commit_sha = resolve_deploy_commit_sha()
        if commit_sha != UNKNOWN:
            findings.append((
                OK,
                f"Build identity resolves ({commit_sha[:12]}) — /-/version/ can report what this box runs.",
            ))
        else:
            findings.append((
                WARN,
                "This box cannot say what code it is running — /-/version/ reports commit_sha=unknown, "
                "and post-deploy cache busting is inert (browsers cannot detect a stale shell). "
                "Rebuild the image so scripts/write_build_stamp.py can stamp it "
                "(`docker compose -f deploy/selfhost/docker-compose.yml build`), or set GIT_COMMIT "
                "in the environment if you deploy without Docker.",
            ))

        # --- TLS posture -----------------------------------------------------
        # A box without a certificate is not merely "less secure": the origin is not
        # a SECURE CONTEXT, so the browser withholds crypto.subtle and the offline
        # PIN vault can never seal. Every school that pressed "make this device
        # offline ready" on a plain-HTTP box got "Local access could not be enabled
        # on this browser", which blamed the browser for a property of the URL.
        # Readiness has to SAY that, because nothing else in the stack can.
        from apps.schools import edge_tls as _tls

        resolution = _tls.resolve_mode()
        if resolution.error:
            findings.append((
                FAIL,
                f"{_tls.ENV_MODE}={resolution.raw!r} is not a mode I recognise "
                f"({', '.join(_tls.TLS_MODES)}), so the box fell back to plain HTTP. "
                "A typo here hands a school HTTP while its runbook says HTTPS.",
            ))
        elif resolution.mode == _tls.MODE_OFF:
            findings.append((
                WARN,
                "TLS is off — the box serves plain HTTP. Login works, but the origin "
                "is not a secure context, so offline PIN / local mode CANNOT be "
                "enabled on any browser. `manage.py edge_tls --plan-to selfsigned` "
                "prints the way out; docs/EDGE_TLS_RUNBOOK.md explains the choices.",
            ))
        else:
            findings.append((
                OK,
                f"TLS mode is {resolution.mode} — the box serves a secure context, so "
                "offline PIN / local mode can enrol.",
            ))

        if resolution.mode in _tls.FILE_BACKED_MODES:
            cert_path, key_path, _ca = _tls.certificate_paths()
            dns_names, ip_addresses = _tls.san_candidates(allowed_hosts=allowed_hosts)
            cert = _tls.inspect_certificate(cert_path)
            if not cert.exists:
                findings.append((
                    FAIL,
                    f"TLS mode is {resolution.mode} but no certificate at {cert_path}. "
                    + (
                        "Run `manage.py edge_tls --issue-selfsigned`."
                        if resolution.mode == _tls.MODE_SELF_SIGNED
                        else f"Point {_tls.ENV_CERT} at the fullchain your CA issued."
                    ),
                ))
            elif cert.error:
                findings.append((FAIL, f"Certificate at {cert_path}: {cert.error}"))
            else:
                # Presence is not usability — the lesson _fernet_key_defects learned.
                missing = cert.covers(dns_names, ip_addresses)
                if missing:
                    findings.append((
                        FAIL,
                        "The certificate does not assert "
                        + ", ".join(missing)
                        + " — browsers show a name-mismatch warning at exactly the "
                        "addresses people type. Reissue with those names "
                        f"({_tls.ENV_HOSTNAMES}) or add them to ALLOWED_HOSTS.",
                    ))
                elif cert.days_remaining is not None and cert.days_remaining < 0:
                    findings.append((
                        FAIL,
                        f"The certificate EXPIRED {abs(cert.days_remaining)} days ago "
                        f"({cert.not_after}). Every browser refuses the box.",
                    ))
                elif cert.days_remaining is not None and cert.days_remaining < 30:
                    findings.append((
                        WARN,
                        f"The certificate expires in {cert.days_remaining} days "
                        f"({cert.not_after}). An offline box has nothing to renew it "
                        "automatically — put the date in the school's calendar.",
                    ))
                else:
                    findings.append((
                        OK,
                        f"Certificate covers every address the box answers at and is "
                        f"valid for {cert.days_remaining} more days.",
                    ))
            if not os.path.exists(key_path):
                findings.append((FAIL, f"TLS mode is {resolution.mode} but no private key at {key_path}."))

        # The flags a mode implies, versus the flags actually in force. An explicit
        # env var deliberately wins — but ONE direction is a lockout and the other is
        # merely a downgrade, so they are not the same finding.
        if resolution.source != "default" and not debug:
            for name, expected in _tls.derived_security_flags(resolution.mode).items():
                actual = getattr(settings, name, None)
                if actual == expected:
                    continue
                if expected is False and actual:
                    findings.append((
                        FAIL,
                        f"{name}={actual} but {_tls.ENV_MODE}={resolution.mode} implies "
                        f"{expected}. On a plain-HTTP origin this is the classic lockout: "
                        "the cookie is never set, the login POST 302s and bounces, and "
                        "nothing is logged. Delete the explicit value from .env.",
                    ))
                else:
                    findings.append((
                        WARN,
                        f"{name}={actual} overrides the {resolution.mode} default of "
                        f"{expected}. Legal, but the mode no longer describes the box.",
                    ))
            if resolution.mode in {_tls.MODE_SELF_SIGNED, _tls.MODE_PROVIDED} and int(
                getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0
            ) > 0:
                findings.append((
                    FAIL,
                    "SECURE_HSTS_SECONDS is set on a LAN certificate. HSTS tells every "
                    "browser to refuse plain HTTP to this origin for the full max-age, "
                    "and a LAN name or IP is an origin another box may hold next term. "
                    "This makes the TLS decision irreversible from the browser side.",
                ))

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
