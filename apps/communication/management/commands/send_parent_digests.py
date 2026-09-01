"""Periodic parent digest (daily/weekly) — Phase 4.

Builds a REAL per-student digest for each eligible guardian from live facts
(outstanding fee balance, new grades, attendance flags, unread messages),
narrates it with the AI gateway when available, and ALWAYS falls back to a
deterministic HTML+text template when AI is off/unconfigured/ungrounded — a
digest is never blocked on AI.

Cadence matching (NotificationPreference.digest_cadence):
    * ``--cadence weekly`` (default): only guardians whose pref cadence is
      WEEKLY *or* who have no preference row (WEEKLY is the digest default).
    * ``--cadence daily``: only guardians whose pref cadence is DAILY.
    * IMMEDIATE-cadence guardians are skipped on both runs — "immediate" means
      they get real-time notifications, not a batched digest.
    * A guardian with no pref row who unticked "Send me a weekly summary on
      Friday afternoon." (``siteconfig.UserPreference.receive_weekly_summary``,
      the only digest control any user is shown) is skipped on the weekly run.

Honesty: a guardian whose digest would have NO facts is skipped (no hollow
"nothing happened" email). Sends are failure-isolated per guardian; we only
count ``sent`` when the email facade reports success.

Dedupe: there is no ``last_digest_sent_at`` field on NotificationPreference or
StudentGuardian, so frequency is controlled by the cron cadence (the periodic
job fires this once per period). Within a single run we also de-duplicate by
``guardian_user`` so a parent linked to several students receives ONE combined
email, not one per child.

    python manage.py send_parent_digests                       # weekly, dry-run
    python manage.py send_parent_digests --cadence daily        # daily, dry-run
    python manage.py send_parent_digests --cadence weekly --apply
    python manage.py send_parent_digests --school <id> --apply  # scope to one tenant
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from html import escape

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

_ZERO = Decimal("0.00")

# Period length per cadence. The cutoff is "now minus this many days"; the
# digest only counts facts that landed inside the window.
_CADENCE_DAYS = {"daily": 1, "weekly": 7}


@dataclass
class _StudentFacts:
    """Live facts for one student over the digest period."""

    name: str
    outstanding_balance: Decimal = _ZERO  # money is Decimal, never float
    new_grades: int = 0
    absences: int = 0
    lates: int = 0
    unread_messages: int = 0

    def has_signal(self) -> bool:
        """True if anything worth telling the parent happened this period."""
        return bool(
            self.outstanding_balance > _ZERO
            or self.new_grades
            or self.absences
            or self.lates
            or self.unread_messages
        )


@dataclass
class _GuardianDigest:
    """Accumulated facts for one guardian (may cover several students)."""

    email: str
    school: object
    students: list[_StudentFacts] = field(default_factory=list)

    def has_signal(self) -> bool:
        return any(s.has_signal() for s in self.students)


def _outstanding_balance_for_student(student, school) -> Decimal:
    """Sum of unpaid AR invoice balances for one student (Decimal, tenant-scoped)."""
    try:
        from apps.finance.models import Invoice
    except Exception:  # noqa: BLE001 — finance app optional in some deploys
        return _ZERO
    total = _ZERO
    # tenant-isolation-allow: student-and-school-both-filtered explicitly
    qs = (
        Invoice.objects.filter(student=student, school=school)
        .filter(invoice_type=Invoice.InvoiceType.AR)
        .exclude(status__in=[Invoice.Status.PAID, Invoice.Status.VOID])
        .filter(deleted_at__isnull=True)
    )
    for inv in qs:
        # computed_balance is a Decimal property (total_amount - received
        # payments), so we never float() a money value (scan_money_float gate).
        bal = getattr(inv, "computed_balance", None)
        if isinstance(bal, Decimal):
            total += bal
    return total


def _new_grades_for_student(student, school, cutoff) -> int:
    """Count of evaluations created for the student in the period (tenant-scoped)."""
    try:
        from apps.evals.models import Evaluation
    except Exception:  # noqa: BLE001
        return 0
    # tenant-isolation-allow: student-and-school-both-filtered explicitly
    return Evaluation.objects.filter(
        student=student, school=school, created_at__gte=cutoff
    ).count()


def _attendance_flags_for_student(student, school, cutoff_date) -> tuple[int, int]:
    """(absences, lates) for the student in the period (tenant-scoped)."""
    try:
        from apps.academics.models import Attendance
    except Exception:  # noqa: BLE001
        return (0, 0)
    # tenant-isolation-allow: student-and-school-both-filtered explicitly
    base = Attendance.objects.filter(
        student=student, school=school, date__gte=cutoff_date
    )
    absences = base.filter(status=Attendance.Status.ABSENT).count()
    lates = base.filter(status=Attendance.Status.LATE).count()
    return (absences, lates)


def _unread_messages_for_guardian(guardian_user) -> int:
    """Count of unread internal messages addressed to the guardian user."""
    if guardian_user is None:
        return 0
    try:
        from apps.communication.models import Message
    except Exception:  # noqa: BLE001
        return 0
    # tenant-isolation-allow: recipient-is-the-guardian-user-themselves
    return Message.objects.filter(recipient=guardian_user, is_read=False).count()


def _resolve_email(link) -> str:
    """Best email for a guardian link: the link's email, then the user's."""
    email = (getattr(link, "email", "") or "").strip()
    if email:
        return email
    user = getattr(link, "guardian_user", None)
    return (getattr(user, "email", "") or "").strip() if user else ""


def _cadence_matches(
    pref, run_cadence: str, *, weekly_summary_optin: bool = True
) -> bool:
    """Whether a guardian on ``pref`` should receive this run's digest.

    No preference row → defaults to WEEKLY. IMMEDIATE never matches a digest.

    ``weekly_summary_optin`` is the "Send me a weekly summary on Friday
    afternoon." checkbox on accounts:notification_preferences
    (``siteconfig.UserPreference.receive_weekly_summary``). It is the ONLY digest
    control a user is ever shown, and nothing on the platform writes a
    ``NotificationPreference`` row — so reading only ``digest_cadence`` meant the
    box the parent unticked was written by the screen and read by no sender.
    A stored ``NotificationPreference`` still wins: an explicit granular choice
    outranks the coarse checkbox, the same precedence ``dispatch.get_preference``
    uses.
    """
    from apps.communication.models import NotificationPreference

    if pref is None:
        return run_cadence == "weekly" and weekly_summary_optin
    cadence = (pref.digest_cadence or "").strip().lower()
    if cadence == NotificationPreference.Cadence.IMMEDIATE:
        return False
    if not cadence:
        return run_cadence == "weekly" and weekly_summary_optin
    return cadence == run_cadence


def _fmt_money(amount: Decimal) -> str:
    """Format a Decimal balance without ever calling float()."""
    return f"{amount.quantize(Decimal('0.01'))}"


class Command(BaseCommand):
    help = "Send daily/weekly parent digests built from real per-student facts (Phase 4)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cadence",
            choices=sorted(_CADENCE_DAYS),
            default="weekly",
            help="Digest cadence to run (default: weekly). Only matching guardians are sent.",
        )
        parser.add_argument(
            "--school",
            type=int,
            default=None,
            help="Optional: scope to a single school id (default: all schools).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually send. Without this flag the command is a dry-run.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=2000,
            help="Max guardian links to scan (safety cap).",
        )

    def handle(self, *args, **options):
        """Run the digest once PER TENANT SCHEMA, not once on whatever schema we land in.

        Every table this command reads -- StudentGuardian, NotificationPreference,
        Message, Invoice, Evaluation, Attendance -- belongs to a TENANT_APP, so under
        ``USE_DJANGO_TENANTS`` it exists only inside a tenant schema. A management
        command has no request, so django-tenants never binds one and the connection
        sits on ``public``. ``periodic.run_job`` calls this with no schema context
        either -- the same hole ``advance_running_batches`` documents in
        ``apps/people/school_batch_service.py`` after it silently stopped advancing
        every batch, every tick.

        The failure is worse HERE than there, in one specific way: this command sends
        mail. Reading the wrong schema does not merely do nothing -- it decides who is
        a guardian, and it can only be wrong quietly, because a digest with no facts is
        skipped by design and a run that found nobody prints a clean summary of zeros.

        ``tenant_sweep_schema_names`` returns ``[None]`` when tenants are off, so a
        sovereign box (RLS, one schema) enters no context and behaves exactly as
        before. ``limit`` stays the budget for the WHOLE run, shared across schemas --
        it is a safety cap on work done, and multiplying it by the tenant count would
        quietly turn a 2000-row cap into 2000-per-tenant.
        """
        from contextlib import nullcontext

        from apps.people.transfer_service import tenant_sweep_schema_names

        run_cadence = options["cadence"]
        apply = bool(options.get("apply"))
        limit = int(options.get("limit") or 2000)
        school_id = options.get("school")

        try:
            from django_tenants.utils import schema_context
        except ImportError:  # single-schema deployment; the sweep is a no-op
            schema_context = None

        totals = {
            "scanned": 0,
            "cadence_skipped": 0,
            "no_email": 0,
            "eligible": 0,
            "sent": 0,
            "empty_skipped": 0,
            "errored": 0,
        }
        schemas = schemas_failed = 0
        budget = limit

        for schema_name in tenant_sweep_schema_names():
            if budget <= 0:
                break
            try:
                # BUILDING the context is inside the try, not just entering it. A factory that
                # raises would otherwise escape the guard entirely -- which my own test caught,
                # and which for redrive would have broken the NEVER-raises contract outright.
                ctx = (
                    schema_context(schema_name)
                    if (schema_name and schema_context is not None)
                    else nullcontext()
                )
                with ctx:
                    result = self._run_for_schema(
                        run_cadence=run_cadence,
                        apply=apply,
                        budget=budget,
                        school_id=school_id,
                    )
            except Exception:  # noqa: BLE001 -- one bad tenant must not starve the rest
                schemas_failed += 1
                logger.exception(
                    "send_parent_digests: schema=%s failed", schema_name or "(current)"
                )
                continue
            schemas += 1
            budget -= int(result.get("scanned") or 0)
            for key in totals:
                totals[key] += int(result.get(key) or 0)

        # schemas / schemas_failed are printed even at zero. A tenant that raised is the
        # only thing separating "nobody was eligible" from "we never looked", and those
        # two read identically in a summary of zeros.
        self.stdout.write(
            "parent_digests "
            f"cadence={run_cadence} mode={'apply' if apply else 'dry-run'} "
            f"schemas={schemas} schemas_failed={schemas_failed} "
            f"scanned={totals['scanned']} cadence_skipped={totals['cadence_skipped']} "
            f"no_email={totals['no_email']} eligible_guardians={totals['eligible']} "
            f"sent={totals['sent']} empty_skipped={totals['empty_skipped']} "
            f"errored={totals['errored']}"
        )

    def _run_for_schema(self, *, run_cadence, apply, budget, school_id):
        """One digest pass on the CURRENT connection. Caller owns the schema."""
        from apps.communication.models import NotificationPreference
        from apps.people.models import StudentGuardian

        now = timezone.now()
        cutoff = now - timezone.timedelta(days=_CADENCE_DAYS[run_cadence])
        cutoff_date = cutoff.date()

        links = (
            StudentGuardian.objects.filter(is_active=True, receives_email=True)
            .select_related("guardian_user", "student", "student__school")
        )
        if school_id is not None:
            # tenant-isolation-allow: operator-supplied-school-scope-filter
            links = links.filter(student__school_id=school_id)
        links = links.order_by("guardian_user_id", "id")[:budget]

        # Preload preferences for the guardians we touch (avoid N+1 + repeated
        # DoesNotExist). One row per user (OneToOne).
        guardian_ids = {
            link.guardian_user_id for link in links if link.guardian_user_id
        }
        prefs_by_user = {
            p.user_id: p
            for p in NotificationPreference.objects.filter(user_id__in=guardian_ids)
        }
        # The weekly-summary checkbox the parent actually ticks. Absent row →
        # True (the model default), so a guardian who never opened the screen is
        # unaffected; a read error fails OPEN for the same reason.
        try:
            from apps.siteconfig.models_tooling import UserPreference

            weekly_optin_by_user = {
                row.user_id: bool(row.receive_weekly_summary)
                for row in UserPreference.objects.filter(
                    user_id__in=guardian_ids
                ).only("user_id", "receive_weekly_summary")
            }
        except Exception:  # noqa: BLE001 — a preferences blip never blocks a digest
            logger.warning(
                "send_parent_digests: weekly-summary preference read failed",
                exc_info=True,
            )
            weekly_optin_by_user = {}

        # Accumulate facts per guardian_user so a parent of several children
        # gets ONE combined email (in-run dedupe).
        digests: "OrderedDict[int, _GuardianDigest]" = OrderedDict()
        scanned = cadence_skipped = no_email = 0

        for link in links:
            guardian_user = getattr(link, "guardian_user", None)
            student = getattr(link, "student", None)
            if student is None:
                continue
            school = getattr(student, "school", None)
            if school is None:
                continue
            scanned += 1

            guardian_pk = getattr(guardian_user, "pk", None)
            pref = prefs_by_user.get(guardian_pk)
            if not _cadence_matches(
                pref,
                run_cadence,
                weekly_summary_optin=weekly_optin_by_user.get(guardian_pk, True),
            ):
                cadence_skipped += 1
                continue

            email = _resolve_email(link)
            if not email:
                no_email += 1
                continue

            facts = self._facts_for_student(student, school, cutoff, cutoff_date, guardian_user)
            if not facts.has_signal():
                # Honesty: don't pad the digest with an empty student.
                continue

            key = getattr(guardian_user, "pk", None) or f"link:{link.pk}"
            digest = digests.get(key)
            if digest is None:
                digest = _GuardianDigest(email=email, school=school)
                digests[key] = digest
            digest.students.append(facts)

        sent = empty_skipped = errored = 0
        for key, digest in digests.items():
            if not digest.has_signal():
                empty_skipped += 1
                continue
            try:
                ok = self._send_digest(digest, run_cadence, apply=apply)
            except Exception as exc:  # noqa: BLE001 — never abort the run for one parent
                errored += 1
                logger.warning(
                    "send_parent_digests: guardian=%s failed err=%s",
                    key, type(exc).__name__,
                )
                continue
            if ok:
                sent += 1
            else:
                # Honest tally: facade reported failure → not "sent".
                errored += 1

        return {
            "scanned": scanned,
            "cadence_skipped": cadence_skipped,
            "no_email": no_email,
            "eligible": len(digests),
            "sent": sent,
            "empty_skipped": empty_skipped,
            "errored": errored,
        }

    # -- fact gathering --------------------------------------------------

    def _facts_for_student(self, student, school, cutoff, cutoff_date, guardian_user) -> _StudentFacts:
        name = (
            getattr(student, "get_full_name", lambda: "")()
            or getattr(student, "first_name", "")
            or f"#{getattr(student, 'pk', '?')}"
        )
        facts = _StudentFacts(name=name)
        facts.outstanding_balance = _outstanding_balance_for_student(student, school)
        facts.new_grades = _new_grades_for_student(student, school, cutoff)
        facts.absences, facts.lates = _attendance_flags_for_student(
            student, school, cutoff_date
        )
        facts.unread_messages = _unread_messages_for_guardian(guardian_user)
        return facts

    # -- rendering -------------------------------------------------------

    def _fact_lines(self, facts: _StudentFacts) -> list[str]:
        """Plain-text fact lines for one student (only non-empty signals)."""
        lines: list[str] = []
        if facts.outstanding_balance > _ZERO:
            lines.append(f"Outstanding fee balance: {_fmt_money(facts.outstanding_balance)}")
        if facts.new_grades:
            lines.append(f"New grades this period: {facts.new_grades}")
        if facts.absences:
            lines.append(f"Absences this period: {facts.absences}")
        if facts.lates:
            lines.append(f"Late arrivals this period: {facts.lates}")
        if facts.unread_messages:
            lines.append(f"Unread messages in your inbox: {facts.unread_messages}")
        return lines

    def _template_bodies(self, digest: _GuardianDigest, run_cadence: str) -> tuple[str, str]:
        """Deterministic (text, html) digest from facts — the always-available path."""
        school_name = getattr(digest.school, "name", "") or "your school"
        period = "this week" if run_cadence == "weekly" else "today"
        text_parts = [f"Update from {school_name} ({period}):", ""]
        html_parts = [
            f"<p>Update from <strong>{escape(school_name)}</strong> ({escape(period)}):</p>"
        ]
        for student in digest.students:
            lines = self._fact_lines(student)
            if not lines:
                continue
            text_parts.append(student.name)
            text_parts.extend(f"  - {ln}" for ln in lines)
            text_parts.append("")
            html_parts.append(f"<h3>{escape(student.name)}</h3>")
            html_parts.append(
                "<ul>" + "".join(f"<li>{escape(ln)}</li>" for ln in lines) + "</ul>"
            )
        text_parts.append("Log in to your parent portal for full details.")
        html_parts.append(
            "<p>Log in to your parent portal for full details.</p>"
        )
        return ("\n".join(text_parts).strip() + "\n", "".join(html_parts))

    def _narrate(self, digest: _GuardianDigest, run_cadence: str, text_body: str) -> str:
        """Optional AI narration; returns '' to fall back to the template."""
        try:
            from services.ai_helpers import invoke_with_request
        except ImportError:
            return ""
        period = "this week" if run_cadence == "weekly" else "today"
        school_name = getattr(digest.school, "name", "") or "your school"
        prompt = (
            "You are writing a short, warm digest email to a parent from their "
            f"child's school ({school_name}). Summarise the facts below for "
            f"{period} in 2-4 friendly sentences. Be accurate; do NOT invent any "
            "numbers, names, or events beyond the facts. If there is a fee "
            "balance, mention it gently. Facts:\n\n" + text_body
        )
        try:
            result = invoke_with_request(
                task_type="NARRATIVE",
                prompt=prompt,
                school=digest.school,
                metadata={"audience": "parents", "surface": "parent_digest"},
                require_available=False,
            )
        except Exception as exc:  # noqa: BLE001 — never fail the digest on gateway error
            logger.debug("send_parent_digests: AI narrate failed err=%s", type(exc).__name__)
            return ""
        if result is None:
            return ""
        try:
            response, _meta = result
        except (TypeError, ValueError):
            response = result
        return str(response or "").strip()

    def _send_digest(self, digest: _GuardianDigest, run_cadence: str, *, apply: bool) -> bool:
        from apps.communication.notification_service import send_email

        school_name = getattr(digest.school, "name", "") or "your school"
        period_label = "Weekly" if run_cadence == "weekly" else "Daily"
        subject = f"{period_label} update from {school_name}"

        text_body, html_body = self._template_bodies(digest, run_cadence)

        # Prefer AI narration; ALWAYS keep the deterministic template as the
        # body of record so the facts are present even alongside narration.
        narrative = self._narrate(digest, run_cadence, text_body)
        if narrative:
            text_body = narrative + "\n\n" + text_body
            html_body = f"<p>{escape(narrative)}</p>" + html_body

        if not apply:
            # Dry-run: render but do not send. Report as "would send" success.
            logger.info(
                "send_parent_digests[dry-run] to=%s subject=%s",
                digest.email, subject,
            )
            return True

        # send_email routes through the reliability layer, which gates the
        # suppression list and audits delivery; tenant-scoped via school.
        return bool(
            send_email(
                to_addresses=[digest.email],
                subject=subject,
                body=text_body,
                html_message=html_body,
                school=digest.school,
                fail_silently=True,
            )
        )
