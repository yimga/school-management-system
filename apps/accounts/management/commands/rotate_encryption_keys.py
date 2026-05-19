"""``python manage.py rotate_encryption_keys`` — v3.33.0.

Operator-driven MultiFernet key rotation.

By default the command does a **dry run**: it walks every Fernet-wrapped
column, decrypts each row under the active MultiFernet (which holds
every key in ``settings.DJANGO_CRYPTOGRAPHY_KEYS``), and reports which
rows would be re-encrypted under the newest key — but never writes.

Pass ``--apply`` to actually re-encrypt and commit. Pass
``--model app_label.ModelName`` to scope the run to a single model
(useful when partial rotation has stalled and you need to finish
just one table).

The command is **idempotent**: a second run finds zero rows changed
because every ciphertext is already wrapped under the primary key.

NEVER logs key material. The audit trail goes to
``logs/key_rotation_<utc_iso>.jsonl`` and contains counts + per-row
booleans only — never bytes.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "MultiFernet key rotation: re-encrypt every Fernet-wrapped column "
        "under the newest key in DJANGO_CRYPTOGRAPHY_KEYS. Dry-run by default."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help=(
                "Actually re-encrypt and commit. Default behavior is "
                "dry-run (scan + verify decrypt, never write)."
            ),
        )
        parser.add_argument(
            "--model",
            dest="model",
            default=None,
            help=(
                "Scope to a single model: 'app_label.ModelName'. "
                "When omitted, walks every registered encrypted column."
            ),
        )
        parser.add_argument(
            "--verify-orphans",
            action="store_true",
            default=False,
            help=(
                "Instead of rotating, run the orphan-ciphertext audit: "
                "scan every encrypted column and report rows that do "
                "not decrypt under any currently-active key."
            ),
        )

    def handle(self, *args, **options) -> None:
        # Local imports keep the command loadable even when the
        # cryptography extra is missing (the import surface is the
        # smallest possible path to a useful error).
        from apps.accounts.legacy_hashes.key_rotation import (
            rotate_all_encrypted_columns,
            verify_no_orphan_ciphertexts,
        )
        from apps.accounts.legacy_hashes.encryption import (
            active_key_count,
            backend_in_use,
        )

        self.stdout.write(
            self.style.NOTICE(
                f"encryption backend: {backend_in_use()}; "
                f"active key count: {active_key_count()}"
            )
        )

        if options.get("verify_orphans"):
            summary = verify_no_orphan_ciphertexts(
                model_filter=options.get("model"),
            )
            totals = summary.get("totals", {})
            self.stdout.write(
                f"orphan scan: models={totals.get('models_scanned', 0)} "
                f"rows={totals.get('rows_scanned', 0)} "
                f"orphans={totals.get('orphan_count', 0)}"
            )
            for tbl in summary.get("tables", []):
                if tbl.get("orphan_count", 0) > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {tbl['model']}: {tbl['orphan_count']} orphan(s) "
                            f"pks={tbl['orphan_pks'][:10]}"
                            f"{'...' if len(tbl['orphan_pks']) > 10 else ''}"
                        )
                    )
            if totals.get("orphan_count", 0) > 0:
                raise CommandError(
                    "Orphan ciphertexts detected. Reinstate the dropped "
                    "key in DJANGO_CRYPTOGRAPHY_KEYS and re-run."
                )
            return

        dry_run = not options.get("apply", False)
        if dry_run:
            self.stdout.write(self.style.NOTICE("running in DRY-RUN mode (no writes)"))
        else:
            self.stdout.write(self.style.WARNING("APPLYING — re-encrypting rows under newest key"))

        summary = rotate_all_encrypted_columns(
            dry_run=dry_run,
            model_filter=options.get("model"),
        )
        totals = summary.get("totals", {})
        log_path = summary.get("log_path", "")
        self.stdout.write(
            f"scanned={totals.get('rows_scanned', 0)} "
            f"rewrapped={totals.get('rows_rewrapped', 0)} "
            f"skipped={totals.get('rows_skipped', 0)} "
            f"failed={totals.get('rows_failed', 0)}"
        )
        for tbl in summary.get("tables", []):
            self.stdout.write(
                f"  {tbl['model']}: scanned={tbl['rows_scanned']} "
                f"rewrapped={tbl['rows_rewrapped']} "
                f"skipped={tbl['rows_skipped']} "
                f"failed={tbl['rows_failed']}"
            )
        if log_path:
            self.stdout.write(self.style.NOTICE(f"audit log: {log_path}"))
        if totals.get("rows_failed", 0) > 0:
            raise CommandError(
                f"{totals['rows_failed']} row(s) failed to re-encrypt — "
                "check the audit log."
            )
