"""Wave H (2026-05-15): production debug surface for the at-risk model.

The nightly batch (``compute_nightly_risk``) already runs the predictor
on every active tenant and persists ``RiskFactor`` rows with a
``model_version`` string — but operators have no quick way to verify
which path the predictor actually took: heuristic fallback vs the loaded
ML artifact pointed at by ``settings.AT_RISK_MODEL_PATH``.

This command surfaces that on demand::

    python manage.py score_student_risk --student <id>
    python manage.py score_student_risk --school <slug> --top 10
    python manage.py score_student_risk --reload  # bust the joblib cache before scoring

Use it to:

* validate a freshly deployed ML artifact (``model_version`` should be
  non-empty and match the artifact filename);
* inspect why a specific student is flagged (``reason_summary`` plus
  per-feature breakdown);
* preview the nightly batch output without writing ``RiskFactor`` rows.

Never raises into a 500 — debug only. Exit code 0.
"""

from __future__ import annotations

import logging

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand

from apps.analytics.ml.at_risk_features import extract_features
from apps.analytics.ml.at_risk_model import predict_at_risk

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Show at-risk score + model_version for one or many students (debug surface)."

    def add_arguments(self, parser):
        parser.add_argument("--student", default="", help="StudentProfile id to score.")
        parser.add_argument("--school", default="", help="School slug to scan.")
        parser.add_argument("--top", type=int, default=5,
                            help="When --school is set, show the N highest-scoring students.")
        parser.add_argument("--reload", action="store_true",
                            help="Bust the in-process joblib cache before predicting (use after deploying a new artifact).")

    def handle(self, *args, **opts):
        if opts.get("reload"):
            from apps.analytics.ml import at_risk_model as arm
            arm._MODEL_CACHE.clear()
            self.stdout.write("at_risk_model: cache cleared.")

        student_id = (opts.get("student") or "").strip()
        if student_id:
            self._score_one(student_id)
            return

        slug = (opts.get("school") or "").strip()
        if not slug:
            self.stderr.write(self.style.ERROR(
                "Pass either --student <id> or --school <slug>."
            ))
            return
        self._score_top_for_school(slug, top=max(1, int(opts.get("top") or 5)))

    def _score_one(self, student_id: str) -> None:
        try:
            StudentProfile = django_apps.get_model("people", "StudentProfile")
        except LookupError:
            self.stderr.write(self.style.ERROR("StudentProfile model not registered."))
            return
        try:
            student = StudentProfile.objects.filter(pk=student_id).first()
        except (ValueError, TypeError):
            student = None
        if student is None:
            self.stderr.write(self.style.ERROR(f"No StudentProfile with id={student_id}."))
            return
        score, reason, model_version = predict_at_risk(student)
        path = "ml-artifact" if model_version else "heuristic"
        self._print_row(student, score, reason, model_version, path)

    def _score_top_for_school(self, slug: str, *, top: int) -> None:
        try:
            School = django_apps.get_model("schools", "School")
            StudentProfile = django_apps.get_model("people", "StudentProfile")
        except LookupError:
            self.stderr.write(self.style.ERROR("Required models not registered."))
            return
        school = School.objects.filter(slug=slug).first()
        if school is None:
            self.stderr.write(self.style.ERROR(f"No school with slug={slug!r}."))
            return
        rows: list[tuple[float, str, str | None, object]] = []
        # tenant-isolation-allow: explicitly scoped via school= below
        students = StudentProfile.objects.filter(school=school).select_related("user")[:200]
        for student in students:
            try:
                features = extract_features(student)  # exercised so failures surface
            except Exception as exc:  # noqa: BLE001 — debug surface
                logger.debug("feature extraction failed for %s: %s", student.pk, exc)
                continue
            del features  # only used for failure detection here
            score, reason, model_version = predict_at_risk(student)
            rows.append((score, reason, model_version, student))
        rows.sort(key=lambda r: -r[0])
        for score, reason, mv, student in rows[:top]:
            path = "ml-artifact" if mv else "heuristic"
            self._print_row(student, score, reason, mv, path)
        if not rows:
            self.stdout.write(self.style.WARNING(
                f"No StudentProfile rows for school={slug}; nothing to score."
            ))

    def _print_row(self, student, score: float, reason: str, model_version: str | None, path: str) -> None:
        label = f"{getattr(student, 'pk', '?')!s:>12s}"
        score_str = f"{score:>6.2f}"
        band = "RED" if score >= 75 else ("AMBER" if score >= 50 else "GREEN")
        version_str = model_version or "—"
        self.stdout.write(
            f"{label}  score={score_str}  band={band:<5s}  path={path:<11s}  version={version_str}"
        )
        self.stdout.write(f"               {reason}")
