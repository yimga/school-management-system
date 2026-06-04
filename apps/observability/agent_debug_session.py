"""Foldable agent debug-session NDJSON logger (session 446df4)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

SESSION_ID = "446df4"
LOG_FILENAME = f"debug-{SESSION_ID}.log"


def _log_path(base_dir: Path) -> Path:
    return base_dir / LOG_FILENAME


def agent_debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    run_id: str | None = None,
    base_dir: Path | None = None,
) -> None:
    # #region agent log
    root = base_dir or Path(__file__).resolve().parents[2]
    entry = {
        "sessionId": SESSION_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": run_id or os.environ.get("RMC_AGENT_DEBUG_RUN_ID", "pre-fix"),
    }
    try:
        with _log_path(root).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass
    # #endregion


def workflow_progress_strip_deploy_probe(base_dir: Path) -> dict[str, Any]:
    """Filesystem + settings probe for components/rmc_workflow_progress_strip.html."""
    rel = Path("templates/components/rmc_workflow_progress_strip.html")
    expected = base_dir / rel
    templates_dir = base_dir / "templates"
    return {
        "expected_path": str(expected),
        "present_on_disk": expected.is_file(),
        "templates_dir_present": templates_dir.is_dir(),
        "render_git_commit": os.environ.get("RENDER_GIT_COMMIT", ""),
        "render_service_id": os.environ.get("RENDER_SERVICE_ID", ""),
    }
