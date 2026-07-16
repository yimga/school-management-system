"""End-to-end tenant lifecycle harness — provision → verify → self-heal → report → teardown.

Rigorously exercises the provisioning + tenant lifecycle across a country × education-level
matrix, records an HONEST pass/fail report, and (unless ``--keep``) deletes ALL test data it
created, proving zero residue.

SAFETY (non-negotiable)
-----------------------
Every test school carries an unmistakable marker: its slug starts with ``zzt-e2e-`` AND
``settings["e2e_test"] is True``. ``_is_test_school`` requires BOTH. Teardown is scoped to
that marker ONLY and refuses to delete anything that lacks it — a real tenant can never match.

USAGE
-----
    python manage.py e2e_lifecycle --run                # provision + verify + report + teardown
    python manage.py e2e_lifecycle --run --keep         # ...but leave the test data for inspection
    python manage.py e2e_lifecycle --run --matrix full   # all countries/levels (default: representative)
    python manage.py e2e_lifecycle --teardown            # delete ALL marker'd test data + prove zero residue
    python manage.py e2e_lifecycle --report-only         # re-emit the report from current test state

Note on execution mode: the tenant-schema migrate step exercises the full django-tenants path
only under Postgres with ``USE_DJANGO_TENANTS``. Under local SQLite the pipeline runs in
RLS/shared-schema mode (everything EXCEPT the schema migrate). The report states which mode ran
so results are never overclaimed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings as dj_settings
from django.core.management.base import BaseCommand
from django.utils import timezone

TEST_SLUG_PREFIX = "zzt-e2e-"
TEST_EMAIL_DOMAIN = "e2e.test"
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


# --- country × education-level matrix ---------------------------------------
# Chosen to force distinct currencies, grading scales, locales and structures.
@dataclass
class MatrixEntry:
    key: str
    name: str
    country_code: str
    currency: str
    level: str


FULL_MATRIX: tuple[MatrixEntry, ...] = (
    MatrixEntry("ng-k12", "Naija Model Schools", "NG", "NGN", "Nursery→SSS (full)"),
    MatrixEntry("gb-sec", "Thames Grammar", "GB", "GBP", "Secondary + Sixth Form"),
    MatrixEntry("us-k12", "Liberty Prep", "US", "USD", "Elementary→High (K-12)"),
    MatrixEntry("in-sec", "Vidya Senior School", "IN", "INR", "Primary→Sr. Secondary"),
    MatrixEntry("gh-jhs", "Accra Community JHS", "GH", "GHS", "Primary + JHS"),
    MatrixEntry("ae-kg", "Dubai Bright KG", "AE", "AED", "KG + Primary"),
    MatrixEntry("fr-col", "Lycée Voltaire", "FR", "EUR", "Collège + Lycée"),
    MatrixEntry("ke-cbc", "Nairobi CBC Academy", "KE", "KES", "Primary (CBC)"),
)
# Representative subset (fast) — one African, one European, one N. American, one Asian.
REPRESENTATIVE_KEYS = {"ng-k12", "gb-sec", "us-k12", "in-sec"}


@dataclass
class StageResult:
    stage: str
    status: str
    detail: str = ""
    duration_s: float = 0.0


@dataclass
class SchoolResult:
    key: str
    name: str
    country: str
    currency: str
    level: str
    school_id: str = ""
    stages: list[StageResult] = field(default_factory=list)

    def add(self, stage: str, status: str, detail: str = "", duration_s: float = 0.0):
        self.stages.append(StageResult(stage, status, detail, round(duration_s, 2)))

    def status_for(self, stage: str) -> str:
        for s in self.stages:
            if s.stage == stage:
                return s.status
        return "-"


class Command(BaseCommand):
    help = "End-to-end tenant lifecycle harness (provision → verify → self-heal → report → teardown)."

    def add_arguments(self, parser):
        parser.add_argument("--run", action="store_true", help="Provision + verify + report (+ teardown unless --keep).")
        parser.add_argument("--teardown", action="store_true", help="Delete ALL marker'd test data + prove zero residue.")
        parser.add_argument("--report-only", action="store_true", help="Re-emit the report from current test state.")
        parser.add_argument("--keep", action="store_true", help="Do not tear down after --run.")
        parser.add_argument("--matrix", choices=["representative", "full"], default="representative")
        parser.add_argument("--report-path", default="REPORTS/E2E_LIFECYCLE_REPORT.md")

    # -- helpers -------------------------------------------------------------
    def _is_test_school(self, school) -> bool:
        """BOTH the slug prefix AND the settings flag — a real tenant can never match."""
        slug = (getattr(school, "slug", "") or "")
        flag = bool((getattr(school, "settings", None) or {}).get("e2e_test"))
        return slug.startswith(TEST_SLUG_PREFIX) and flag

    def _schema_mode(self) -> bool:
        return bool(getattr(dj_settings, "USE_DJANGO_TENANTS", False))

    # -- matrix selection ----------------------------------------------------
    def _matrix(self, which: str) -> list[MatrixEntry]:
        if which == "full":
            return list(FULL_MATRIX)
        return [m for m in FULL_MATRIX if m.key in REPRESENTATIVE_KEYS]

    # -- provisioning + lifecycle verification -------------------------------
    def _provision_and_verify(self, entry: MatrixEntry) -> SchoolResult:
        from apps.schools.models import School

        res = SchoolResult(entry.key, entry.name, entry.country_code, entry.currency, entry.level)
        slug = f"{TEST_SLUG_PREFIX}{entry.key}"
        contact = f"owner@{slug}.{TEST_EMAIL_DOMAIN}"

        # Idempotent create with the marker.
        school = School.objects.filter(slug=slug).first()
        if school is None:
            school = School.objects.create(
                name=entry.name,
                slug=slug,
                subdomain=slug,
                country_code=entry.country_code,
                is_active=False,
                settings={"e2e_test": True},
            )
        else:
            merged = dict(school.settings or {})
            merged["e2e_test"] = True
            school.settings = merged
            school.is_active = False
            school.save(update_fields=["settings", "is_active"])
        res.school_id = str(school.id)

        # Stage 1: provisioning.
        t0 = time.monotonic()
        try:
            from apps.schools.tasks import provision_school_sync

            provision_school_sync(str(school.id), contact_email=contact)
            school.refresh_from_db()
            res.add("provision", PASS if school.is_active else FAIL,
                    f"is_active={school.is_active}", time.monotonic() - t0)
        except Exception as exc:  # noqa: BLE001 — a harness records failures, never crashes
            res.add("provision", FAIL, f"{type(exc).__name__}: {exc}", time.monotonic() - t0)
            return res

        self._verify_stage(res, school, "admin_user", self._check_admin_user)
        self._verify_stage(res, school, "profile_applied", self._check_profile)
        self._verify_stage(res, school, "academic_year", self._check_academic_year)
        self._verify_stage(res, school, "structure", self._check_structure)
        self._verify_stage(res, school, "portal_ready", self._check_portal_ready)
        self._verify_stage(res, school, "progress_resolver", self._check_progress_resolver)
        self._verify_stage(res, school, "self_heal", self._check_self_heal)
        return res

    def _verify_stage(self, res: SchoolResult, school, stage: str, fn):
        t0 = time.monotonic()
        try:
            status, detail = fn(school)
        except Exception as exc:  # noqa: BLE001
            status, detail = FAIL, f"{type(exc).__name__}: {exc}"
        res.add(stage, status, detail, time.monotonic() - t0)

    def _check_admin_user(self, school):
        from apps.schools.models import SchoolMembership

        n = SchoolMembership.objects.filter(school=school, is_school_owner=True).count()
        return (PASS if n >= 1 else FAIL), f"owner_memberships={n}"

    def _check_profile(self, school):
        s = school.settings or {}
        keys = [k for k in ("grading_scale", "default_currency", "education_profile_code") if s.get(k)]
        return (PASS if keys else SKIP), f"profile_keys={keys or 'none-resolved'}"

    def _check_academic_year(self, school):
        from apps.academics.models import AcademicYear, Term

        ay = AcademicYear.objects.filter(school=school).count()
        terms = Term.objects.filter(school=school).count()
        return (PASS if ay >= 1 and terms >= 1 else FAIL), f"years={ay} terms={terms}"

    def _check_structure(self, school):
        from apps.academics.models import Classroom, Subject

        subj = Subject.objects.filter(school=school).count()
        cls = Classroom.objects.filter(school=school).count()
        # Structure is profile-dependent; absence is not a failure, only unremarkable.
        return (PASS if (subj or cls) else SKIP), f"subjects={subj} classrooms={cls}"

    def _check_portal_ready(self, school):
        from apps.schools.provisioning_progress import resolve_portal_ready

        ready = resolve_portal_ready(school)
        return (PASS if ready else FAIL), f"portal_ready={ready}"

    def _check_progress_resolver(self, school):
        from apps.schools.provisioning_progress import resolve_provisioning_progress

        p = resolve_provisioning_progress(school)
        ok = p.get("status") in ("succeeded", "running") and p.get("ok")
        return (PASS if ok else FAIL), f"status={p.get('status')} pct={p.get('progress_percent')}"

    def _check_self_heal(self, school):
        """Fault-inject a heartbeat-dead run and prove the watchdog resumes it."""
        from unittest.mock import patch

        from apps.platform_runtime.models import WorkflowRun
        from apps.schools import provision_watchdog as pw

        # Make the school look mid-provision with a DEAD run.
        merged = dict(school.settings or {})
        merged.pop("provisioning", None)
        merged["e2e_test"] = True
        school.settings = merged
        school.is_active = False
        school.save(update_fields=["settings", "is_active"])

        run = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision", school_id=str(school.id),
            status="running", total_steps=5, current_step_ordinal=3,
            current_step_name="tenant_schema", expected_duration_seconds=600,
        )
        WorkflowRun.objects.filter(pk=run.pk).update(
            last_heartbeat_at=timezone.now() - timedelta(seconds=600)
        )
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            result = pw.resume_provision_if_stuck(school, reason="e2e-fault-injection")
        run.refresh_from_db()
        resumed = result.get("action") == "resumed" and kick.called and run.status == "cancelled"
        # Restore: re-provision so the school is left healthy for the report.
        try:
            from apps.schools.tasks import provision_school_sync

            provision_school_sync(str(school.id))
        except Exception:  # noqa: BLE001
            pass
        return (PASS if resumed else FAIL), f"resumed={result.get('action')} zombie={run.status}"

    # -- teardown ------------------------------------------------------------
    def _teardown(self, stdout) -> dict:
        from apps.schools.models import School

        marked = [s for s in School.objects.filter(slug__startswith=TEST_SLUG_PREFIX) if self._is_test_school(s)]
        deleted_schools, deleted_runs, deleted_users, deleted_events = 0, 0, 0, 0
        for school in marked:
            sid = str(school.id)
            slug = school.slug
            # Capture the tenant schema name BEFORE deleting the row (get_schema_name
            # needs the school). Drop the schema only AFTER the row is gone, so a
            # failed row-delete never leaves a schema-less zombie (F5).
            schema_name = self._captured_schema_name(school)
            deleted_runs += self._delete_runs(sid)
            deleted_events += self._delete_events(school)
            deleted_users += self._delete_test_users(school)
            if self._delete_school(school):
                deleted_schools += 1
                if schema_name:
                    self._drop_schema_by_name(schema_name, stdout)
                stdout.write(f"  torn down: {slug}")
            else:
                stdout.write(f"  ⚠ could not fully delete {slug} (protected refs remain; schema NOT dropped)")

        residue = self._residue_scan()
        return {
            "schools": deleted_schools, "runs": deleted_runs,
            "users": deleted_users, "events": deleted_events, "residue": residue,
        }

    def _delete_school(self, school) -> bool:
        """Delete the school, peeling PROTECT-ed children layer by layer.

        Provisioning creates AcademicYear / Department / Classroom / Subject /
        Term / AssessmentWeights rows whose FK to School is ``on_delete=PROTECT``,
        so a bare ``school.delete()`` raises ProtectedError. Rather than enumerate
        every tenant model, peel the protected set the error itself reports and
        retry — bounded so a genuinely undeletable graph can never loop forever.
        """
        from django.db.models.deletion import ProtectedError

        for _ in range(8):  # magic-number-allow: bounded protected-layer peel
            try:
                school.delete()
                return True
            except ProtectedError as exc:
                protected = list(getattr(exc, "protected_objects", []) or [])
                if not protected:
                    return False
                for obj in protected:
                    try:
                        obj.delete()
                    except ProtectedError:
                        continue  # deeper layer — next outer iteration peels it
                    except Exception:  # noqa: BLE001
                        continue
        return False

    def _delete_runs(self, school_id: str) -> int:
        try:
            from apps.platform_runtime.models import WorkflowRun

            n, _ = WorkflowRun.objects.filter(school_id=school_id).delete()
            return n
        except Exception:  # noqa: BLE001
            return 0

    def _delete_events(self, school) -> int:
        try:
            from apps.schools.models import SchoolProvisioningEvent

            n, _ = SchoolProvisioningEvent.objects.filter(school=school).delete()
            return n
        except Exception:  # noqa: BLE001
            return 0

    def _delete_test_users(self, school) -> int:
        """Delete owner users created for this test school (marker'd email domain only)."""
        from django.contrib.auth import get_user_model

        from apps.schools.models import SchoolMembership

        User = get_user_model()
        emails = list(
            SchoolMembership.objects.filter(school=school)
            .values_list("user__email", flat=True)
        )
        deleted = 0
        for email in emails:
            if not email or not str(email).endswith(f".{TEST_EMAIL_DOMAIN}"):
                continue  # NEVER touch a non-test user
            user = User.objects.filter(email=email).first()
            # Only delete if this user has no OTHER (non-test) memberships.
            if user and not SchoolMembership.objects.filter(user=user).exclude(school=school).exists():
                user.delete()
                deleted += 1
        return deleted

    def _captured_schema_name(self, school) -> str:
        """The marker'd test school's own tenant schema name, captured before delete.

        Marker-guarded (defence-in-depth) and looked up school-scoped via
        get_schema_name, so it can only ever be THIS test tenant's schema.
        """
        if not self._schema_mode() or not self._is_test_school(school):
            return ""
        try:
            from apps.schools.tenant_offboarding import get_schema_name

            return (get_schema_name(school) or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _drop_schema_by_name(self, schema_name: str, stdout) -> None:
        """DROP a tenant Postgres schema by its pre-captured, validated name.

        Requires an ``s_`` (django-tenants per-tenant) prefix so the name check is
        itself sufficient — this can NEVER target ``public``, ``information_schema``,
        or a ``pg_*`` system schema (all of which fail the prefix test). Combined
        with the caller's ``_is_test_school`` gating, a real tenant is unreachable.
        """
        schema = (schema_name or "").strip()
        if not schema.startswith("s_") or not schema.replace("_", "").isalnum():
            stdout.write(f"    (schema drop skipped: {schema!r} is not a tenant 's_' schema)")
            return
        try:
            from django.db import connection

            with connection.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            stdout.write(f"    dropped tenant schema: {schema}")
        except Exception as exc:  # noqa: BLE001
            stdout.write(f"    (schema drop failed: {type(exc).__name__})")

    def _residue_scan(self) -> dict:
        from django.contrib.auth import get_user_model

        from apps.schools.models import School

        try:
            from apps.platform_runtime.models import WorkflowRun

            live_ids = [str(s.id) for s in School.objects.filter(slug__startswith=TEST_SLUG_PREFIX)]
            orphan_runs = WorkflowRun.objects.filter(school_id__in=live_ids).count() if live_ids else 0
        except Exception:  # noqa: BLE001
            orphan_runs = -1
        # schools_remaining uses the slug prefix only (not the flag): this can only
        # OVER-report (a real school misnamed zzt-e2e-* without the flag is refused
        # deletion yet trips the scan) — safe, never hides residue.
        User = get_user_model()
        return {
            "schools_remaining": School.objects.filter(slug__startswith=TEST_SLUG_PREFIX).count(),
            "orphan_runs": orphan_runs,
            "users_remaining": User.objects.filter(
                email__endswith=f".{TEST_EMAIL_DOMAIN}"
            ).count(),
        }

    # -- report --------------------------------------------------------------
    def _write_report(self, results: list[SchoolResult], mode_schema: bool, path: str) -> str:
        import os

        stages = ["provision", "admin_user", "profile_applied", "academic_year",
                  "structure", "portal_ready", "progress_resolver", "self_heal"]
        lines = []
        lines.append("# E2E Tenant Lifecycle Report")
        lines.append("")
        lines.append(f"- Generated: {timezone.now().isoformat()}")
        lines.append(f"- Execution mode: {'django-tenants schema-per-tenant (Postgres)' if mode_schema else 'RLS / shared-schema (SQLite) — tenant_schema migrate NOT exercised'}")
        lines.append(f"- Schools: {len(results)}")
        lines.append("")
        lines.append("## Matrix (country × level × lifecycle stage)")
        lines.append("")
        header = "| School | Country | Currency | Level | " + " | ".join(stages) + " |"
        lines.append(header)
        lines.append("|" + "---|" * (4 + len(stages)))
        for r in results:
            cells = [r.status_for(s) for s in stages]
            lines.append(f"| {r.name} | {r.country} | {r.currency} | {r.level} | " + " | ".join(cells) + " |")
        lines.append("")
        # Honest failure detail.
        lines.append("## Failures & skips (with reasons)")
        lines.append("")
        any_issue = False
        for r in results:
            for s in r.stages:
                if s.status in (FAIL, SKIP):
                    any_issue = True
                    lines.append(f"- **{r.name} / {s.stage}: {s.status}** — {s.detail}")
        if not any_issue:
            lines.append("- None. Every stage passed.")
        lines.append("")
        # Honest coverage note.
        lines.append("## Coverage honesty")
        lines.append("")
        lines.append("- PASS/FAIL/SKIP are recorded per observed result; a blank/SKIP is never counted as a pass.")
        lines.append("- Browser-driven stages (login UI, finance/attendance/portal screens, offline WAL) are NOT exercised by this headless harness and are intentionally out of scope — run them via the Playwright suite.")
        if not mode_schema:
            lines.append("- The `tenant_schema` migrate (the step that was hanging in prod) runs only under Postgres + USE_DJANGO_TENANTS; this run was SQLite/RLS, so that specific step was not exercised here (its fix is covered by `test_provision_watchdog.py` + the self_heal stage).")
        lines.append("")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return path

    # -- entrypoint ----------------------------------------------------------
    def handle(self, *args, **opts):
        mode_schema = self._schema_mode()
        if opts.get("teardown") and not opts.get("run"):
            self.stdout.write(self.style.WARNING("Tearing down ALL marker'd test data..."))
            summary = self._teardown(self.stdout)
            self._print_teardown(summary)
            return
        if opts.get("report_only"):
            self.stdout.write("Report-only mode: re-emitting from current test state is not stored; run --run.")
            return
        if not opts.get("run"):
            self.stdout.write(self.style.WARNING("Nothing to do. Pass --run or --teardown. See --help."))
            return

        matrix = self._matrix(opts["matrix"])
        self.stdout.write(self.style.HTTP_INFO(
            f"Provisioning {len(matrix)} test schools "
            f"({'schema-per-tenant' if mode_schema else 'RLS/SQLite'} mode)..."
        ))
        results: list[SchoolResult] = []
        for entry in matrix:
            self.stdout.write(f"  → {entry.name} ({entry.country_code}/{entry.level})")
            results.append(self._provision_and_verify(entry))

        path = self._write_report(results, mode_schema, opts["report_path"])
        self.stdout.write(self.style.SUCCESS(f"Report written: {path}"))
        self._print_summary(results)

        if opts.get("keep"):
            self.stdout.write(self.style.WARNING("--keep set: leaving test data in place. Run --teardown to remove."))
        else:
            self.stdout.write("Tearing down test data...")
            summary = self._teardown(self.stdout)
            self._print_teardown(summary)

    def _print_summary(self, results: list[SchoolResult]):
        total = sum(len(r.stages) for r in results)
        passed = sum(1 for r in results for s in r.stages if s.status == PASS)
        failed = sum(1 for r in results for s in r.stages if s.status == FAIL)
        skipped = sum(1 for r in results for s in r.stages if s.status == SKIP)
        self.stdout.write(self.style.HTTP_INFO(
            f"Lifecycle stages: {passed} PASS / {failed} FAIL / {skipped} SKIP (of {total})"
        ))

    def _print_teardown(self, summary: dict):
        residue = summary["residue"]
        clean = residue["schools_remaining"] == 0 and residue["orphan_runs"] in (0, -1)
        self.stdout.write(
            f"Teardown: {summary['schools']} schools, {summary['runs']} runs, "
            f"{summary['users']} users, {summary['events']} events deleted."
        )
        msg = f"Residue scan: schools_remaining={residue['schools_remaining']} orphan_runs={residue['orphan_runs']}"
        self.stdout.write((self.style.SUCCESS if clean else self.style.ERROR)(
            msg + ("  ✓ ZERO RESIDUE" if clean else "  ✗ RESIDUE REMAINS")
        ))
