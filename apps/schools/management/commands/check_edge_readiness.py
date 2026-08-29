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


def _resolves(hostname: str, timeout_seconds: float = 3.0) -> bool:
    """Does this name resolve from the box? Never blocks readiness for long.

    Run on a daemon thread with a join timeout because the entrypoint calls this
    command on EVERY container start: a resolver that hangs must not be able to hold
    a school's box in a boot loop. A timeout counts as "does not resolve", which is
    the honest answer for a name nobody can look up quickly.
    """
    import socket
    import threading

    outcome: list[bool] = []

    def _probe() -> None:
        try:
            socket.getaddrinfo(hostname, None)
            outcome.append(True)
        except Exception:  # noqa: BLE001 — any resolver failure is "no"
            outcome.append(False)

    worker = threading.Thread(target=_probe, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    return bool(outcome and outcome[0])


def _ollama_host(endpoint: str) -> str:
    """Hostname out of an Ollama endpoint, or "" when it cannot be read."""
    from urllib.parse import urlsplit

    try:
        return (urlsplit(endpoint.strip()).hostname or "").strip()
    except ValueError:
        return ""


def _ollama_answers(endpoint: str, timeout_seconds: float = 3.0) -> bool:
    """Does the model server actually respond? Bounded, like :func:`_resolves`.

    This command runs on EVERY container start, so a hung model host must not be
    able to hold a school's box in a boot loop. No answer in time is reported as
    "did not answer", which is what an operator needs to know either way.
    """
    import urllib.error
    import urllib.request

    base = endpoint.strip().rstrip("/")
    if base.endswith("/api/generate"):
        base = base[: -len("/api/generate")]
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout_seconds) as resp:
            return 200 <= int(getattr(resp, "status", 0) or 0) < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


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
                    # The address depends on the TLS mode, so ASK. This line used
                    # to end "plain HTTP; the box has no TLS" unconditionally, which
                    # on a box that HAS TLS is both false and harmful: the web port
                    # redirects to https, and Django builds that redirect from a host
                    # that carries the port, so the browser is sent to a TLS
                    # handshake against a plain socket and hangs. Naming the
                    # terminator instead is the address that answers.
                    from apps.schools import edge_tls as _tls_reach

                    _reach = _tls_reach.resolve_mode()
                    if _reach.error or _reach.mode == _tls_reach.MODE_OFF:
                        _how = ("http://<host>:<web-port>/ (plain HTTP; this box serves no TLS)")
                    else:
                        _how = ("https://<host>/ — the terminator, not the web port. "
                                "<web-port> serves /edge/trust/ for enrolment and "
                                "redirects everything else to https")
                    findings.append((
                        OK,
                        f"ALLOWED_HOSTS covers *.{base_domain} — a LAN hostname like "
                        f"'<slug>.{base_domain}' is accepted. Reach the box over "
                        f"{_how}.",
                    ))
                else:
                    findings.append((
                        WARN,
                        f"MULTI_TENANT_BASE_DOMAIN={base_domain} but ALLOWED_HOSTS has neither "
                        f"'{base_domain}' nor the wildcard '{dotted}' — a '{dotted}' hostname will "
                        f"400. Add '{dotted}' to ALLOWED_HOSTS.",
                    ))

        # --- Single-tenant / tenancy coherence ------------------------------
        # Not `single_tenant` alone. A box recognised from the compose marker or
        # ENVIRONMENT=selfhost carries no SINGLE_TENANT line -- .env.example has
        # never had one -- and every check in this block used to be gated on that
        # literal, so the boxes most likely to be misconfigured were the ones that
        # got no checks at all.
        sovereign_box = single_tenant or bool(
            getattr(settings, "RMC_IS_SELFHOST_BOX", False)
        )
        if sovereign_box and use_django_tenants:
            findings.append((
                WARN,
                "SINGLE_TENANT=True but USE_DJANGO_TENANTS=True: the bare-hostname "
                "fallback only works in shared/RLS mode. Set USE_DJANGO_TENANTS=0 for a "
                "bare-host single-school box, or reach the school via its subdomain.",
            ))
        elif sovereign_box:
            findings.append((
                OK,
                (
                    "SINGLE_TENANT + shared mode: bare-hostname resolution active."
                    if single_tenant
                    else "Sovereign box + shared mode: bare-hostname resolution "
                    "active (recognised without a SINGLE_TENANT line)."
                ),
            ))
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
                        "This is a single-school box but a bare-IP host still routes "
                        f"to {getattr(probe, 'urlconf', '?')} — it serves the operator "
                        "control plane to its school and 500s on /authentication/backend/.",
                    ))
            except Exception as exc:  # noqa: BLE001 — readiness must never crash
                findings.append((WARN, f"Could not probe host routing: {exc}"))

            # Where devices install this box's CA. Reported here rather than left to
            # the bootstrap banner because THIS is the command a runbook tells an
            # operator to run after a move, and after a move is exactly when nobody
            # is sure whether the address changed.
            try:
                from django.urls import reverse as _reverse

                from apps.schools import edge_tls as _et

                _resolved = _reverse("edge_trust", urlconf="config.tenant_urls")
                if _resolved != _et.TRUST_ENROLMENT_PATH:
                    findings.append((
                        FAIL,
                        f"Trust enrolment resolves to {_resolved} but every runbook, "
                        f"banner and printout says {_et.TRUST_ENROLMENT_PATH}. "
                        "Devices sent to the documented address get a 404.",
                    ))
                else:
                    _t_dns, _t_ips = _et.effective_addresses(
                        allowed_hosts=list(getattr(settings, "ALLOWED_HOSTS", []) or [])
                    )
                    _t_url = _et.trust_enrolment_url(_t_dns, _t_ips)
                    if not _t_url:
                        findings.append((
                            WARN,
                            "This box holds no address a device could be sent to, so "
                            "there is no trust-enrolment URL to hand out. Set "
                            f"{_et.ENV_HOSTNAMES} or ALLOWED_HOSTS.",
                        ))
                    else:
                        # Asked of the address that was actually CHOSEN. An earlier
                        # version asked a parallel question -- "are there any
                        # non-localhost names?" -- and got yes from the platform's
                        # public domain, which trust_enrolment_url had already
                        # refused to use. It then reported an IP-only box as
                        # name-stable, which is the reassurance you least want to be
                        # wrong.
                        import ipaddress as _ipa

                        _host = _t_url.split("//", 1)[-1].split("/", 1)[0]
                        _host = _host.rsplit(":", 1)[0].strip("[]")
                        try:
                            _ipa.ip_address(_host)
                            _is_ip = True
                        except ValueError:
                            _is_ip = False
                        if _is_ip:
                            findings.append((
                                WARN,
                                f"Devices install this box's CA at {_t_url} — but that "
                                "is an IP, and an IP changes. When it does, every "
                                "printout and whiteboard naming it is wrong and the "
                                "box gives no sign; the CA itself is fine, so nobody "
                                "has to be revisited, but nobody NEW can enrol either. "
                                "A stable name fixes it for good — map it in the "
                                "router's DNS (see docs/EDGE_LAN_HOSTNAME_DNS.md). "
                                "Note `.local` is mDNS and this stack ships no mDNS "
                                "responder, so a .local name resolves only where "
                                "something else publishes it.",
                            ))
                        elif not _resolves(_host):
                            # THE FAILURE THIS CHECK EXISTS FOR. A name in the
                            # certificate is not an address until something resolves
                            # it, and the box cannot tell the difference by looking at
                            # its own config -- which is exactly why this used to be
                            # reported as [OK]. A device opening it gets NXDOMAIN, and
                            # an unresolvable name is strictly WORSE than an IP: the
                            # IP works today.
                            # WARN and deliberately not FAIL. This resolves from
                            # INSIDE the container, whose resolver is not a phone's:
                            # a router DNS entry can be visible to every device on the
                            # LAN and invisible here. A FAIL would refuse to boot an
                            # otherwise healthy box (RMC_EDGE_READINESS_STRICT=1) over
                            # an inference this check cannot authoritatively make --
                            # and the box serves perfectly well at its IP meanwhile.
                            findings.append((
                                WARN,
                                f"Devices are told to install this box's CA at {_t_url}, "
                                f"but '{_host}' does not resolve FROM THIS BOX, so a "
                                "device opening that URL probably gets NXDOMAIN. Being "
                                "in the certificate is not the same as being on the "
                                "network. Either map the name to this box in the "
                                "router's DNS (docs/EDGE_LAN_HOSTNAME_DNS.md), or hand "
                                "devices the IP instead — the CA is identical whichever "
                                "address they fetch it from. `.local` is mDNS and this "
                                "stack runs no mDNS responder. Checked from inside the "
                                "container: if the school's DNS serves this name to "
                                "devices but not to Docker, enrolment is fine and this "
                                "line is the false alarm.",
                            ))
                        else:
                            findings.append((
                                OK,
                                f"Devices install this box's CA at {_t_url} — a NAME, "
                                "and it resolves from this box, so a new DHCP lease or "
                                "a move to another subnet does not change it. Resolution "
                                "is checked from the BOX; a device with its own resolver "
                                "(or a hosts-file entry someone made on one laptop) can "
                                "still differ.",
                            ))
            except Exception as exc:  # noqa: BLE001 — readiness must never crash
                findings.append((WARN, f"Could not resolve trust enrolment: {exc}"))

            # Confirm exactly one active school (tolerant of an unmigrated/unavailable DB).
            try:
                from apps.schools.models import School

                count = School.objects.filter(is_active=True).count()
                if count == 0:
                    findings.append((WARN, "This is a single-school box but no active school exists yet — provision one."))
                elif count == 1:
                    findings.append((OK, "Exactly one active school — bare-hostname will resolve to it."))
                else:
                    findings.append((FAIL, f"This is a single-school box but {count} active schools exist — resolution is ambiguous (returns none)."))
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
                # A SET endpoint is not a REACHABLE one, and reporting OK for the
                # first was how a box ran for weeks answering every copilot
                # question with "the language model on this server is offline".
                # The name is the usual culprit: host.docker.internal does not
                # exist on Linux without an extra_hosts host-gateway mapping.
                host = _ollama_host(ollama)
                if host and not _resolves(host):
                    hint = (
                        " Add `extra_hosts: [\"host.docker.internal:host-gateway\"]` to the"
                        " app service, or point OLLAMA_ENDPOINT at the host's LAN IP."
                        if host == "host.docker.internal"
                        else " Check the hostname, or use an IP."
                    )
                    findings.append((
                        FAIL,
                        f"OLLAMA_ENDPOINT={ollama} but {host} does not resolve from this "
                        f"container — the AI copilot will answer from rules only and say the "
                        f"model is offline.{hint}",
                    ))
                elif not _ollama_answers(ollama):
                    findings.append((
                        WARN,
                        f"OLLAMA_ENDPOINT={ollama} resolves but did not answer /api/tags — "
                        "start it with `ollama serve` and pull the model in OLLAMA_MODEL. "
                        "Until then AI degrades to deterministic rules (no crash).",
                    ))
                else:
                    findings.append((OK, f"OLLAMA_ENDPOINT={ollama} answered — local model tier is live."))
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

        # --- Will this box serve the OPERATOR surface to a school? -----------
        # The worst outcome in this whole file. A box that is not recognised as a box
        # is handed config.urls, the developer urlconf: operator chrome ("Search
        # tenants, incidents, commands"), 428 /super/ control-plane routes, and an
        # "Access required" page offering a Request-access button INTO the control
        # plane -- to a school, on their own appliance, after logging in with their
        # own credentials. It also hard-redirects every page to My profile when the
        # account is below the ADMIN security minimum, which reads as "the box is
        # broken" rather than as a posture gate.
        from apps.schools.middleware import is_sovereign_single_tenant_box as _sovereign

        # Only where this process is actually an appliance. A developer machine
        # serves config.urls on purpose and is not a finding, and saying otherwise
        # would make --strict unusable everywhere except the box.
        #
        # RMC_SELFHOST_STACK is the primary signal: the compose file sets it as a
        # literal on every box, no .env can remove it, and it is provenance rather
        # than classification -- so it does not make this circular, which keying off
        # the recognition markers would (a box that is not recognised is exactly the
        # box that needs to be told).
        #
        # RMC_EDGE_TLS_MODE stays as a second signal for a box that predates the
        # compose marker or runs outside compose. It was the ONLY signal until
        # 2026-08-25, on the strength of a comment here claiming the shipped
        # template carried it. It does not: neither deploy/selfhost/.env.example nor
        # the .env of the box this check was written for had ever set it, so on a
        # real appliance the loudest check in this file was silent in BOTH
        # directions -- no FAIL when the school was being shown the operator
        # surface, and no OK to confirm the fix afterwards.
        _looks_like_an_appliance = (
            str(os.environ.get("RMC_SELFHOST_STACK", "") or "").strip().lower()
            in {"1", "true", "yes", "on"}
            or os.environ.get("RMC_EDGE_TLS_MODE") is not None
        )
        if not _looks_like_an_appliance:
            pass
        elif not _sovereign():
            findings.append((
                FAIL,
                "This process is NOT recognised as a sovereign single-school box, so "
                "it will serve the operator URL surface: /super/ control-plane routes, "
                "operator chrome, and a 'Request access' page a school must never be "
                "shown. Set ENVIRONMENT=selfhost (the shipped compose file already "
                "does) or SINGLE_TENANT=1 in deploy/selfhost/.env and restart. Verify "
                "with `manage.py check_edge_readiness` -- this line must disappear.",
            ))
        else:
            findings.append((
                OK,
                "Recognised as a sovereign single-school box: it serves "
                "config.tenant_urls, the control-plane routes are not mounted at all, "
                "and the security-strength gate soft-locks instead of hard-redirecting "
                "every page to My profile.",
            ))

        # --- Is this mode achievable for these addresses at all? -------------
        # A school that picks a public certificate authority for a box reachable
        # only at 10.10.20.137 has chosen something no CA on earth can deliver, and
        # the symptom is not an error message -- it is a terminator retrying an ACME
        # order forever while the box serves nothing.
        _feas_dns, _feas_ips = _tls.san_candidates(allowed_hosts=allowed_hosts)

        # Can each declared name go into a certificate AT ALL, and will it look like
        # itself when it gets there? Local-first means the name on the building is
        # written in the script the school actually uses, and a certificate carries
        # DNS names as ASCII. Both outcomes -- silently dropped, or carried as an
        # "xn--" A-label -- are discovered by someone standing in front of a device
        # that will not connect unless they are said here first.
        if resolution.mode in _tls.HTTPS_MODES:
            # Only where a certificate actually exists. On a plain-HTTP box there is
            # nothing for a name to fail to go into, and a FAIL about certificates
            # would be a lie -- the loud thing on that box is the missing TLS itself,
            # which is already reported above.
            for _severity, _message in _tls.hostname_findings(
                _tls.declared_hostnames(allowed_hosts=allowed_hosts)
            ):
                findings.append((FAIL if _severity == "fail" else WARN, _message))
        for _severity, _message in _tls.mode_feasibility(
            resolution.mode, _feas_dns, _feas_ips
        ):
            findings.append((FAIL if _severity == "fail" else WARN, _message))

        # Will the way this box is reached SURVIVE the address changing? An IP-only
        # box works perfectly until DHCP hands out a different lease, and then every
        # device shows a certificate error at an address that no longer exists. The
        # fix is free and the failure is invisible until the day it happens, which is
        # exactly the combination worth a standing warning.
        for _severity, _message in _tls.stability_findings(_feas_dns, _feas_ips):
            findings.append((FAIL if _severity == "fail" else WARN, _message))
        if _tls.trust_local_addresses():
            _held = _tls.local_addresses()
            findings.append((
                OK,
                "Self-healing addresses are ON: this box serves and asserts the "
                "addresses it currently holds ("
                + (", ".join(_held) if _held else "none detected")
                + "), so a new DHCP lease or a move does not need anyone to edit a file.",
            ))

        if resolution.mode in _tls.FILE_BACKED_MODES:
            cert_path, key_path, _ca = _tls.certificate_paths()
            dns_names, ip_addresses = _tls.san_candidates(allowed_hosts=allowed_hosts)
            cert = _tls.inspect_certificate(cert_path)
            # A relocated box is the classic victim of a dead RTC: shipped across a
            # border, it powers on believing it is years in the past, rejects its own
            # certificate as 'not yet valid', and nothing in the browser error mentions
            # the clock. Its own CA gives us a floor to detect that without a network.
            _ca_facts = _tls.inspect_certificate(_ca)
            for _severity, _message in _tls.clock_findings(cert, _ca_facts):
                findings.append((FAIL if _severity == "fail" else WARN, _message))

            # The one artefact that cannot be regenerated, and whether this box still
            # holds the one it recorded. A CA that has silently been REPLACED looks
            # perfect from every other angle -- the certificate is valid, the chain is
            # complete, the dates are fine -- and every device in the building rejects
            # it. Only the recorded fingerprint can tell you.
            from apps.schools import edge_trust_state as _anchor

            for _severity, _message in _anchor.anchor_findings(_ca_facts):
                findings.append((
                    {"fail": FAIL, "warn": WARN}.get(_severity, OK),
                    _message,
                ))

            # Reissuing is only half a heal: the terminator reads its certificate at
            # config load, not per handshake. Comparing what is SERVED against what is
            # on disk is the only way to see, from in here, that the two disagree.
            _term = (os.getenv("RMC_EDGE_TLS_TERMINATOR", "edge-tls:443") or "").strip()
            if _term and cert.exists:
                _thost, _, _tport = _term.partition(":")
                try:
                    _tport_n = int(_tport or "443")
                except ValueError:
                    _tport_n = 443
                for _severity, _message in _tls.terminator_findings(
                    cert_path, _thost, _tport_n, timeout=3.0
                ):
                    findings.append((
                        {"fail": FAIL, "warn": WARN}.get(_severity, OK),
                        _message,
                    ))
            if resolution.mode == _tls.MODE_SELF_SIGNED and _ca_facts.exists:
                # We cannot prove a backup exists somewhere safe, so we never claim
                # it does. But we CAN detect the mistake of leaving the bundle in the
                # certificate directory: a backup that shares a volume with the key it
                # protects survives none of the events a backup exists for, and it puts
                # an encrypted copy of the CA key on the box permanently.
                _ca_dir = os.path.dirname(_ca) or "."
                try:
                    _stray = sorted(
                        name
                        for name in os.listdir(_ca_dir)
                        if name.lower().endswith((".p12", ".pfx"))
                    )
                except OSError:
                    _stray = []
                if _stray:
                    findings.append((
                        WARN,
                        "A CA bundle ("
                        + ", ".join(_stray)
                        + f") is sitting in {_ca_dir}, the same volume as the key it "
                        "backs up. It protects against nothing that way -- lose the "
                        "volume and you lose both. Copy it off the box and delete it "
                        "from here.",
                    ))
                elif not ((_anchor.load_state().get("active") or {}).get("exported_at")):
                    # Only when the box cannot confirm a backup for itself. Saying this
                    # alongside "backup read back and verified" is noise that trains an
                    # operator to skim the report, which is how the findings that matter
                    # get missed.
                    findings.append((
                        WARN,
                        "The box CA is the only artefact here that cannot be regenerated: "
                        "lose it and every device that trusts this box must be visited in "
                        "person. Export it before the box moves or is rebuilt -- "
                        "`edge_tls --export-ca <path>` -- and keep the copy off the box.",
                    ))
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
            # Present in the environment AT ALL, even where it currently agrees with
            # the mode. Agreement today is not the property that matters: an explicit
            # value wins forever, so the day somebody changes the mode -- selfsigned to
            # acme, or back to off to debug something -- the flag silently does not
            # follow, and the box is left in a combination nobody chose. That is
            # exactly the trap deriving them removed.
            _pinned = [
                _name
                for _name in _tls.derived_security_flags(resolution.mode)
                if os.environ.get(_name) not in (None, "")
            ]
            if _pinned:
                findings.append((
                    WARN,
                    "Set by hand in the environment: "
                    + ", ".join(sorted(_pinned))
                    + f". These are DERIVED from {_tls.ENV_MODE}, and an explicit value "
                    "wins permanently -- so they will not follow the next mode change, "
                    "and the box ends up in a combination nobody chose. They agree with "
                    f"{resolution.mode} today; delete them from .env and they will agree "
                    "with whatever the mode is tomorrow.",
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
