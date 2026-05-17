"""Backfill the at-risk registry from the legacy env-var artifact path.

Before Wave 1 (v2.92), the loader read `AT_RISK_MODEL_PATH` directly.
After Wave 1, the registry is authoritative. This command bridges the
two: read the env var, hash the file, register a row, promote it.

Idempotent: if a row already exists with the same model_version, it's
a no-op (so this is safe to run in every deploy).

Usage:
    python manage.py bootstrap_at_risk_registry --operator-username admin
    python manage.py bootstrap_at_risk_registry \
        --artifact var/at_risk_model.joblib \
        --model-version at_risk_v1_synthetic \
        --operator-username admin

Without --artifact, falls back to `settings.AT_RISK_MODEL_PATH` /
`AT_RISK_MODEL_PATH` env var. Without --model-version, defaults to
`legacy_<basename>_<sha8>`.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User

logger = logging.getLogger("apps.analytics.commands.bootstrap_at_risk_registry")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = (
        "Register the existing AT_RISK_MODEL_PATH artifact in the registry "
        "and promote it. Safe to run multiple times (idempotent)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--artifact", default=None)
        parser.add_argument("--model-version", default=None)
        parser.add_argument(
            "--operator-username", default=None,
            help=(
                "User whose action this is attributed to in audit fields. "
                "When omitted, falls back to the first superuser, then to "
                "the user 'admin' if present. Predeploy invocations can "
                "skip this flag safely."
            ),
        )
        parser.add_argument(
            "--no-promote", action="store_true",
            help="Register as candidate but skip the promote step.",
        )

    def handle(self, *args, **opts):
        from apps.analytics.models import AtRiskModelArtifact

        artifact = opts.get("artifact") or (
            getattr(settings, "AT_RISK_MODEL_PATH", None)
            or os.environ.get("AT_RISK_MODEL_PATH")
            or ""
        ).strip()
        if not artifact:
            # Graceful skip: predeploy should not fail when the legacy
            # artifact path isn't configured on this environment. The
            # registry is empty; runtime falls back to the heuristic baseline.
            self.stdout.write(self.style.WARNING(
                "No AT_RISK_MODEL_PATH and no --artifact given. "
                "Nothing to register; skipping."
            ))
            return
        artifact_path = Path(artifact)
        if not artifact_path.exists():
            self.stdout.write(self.style.WARNING(
                f"Artifact path '{artifact_path}' does not exist on disk. "
                "Skipping registry bootstrap."
            ))
            return

        # Resolve operator: explicit --operator-username → first superuser →
        # the conventional 'admin' user (created by seed_render_users).
        operator = self._resolve_operator(opts.get("operator_username"))
        if operator is None:
            self.stdout.write(self.style.WARNING(
                "No operator user available (tried explicit username, first "
                "superuser, and username='admin'). Skipping registry bootstrap; "
                "re-run after seed_render_users has provisioned the admin user."
            ))
            return

        digest = _sha256_of(artifact_path)
        version = opts.get("model_version") or (
            f"legacy_{artifact_path.stem}_{digest[:8]}"
        )

        existing = AtRiskModelArtifact.objects.filter(
            model_version=version,
        ).first()
        if existing is not None:
            self.stdout.write(
                f"Registry row '{version}' already exists "
                f"(status={existing.status}). Skipping registration."
            )
            target = existing
        else:
            trained_at = self._read_trained_at(artifact_path)
            feature_order, training_rows = self._read_bundle_metadata(artifact_path)
            target = AtRiskModelArtifact.objects.create(
                model_version=version,
                artifact_path=str(artifact_path),
                trained_at=trained_at,
                training_dataset_hash="",
                training_row_count=training_rows,
                feature_order=feature_order,
                status=AtRiskModelArtifact.Status.CANDIDATE,
                registered_by=operator,
                notes="Bootstrap-registered from legacy env-var path.",
            )
            self.stdout.write(self.style.SUCCESS(
                f"Registered '{version}' [candidate] id={target.pk}"
            ))

        if opts.get("no_promote"):
            return

        if target.status == AtRiskModelArtifact.Status.PRODUCTION:
            self.stdout.write(f"'{version}' is already PRODUCTION; no-op.")
            return
        previous = target.promote(by_user=operator)
        msg = f"Promoted '{version}' to PRODUCTION"
        if previous is not None:
            msg += f"; archived previous '{previous.model_version}'"
        self.stdout.write(self.style.SUCCESS(msg + "."))

    def _resolve_operator(self, explicit_username: str | None):
        """Return a User instance for audit attribution, or None.

        Priority:
          1. The explicit --operator-username argument (if it resolves).
          2. The first superuser by date_joined.
          3. The user with username='admin' (seed_render_users convention).
        """
        if explicit_username:
            try:
                return User.objects.get(username=explicit_username)
            except User.DoesNotExist:
                pass
        first_super = (
            User.objects.filter(is_superuser=True, is_active=True)
            .order_by("date_joined", "pk")
            .first()
        )
        if first_super is not None:
            return first_super
        try:
            return User.objects.get(username="admin")
        except User.DoesNotExist:
            return None

    def _read_trained_at(self, artifact_path: Path):
        """Best-effort trained_at; mtime fallback."""
        try:
            import joblib  # type: ignore

            bundle = joblib.load(artifact_path)
        except (ImportError, FileNotFoundError, OSError, ValueError):
            return datetime.fromtimestamp(
                os.path.getmtime(artifact_path), tz=dt_timezone.utc,
            )
        if isinstance(bundle, dict):
            raw = bundle.get("trained_at")
            if isinstance(raw, str):
                try:
                    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    pass
        return datetime.fromtimestamp(
            os.path.getmtime(artifact_path), tz=dt_timezone.utc,
        )

    def _read_bundle_metadata(self, artifact_path: Path):
        try:
            import joblib  # type: ignore

            bundle = joblib.load(artifact_path)
        except (ImportError, FileNotFoundError, OSError, ValueError):
            return [], 0
        if not isinstance(bundle, dict):
            return [], 0
        feature_order = list(bundle.get("feature_order") or [])
        training_rows = int(bundle.get("training_row_count") or 0)
        return feature_order, training_rows
