#!/usr/bin/env python3
"""Completion gate: eager filter-arg VariableDoesNotExist 500 class is 100% sealed.

This is the proof harness for the production failure class that 500'd
``/super/schools/`` and ``/configuration/`` on 2026-07-22
(``Failed lookup for key [ops_surface]``).

Django resolves every filter *argument* eagerly. A missing top-level context
variable used as ``|default:``, ``|default_if_none:``, ``|slice:``, or ``|add:``
argument raises ``VariableDoesNotExist`` — even when the left-hand value is set.

This verifier does NOT stop at "scanner is green". It must PASS every row:

  S1  Static scanner --strict → 0 findings
  S2  Banned production patterns absent from every template
  S3  Scanner unit tests green
  S4  CI + pre-push wiring present
  S5  Agent completion prompt present
  R1  Django behavioral seals (default/slice raise; literal binding safe)
  R2  Ops-center frame renders with sparse context (no ops_surface)
  R3  Planner strip renders without backend_max_items_slice
  R4  Every consumer of rmc_operational_center_frame is free of banned defaults
  R5  Django regression test module green

Exit 0 and print ``EAGER_FILTER_ARG_COMPLETION_PASS`` only when every row passes.
Writes ``docs/generated/eager_filter_arg_completion_audit.json``.

Usage:
  python scripts/verify_eager_filter_arg_completion.py
  python scripts/verify_eager_filter_arg_completion.py --static-only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "docs" / "generated" / "eager_filter_arg_completion_audit.json"
TEMPLATES = ROOT / "templates"
PROMPT = ROOT / "docs" / "prompts" / "EAGER_FILTER_ARG_COMPLETION_PROMPT.md"
SCANNER = ROOT / "scripts" / "scan_include_with_default_context_var.py"
SCANNER_TESTS = "scripts.tests.test_scan_include_with_default_context_var"
DJANGO_TESTS = "apps.platform_runtime.tests.test_operational_center_frame_include"

# Patterns that caused (or would reintroduce) production 500s.
_BANNED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\|\s*default\s*:\s*ops_surface\b", "|default:ops_surface"),
    (r"\|\s*default\s*:\s*ops_page_archetype\b", "|default:ops_page_archetype"),
    (r"\|\s*default\s*:\s*PREVIEW_NOTE\b", "|default:PREVIEW_NOTE"),
    (
        r"\|\s*slice\s*:\s*backend_max_items_slice\b",
        "|slice:backend_max_items_slice",
    ),
    (
        r"\|\s*default\s*:\s*HEADER_WEATHER_TIMEZONE\b",
        "|default:HEADER_WEATHER_TIMEZONE",
    ),
    (
        r"\|\s*default\s*:\s*TWITTER_SITE_HANDLE\b",
        "|default:TWITTER_SITE_HANDLE",
    ),
    (
        r"SITE_ADMIN_THEME\s*\|\s*default\s*:\s*SITE_THEME\b",
        "SITE_ADMIN_THEME|default:SITE_THEME",
    ),
    (
        r"SITE_ADMIN_THEME\s*\|\s*default\s*:\s*SITE\b",
        "SITE_ADMIN_THEME|default:SITE",
    ),
)

_COMMENT_RE = re.compile(
    r"\{#.*?#\}|\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|<!--.*?-->",
    re.DOTALL,
)

_OPS_FRAME_INCLUDE_RE = re.compile(
    r"""\{\%\s*include\s+[\"']components/rmc_operational_center_frame\.html[\"']""",
)


@dataclass
class Row:
    check_id: str
    label: str
    ok: bool
    proof: str


def _run(
    cmd: list[str],
    *,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out[-1200:] if out else ""
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except OSError as exc:
        return 1, str(exc)


def _template_files() -> list[Path]:
    files: list[Path] = []
    if TEMPLATES.is_dir():
        files.extend(TEMPLATES.rglob("*.html"))
    apps = ROOT / "apps"
    if apps.is_dir():
        for base in sorted(apps.glob("*/templates")):
            files.extend(base.rglob("*.html"))
    return files


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def check_static_scanner() -> Row:
    code, out = _run([sys.executable, str(SCANNER), "--strict"], timeout=120)
    return Row(
        "S1",
        "Static scanner --strict is 0 findings",
        code == 0 and "0 finding" in out,
        out or "scanner silent",
    )


def check_banned_patterns() -> Row:
    hits: list[str] = []
    for path in _template_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        rel = path.relative_to(ROOT).as_posix()
        for pattern, label in _BANNED_PATTERNS:
            if re.search(pattern, text):
                hits.append(f"{rel}: {label}")
    ok = not hits
    proof = "no banned patterns" if ok else "; ".join(hits[:12])
    if len(hits) > 12:
        proof += f" (+{len(hits) - 12} more)"
    return Row("S2", "Banned production filter-arg patterns absent", ok, proof)


def check_scanner_unit_tests() -> Row:
    code, out = _run(
        [sys.executable, "-m", "unittest", SCANNER_TESTS, "-v"],
        timeout=120,
    )
    ok = code == 0 and "\nOK" in ("\n" + out)
    return Row(
        "S3",
        "Scanner stdlib unit tests green",
        ok,
        out[-400:] if out else f"exit={code}",
    )


def check_wiring() -> Row:
    workflow = (
        ROOT / ".github" / "workflows" / "architectural-boundaries.yml"
    ).read_text(encoding="utf-8", errors="replace")
    prepush = (ROOT / "scripts" / "pre_push_boundary_check.py").read_text(
        encoding="utf-8", errors="replace"
    )
    gate_wiring = (ROOT / "scripts" / "verify_ci_gate_wiring.py").read_text(
        encoding="utf-8", errors="replace"
    )
    needed = [
        ("workflow invokes scanner --strict", "scan_include_with_default_context_var.py --strict" in workflow),
        ("workflow runs scanner unit tests", "test_scan_include_with_default_context_var" in workflow),
        ("pre-push lists scanner", "scan_include_with_default_context_var.py" in prepush),
        (
            "REQUIRED_GATES lists scanner",
            "scan_include_with_default_context_var.py" in gate_wiring,
        ),
        (
            "REQUIRED_GATES lists this completion verifier",
            "verify_eager_filter_arg_completion.py" in gate_wiring,
        ),
    ]
    missing = [name for name, ok in needed if not ok]
    return Row(
        "S4",
        "CI / pre-push / REQUIRED_GATES wiring present",
        not missing,
        "wired" if not missing else "missing: " + ", ".join(missing),
    )


def check_prompt_present() -> Row:
    ok = PROMPT.is_file() and "EAGER_FILTER_ARG_COMPLETION_PASS" in PROMPT.read_text(
        encoding="utf-8", errors="replace"
    )
    return Row(
        "S5",
        "Agent completion prompt present and references PASS token",
        ok,
        str(PROMPT.relative_to(ROOT).as_posix()) if ok else "prompt missing/incomplete",
    )


def check_ops_consumers_clean() -> Row:
    """Every template that includes the ops frame must not carry banned defaults."""
    dirty: list[str] = []
    consumer_count = 0
    for path in _template_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if not _OPS_FRAME_INCLUDE_RE.search(text):
            continue
        consumer_count += 1
        cleaned = _strip_comments(text)
        for pattern, label in _BANNED_PATTERNS[:2]:  # ops_surface / ops_page_archetype
            if re.search(pattern, cleaned):
                dirty.append(f"{path.relative_to(ROOT).as_posix()}: {label}")
    ok = not dirty and consumer_count > 0
    proof = (
        f"consumers={consumer_count} clean"
        if ok
        else (
            f"consumers={consumer_count}; dirty=" + "; ".join(dirty[:8])
            if dirty
            else "no ops-frame consumers found"
        )
    )
    return Row(
        "R4",
        "All rmc_operational_center_frame consumers free of banned defaults",
        ok,
        proof,
    )


def _django_setup() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
    import django

    django.setup()


def check_django_behavior_and_sparse_renders() -> list[Row]:
    rows: list[Row] = []
    try:
        _django_setup()
        from django.template import Context, Template
        from django.template.base import VariableDoesNotExist
        from django.template.loader import get_template
    except Exception as exc:  # noqa: BLE001 — prove setup failure as FAIL row
        return [
            Row(
                "R1",
                "Django behavioral seals",
                False,
                f"django_setup_failed:{exc}",
            )
        ]

    # R1a — default raises even when left is set
    try:
        Template("{{ a|default:missing_fallback }}").render(Context({"a": "present"}))
        rows.append(
            Row(
                "R1a",
                "Django |default:missing raises even when left is set",
                False,
                "did not raise VariableDoesNotExist",
            )
        )
    except VariableDoesNotExist:
        rows.append(
            Row(
                "R1a",
                "Django |default:missing raises even when left is set",
                True,
                "VariableDoesNotExist raised as expected",
            )
        )
    except Exception as exc:  # noqa: BLE001
        rows.append(
            Row(
                "R1a",
                "Django |default:missing raises even when left is set",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        )

    # R1b — slice raises when limit missing
    try:
        Template("{% for x in items|slice:lim %}{{ x }}{% endfor %}").render(
            Context({"items": [1, 2, 3]})
        )
        rows.append(
            Row(
                "R1b",
                "Django |slice:missing raises",
                False,
                "did not raise VariableDoesNotExist",
            )
        )
    except VariableDoesNotExist:
        rows.append(
            Row(
                "R1b",
                "Django |slice:missing raises",
                True,
                "VariableDoesNotExist raised as expected",
            )
        )
    except Exception as exc:  # noqa: BLE001
        rows.append(
            Row(
                "R1b",
                "Django |slice:missing raises",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        )

    # R1c — literal-bound slice is safe
    try:
        out = Template(
            '{% with lim=backend_max_items_slice|default:":2" %}'
            "{% for x in items|slice:lim %}{{ x }}{% endfor %}"
            "{% endwith %}"
        ).render(Context({"items": [1, 2, 3, 4]}))
        rows.append(
            Row(
                "R1c",
                "Literal |default binding makes |slice safe without context var",
                out == "12",
                repr(out),
            )
        )
    except Exception as exc:  # noqa: BLE001
        rows.append(
            Row(
                "R1c",
                "Literal |default binding makes |slice safe without context var",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        )

    # R2 — ops frame sparse render (the production 500)
    sparse = {
        "nav_groups": [
            {
                "key": "fleet",
                "label": "Fleet",
                "title": "Fleet",
                "body": "Schools",
            }
        ],
        "center_title": "Schools",
        "center_eyebrow": "Platform operators",
        "os_center_key": "schools_list",
    }
    try:
        html = get_template("components/rmc_operational_center_frame.html").render(sparse)
        ok = (
            "rmc-operational-center-frame" in html
            and "Schools" in html
            and "ops_surface" not in html
        )
        rows.append(
            Row(
                "R2a",
                "Ops frame renders without ops_surface / ops_page_archetype",
                ok,
                f"len={len(html)} has_frame={'rmc-operational-center-frame' in html}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        rows.append(
            Row(
                "R2a",
                "Ops frame renders without ops_surface / ops_page_archetype",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        )

    try:
        tenant_ctx = {
            "tenant_surface": "1",
            "nav_groups": [],
            "center_title": "Packs",
            "os_center_key": "tenant_pack_setup",
        }
        html = get_template("components/rmc_operational_center_frame.html").render(
            tenant_ctx
        )
        rows.append(
            Row(
                "R2b",
                "Ops frame tenant branch renders without ops_page_archetype",
                "rmc-operational-center-frame--tenant" in html,
                f"len={len(html)}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        rows.append(
            Row(
                "R2b",
                "Ops frame tenant branch renders without ops_page_archetype",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        )

    # R3 — planner strip without backend_max_items_slice
    try:
        html = get_template(
            "partials/shell_chrome_backend_planner_recommended_next_strip.html"
        ).render({"recommended_next_steps": []})
        rows.append(
            Row(
                "R3",
                "Planner strip renders without backend_max_items_slice",
                "backend-planner" in html
                or "Recommended" in html
                or "pending" in html.lower(),
                f"len={len(html)}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        rows.append(
            Row(
                "R3",
                "Planner strip renders without backend_max_items_slice",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        )

    return rows


def check_django_test_module() -> Row:
    env = os.environ.copy()
    gate_db = ROOT / ".django_test_dbs" / "eager_filter_arg_gate.sqlite3"
    env["DJANGO_TEST_DB_FILE"] = str(gate_db)
    cmd = [
        sys.executable,
        "scripts/run_sqlite_memory_tests.py",
        DJANGO_TESTS,
        "--verbosity=1",
        "--no-input",
    ]
    if not gate_db.is_file():
        cmd.append("--fresh")
    code, out = _run(cmd, timeout=900, env=env)
    teardown_lock = (
        code != 0
        and "PermissionError" in out
        and "WinError 32" in out
        and "\nOK\n" in out
    )
    ok = code == 0 or teardown_lock
    return Row(
        "R5",
        "Django regression test module green",
        ok,
        out[-500:] if out else f"exit={code}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Skip Django runtime rows (deps-free CI subset)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows: list[Row] = [
        check_static_scanner(),
        check_banned_patterns(),
        check_scanner_unit_tests(),
        check_wiring(),
        check_prompt_present(),
        check_ops_consumers_clean(),
    ]

    if not args.static_only:
        rows.extend(check_django_behavior_and_sparse_renders())
        rows.append(check_django_test_module())

    failed = [r for r in rows if not r.ok]
    passed = [r for r in rows if r.ok]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "static_only": bool(args.static_only),
        "pass_count": len(passed),
        "fail_count": len(failed),
        "total": len(rows),
        "complete": not failed,
        "pass_token": "EAGER_FILTER_ARG_COMPLETION_PASS" if not failed else None,
        "rows": [asdict(r) for r in rows],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("eager-filter-arg completion audit")
        for r in rows:
            mark = "PASS" if r.ok else "FAIL"
            print(f"  [{mark}] {r.check_id}  {r.label}")
            print(f"         {r.proof}")
        print(f"wrote {GENERATED.relative_to(ROOT).as_posix()}")
        if failed:
            print(f"EAGER_FILTER_ARG_COMPLETION_FAIL  ({len(failed)}/{len(rows)} failed)")
            return 1
        print("EAGER_FILTER_ARG_COMPLETION_PASS")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
