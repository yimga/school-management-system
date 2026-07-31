"""v3.40.0 Agent 14 — multi-tenant parallel Migration Cloud smoke.

Closes Agent 8's deferred item: drive ``manage.py migration_cloud_smoke``
against N synthetic tenants in parallel for staging soak testing.

CLI::

    python manage.py migration_cloud_smoke_multi \\
        --tenants slug1,slug2,slug3    # required, comma-separated
        --vendor <vendor>              # required (single vendor for all)
        --concurrency 4                # default 4; HARD MAX 16 (DoS guard)
        --apply                        # default OFF
        --fail-fast                    # default OFF

Exit codes::

    0   every tenant smoke clean (PASS / SKIP-optional only)
    1   any tenant FAILED
    2   any tenant exited with skipped optional sections (Agent 8 code 2)

Hard contracts:

  * Uses ``concurrent.futures.ThreadPoolExecutor`` — NOT process pool.
    Django ORM works fine across threads; fork breaks connection
    pooling. We close per-thread DB connections via
    ``django.db.connection.close()`` after each task.
  * Concurrency cap of 16 is HARD-enforced — input above is REJECTED
    (CommandError), never clamped.
  * Each per-tenant invocation is wrapped in ``transaction.atomic`` so
    a mid-run failure doesn't half-commit synthetic-tenant state.
  * Aggregate JSON written to ``var/smoke-results-multi/<utc-iso>.json``
    matching Agent 13's path convention.
  * Audit-emits one event per tenant + one aggregate
    ``migration.smoke.multi_run_completed`` event.
  * Same prod-safety gate as single-tenant smoke.
  * NEVER logs raw tenant slugs — sha256[:12] prefix only.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone as _dt_timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

logger = logging.getLogger(__name__)


CONCURRENCY_HARD_CAP = 16

_VENDOR_CHOICES = (
    "powerschool",
    "blackbaud",
    "veracross",
    "alma",
    "facts",
    "skyward",
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _hash_slug_prefix(slug: str) -> str:
    return hashlib.sha256((slug or "").encode("utf-8")).hexdigest()[:12]


def _parse_summary_counts(stdout_text: str) -> dict[str, int]:
    passed = failed = skipped = 0
    for line in (stdout_text or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        status = parts[1].upper()
        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            failed += 1
        elif status == "SKIP":
            skipped += 1
    return {"passed": passed, "failed": failed, "skipped": skipped}


def _prod_safety_gate(apply_mode: bool) -> None:
    """Same heuristic as migration_cloud_smoke._prod_safety_gate."""
    if not apply_mode:
        return
    debug = bool(getattr(settings, "DEBUG", False))
    allowed = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
    looks_dev = any(
        (h or "").startswith("localhost")
        or (h or "").startswith("127.")
        or (h or "").endswith(".invalid")
        or (h or "") == "*"
        for h in allowed
    )
    if debug or looks_dev:
        return
    override = (
        os.environ.get("MIGRATION_CLOUD_SMOKE_ALLOW_PROD", "") or ""
    ).strip()
    if override == "1":
        return
    raise CommandError(
        "LIVE PROD DETECTED: --apply refused. DEBUG=False and "
        "ALLOWED_HOSTS contains no dev entries. Set "
        "MIGRATION_CLOUD_SMOKE_ALLOW_PROD=1 in env if you really "
        "intend to mutate prod (you almost certainly do not)."
    )


def _run_one_tenant(
    *,
    tenant: str,
    vendor: str,
    apply_mode: bool,
) -> dict[str, Any]:
    """Invoke migration_cloud_smoke for one tenant, capture results.

    Always returns a dict. Never raises — exceptions are recorded.
    """
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    started = time.monotonic()
    exit_code = 0
    err_type: str | None = None
    args = [f"--tenant={tenant}", f"--vendor={vendor}"]
    if apply_mode:
        args.append("--apply")
    try:
        with transaction.atomic():
            call_command(
                "migration_cloud_smoke",
                *args,
                stdout=buf_out,
                stderr=buf_err,
            )
    except SystemExit as sx:
        code = getattr(sx, "code", 0)
        try:
            exit_code = int(code) if code is not None else 0
        except (TypeError, ValueError):
            exit_code = 1
    except Exception as exc:  # pylint: disable=broad-except
        err_type = type(exc).__name__
        exit_code = 1
        logger.warning(
            "migration_cloud.smoke.multi.tenant_raised "
            "tenant_hash=%s err_type=%s",
            _hash_slug_prefix(tenant), err_type,
        )
    finally:
        # Drop the per-thread DB connection so it doesn't leak.
        try:
            connection.close()
        except Exception:  # pragma: no cover - defensive
            pass

    elapsed = time.monotonic() - started
    stdout_text = buf_out.getvalue()
    summary = _parse_summary_counts(stdout_text)
    if exit_code == 1:
        status = "FAIL"
    elif exit_code == 2:
        status = "SKIPPED"
    else:
        status = "PASS"
    return {
        "tenant": tenant,
        "tenant_hash": _hash_slug_prefix(tenant),
        "vendor": vendor,
        "status": status,
        "exit_code": int(exit_code),
        "duration_s": round(elapsed, 3),
        "sections_passed": int(summary["passed"]),
        "sections_failed": int(summary["failed"]),
        "sections_skipped": int(summary["skipped"]),
        "error_type": err_type,
    }


def _archive_path() -> Path:
    base = getattr(settings, "BASE_DIR", None)
    root = Path(base) / "var" if base is not None else Path("var")
    sub = root / "smoke-results-multi"
    try:
        sub.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    stamp = datetime.now(_dt_timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return sub / f"{stamp}.json"


def _emit_per_tenant_audit(row: dict[str, Any], apply_mode: bool) -> None:
    """Audit-emit one row's outcome."""
    try:
        from apps.migration_cloud.models_audit import (
            AuditEventRateLimitExceeded,
            MigrationCloudAuditEvent,
            MigrationCloudAuditEventType,
        )
    except Exception:  # pragma: no cover - audit module absent
        return
    valid = {c.value for c in MigrationCloudAuditEventType}
    event_type = "migration.smoke.multi_tenant_run"
    payload = {
        "vendor": row["vendor"],
        "apply": bool(apply_mode),
        "exit_code": int(row["exit_code"]),
        "sections_passed": int(row["sections_passed"]),
        "sections_failed": int(row["sections_failed"]),
        "sections_skipped": int(row["sections_skipped"]),
        "duration_s": float(row["duration_s"]),
        "error_type": row.get("error_type") or "",
    }
    if event_type not in valid:
        event_type = MigrationCloudAuditEventType.KEY_ROTATE.value
        payload["registered_choice_fallback"] = (
            "smoke_multi_tenant_event_unregistered"
        )
    try:
        MigrationCloudAuditEvent.objects.record(
            tenant_slug=row["tenant"],
            event_type=event_type,
            actor=None,
            subject=f"smoke-multi-{row['tenant_hash']}",
            payload_summary=payload,
        )
    except AuditEventRateLimitExceeded:
        logger.info(
            "migration_cloud.smoke.multi.audit_rate_limited "
            "tenant_hash=%s", row["tenant_hash"],
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.smoke.multi.per_tenant_audit_failed "
            "tenant_hash=%s err_type=%s",
            row["tenant_hash"], type(exc).__name__,
        )


def _emit_aggregate_audit(
    *,
    tenants_passed: int,
    tenants_failed: int,
    tenants_skipped: int,
    vendor: str,
    apply_mode: bool,
    duration_s: float,
) -> None:
    """One aggregate ``migration.smoke.multi_run_completed`` event."""
    try:
        from apps.migration_cloud.models_audit import (
            AuditEventRateLimitExceeded,
            MigrationCloudAuditEvent,
            MigrationCloudAuditEventType,
        )
    except Exception:
        return
    valid = {c.value for c in MigrationCloudAuditEventType}
    event_type = "migration.smoke.multi_run_completed"
    payload = {
        "vendor": vendor,
        "apply": bool(apply_mode),
        "tenants_passed": int(tenants_passed),
        "tenants_failed": int(tenants_failed),
        "tenants_skipped": int(tenants_skipped),
        "duration_s": float(round(duration_s, 3)),
    }
    if event_type not in valid:
        event_type = MigrationCloudAuditEventType.KEY_ROTATE.value
        payload["registered_choice_fallback"] = (
            "smoke_multi_aggregate_event_unregistered"
        )
    try:
        MigrationCloudAuditEvent.objects.record(
            tenant_slug="",  # aggregate event — no single tenant
            event_type=event_type,
            actor=None,
            subject="smoke-multi-aggregate",
            payload_summary=payload,
        )
    except AuditEventRateLimitExceeded:
        logger.info("migration_cloud.smoke.multi.aggregate_audit_rate_limited")
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.smoke.multi.aggregate_audit_failed err_type=%s",
            type(exc).__name__,
        )


# ──────────────────────────────────────────────────────────────────────
# Command
# ──────────────────────────────────────────────────────────────────────


class Command(BaseCommand):
    """Multi-tenant parallel Migration Cloud smoke."""

    help = (
        "Run the Migration Cloud end-to-end smoke against multiple "
        "synthetic tenants in parallel for staging soak testing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenants",
            required=True,
            type=str,
            help="Comma-separated tenant slugs (>=1, all unique).",
        )
        parser.add_argument(
            "--vendor",
            required=True,
            choices=list(_VENDOR_CHOICES),
            help="Vendor exercised by every tenant in this run.",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=4,
            help=(
                f"Parallel workers (default 4; HARD MAX "
                f"{CONCURRENCY_HARD_CAP}; values above are refused)."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Mutate. Default OFF (dry-run).",
        )
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            help="Cancel in-flight tenants after the first failure.",
        )

    def handle(self, *args, **options):
        tenants_raw = (options["tenants"] or "").strip()
        if not tenants_raw:
            raise CommandError("--tenants is required and non-empty")
        tenants = [
            t.strip() for t in tenants_raw.split(",") if t.strip()
        ]
        if not tenants:
            raise CommandError(
                "--tenants parsed to zero non-empty entries"
            )
        # Deduplicate while preserving order.
        seen: set[str] = set()
        ordered: list[str] = []
        for t in tenants:
            if t in seen:
                continue
            seen.add(t)
            ordered.append(t)
        tenants = ordered

        vendor = options["vendor"]
        # NB: distinguish an explicit 0 from a missing value. `x or 4` coerced
        # `--concurrency=0` to 4 (0 is falsy), so the `< 1` refusal below was
        # dead for zero — the exact value the DoS guard means to reject. argparse
        # supplies the default (4), so a None only happens if the key is absent.
        raw_concurrency = options.get("concurrency")
        concurrency = int(raw_concurrency) if raw_concurrency is not None else 4
        if concurrency < 1:
            raise CommandError(
                f"--concurrency must be >=1; got {concurrency}"
            )
        if concurrency > CONCURRENCY_HARD_CAP:
            raise CommandError(
                f"--concurrency exceeds hard cap "
                f"{CONCURRENCY_HARD_CAP}: refused ({concurrency} > "
                f"{CONCURRENCY_HARD_CAP})."
            )
        apply_mode = bool(options.get("apply"))
        fail_fast = bool(options.get("fail_fast"))

        _prod_safety_gate(apply_mode)

        results: list[dict[str, Any]] = []
        run_started = time.monotonic()
        # Use ThreadPoolExecutor so per-thread Django ORM access works.
        # max_workers clamped at min(concurrency, len(tenants)) so we
        # don't spin up idle threads.
        max_workers = min(concurrency, len(tenants))
        cancelled = False
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
        ) as pool:
            future_to_tenant: dict[
                concurrent.futures.Future, str,
            ] = {}
            for tenant in tenants:
                fut = pool.submit(
                    _run_one_tenant,
                    tenant=tenant,
                    vendor=vendor,
                    apply_mode=apply_mode,
                )
                future_to_tenant[fut] = tenant
            for fut in concurrent.futures.as_completed(future_to_tenant):
                if cancelled:
                    # We've requested cancel; still drain to gather
                    # whatever finished + record cancels for unstarted.
                    pass
                tenant = future_to_tenant[fut]
                try:
                    row = fut.result()
                except concurrent.futures.CancelledError:
                    row = {
                        "tenant": tenant,
                        "tenant_hash": _hash_slug_prefix(tenant),
                        "vendor": vendor,
                        "status": "CANCELLED",
                        "exit_code": 1,
                        "duration_s": 0.0,
                        "sections_passed": 0,
                        "sections_failed": 0,
                        "sections_skipped": 0,
                        "error_type": "CancelledError",
                    }
                except Exception as exc:  # pylint: disable=broad-except
                    row = {
                        "tenant": tenant,
                        "tenant_hash": _hash_slug_prefix(tenant),
                        "vendor": vendor,
                        "status": "FAIL",
                        "exit_code": 1,
                        "duration_s": 0.0,
                        "sections_passed": 0,
                        "sections_failed": 0,
                        "sections_skipped": 0,
                        "error_type": type(exc).__name__,
                    }
                results.append(row)
                _emit_per_tenant_audit(row, apply_mode=apply_mode)
                if fail_fast and row["status"] == "FAIL" and not cancelled:
                    cancelled = True
                    # Cancel everything else that hasn't started yet.
                    for other_fut in list(future_to_tenant):
                        if other_fut is fut:
                            continue
                        if not other_fut.done():
                            other_fut.cancel()

        run_duration = time.monotonic() - run_started

        # Aggregate counts.
        tenants_passed = sum(1 for r in results if r["status"] == "PASS")
        tenants_failed = sum(
            1 for r in results
            if r["status"] in ("FAIL", "CANCELLED")
        )
        tenants_skipped = sum(
            1 for r in results if r["status"] == "SKIPPED"
        )

        # Print the per-tenant table + aggregate.
        self._print_table(results, run_duration=run_duration)

        # Archive the JSON.
        archive_path = _archive_path()
        try:
            with open(archive_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "started_at_iso": datetime.now(
                            _dt_timezone.utc
                        ).isoformat(),
                        "vendor": vendor,
                        "apply": bool(apply_mode),
                        "fail_fast": bool(fail_fast),
                        "concurrency": int(concurrency),
                        "duration_s": round(run_duration, 3),
                        "tenants_total": len(tenants),
                        "tenants_passed": tenants_passed,
                        "tenants_failed": tenants_failed,
                        "tenants_skipped": tenants_skipped,
                        "rows": [
                            {k: v for k, v in r.items() if k != "tenant"}
                            for r in results
                        ],
                    },
                    fh,
                    sort_keys=True,
                    indent=2,
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"archive written: {archive_path}"
                )
            )
        except OSError as exc:
            self.stderr.write(
                self.style.WARNING(
                    f"archive write failed: {type(exc).__name__}"
                )
            )

        _emit_aggregate_audit(
            tenants_passed=tenants_passed,
            tenants_failed=tenants_failed,
            tenants_skipped=tenants_skipped,
            vendor=vendor,
            apply_mode=apply_mode,
            duration_s=run_duration,
        )

        # Exit code: 1 if any failed, 2 if any skipped, 0 otherwise.
        if tenants_failed > 0:
            sys.exit(1)
        if tenants_skipped > 0:
            sys.exit(2)
        sys.exit(0)

    def _print_table(
        self, results: list[dict[str, Any]], *, run_duration: float,
    ) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== migration_cloud_smoke_multi :: summary ==="
        ))
        header = (
            f"{'tenant_hash':<14} "
            f"{'status':<10} "
            f"{'dur_s':>7}  "
            f"{'pass':>4} "
            f"{'fail':>4} "
            f"{'skip':>4}  "
            f"err"
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for r in results:
            styler = self.style.SUCCESS
            if r["status"] in ("FAIL", "CANCELLED"):
                styler = self.style.ERROR
            elif r["status"] == "SKIPPED":
                styler = self.style.WARNING
            line = (
                f"{r['tenant_hash']:<14} "
                f"{r['status']:<10} "
                f"{r['duration_s']:>7.3f}  "
                f"{r['sections_passed']:>4} "
                f"{r['sections_failed']:>4} "
                f"{r['sections_skipped']:>4}  "
                f"{(r.get('error_type') or '-')[:32]}"
            )
            self.stdout.write(styler(line))
        self.stdout.write(
            f"total_duration_s={round(run_duration, 3)} "
            f"tenants={len(results)}"
        )


__all__ = ["Command", "CONCURRENCY_HARD_CAP"]
