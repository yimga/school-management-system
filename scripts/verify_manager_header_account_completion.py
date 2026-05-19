#!/usr/bin/env python3
"""
Manager header alignment + account menu completion gate.

Writes docs/generated/manager_header_account_audit.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "manager_header_account_audit.json"
MIDDLEWARE = ROOT / "apps" / "schools" / "middleware.py"


@dataclass
class Row:
    check_id: str
    label: str
    ok: bool
    proof: str


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _contains(rel: str, needle: str) -> bool:
    return needle in _read(rel)


def _run_tests(labels: list[str]) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "scripts/run_sqlite_memory_tests.py",
        *labels,
        "--verbosity=1",
        "--no-input",
    ]
    env = {**os.environ, "PYTHONWARNINGS": "ignore"}
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300, env=env
        )
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-600:]
        return proc.returncode == 0, tail
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def _run_manage(*args: str, timeout: int = 90, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    cmd = [sys.executable, "manage.py", *args]
    env = {**os.environ, **(extra_env or {})}
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout, env=env
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)


def _kb_article_count() -> tuple[bool, str]:
    code = (
        "from apps.portal.models_kb import KBArticle; "
        "print(KBArticle.objects.count())"
    )
    cmd = [sys.executable, "manage.py", "shell", "-c", code]
    env = {**os.environ, "DJANGO_LOG_LEVEL": "ERROR", "PYTHONWARNINGS": "ignore"}
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "shell failed")[-200:]
    count = None
    for line in reversed((proc.stdout or "").splitlines()):
        stripped = line.strip()
        if stripped.isdigit():
            count = int(stripped)
            break
    if count is None:
        return False, (proc.stdout or "empty stdout")[-200:]
    return count >= 8, f"{count} articles (min 8)"


def main() -> int:
    rows: list[Row] = []

    def add(check_id: str, label: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, label, ok, proof))

    mw = _read("apps/schools/middleware.py")
    for path in (
        "/authentication/documentation/",
        "/authentication/notifications/",
        "/kb/",
        "/feedback-loop/",
    ):
        add(
            f"allow-{path.strip('/')}",
            f"Manager allowlist includes {path}",
            path in mw,
            "MANAGER_HOST_ALLOWED_PREFIXES",
        )

    add(
        "header-height-token",
        "Shared header control height token",
        _contains("static/css/rmc-platform-header.css", "--rmc-header-control-height"),
        "rmc-platform-header.css",
    )
    add(
        "header-user-compact",
        "Compact user dropdown on cp-navbar",
        _contains("static/css/rmc-platform-header.css", ".cp-navbar .user-dropdown-trigger"),
        "rmc-platform-header.css",
    )
    add(
        "operator-render-module",
        "Operator account render helper",
        (ROOT / "apps/accounts/operator_account_render.py").is_file(),
        "operator_account_render.py",
    )
    for partial in (
        "templates/accounts/partials/operator_profile_body.html",
        "templates/accounts/partials/operator_profile_edit_body.html",
        "templates/accounts/partials/operator_documentation_body.html",
        "templates/accounts/partials/notifications_body.html",
        "templates/accounts/partials/operator_notification_preferences_body.html",
    ):
        add(
            f"partial-{Path(partial).stem}",
            f"Operator partial exists: {partial}",
            (ROOT / partial).is_file(),
            partial,
        )

    dropdown = _read("templates/components/user_dropdown.html")
    add(
        "dropdown-kb",
        "User dropdown Help uses kb:kb_home",
        "kb:kb_home" in dropdown and 'href="#"' not in dropdown,
        "user_dropdown.html",
    )

    manager_urls_src = _read("config/manager_urls.py")
    add(
        "manager-help-kb",
        "manager_help redirects to kb:kb_home",
        'reverse("kb:kb_home")' in manager_urls_src,
        "manager_urls.py",
    )
    add(
        "views-render-account",
        "Account views use render_account_page",
        all(
            needle in _read("apps/accounts/views.py")
            for needle in (
                "render_account_page",
                "operator_profile_body.html",
                "operator_profile_edit_body.html",
                "operator_documentation_body.html",
                "notifications_body.html",
                "operator_notification_preferences_body.html",
            )
        ),
        "accounts/views.py",
    )

    add(
        "seed-kb-command",
        "KB seed command exists for operator help content",
        (ROOT / "apps/portal/management/commands/seed_kb_articles.py").is_file(),
        "seed_kb_articles",
    )

    migrate_rc, _ = _run_manage(
        "migrate",
        "--check",
        extra_env={"DJANGO_LOG_LEVEL": "ERROR"},
    )
    add(
        "migrations-applied",
        "No pending Django migrations (migrate --check)",
        migrate_rc == 0,
        "exit 0" if migrate_rc == 0 else "pending migrations — run manage.py migrate",
    )

    kb_ok, kb_proof = _kb_article_count()
    add(
        "kb-seeded",
        "Knowledge base has seeded articles for Help Center",
        kb_ok,
        kb_proof,
    )

    for path in (
        "/authentication/profile/password/",
        "/authentication/mfa/setup/",
    ):
        add(
            f"allow-{path.strip('/').replace('/', '-')}",
            f"Manager allowlist covers {path}",
            any(
                path.startswith(p)
                for p in (
                    "/authentication/profile/",
                    "/authentication/mfa/",
                )
                if p in mw
            ),
            "MANAGER_HOST_ALLOWED_PREFIXES",
        )

    add(
        "manager-support-feedback-loop",
        "Support and feedback redirect to manager_feedback_loop",
        manager_urls_src.count('reverse("manager_feedback_loop")') >= 2,
        "manager_urls.py",
    )

    tests_ok, tail = _run_tests(
        [
            "apps.schools.tests.test_manager_header_account_paths",
            "apps.siteconfig.tests.test_interaction_integrity_contract",
        ]
    )
    add("tests", "Manager header + interaction contract tests", tests_ok, tail or "django tests")

    failures = [r for r in rows if not r.ok]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "MANAGER_HEADER_ACCOUNT_PASS" if not failures else "MANAGER_HEADER_ACCOUNT_FAIL",
        "pass_count": sum(1 for r in rows if r.ok),
        "fail_count": len(failures),
        "rows": [
            {"id": r.check_id, "label": r.label, "status": "PASS" if r.ok else "FAIL", "proof": r.proof}
            for r in rows
        ],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(payload["verdict"], f"({payload['pass_count']} pass / {payload['fail_count']} fail)")
    for r in failures:
        print(f"  FAIL {r.check_id}: {r.label} — {r.proof}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
