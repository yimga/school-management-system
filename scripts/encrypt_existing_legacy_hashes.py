#!/usr/bin/env python
"""One-shot backfill: encrypt any plaintext legacy_password_hash rows.

Migration 0033 wraps the three legacy_* User columns in Fernet-encrypted
descriptors. Going forward every write happens through the encrypted
field's ``get_prep_value`` and the bytes hit the DB as ciphertext.

If a production deployment imported users between v3.28 (introduction
of the columns) and v3.29 (encryption wrap), those rows still hold
plaintext. This script reads each affected row, re-saves it, and lets
the now-encrypted field's ``get_prep_value`` produce ciphertext. The
write is wrapped in a per-row atomic so a transient failure can't
leave the row half-touched.

Idempotency:

* Already-encrypted rows decrypt cleanly on read, then re-encrypt on
  save. Fernet uses a random IV so each save produces different
  ciphertext bytes, but the *decrypted* plaintext is identical. Safe
  to re-run.
* Empty-string rows are skipped (the "no legacy hash" sentinel).

Usage (from the project root):

    python scripts/encrypt_existing_legacy_hashes.py            # dry run
    python scripts/encrypt_existing_legacy_hashes.py --apply    # write

The script logs only counts + statuses. The hash value is NEVER printed.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("encrypt_existing_legacy_hashes")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually re-save rows. Default is dry-run (count + report only).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=200,
        help="Iterator chunk size for the User scan. Default 200.",
    )
    args = parser.parse_args()

    logger = _setup_logger()
    dry_run = not args.apply

    import django

    django.setup()

    from django.contrib.auth import get_user_model
    from django.db import DatabaseError, transaction

    from apps.accounts.legacy_hashes.encryption import backend_in_use

    UserModel = get_user_model()
    # tenant-isolation-allow: auth-layer-system-wide-user-table-platform-backfill
    qs = UserModel.objects.exclude(legacy_password_hash="")
    total = qs.count()
    logger.info(
        "encrypt_existing_legacy_hashes_start",
        extra={"total_rows": total, "dry_run": dry_run, "backend": backend_in_use()},
    )

    if dry_run:
        logger.info(
            "encrypt_existing_legacy_hashes_dry_run_report",
            extra={"rows_that_would_be_resaved": total},
        )
        print(f"DRY RUN — rows that would be re-saved: {total}")
        print(f"Active encryption backend: {backend_in_use()}")
        print("Re-run with --apply to perform the writes.")
        return 0

    encrypted = 0
    failed = 0
    for user in qs.only(
        "id", "legacy_password_hash", "legacy_hash_algorithm", "legacy_hash_params"
    ).iterator(chunk_size=args.chunk_size):
        try:
            with transaction.atomic():
                # Re-assigning the same value forces get_prep_value to
                # run on save, producing ciphertext when the encrypted
                # field is active.
                user.legacy_password_hash = user.legacy_password_hash
                user.legacy_hash_algorithm = user.legacy_hash_algorithm
                user.legacy_hash_params = user.legacy_hash_params
                user.save(
                    update_fields=(
                        "legacy_password_hash",
                        "legacy_hash_algorithm",
                        "legacy_hash_params",
                    )
                )
            encrypted += 1
        except DatabaseError:
            failed += 1
            logger.exception(
                "encrypt_existing_legacy_hashes_row_failed",
                extra={"user_id": user.pk},
            )

    logger.info(
        "encrypt_existing_legacy_hashes_complete",
        extra={"encrypted": encrypted, "failed": failed, "total": total},
    )
    print(f"Encrypted {encrypted} rows; {failed} failed. Backend: {backend_in_use()}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
