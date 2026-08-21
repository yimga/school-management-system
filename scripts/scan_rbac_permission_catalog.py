"""Every permission code a surface gates on must exist in the RBAC catalog.

``has_feature_permission("nope.nope")`` does not raise. It resolves the code
against ``Permission`` rows, finds nothing, and returns ``False`` — forever, for
everyone. A gate on a code that was never seeded is not a strict gate; it is a
surface no role can ever reach, and it fails silently and permanently.

Four of them shipped:

    finance.access, finance.view_dashboard, reports.view, marketplace.view
        -> apps/platform_runtime/action_engine.py

Nobody but a Django superuser could see the operator finance strip or the
marketplace actions, and nothing anywhere said why. The same drift is what left
``iam.request_access`` off the SUPERADMIN role: the catalog and the call sites
are maintained in two places, by hand, and they diverge.

This gate closes the loop in the checkable direction: a code CALLED in ``apps/``
must be DEFINED by an ``apps/accounts/migrations/`` data step. (The reverse
direction — a seeded code nobody checks — is legitimate; a code is often seeded
one release before the surface that uses it lands.)

Superadmin coverage is deliberately NOT checked here. It used to be a seeded
list, which is exactly why it drifted through five migrations; it is now
structural in ``apps.accounts.superadmin`` and reconciled on ``post_migrate`` by
``apps.accounts.superadmin_sync``. The tests in
``apps/accounts/tests/test_superadmin_holds_everything_2026_08_20.py`` hold that
guarantee — a scanner cannot see it.

When a code is genuinely resolved somewhere else (a Django built-in
``app.codename`` handed to ``permission_required``, a code owned by another
service), mark the line:

    user.has_feature_permission("thing.code")  # rbac-code-allow: <why>

Usage:
    python scripts/scan_rbac_permission_catalog.py          # report, non-zero on findings
    python scripts/scan_rbac_permission_catalog.py --json   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXEMPTION = "rbac-code-allow"

#: Call sites that resolve a code through the tenant ``Permission`` catalog.
CALL_PATTERN = re.compile(
    r"\b("
    r"has_feature_permission"
    r"|require_permission"
    r"|permission_access"
    r"|user_has_permission"
    r"|enforce_permission_token"
    r"|check_permission_token"
    r"|feature_permission_allowed"
    r")\s*\("
)

#: A colon-manifest code: dotted, lowercase, no spaces (``athletics.eligibility.override``).
CODE_PATTERN = re.compile(r"""["']([a-z_]+(?:\.[a-z_]+)+)["']""")

#: Django's OWN permission strings are ``app_label.codename`` and are resolved by
#: ``auth.Permission``, not by the tenant catalog. ``permission_required`` is
#: overloaded across both systems, so these app labels are not our codes.
DJANGO_APP_LABELS = frozenset(
    {
        "academics",
        "admin",
        "auth",
        "contenttypes",
        "people",
        "sessions",
    }
)

SKIP_DIR_PARTS = ("/tests/", "/migrations/", "/__pycache__/")


def _iter_python_files():
    for path in sorted((REPO_ROOT / "apps").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if any(part in f"/{rel}" for part in SKIP_DIR_PARTS):
            continue
        yield path, rel


def catalog_codes() -> set[str]:
    """Codes any accounts data migration defines as a ``Permission`` row.

    Migrations declare them as ``("code", "Name", "Description")`` tuples, which
    is stable across every seeding migration in the app (0004 through 0058).
    """
    codes: set[str] = set()
    tuple_pattern = re.compile(
        r"""\(\s*["']([a-z_]+(?:\.[a-z_]+)+)["']\s*,\s*["']""",
    )
    migrations = REPO_ROOT / "apps" / "accounts" / "migrations"
    for path in sorted(migrations.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        codes.update(tuple_pattern.findall(text))
    return codes


def _call_argument_span(text: str, start: int, limit: int = 400) -> str:
    """Text from an opening paren to its match, so we only read this call's args."""
    depth = 1
    out: list[str] = []
    for char in text[start : start + limit]:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        out.append(char)
    return "".join(out)


def _exempt(lines: list[str], index: int) -> bool:
    """Marker on the line itself or the line above it."""
    if EXEMPTION in lines[index]:
        return True
    return index > 0 and EXEMPTION in lines[index - 1]


def gated_codes() -> list[tuple[str, int, str]]:
    """(relative path, 1-indexed line, code) for every catalog code that is gated on."""
    found: list[tuple[str, int, str]] = []
    for path, rel in _iter_python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if not CALL_PATTERN.search(text):
            continue
        lines = text.splitlines()
        for match in CALL_PATTERN.finditer(text):
            line_index = text.count("\n", 0, match.start())
            if line_index < len(lines) and _exempt(lines, line_index):
                continue
            for code in CODE_PATTERN.findall(
                _call_argument_span(text, match.end())
            ):
                if code.split(".", 1)[0] in DJANGO_APP_LABELS:
                    continue
                found.append((rel, line_index + 1, code))
    return found


def findings() -> list[dict]:
    catalog = catalog_codes()
    out = []
    seen: set[tuple[str, int, str]] = set()
    for rel, line, code in gated_codes():
        if code in catalog:
            continue
        key = (rel, line, code)
        if key in seen:
            continue
        seen.add(key)
        out.append({"path": rel, "line": line, "code": code})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = findings()

    if args.json:
        print(json.dumps(results, indent=2))
        return 1 if results else 0

    for item in results:
        print(
            f"  {item['path']}:{item['line']}  {item['code']}  "
            "is gated on but never seeded"
        )
    print(f"rbac-permission-catalog: {len(results)} finding(s).")
    if results:
        print(
            "\nThese codes exist in no Permission row, so no role can hold them and\n"
            "the surfaces behind them deny everyone but a superadmin, permanently.\n"
            "Seed each one in an apps/accounts/migrations/ data step (see 0058 for\n"
            "the additive get_or_create + .add() pattern), or mark a deliberate\n"
            f"exception with  # {EXEMPTION}: <why>",
            file=sys.stderr,
        )
    return 1 if results else 0


if __name__ == "__main__":
    raise SystemExit(main())
