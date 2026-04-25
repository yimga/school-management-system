"""1022 + 1028: Single tuple for PATH II shell/siteconfig/marketplace wave `manage.py test` modules."""

from __future__ import annotations

from pathlib import Path

# Keep in sync with docs/runbook/SOT_VALIDATION_STANZA.md and SOT §11.4 bars.
WAVE_SHELL_TEST_MODULES: tuple[str, ...] = (
    "apps.platform_runtime.tests.test_shell_contract",
    "apps.platform_runtime.tests.test_marketing_shell",
    "apps.platform_runtime.tests.test_wave_stanza_contract",
    "apps.siteconfig.tests.test_ccc_control_center_contract",
    "apps.siteconfig.tests.test_sync_center_mutating_policy",
    "apps.siteconfig.tests.test_tag_manager_mutating_policy",
    "apps.siteconfig.tests.test_impersonation_consent_mutating_policy",
    "apps.siteconfig.tests.test_clear_preview_mutating_policy",
    "apps.siteconfig.tests.test_mutating_routes_expansion",
    "apps.accounts.tests.test_backend_dashboard_shell_render",
    "apps.marketplace.tests.test_permissions",
    "apps.marketplace.tests.test_tenant_marketplace_post_security",
    "apps.schools.tests.test_control_plane_shell_render",
)


def parse_wave_modules_from_runbook_text(text: str) -> tuple[str, ...]:
    """
    Parse ordered `apps.*.tests.*` module lines from the first ```bash fenced block.
    Stops at the `--noinput` / trailing stanza line (flags only).
    """
    lines: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        line = stripped.rstrip("\\").strip()
        if not line or line.startswith("DJANGO_TEST_DB_FILE") or "manage.py test" in line:
            continue
        if line.startswith("--"):
            break
        if line.startswith("apps.") and ".tests." in line:
            lines.append(line)
    return tuple(lines)


def wave_modules_from_runbook_path(runbook: Path) -> tuple[str, ...]:
    body = runbook.read_text(encoding="utf-8", errors="replace")
    return parse_wave_modules_from_runbook_text(body)
