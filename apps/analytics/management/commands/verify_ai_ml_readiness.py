"""Single-command readiness check across Waves 1-10.

Prints a status table so operators can confirm what's wired vs what's
still pending. Exits 0 if every gate the operator opted into is
satisfied; otherwise reports which checks failed.

Checks (each shows [OK]/[ - ]/[opt] + a one-line reason):
  * schema:    all required tables exist (migrations 0022-0027 applied)
  * registry:  at least one AtRiskModelArtifact row in any status
  * production: exactly one AtRiskModelArtifact has status=production
  * inference: at least one AtRiskInferenceRun in last 7 days
  * embeddings: at least one AIEmbeddingStore row with scope=student
  * digest:    at least one RiskDigestRecipient exists (any school)
  * shap:      `shap` library importable (Wave 10 opt-in)
  * pgvector:  PGVECTOR_ENABLED + vendor=postgresql + extension OK
  * celery:    at least one analytics.* beat schedule entry enabled

Output is JSON when --json is passed; otherwise human-readable table.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

logger = logging.getLogger("apps.analytics.commands.verify_ai_ml_readiness")


def _check_schema() -> dict[str, Any]:
    """Each Wave 1-10 table the operator should have. Skips check if
    Django's table introspection isn't available."""
    required = [
        "analytics_atriskmodelartifact",
        "analytics_atriskinferencerun",
        "analytics_atriskshadowrun",
        "analytics_atriskshadowcomparison",
        "analytics_gradepredictionmodelartifact",
        "analytics_gradepredictionlabel",
        "analytics_gradeprediction",
        "analytics_gradepredictionshadowrun",
        "analytics_gradepredictionshadowcomparison",
        "analytics_riskdigestrecipient",
    ]
    try:
        existing = set(connection.introspection.table_names())
    except Exception as exc:  # noqa: BLE001 — never crash on weird vendors
        return {"ok": False, "detail": f"table introspection failed: {exc}"}
    missing = [t for t in required if t not in existing]
    if missing:
        return {
            "ok": False,
            "detail": f"missing tables: {', '.join(missing)}",
        }
    return {"ok": True, "detail": f"all {len(required)} tables present"}


def _check_registry() -> dict[str, Any]:
    try:
        from apps.analytics.models import AtRiskModelArtifact
        n = AtRiskModelArtifact.objects.count()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}
    if n == 0:
        return {
            "ok": False,
            "detail": "no artifacts registered — run bootstrap_at_risk_registry",
        }
    return {"ok": True, "detail": f"{n} artifact(s) registered"}


def _check_production_artifact() -> dict[str, Any]:
    try:
        from apps.analytics.models import AtRiskModelArtifact
        prod = AtRiskModelArtifact.current_production()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}
    if prod is None:
        return {
            "ok": False,
            "detail": "no PRODUCTION row — operator must promote a candidate",
        }
    return {"ok": True, "detail": f"production='{prod.model_version}'"}


def _check_inference_recency() -> dict[str, Any]:
    try:
        from apps.analytics.models import AtRiskInferenceRun
        cutoff = timezone.now() - timezone.timedelta(days=7)
        n = AtRiskInferenceRun.objects.filter(started_at__gte=cutoff).count()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}
    if n == 0:
        return {
            "ok": False,
            "detail": "no inference runs in last 7 days — cron not wired?",
        }
    return {"ok": True, "detail": f"{n} run(s) in last 7d"}


def _check_embeddings() -> dict[str, Any]:
    try:
        from apps.siteconfig.models import AIEmbeddingStore
        # tenant-isolation-allow: AIEmbeddingStore is platform-wide by design.
        n = AIEmbeddingStore.objects.filter(scope="student").count()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}
    if n == 0:
        return {
            "ok": False,
            "detail": "no student embeddings — run build_student_embeddings",
        }
    return {"ok": True, "detail": f"{n} student embedding(s) indexed"}


def _check_digest_recipients() -> dict[str, Any]:
    try:
        from apps.analytics.models import RiskDigestRecipient
        # tenant-isolation-allow: cross-tenant existence audit
        n = RiskDigestRecipient.objects.filter(enabled=True).count()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}
    if n == 0:
        return {
            "ok": False,
            "detail": "no enabled RiskDigestRecipient rows — operator must seed via admin",
        }
    return {"ok": True, "detail": f"{n} enabled recipient(s) across tenants"}


def _check_shap_optional() -> dict[str, Any]:
    try:
        import shap  # noqa: F401
        return {"ok": True, "detail": "installed (Wave 10 opt-in available)"}
    except ImportError:
        return {
            "ok": False, "detail": "not installed — install with `pip install shap`"
                                   " (Wave 10 path falls back to fast)",
            "optional": True,
        }


def _check_pgvector_optional() -> dict[str, Any]:
    enabled = bool(getattr(settings, "PGVECTOR_ENABLED", False))
    vendor = connection.vendor
    if not enabled:
        return {
            "ok": False, "optional": True,
            "detail": "PGVECTOR_ENABLED=False (JSON cosine path active)",
        }
    if vendor != "postgresql":
        return {
            "ok": False, "optional": True,
            "detail": f"vendor={vendor}; pgvector requires postgresql",
        }
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_extension WHERE extname='vector' LIMIT 1"
            )
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "optional": True,
            "detail": f"pg_extension query failed: {exc}",
        }
    if not row:
        return {
            "ok": False, "optional": True,
            "detail": "extension `vector` not loaded in this DB",
        }
    return {"ok": True, "detail": "PGVECTOR_ENABLED + extension installed"}


def _check_celery_beat() -> dict[str, Any]:
    schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
    analytics_entries = [
        k for k, v in schedule.items()
        if (v.get("task") or "").startswith("analytics.")
    ]
    if not analytics_entries:
        return {
            "ok": False,
            "detail": "no analytics.* beat entries — flip ENABLE_*_BEAT env vars",
        }
    return {
        "ok": True,
        "detail": f"{len(analytics_entries)} analytics beat entries: "
                  f"{', '.join(analytics_entries)}",
    }


_CHECKS = [
    ("schema", _check_schema),
    ("registry", _check_registry),
    ("production", _check_production_artifact),
    ("inference_recency", _check_inference_recency),
    ("embeddings", _check_embeddings),
    ("digest_recipients", _check_digest_recipients),
    ("shap_optional", _check_shap_optional),
    ("pgvector_optional", _check_pgvector_optional),
    ("celery_beat", _check_celery_beat),
]


class Command(BaseCommand):
    help = "Print a readiness table for the AI/ML stack (Waves 1-10)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument(
            "--strict", action="store_true",
            help="Exit non-zero if any non-optional check fails.",
        )

    def handle(self, *args, **opts):
        results = []
        for name, fn in _CHECKS:
            try:
                res = fn()
            except Exception as exc:  # noqa: BLE001
                res = {"ok": False, "detail": f"check crashed: {exc}"}
            res["check"] = name
            results.append(res)

        if opts.get("json"):
            self.stdout.write(json.dumps(results, indent=2))
        else:
            self.stdout.write("AI/ML readiness:")
            for r in results:
                mark = "[OK ]" if r["ok"] else ("[opt]" if r.get("optional") else "[ - ]")
                self.stdout.write(f"  {mark} {r['check']:22s} - {r['detail']}")

        if opts.get("strict"):
            hard_failures = [
                r for r in results if not r["ok"] and not r.get("optional")
            ]
            if hard_failures:
                raise SystemExit(1)
