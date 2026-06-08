#!/usr/bin/env python3
"""Gate: multi-tenant social media integration engine completion."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "social_media_engine_audit.json"


@dataclass
class Row:
    check_id: str
    description: str
    status: str
    proof: str


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _contains(rel: str, needle: str) -> bool:
    p = ROOT / rel
    return p.is_file() and needle in p.read_text(encoding="utf-8")


def _run(
    cmd: list[str],
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    try:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=run_env,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out[-500:] if out else ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()
    py = sys.executable
    rows: list[Row] = []

    def add(check_id: str, description: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, description, "PASS" if ok else "FAIL", proof))

    add(
        "app_registered",
        "social_media app in INSTALLED_APPS",
        _contains("config/settings.py", "apps.social_media.apps.SocialMediaConfig"),
        "settings.py",
    )
    settings_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    shared_block = ""
    if "SHARED_APPS = [" in settings_text:
        shared_block = settings_text.split("SHARED_APPS = [", 1)[1].split("TENANT_APPS", 1)[0]
    add(
        "shared_apps_registered",
        "social_media in SHARED_APPS (migrate_schemas --shared on Render)",
        "apps.social_media.apps.SocialMediaConfig" in shared_block,
        "SHARED_APPS block",
    )
    add(
        "integration_model",
        "SocialMediaIntegration model + encrypted tokens",
        _contains("apps/social_media/models.py", "class SocialMediaIntegration")
        and _contains("apps/social_media/models.py", "encrypted_oauth_token"),
        "models.py",
    )
    add(
        "aggregator_service",
        "Per-tenant feed aggregator with cache fallback",
        _exists("apps/social_media/services/aggregator.py")
        and _contains("apps/social_media/services/aggregator.py", "feed_cache_json"),
        "aggregator.py",
    )
    add(
        "throttle_isolation",
        "Leaky-bucket throttle per tenant scope",
        _exists("apps/social_media/services/throttle.py"),
        "throttle.py",
    )
    add(
        "publisher_emergency",
        "Cross-post publisher + emergency router",
        _exists("apps/social_media/services/publisher.py")
        and _exists("apps/social_media/services/emergency.py"),
        "publisher + emergency",
    )
    add(
        "api_routes",
        "API v1 social endpoints wired",
        _contains("apps/api/urls_v1.py", "social/feed/")
        and _contains("apps/api/urls_v1.py", "SocialFeedAPI"),
        "urls_v1.py",
    )
    add(
        "react_components",
        "SocialFeedGrid + SocialModerationQueue",
        _exists("src/components/social/SocialFeedGrid.tsx")
        and _exists("src/components/social/SocialModerationQueue.tsx"),
        "src/components/social/",
    )
    add(
        "react_island_mount",
        "Proud campus template + social-feed.mount.js wired",
        _exists("templates/social_media/proud_campus_feed.html")
        and _contains("templates/social_media/proud_campus_feed.html", "data-rmc-social-feed")
        and _contains("templates/social_media/proud_campus_feed.html", "social-feed.mount.js")
        and _exists("static/js/dist/social-feed.mount.js"),
        "templates/social_media/proud_campus_feed.html",
    )
    add(
        "isolation_tests",
        "Adversarial isolation test modules",
        _exists("apps/social_media/tests/test_social_isolation.py")
        and _exists("apps/social_media/tests/test_comprehensive_social.py"),
        "tests/",
    )

    if args.run_tests:
        test_db = (
            ROOT
            / ".django_test_dbs"
            / f"social_media_engine_{uuid.uuid4().hex}.sqlite3"
        )
        test_db.parent.mkdir(parents=True, exist_ok=True)
        code, tail = _run(
            [
                py,
                "manage.py",
                "test",
                "apps.social_media.tests.test_social_isolation.SocialScopeUnitTests",
                "apps.social_media.tests.test_social_isolation.SocialModelConstraintUnitTests",
                "apps.social_media.tests.test_comprehensive_social.EmergencyRouterTests",
                "--verbosity=1",
                "--noinput",
            ],
            timeout=360,
            env={"DJANGO_TEST_DB_FILE": str(test_db)},
        )
        add("django_tests_fast", "Social media fast isolation tests green", code == 0, tail or "ok")
        vitest_bin = ROOT / "node_modules" / ".bin" / "vitest"
        if sys.platform == "win32":
            vitest_bin = vitest_bin.with_suffix(".cmd")
        if vitest_bin.is_file():
            code2, tail2 = _run(
                [str(vitest_bin), "run", "src/components/social"],
                timeout=180,
            )
        else:
            npm = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
            code2, tail2 = _run([npm, "run", "test:social"], timeout=180)
        add("vitest_social", "Social React component tests green", code2 == 0, tail2 or "ok")

    failed = [r for r in rows if r.status == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "SOCIAL_MEDIA_ENGINE_PASS" if not failed else "SOCIAL_MEDIA_ENGINE_FAIL",
        "pass_count": sum(1 for r in rows if r.status == "PASS"),
        "total": len(rows),
        "rows": [asdict(r) for r in rows],
    }
    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(payload["status"], f"({payload['pass_count']}/{payload['total']})")
    for row in rows:
        print(f"  [{row.status}] {row.check_id}: {row.description}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
