"""v3.38.0 Agent 5 — audit-chain integrity verifier.

v3.39.0 Agent 1 — extended with ``--all-tenants`` sweep mode + optional
``--email-on-broken=<addr>`` notification for the weekly Celery beat.

Usage::

    python manage.py verify_audit_chain --tenant=<slug>
    python manage.py verify_audit_chain --tenant=<slug> --repair-genesis
    python manage.py verify_audit_chain --all-tenants
    python manage.py verify_audit_chain --all-tenants \
        --email-on-broken=audit-ops@example.invalid

Walks the per-tenant chain in ``created_at`` order and asserts:

  1. Every event's stored ``integrity_hash`` matches the value
     re-derived from its current field values
     (``recompute_integrity_hash``).
  2. Every event's ``prev_event_hash`` matches the prior event's
     ``integrity_hash`` (or the genesis sentinel for the first event).

Both comparisons use :func:`hmac.compare_digest` for constant-time
semantics.

Exit codes:

  * 0 — clean chain (or all tenants clean in ``--all-tenants`` mode).
  * 1 — chain broken; broken event IDs printed to stderr.

``--repair-genesis`` is the ONLY mutation path: if the very first
event per tenant has an empty / missing ``prev_event_hash``, it's
populated with the sentinel and the row's ``integrity_hash`` is
recomputed. NEVER modifies later events. (single-tenant mode only)

``--all-tenants`` iterates over every active tenant via
``apps.schools.models.School.objects.filter(is_active=True)``. The
queryset is intentionally cross-tenant for audit sweep purposes; see
the marker on the line below.

``--email-on-broken=<addr>`` — when ANY chain is broken in
``--all-tenants`` mode, send a summary email via
:func:`django.core.mail.send_mail`. The body carries ONLY
tenant_id_hash prefixes, count of broken events, and the first broken
event UUID — NEVER hash bytes, NEVER payload bytes, NEVER raw slug.
"""
from __future__ import annotations

import hmac
import logging
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.migration_cloud.models_audit import (
    GENESIS_SENTINEL,
    MigrationCloudAuditEvent,
    _hash_tenant_slug,
    _compute_integrity_hash,
)

logger = logging.getLogger(__name__)

# Test seams patch either this module attribute or django.core.mail.send_mail.
# Keep the attribute present while resolving the real callable lazily.
send_mail = None


class Command(BaseCommand):
    help = "Verify the integrity hash-chain for an audit log tenant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            required=False,
            default=None,
            type=str,
            help="Tenant slug whose chain to verify.",
        )
        parser.add_argument(
            "--all-tenants",
            action="store_true",
            help=(
                "Verify the chain for every active tenant. Mutually "
                "exclusive with --tenant. Exit 1 if ANY chain is broken."
            ),
        )
        parser.add_argument(
            "--email-on-broken",
            default="",
            type=str,
            help=(
                "Email address to notify when --all-tenants finds at "
                "least one broken chain. Body carries only hash prefixes "
                "and the first broken event UUID — never raw hash or "
                "payload bytes."
            ),
        )
        parser.add_argument(
            "--repair-genesis",
            action="store_true",
            help=(
                "Populate a missing prev_event_hash on the first event "
                "with the genesis sentinel. NEVER modifies later events. "
                "Single-tenant mode only."
            ),
        )
        # v3.39.0 Agent 2 — root-key signature check.
        parser.add_argument(
            "--check-root-signature",
            action="store_true",
            help=(
                "Additionally verify each event's root_key_signature "
                "(HMAC-SHA512 keyed by MIGRATION_CLOUD_AUDIT_SIGNING_KEY). "
                "Exit code 2 (NOT 1) when chain is intact but root "
                "signatures mismatch — disambiguates backup-restore "
                "tampering from chain corruption. Events with "
                "root_key_signature=NULL are reported as 'unsigned "
                "legacy' (key wasn't configured at write time)."
            ),
        )

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        all_tenants = bool(options.get("all_tenants"))
        tenant_slug = options.get("tenant")
        repair_genesis = bool(options.get("repair_genesis"))
        email_on_broken = (options.get("email_on_broken") or "").strip()
        check_root_signature = bool(options.get("check_root_signature"))

        if all_tenants and tenant_slug:
            raise CommandError(
                "--all-tenants and --tenant are mutually exclusive."
            )
        if not all_tenants and not tenant_slug:
            raise CommandError(
                "Either --tenant=<slug> or --all-tenants is required."
            )
        if all_tenants and repair_genesis:
            raise CommandError(
                "--repair-genesis is single-tenant only; combine with "
                "--tenant=<slug>."
            )

        if all_tenants:
            self._handle_all_tenants(
                email_on_broken=email_on_broken,
                check_root_signature=check_root_signature,
            )
            return

        # Single-tenant path. The walker now returns broken-by-chain AND
        # broken-by-signature lists so the caller can pick exit codes:
        #   chain broken                      → exit 1
        #   chain ok, signature mismatch      → exit 2
        #   chain ok, signature legacy/clean  → exit 0
        broken, broken_sig, unsigned_legacy, events_checked = (
            self._verify_one_tenant(
                tenant_slug=tenant_slug,
                repair_genesis=repair_genesis,
                check_root_signature=check_root_signature,
            )
        )
        if broken:
            self.stderr.write(
                f"verify_audit_chain: {len(broken)} broken event(s) "
                f"for tenant {tenant_slug!r}"
            )
            sys.exit(1)
        if check_root_signature and broken_sig:
            self.stderr.write(
                f"verify_audit_chain: chain clean but "
                f"{len(broken_sig)} root-signature mismatch(es) for "
                f"tenant {tenant_slug!r} — possible backup-restore "
                f"tamper. first_mismatch_uuid={broken_sig[0]}"
            )
            sys.exit(2)
        legacy_note = ""
        if check_root_signature and unsigned_legacy:
            legacy_note = (
                f" unsigned_legacy={len(unsigned_legacy)} (key wasn't "
                f"configured at write time — not a tamper signal)"
            )
        self.stdout.write(
            f"verify_audit_chain: clean tenant={tenant_slug!r} "
            f"events={events_checked}{legacy_note}"
        )

    # ------------------------------------------------------------------
    # All-tenants sweep
    # ------------------------------------------------------------------

    def _handle_all_tenants(
        self,
        *,
        email_on_broken: str,
        check_root_signature: bool = False,
    ) -> None:
        # Lazy-import the School model so the management command can
        # be loaded for --help in lanes without the full apps tree
        # bootstrapped.
        from apps.schools.models import School

        # tenant-isolation-allow: cross-tenant-audit-chain-verification-sweep
        active_tenants = list(
            School.objects.filter(is_active=True).order_by("slug")
        )

        tenants_checked = 0
        tenants_clean = 0
        total_events_checked = 0
        broken_summary: list[dict] = []
        signature_mismatch_summary: list[dict] = []
        total_unsigned_legacy = 0

        for school in active_tenants:
            slug = getattr(school, "slug", "") or ""
            if not slug:
                continue
            tenants_checked += 1
            broken, broken_sig, unsigned_legacy, events_checked = (
                self._verify_one_tenant(
                    tenant_slug=slug,
                    repair_genesis=False,
                    quiet=True,
                    check_root_signature=check_root_signature,
                )
            )
            total_events_checked += events_checked
            total_unsigned_legacy += len(unsigned_legacy)
            tenant_hash_prefix = _hash_tenant_slug(slug)
            if broken:
                first_broken_uuid = broken[0]
                broken_summary.append({
                    "tenant_id_hash": tenant_hash_prefix,
                    "first_broken_event_uuid": first_broken_uuid,
                    "broken_count": len(broken),
                })
                self.stderr.write(
                    f"verify_audit_chain: BROKEN tenant_hash="
                    f"{tenant_hash_prefix} broken_events={len(broken)} "
                    f"first_broken_uuid={first_broken_uuid}"
                )
            elif check_root_signature and broken_sig:
                signature_mismatch_summary.append({
                    "tenant_id_hash": tenant_hash_prefix,
                    "first_mismatch_uuid": broken_sig[0],
                    "mismatch_count": len(broken_sig),
                })
                self.stderr.write(
                    f"verify_audit_chain: SIGNATURE MISMATCH tenant_hash="
                    f"{tenant_hash_prefix} mismatches={len(broken_sig)} "
                    f"first_uuid={broken_sig[0]} — possible "
                    f"backup-restore tamper"
                )
            else:
                tenants_clean += 1

        tenants_broken = len(broken_summary)
        tenants_sig_mismatch = len(signature_mismatch_summary)
        summary_parts = [
            "verify_audit_chain --all-tenants summary:",
            f"tenants_checked={tenants_checked}",
            f"tenants_clean={tenants_clean}",
            f"tenants_broken={tenants_broken}",
            f"total_events_checked={total_events_checked}",
        ]
        if check_root_signature:
            summary_parts.append(
                f"tenants_sig_mismatch={tenants_sig_mismatch}"
            )
            summary_parts.append(
                f"total_unsigned_legacy={total_unsigned_legacy}"
            )
        self.stdout.write(" ".join(summary_parts))

        if broken_summary and email_on_broken:
            self._send_break_email(
                recipient=email_on_broken,
                tenants_checked=tenants_checked,
                tenants_broken=tenants_broken,
                total_events_checked=total_events_checked,
                broken_summary=broken_summary,
            )

        if broken_summary:
            sys.exit(1)
        if check_root_signature and signature_mismatch_summary:
            sys.exit(2)

    # ------------------------------------------------------------------
    # Single-tenant walk
    # ------------------------------------------------------------------

    def _verify_one_tenant(
        self,
        *,
        tenant_slug: str,
        repair_genesis: bool,
        quiet: bool = False,
        check_root_signature: bool = False,
    ) -> tuple[list[str], list[str], list[str], int]:
        """Walk one tenant's chain.

        Returns 4-tuple ``(broken, broken_sig, unsigned_legacy, events_checked)``:

          * ``broken`` — event UUIDs where the integrity/link hash chain is broken.
          * ``broken_sig`` — event UUIDs whose root_key_signature mismatches
            (only populated when ``check_root_signature=True`` AND Agent 2's
            root-signing column has shipped; otherwise always empty list).
          * ``unsigned_legacy`` — event UUIDs that have no root_key_signature
            because the signing key wasn't configured at write time.
          * ``events_checked`` — total events walked.
        """
        tenant_hash = _hash_tenant_slug(tenant_slug)

        # tenant-isolation-allow: audit-verifier-walk-chain-per-tenant-by-hash-prefix
        chain = list(
            MigrationCloudAuditEvent.objects
            .filter(tenant_id_hash=tenant_hash)
            .order_by("created_at", "id")
        )

        if not chain:
            if not quiet:
                self.stdout.write(
                    f"verify_audit_chain: no events for tenant_id_hash={tenant_hash}"
                )
            return [], [], [], 0

        broken: list[str] = []
        broken_sig: list[str] = []
        unsigned_legacy: list[str] = []
        prev_hash = GENESIS_SENTINEL

        for idx, ev in enumerate(chain):
            if (
                idx == 0
                and repair_genesis
                and (ev.prev_event_hash or "") == ""
            ):
                new_integrity = _compute_integrity_hash(
                    pk=str(ev.id),
                    tenant_id_hash=ev.tenant_id_hash,
                    event_type=ev.event_type,
                    actor_id=ev.actor_id,
                    event_subject_hash=ev.event_subject_hash,
                    payload_summary=ev.payload_summary or {},
                    created_at_iso=ev.created_at_iso,
                    prev_event_hash=GENESIS_SENTINEL,
                )
                from django.db import connection
                db_pk = MigrationCloudAuditEvent._meta.pk.get_db_prep_value(
                    ev.pk, connection,
                )
                with connection.cursor() as cur:
                    cur.execute(
                        "UPDATE migration_cloud_migrationcloudauditevent "
                        "SET prev_event_hash=%s, integrity_hash=%s "
                        "WHERE id=%s",
                        [GENESIS_SENTINEL, new_integrity, db_pk],
                    )
                ev.prev_event_hash = GENESIS_SENTINEL
                ev.integrity_hash = new_integrity
                if not quiet:
                    self.stdout.write(
                        f"verify_audit_chain: genesis-repaired event_id={ev.id}"
                    )

            expected = ev.recompute_integrity_hash()
            own_ok = hmac.compare_digest(
                expected.encode("ascii"),
                ev.integrity_hash.encode("ascii"),
            )
            link_ok = hmac.compare_digest(
                prev_hash.encode("ascii"),
                ev.prev_event_hash.encode("ascii"),
            )

            if not (own_ok and link_ok):
                broken.append(str(ev.id))
                if not quiet:
                    self.stderr.write(
                        f"verify_audit_chain: BROKEN event_id={ev.id} "
                        f"own_ok={own_ok} link_ok={link_ok} "
                        f"expected_prev={prev_hash[:12]} "
                        f"stored_prev={ev.prev_event_hash[:12]}"
                    )

            # v3.39.0 Agent 2 — root-key signature verification. Delegate
            # to the service module's ``verify_root_signature`` so the
            # algorithm (HMAC-SHA512 over the canonical-JSON pre-image,
            # NOT over the SHA-256 integrity_hash) stays the single
            # source of truth for both write and verify paths.
            if check_root_signature:
                stored_sig = getattr(ev, "root_key_signature", None)
                if not stored_sig:
                    unsigned_legacy.append(str(ev.id))
                else:
                    from apps.migration_cloud.services.audit_root_signing import (
                        verify_root_signature as _verify_root_signature,
                    )
                    result = _verify_root_signature(ev)
                    if result is None:
                        # Key not configured at verify time — can't check.
                        unsigned_legacy.append(str(ev.id))
                    elif result is False:
                        broken_sig.append(str(ev.id))
                        if not quiet:
                            self.stderr.write(
                                f"verify_audit_chain: ROOT-SIGNATURE "
                                f"MISMATCH event_id={ev.id} — chain "
                                f"intact but root signature does not "
                                f"recompute"
                            )

            prev_hash = ev.integrity_hash

        return broken, broken_sig, unsigned_legacy, len(chain)

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    def _send_break_email(
        self,
        *,
        recipient: str,
        tenants_checked: int,
        tenants_broken: int,
        total_events_checked: int,
        broken_summary: list[dict],
    ) -> None:
        """Send a PII-free summary email when any chain is broken.

        Body contains only tenant_id_hash prefixes + broken count + the
        FIRST broken event UUID per tenant. NEVER includes hash bytes,
        NEVER payload bytes, NEVER raw slug.
        """
        from django.conf import settings
        from django.core.mail import send_mail as django_send_mail

        mailer = send_mail or django_send_mail

        lines = [
            "Migration Cloud audit chain verification — BROKEN CHAINS DETECTED",
            "",
            f"tenants_checked={tenants_checked}",
            f"tenants_broken={tenants_broken}",
            f"total_events_checked={total_events_checked}",
            "",
            "Per-tenant break summary (tenant_id_hash | broken_count | first_broken_event_uuid):",
        ]
        for row in broken_summary:
            lines.append(
                f"  {row['tenant_id_hash']} | "
                f"{row['broken_count']} | "
                f"{row['first_broken_event_uuid']}"
            )
        lines += [
            "",
            "Investigate via `manage.py verify_audit_chain --tenant=<slug>` for the corresponding slug.",
            "Tenant-hash → slug correlation is maintained outside this app per docs/MIGRATION_CLOUD_AUDIT_LOG.md.",
        ]
        body = "\n".join(lines)

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "noreply@runmycampus.com"
        mailer(
            subject="[Migration Cloud] Audit chain BROKEN — weekly verifier",
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=True,
        )
