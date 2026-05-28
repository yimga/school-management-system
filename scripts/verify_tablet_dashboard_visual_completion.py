#!/usr/bin/env python3
"""Tablet dashboard visual proof — Playwright 768/1024 + abrupt-end on backend + parent."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "tablet_dashboard_visual_audit.json"

TENANT_HOST_CANDIDATES = (
    "gilead-school.runmycampus.com",
    "apple-class-qa.runmycampus.com",
    "demo-school.runmycampus.com",
)
LOGIN_PATH = "/authentication/login/"


def _probe_login_form(base: str, host: str, path: str) -> bool:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        req = urllib.request.Request(
            f"{base}{path}",
            headers={"Host": host},
            method="GET",
        )
        with opener.open(req, timeout=12) as resp:
            body = resp.read(65536).decode("utf-8", errors="replace")
            return 'name="username"' in body and "school-not-found" not in body.lower()
    except urllib.error.HTTPError as exc:
        body = exc.read(65536).decode("utf-8", errors="replace") if exc.fp else ""
        if "school-not-found" in body.lower():
            return False
        return 'name="username"' in body
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _probe(base: str, host: str, path: str) -> bool:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        req = urllib.request.Request(
            f"{base}{path}",
            headers={"Host": host},
            method="GET",
        )
        with opener.open(req, timeout=12) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 200:
            return True
        if exc.code in (301, 302, 303, 307, 308):
            location = (exc.headers.get("Location") or "").lower()
            return "school-not-found" not in location
        return False
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _ensure_admin_membership_for_tenant_host(tenant_host: str) -> None:
    """Bind TABLET_QA admin user to the tenant school used for Playwright."""
    import sys

    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.contrib.auth import get_user_model

    from apps.schools.models import School, SchoolMembership

    slug = tenant_host.split(".")[0]
    school = School.objects.filter(subdomain__iexact=slug).first()
    if school is None:
        return
    username = os.environ.get("TABLET_QA_ADMIN_USER", "admin")
    user = get_user_model().objects.filter(username=username).first()
    if user is None:
        return
    SchoolMembership.objects.get_or_create(
        user=user,
        school=school,
        defaults={"role": "ADMIN", "is_primary": False},
    )


def _prepare_tablet_qa_users(usernames: tuple[str, ...]) -> None:
    """Local QA only: confirmed TOTP + verified email + recovery so dashboards are reachable."""
    import sys

    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.contrib.auth import get_user_model

    from scripts.seed_apple_class_qa import ensure_qa_totp

    user_model = get_user_model()
    for username in usernames:
        user = user_model.objects.filter(username=username).first()
        if user is None:
            continue
        ensure_qa_totp(user)
        if not user.email:
            user.email = f"{username}@tablet-qa.local"
        qa_password = os.environ.get("TABLET_QA_ADMIN_PASSWORD", "Sch00l_1234")
        user.set_password(qa_password)
        update_fields = ["email", "password"]
        if int(getattr(user, "password_strength_score", 0) or 0) < 4:
            user.password_strength_score = 4
            update_fields.append("password_strength_score")
        user.save(update_fields=update_fields)
        try:
            from allauth.account.models import EmailAddress

            EmailAddress.objects.update_or_create(
                user=user,
                email=user.email,
                defaults={"verified": True, "primary": True},
            )
        except ImportError:
            pass
        try:
            from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

            device, _ = StaticDevice.objects.get_or_create(
                user=user,
                name="tablet-qa-recovery",
                defaults={"confirmed": True},
            )
            if not device.confirmed:
                device.confirmed = True
                device.save(update_fields=["confirmed"])
            if not device.token_set.exists():
                StaticToken.objects.create(device=device, token="tabletqa1")
        except ImportError:
            pass
        print(f"tablet_qa: prepared security posture for {username}")


def _resolve_tenant_host(base: str) -> str:
    explicit = os.environ.get("TENANT_TEST_HOST", "").strip()
    if explicit:
        return explicit
    for host in TENANT_HOST_CANDIDATES:
        if _probe_login_form(base, host, LOGIN_PATH):
            return host
    return TENANT_HOST_CANDIDATES[0]


def _wait_for_server(base: str, host: str, *, timeout_sec: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _probe_login_form(base, host, LOGIN_PATH):
            return True
        time.sleep(2.0)
    return False


def _spawn_django(port: str) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["SECURITY_ENFORCE_MINIMUM_STRENGTH"] = "0"
    env["USE_FILE_LOGGING"] = "0"
    log_path = REPO / "var" / "evidence" / "tablet-dashboard-visual-runserver.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    return subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
        cwd=REPO,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def _run(cmd: list[str], env: dict[str, str], timeout: int = 900) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spawn-server",
        action="store_true",
        help="Start manage.py runserver on TABLET_QA_PORT when login probe fails.",
    )
    args = parser.parse_args()

    port = os.environ.get("VISUAL_QA_PORT", os.environ.get("TABLET_QA_PORT", "8000"))
    base = f"http://127.0.0.1:{port}"
    spawned: subprocess.Popen[bytes] | None = None
    tenant_host = _resolve_tenant_host(base)

    if not _probe_login_form(base, tenant_host, LOGIN_PATH) and args.spawn_server:
        spawned = _spawn_django(port)
        if not _wait_for_server(base, tenant_host):
            if spawned.poll() is None:
                spawned.terminate()
            print(
                "TABLET_DASHBOARD_VISUAL_FAIL: spawned server never served login",
                file=sys.stderr,
            )
            return 1
        tenant_host = _resolve_tenant_host(base)

    tenant_base = f"http://{tenant_host}:{port}"

    seed_script = REPO / "scripts" / "seed_apple_class_qa.py"
    if tenant_host.startswith("apple-class-qa.") and seed_script.is_file():
        subprocess.run([sys.executable, str(seed_script)], cwd=REPO, check=False, timeout=120)

    _ensure_admin_membership_for_tenant_host(tenant_host)
    _prepare_tablet_qa_users(
        (
            os.environ.get("TABLET_QA_ADMIN_USER", "admin"),
            "appleqa_tenant",
        )
    )
    parent_password = os.environ.get("TABLET_QA_PARENT_PASSWORD", "Test1234")
    subprocess.run(
        [
            sys.executable,
            "manage.py",
            "create_teacher_parent_accounts",
            "--parent-username",
            os.environ.get("TABLET_QA_PARENT_USER", "Parent1"),
            "--password",
            parent_password,
        ],
        cwd=REPO,
        check=False,
        timeout=120,
    )

    if not _probe_login_form(base, tenant_host, LOGIN_PATH):
        print(
            "TABLET_DASHBOARD_VISUAL_SKIP: no tenant login at "
            f"{tenant_base}{LOGIN_PATH} — start Django + ensure_demo_environment",
            file=sys.stderr,
        )
        return 0

    host_rules = os.environ.get(
        "PLAYWRIGHT_HOST_RULES",
        f"MAP {tenant_host} 127.0.0.1",
    )
    qa_password = os.environ.get("TABLET_QA_ADMIN_PASSWORD", "Sch00l_1234")
    env = {
        **os.environ,
        "PLAYWRIGHT_TENANT_BASE_URL": tenant_base,
        "PLAYWRIGHT_HOST_RULES": host_rules,
        "PLAYWRIGHT_TENANT_HOST_RULES": os.environ.get(
            "PLAYWRIGHT_TENANT_HOST_RULES", f"MAP {tenant_host} 127.0.0.1"
        ),
        "TABLET_QA_ADMIN_PASSWORD": qa_password,
        "TABLET_QA_PARENT_PASSWORD": os.environ.get("TABLET_QA_PARENT_PASSWORD", "Test1234"),
    }

    steps: list[dict[str, object]] = []

    pw_cli = REPO / "node_modules" / "playwright" / "cli.js"
    if not pw_cli.is_file():
        print("TABLET_DASHBOARD_VISUAL_FAIL: run npm ci first", file=sys.stderr)
        return 1
    node_bin = shutil.which("node") or "node"
    code, out = _run(
        [
            node_bin,
            str(pw_cli),
            "test",
            "tests/e2e/tablet-dashboard-visual.spec.js",
            "--project=tenant-chromium",
            "--reporter=line",
        ],
        env,
    )
    steps.append({"step": "playwright_tablet_spec", "ok": code == 0, "exit_code": code})
    if code != 0:
        print(out[-12000:], file=sys.stderr)

    sweep_env = {
        **env,
        "SWEEP_TIER": "tenant",
        "SWEEP_INCLUDE_TENANT": "1",
        "SWEEP_TENANT_PATHS": "/authentication/backend/,/portal/parent/",
        "TENANT_BASE_URL": tenant_base,
        "TENANT_SWEEP_SLUG": tenant_host.split(".")[0],
        "VISUAL_QA_PORT": port,
        "USE_TENANT_SUBDOMAIN": "1",
    }
    for width, height, label in ((768, 1024, "portrait"), (1024, 768, "landscape")):
        sweep_env["SWEEP_VIEWPORT_WIDTH"] = str(width)
        sweep_env["SWEEP_VIEWPORT_HEIGHT"] = str(height)
        sweep_env["SWEEP_TIER"] = "tenant"
        sc, sout = _run(["node", "scripts/verify_platform_abrupt_end_sweep.mjs"], sweep_env)
        steps.append(
            {
                "step": f"abrupt_end_{label}",
                "viewport": f"{width}x{height}",
                "ok": sc == 0,
                "exit_code": sc,
            }
        )
        if sc != 0:
            print(sout[-8000:], file=sys.stderr)

    all_ok = all(bool(s.get("ok")) for s in steps)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_host": tenant_host,
        "tenant_base": tenant_base,
        "steps": steps,
        "pass": all_ok,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if spawned is not None and spawned.poll() is None:
        spawned.terminate()
        try:
            spawned.wait(timeout=10)
        except subprocess.TimeoutExpired:
            spawned.kill()

    if all_ok:
        print("TABLET_DASHBOARD_VISUAL_PASS")
        return 0
    print("TABLET_DASHBOARD_VISUAL_FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
