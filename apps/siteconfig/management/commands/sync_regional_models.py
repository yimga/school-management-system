"""
World Engine: sync Ollama models per region from AIModelRegistry.
Runs `ollama pull <model_id>` for each active model in the given cluster (background threads so DB is not locked).
"""
import logging
import subprocess
import threading
from typing import List

from django.core.management.base import BaseCommand

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.siteconfig.models import AIModelRegistry

logger = logging.getLogger(__name__)

# §2.4 Typed exceptions for allowlist shrink (broad_exception_audit)
_SYNC_REGIONAL_MODELS_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    RuntimeError,
    subprocess.SubprocessError,
)


def _pull_model(model_id: str, cluster: str) -> None:
    """Run ollama pull in subprocess; log result."""
    try:
        logger.info("Pulling %s for cluster %s...", model_id, cluster)
        subprocess.run(
            ["ollama", "pull", model_id],
            capture_output=True,
            text=True,
            timeout=3600,
        )
        logger.info("Pulled %s for cluster %s.", model_id, cluster)
    except subprocess.TimeoutExpired:
        logger.warning("Pull timeout for %s (cluster %s).", model_id, cluster)
    except FileNotFoundError:
        logger.warning("ollama CLI not found; install Ollama or set PATH.")
    except _SYNC_REGIONAL_MODELS_ERRORS as e:
        log_exception_with_context(
            "sync_regional_models: pull failed",
            school_id=None,
            extra={"model_id": model_id, "cluster": cluster, "error": str(e)},
        )


class Command(BaseCommand):
    help = "Sync Ollama models for region(s) from AIModelRegistry. Runs ollama pull in background threads."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cluster",
            type=str,
            default=None,
            help="Regional cluster to sync (e.g. CM, KE). If omitted, sync all clusters with active models.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only list models that would be pulled; do not run ollama pull.",
        )

    def handle(self, *args, **options):
        cluster = (options.get("cluster") or "").strip().upper()
        dry_run = options.get("dry_run", False)

        qs = AIModelRegistry.objects.filter(is_active=True).order_by("regional_cluster", "-priority")
        if cluster:
            qs = qs.filter(regional_cluster=cluster)

        models: List[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row in qs:
            key = (row.regional_cluster, row.model_id)
            if key in seen:
                continue
            seen.add(key)
            models.append((row.regional_cluster, row.model_id))

        if not models:
            self.stdout.write(self.style.WARNING("No active models in registry for cluster=%s." % (cluster or "all")))
            return

        for c, mid in models:
            self.stdout.write("Would pull %s for cluster %s." % (mid, c))
        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run: no pulls executed."))
            return

        threads = []
        for c, mid in models:
            t = threading.Thread(target=_pull_model, args=(mid, c))
            t.daemon = True
            t.start()
            threads.append(t)
            self.stdout.write("Pulling %s for cluster %s..." % (mid, c))

        for t in threads:
            t.join(timeout=3700)
        self.stdout.write(self.style.SUCCESS("Sync regional models started (pulls run in background)."))
