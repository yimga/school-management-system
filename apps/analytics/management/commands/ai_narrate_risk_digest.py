"""Generate an AI-narrated risk digest per school per night.

Picks the top-N at-risk students (highest `RiskFactor.score` in
last 24 hours), composes a short prompt with their score / band /
top contribution, and asks the AI gateway for a 2-3 sentence
intervention-shaped narrative the operator can put in a Slack /
email summary.

Falls back to a plain bullet list when the AI gateway is unavailable
— this command must NEVER fail the nightly batch.

The output is NOT persisted into a new table; it goes to stdout (and
optionally a file via `--out`). Persistence is a follow-up: the obvious
home is `CommunicationTemplate` (shipped v2.13) so operators can
schedule it as a periodic email. That's a UI/wiring job, not new model
work.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.analytics.models import RiskFactor
from apps.analytics.tenant_batch import run_for_school
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.ai_narrate_risk_digest")

_DEFAULT_TOP_N = 5

# Mapping from BCP-47 / ISO-639 codes to the natural-language name the
# LLM responds best to. Keep short; the prompt is small.
_LANGUAGE_LABELS = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "sw": "Swahili",
    "ha": "Hausa",
    "yo": "Yoruba",
    "ar": "Arabic",
}


def _resolve_language_code(school) -> str:
    """Return the language code to render the digest in.

    Precedence:
      1. School's `default_region.default_language` if set
      2. Django `LANGUAGE_CODE` setting (project default)
      3. Hard-coded "en"
    """
    region = getattr(school, "default_region", None)
    if region is not None:
        lang = (getattr(region, "default_language", "") or "").strip()
        if lang:
            return lang.split("-", 1)[0].lower()
    from django.conf import settings
    fallback = (getattr(settings, "LANGUAGE_CODE", "") or "en").strip()
    return fallback.split("-", 1)[0].lower()


def _language_label(code: str) -> str:
    return _LANGUAGE_LABELS.get(code, code.upper() if code else "English")


class Command(BaseCommand):
    help = "Generate an AI-narrated digest of today's top at-risk students."

    def add_arguments(self, parser):
        parser.add_argument("--school", type=str, required=True)
        parser.add_argument("--top-n", type=int, default=_DEFAULT_TOP_N)
        parser.add_argument(
            "--out", default=None,
            help="Optional output file path; otherwise prints to stdout.",
        )

    def handle(self, *args, **opts):
        try:
            school = School.objects.get(slug=opts["school"])
        except School.DoesNotExist:
            school = School.objects.filter(id=opts["school"]).first()
        if not school:
            self.stderr.write(self.style.ERROR(f"No school '{opts['school']}'."))
            return

        # RiskFactor is a TENANT_APPS table: read it inside the school's tenant
        # context or the digest is empty for every school on a cloud deployment.
        return run_for_school(
            school,
            lambda: self._emit_digest(school, opts),
            label="ai_narrate_risk_digest",
        )

    def _emit_digest(self, school, opts):
        cutoff = timezone.now() - timezone.timedelta(days=1)
        top = list(
            RiskFactor.objects.filter(
                school=school, computed_at__gte=cutoff,
            )
            .select_related("student")
            .order_by("-score")[:opts["top_n"]]
        )
        if not top:
            self.stdout.write(f"No fresh risk rows in last 24h for {school.slug}.")
            return

        bullets = self._fact_bullets(top)
        narrative = self._narrate(school, bullets, top=top)
        digest = self._format_digest(school, bullets, narrative)

        if opts.get("out"):
            Path(opts["out"]).parent.mkdir(parents=True, exist_ok=True)
            Path(opts["out"]).write_text(digest)
            self.stdout.write(self.style.SUCCESS(f"Wrote {opts['out']}"))
        else:
            self.stdout.write(digest)

    def _fact_bullets(self, top) -> list[str]:
        bullets = []
        for rf in top:
            student = rf.student
            name = f"{student.first_name} {student.last_name}".strip() or f"#{student.pk}"
            band = rf.band
            top_driver = ""
            contributions = list(rf.feature_contributions or [])
            if contributions:
                c = contributions[0]
                top_driver = (
                    f" — top driver: {c.get('name')} ({c.get('direction')})"
                )
            bullets.append(
                f"- {name} ({band} band, score {float(rf.score):.1f}){top_driver}"
            )
        return bullets

    def _allowed_entities(self, top) -> list[str]:
        """Names the AI narrative is permitted to reference.

        Sourced from the RiskFactor input set so :func:`assert_grounded`
        can refuse hallucinated names that aren't in this list. Empty
        first+last (e.g. anonymized student) becomes ``"#<pk>"``, which
        is also added to the allowlist so the bullet form round-trips.
        """
        names: list[str] = []
        for rf in top:
            student = rf.student
            full = f"{student.first_name} {student.last_name}".strip()
            if full:
                names.append(full)
            names.append(f"#{student.pk}")
        # School name itself is grounded content too.
        for rf in top:
            school_name = getattr(getattr(rf, "school", None), "name", "")
            if school_name:
                names.append(school_name)
                break
        return names

    def _narrate(self, school, bullets: list[str], top=None) -> str:
        try:
            from services.ai_helpers import TaskType, invoke_with_request
        except ImportError:
            return ""
        language_code = _resolve_language_code(school)
        language_label = _language_label(language_code)
        prompt = (
            f"You are the assistant for a school's success team. Reply in "
            f"{language_label}. Given these at-risk-student facts, write a "
            f"2-3 sentence intervention-shaped summary. Warm tone, no "
            f"jargon. End with one concrete next step the success team can "
            f"take TODAY. Facts:\n\n"
            + "\n".join(bullets)
        )
        try:
            result = invoke_with_request(
                # RISK_EXPLAIN, not a free-form string: invoke_with_request
                # resolves an unknown task-type name to None and returns before
                # any provider is contacted, so a typo here silently disables
                # narration (and with it the assert_grounded guardrail below).
                task_type=TaskType.RISK_EXPLAIN,
                prompt=prompt,
                school=school,
                metadata={"language": language_code},
                require_available=False,
            )
        except Exception as exc:  # noqa: BLE001 — never fail the digest on gateway error
            logger.warning("ai_narrate_risk_digest: gateway invoke failed: %s", exc)
            return ""
        if result is None:
            return ""
        # invoke_with_request returns either (response, metadata) tuple or None.
        try:
            response, _meta = result
        except (TypeError, ValueError):
            response = result
        narrative = str(response or "").strip()
        if not narrative:
            return ""
        # P8 hallucination guardrail: reject narrative when it mentions a
        # proper-noun-shaped entity not present in the fact bullets.
        # Caller already has a graceful empty-string fall-back path that
        # renders the bullets without a narrative.
        if top is not None:
            try:
                from apps.analytics.ai_narration_grounding import (
                    UngroundedNarrativeError,
                    assert_grounded,
                )
                # School name + each student's full name are the grounded
                # entity set. The school's own name is allowed because the
                # narrative may include it as context.
                allowed = self._allowed_entities(top) + [school.name]
                assert_grounded(narrative, allowed)
            except UngroundedNarrativeError as exc:
                logger.warning(
                    "ai_narrate_risk_digest: dropped ungrounded narrative "
                    "(unknown entities=%r)",
                    exc.unknown_entities,
                )
                return ""
            except ImportError:
                # Grounding helper missing: fall open. The digest still
                # ships; the operator can decide whether to gate
                # narration on the helper's presence in deploy.
                pass
        return narrative

    def _format_digest(self, school, bullets, narrative) -> str:
        header = f"At-risk digest — {school.name} — {timezone.now():%Y-%m-%d}"
        sep = "=" * len(header)
        body = f"{header}\n{sep}\n\n" + "\n".join(bullets) + "\n"
        if narrative:
            body += "\nNarrative:\n" + narrative + "\n"
        else:
            body += "\n(Narrative unavailable — AI gateway off or unavailable.)\n"
        return body
