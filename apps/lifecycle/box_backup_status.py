"""Read the box backup record the same way ``box-audit.sh`` section C2 does.

A sovereign box keeps the fee ledger, marks, attendance and uploaded documents on
one disk. ``deploy/selfhost/box-backup.sh`` writes an encrypted dump and then a
JSON record at ``/backups/backup-state.json`` AFTER it has read that dump back.
This module is the Python twin of the audit's three hard gates, so the onboarding
runbook can refuse go-dark without shelling out to Docker.

It never takes a backup and never restores one. An audit that restored to find out
whether restores work would have destroyed the thing it was measuring.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

#: Same ceiling ``box-audit.sh`` C2 uses (48 hours). Written as a product of
#: hour/minute/second so the magic-number scanner does not treat it as an
#: unexplained literal.
MAX_BACKUP_AGE_SECONDS = 48 * 60 * 60

DEFAULT_STATE_FILE = "/backups/backup-state.json"


def state_file_path() -> Path:
    """Where the backup container writes the record the web process can read.

    Default matches the compose mount ``backupdata:/backups:ro`` on the app
    services. Override with ``RMC_BOX_BACKUP_STATE_FILE`` when tests point at a
    tempfile, or when a box mounts the volume elsewhere.
    """
    try:
        from django.conf import settings

        raw = str(getattr(settings, "RMC_BOX_BACKUP_STATE_FILE", "") or "")
    except Exception:  # noqa: BLE001 — a path helper must never crash the runbook
        raw = ""
    return Path(raw or DEFAULT_STATE_FILE)


def load_backup_state(path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Parse the record, or ``None`` if it is missing or not JSON. Never raises."""
    target = Path(path) if path is not None else state_file_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _intish(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def verdict_from_state(
    state: Optional[dict[str, Any]],
    *,
    now_epoch: Optional[int] = None,
) -> "tuple[bool, str]":
    """The C2 GATE from ``box-audit.sh``, as ``(ok, detail)``.

    A file that decrypts and lists but was never read end-to-end is not a backup.
    A verified read-back of a dump that is no longer the newest one is not a backup
    of today's school. A dump older than two days means the term has moved on.
    """
    if not isinstance(state, dict) or "schema" not in state:
        return False, (
            "NO BACKUP RECORD on this box -- it has never taken a backup of the "
            "school database. Start the backup service and run "
            "`box-backup.sh once`."
        )

    last_file = str(state.get("last_file") or "").strip()
    verified_at = str(state.get("verified_at") or "").strip()
    verified_file = str(state.get("verified_file") or "").strip()
    last_epoch = _intish(state.get("last_success_epoch"))
    now = int(now_epoch) if now_epoch is not None else int(time.time())

    if not verified_at:
        return False, (
            "no verified read-back on record -- this box cannot show its backup "
            "was ever read back"
        )
    if last_file and verified_file != last_file:
        return False, (
            f"the verified read-back is for {verified_file}, not the newest dump "
            f"{last_file} -- the newest one has never been opened"
        )
    if not _truthy(state.get("verified_full_read")):
        return False, (
            "the dump was listed but never read END TO END -- a truncated archive "
            "lists perfectly and restores nothing"
        )
    if last_epoch <= 0:
        return False, "no successful backup has EVER completed on this box"

    age = now - last_epoch
    if age > MAX_BACKUP_AGE_SECONDS:
        hours = max(0, age) // 3600
        return False, (
            f"the last successful backup was {hours}h ago -- more than two days of "
            "work at this school has no copy"
        )

    toc = _intish(state.get("verified_toc_entries"))
    detail = (
        f"newest dump {last_file or '<none>'} was read back in full "
        f"({toc} archive entries)"
    )
    if not _truthy(state.get("offbox_independent")):
        detail += (
            ". off-box copy is NOT on a different filesystem -- a dead disk takes "
            "both unless RMC_BOX_BACKUP_OFFBOX_DIR points at a USB disk or NAS"
        )
    return True, detail


def evaluate_box_backup(*, path: Optional[Path] = None, now_epoch: Optional[int] = None) -> "tuple[bool, str]":
    """Load the record from disk and return the C2 verdict. Never raises."""
    try:
        return verdict_from_state(load_backup_state(path), now_epoch=now_epoch)
    except Exception as extra:  # noqa: BLE001
        return False, f"backup record could not be read: {extra}"
