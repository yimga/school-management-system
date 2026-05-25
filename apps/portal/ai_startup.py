"""Management-command gating and startup logging for AI posture probes."""

from __future__ import annotations

import sys


def management_command_skips_ai_startup_probe() -> bool:
    """Avoid Ollama discovery noise during predeploy / migrations / seeds."""
    if len(sys.argv) < 2:
        return False
    cmd = sys.argv[1]
    exact_skip = frozenset(
        {
            "migrate",
            "makemigrations",
            "collectstatic",
            "shell",
            "test",
            "pytest",
        }
    )
    if cmd in exact_skip:
        return True
    prefix_skip = (
        "migrate",
        "seed_",
        "ensure_",
        "verify_",
        "repair_",
        "backfill_",
        "import_",
        "normalize_",
        "bootstrap_",
        "check_tenant",
        "integration_",
    )
    return any(cmd.startswith(prefix) for prefix in prefix_skip)
